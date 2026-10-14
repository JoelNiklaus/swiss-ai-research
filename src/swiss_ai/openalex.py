"""Match DBLP papers to OpenAlex works and export one row per authorship with countries.

Papers with a DOI are looked up in batches of 100 DOIs per request. Papers without one
(ICLR, ICML, NeurIPS, early ACL venues) are matched by title: one search request ORs up to
TITLES_PER_SEARCH quoted titles, and results are matched back on the normalized title.
Every response is cached on disk, so an interrupted run resumes for free. Venue-years covered
by OpenReview (see `swiss_ai.openreview`) are skipped, because profiles give their countries.
"""

import hashlib
import json
import logging
import os
import re
import time
import unicodedata
from functools import cache

import httpx
import pandas as pd
from dotenv import load_dotenv
from joblib import Parallel, delayed
from tqdm import tqdm

from swiss_ai.openreview import VENUES as OPENREVIEW_VENUES
from swiss_ai.paths import CACHE, DATA, ROOT

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

API = "https://api.openalex.org"
OA_CACHE = CACHE / "openalex"
AUTHORSHIPS = DATA / "authorships.csv.gz"
MATCHES = DATA / "openalex_matches.csv"
WORK_FIELDS = "id,doi,title,publication_year,authorships"
AUTHOR_FIELDS = "id,affiliations"
DOIS_PER_REQUEST = 100
IDS_PER_REQUEST = 100
TITLES_PER_SEARCH = 40
SHORT_TITLE_WORDS = 3
MAX_SEARCH_PAGES = 3
SEARCH_THREADS = 8
PER_PAGE = 200
RETRIES = 4

# OpenAlex books generic Google/Meta/Microsoft/Apple affiliations at US headquarters. A raw
# affiliation string naming a Swiss city or Switzerland overrides that for the authorship.
SWISS_RAW_AFFILIATION = re.compile(
    r"Z[uü]rich|Lausanne|Gen[eè]v|Basel|Bern\b|Switzerland|Schweiz|Suisse",
    re.IGNORECASE,
)


class OpenAlexBudgetError(RuntimeError):
    """Raised when OpenAlex rejects a request because the daily budget is used up."""


def normalize_title(title: str) -> str:
    """Fold to ASCII, lowercase and keep only alphanumeric words, so titles match across sources.

    Folding maps "Nyström" to "nystrom" and "Multi³Hate" to "multi3hate".
    """
    decomposed = unicodedata.normalize("NFKD", title)
    # Drop accents; every other non-alphanumeric character (’, –, ') becomes a word break.
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]", " ", stripped.lower()).split())


def get(entity: str, params: dict[str, str | int]) -> dict:
    """GET an OpenAlex list endpoint with on-disk caching keyed by entity and parameters.

    Args:
        entity: 'works' or 'authors'.
        params: Query parameters without the API key.

    Raises:
        OpenAlexBudgetError: If OpenAlex answers 429 (budget or rate limit exhausted).
    """
    body = json.dumps({"entity": entity, **params}, sort_keys=True)
    path = OA_CACHE / f"{hashlib.sha1(body.encode()).hexdigest()}.json"
    if path.exists():
        return json.loads(path.read_text())
    # OpenAlex occasionally times out on large searches (504); retry those with backoff.
    for attempt in range(RETRIES):
        response = httpx.get(
            f"{API}/{entity}", params={**params, "api_key": api_key()}, timeout=120
        )
        if response.status_code < 500:
            break
        time.sleep(2**attempt)
    if response.status_code == 429:
        raise OpenAlexBudgetError(
            f"OpenAlex budget exhausted, resets in {response.headers['x-ratelimit-reset']}s. "
            "Rerun later; cached responses are reused."
        )
    data = response.raise_for_status().json()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


@cache
def api_key() -> str:
    """Read OPENALEX_API_KEY from the environment or `.env`; OpenAlex requires one since 2026."""
    load_dotenv(ROOT / ".env")
    return os.environ["OPENALEX_API_KEY"]


def get_all(
    entity: str, filter_: str, select: str, max_pages: int | None = None
) -> list[dict]:
    """Fetch result pages for a filter with cursor paging, optionally stopping after max_pages."""
    results, cursor, pages = [], "*", 0
    while cursor and pages != max_pages:
        params = {
            "filter": filter_,
            "select": select,
            "per-page": PER_PAGE,
            "cursor": cursor,
        }
        data = get(entity, params)
        results += data["results"]
        # A short page is the last one; requesting the next (empty) page would cost a call.
        cursor = (
            data["meta"]["next_cursor"] if len(data["results"]) == PER_PAGE else None
        )
        pages += 1
    return results


def lookup_dois(dois: list[str]) -> dict[str, dict]:
    """Map lowercase DOI to its OpenAlex work for every DOI OpenAlex knows."""
    found = {}
    for i in tqdm(range(0, len(dois), DOIS_PER_REQUEST), desc="DOI batches"):
        batch = dois[i : i + DOIS_PER_REQUEST]
        for work in get_all("works", "doi:" + "|".join(batch), WORK_FIELDS):
            found[work["doi"].removeprefix("https://doi.org/").lower()] = work
    return found


def search_batch(batch: list[str]) -> list[dict]:
    """Run one title search that ORs the quoted titles and return works with an exact title."""
    wanted = set(batch)
    filter_ = "title.search:" + "|".join(f'"{t}"' for t in batch)
    # Phrase search also returns longer titles containing the phrase; exact matches rank
    # first, so the first pages suffice and generic short titles cannot page forever.
    works = get_all("works", filter_, WORK_FIELDS, max_pages=MAX_SEARCH_PAGES)
    return [w for w in works if normalize_title(w["title"] or "") in wanted]


def search_titles(titles: list[str]) -> dict[str, list[dict]]:
    """Map normalized title to all OpenAlex works with exactly that normalized title.

    Titles of up to SHORT_TITLE_WORDS words ("A Sampling") match thousands of works, so each
    gets its own search instead of crowding out the others in a batch.
    """
    unique = sorted({normalize_title(t) for t in titles} - {""})
    short = [[t] for t in unique if len(t.split()) <= SHORT_TITLE_WORDS]
    long = [t for t in unique if len(t.split()) > SHORT_TITLE_WORDS]
    batches = short + [
        long[i : i + TITLES_PER_SEARCH] for i in range(0, len(long), TITLES_PER_SEARCH)
    ]
    results = Parallel(n_jobs=SEARCH_THREADS, prefer="threads")(
        delayed(search_batch)(b) for b in tqdm(batches, desc="Title searches")
    )
    found: dict[str, list[dict]] = {}
    for work in (w for works in results for w in works):
        found.setdefault(normalize_title(work["title"]), []).append(work)
    return found


def countries_known(work: dict) -> int:
    """Count authorships with at least one country, used to pick the best of several versions."""
    return sum(bool(a["countries"]) for a in work["authorships"])


def best_version(works: list[dict], year: int) -> dict | None:
    """Pick the version published within a year of the venue with the most country information.

    The same paper often exists as an arXiv preprint and a proceedings version with different
    affiliation coverage.
    """
    candidates = [w for w in works if abs((w["publication_year"] or 0) - year) <= 1]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda w: (countries_known(w), -abs(w["publication_year"] - year)),
    )


def match(papers: pd.DataFrame) -> dict[str, dict]:
    """Return DBLP key to OpenAlex work: DOI lookup first, title search for the rest."""
    with_doi = papers[papers.doi != ""]
    by_doi = lookup_dois(sorted(set(with_doi.doi)))
    matched = {
        k: by_doi[d]
        for k, d in zip(with_doi.key, with_doi.doi, strict=True)
        if d in by_doi
    }

    rest = papers[~papers.key.isin(matched)]
    by_title = search_titles(rest.title.tolist())
    for key, title, year in zip(rest.key, rest.title, rest.year, strict=True):
        title = normalize_title(title)
        work = best_version(by_title[title], year) if title in by_title else None
        if work is not None:
            matched[key] = work
    return matched


def authorship_countries(authorship: dict) -> set[str]:
    """Countries of one authorship, with Swiss raw affiliations overriding their institutions.

    Each raw affiliation string links to the institutions OpenAlex resolved it to. A string that
    names a Swiss location counts as Switzerland even if it resolved to a US headquarters.
    """
    if not authorship["affiliations"]:
        return set(authorship["countries"])
    institution_country = {
        i["id"]: i["country_code"]
        for i in authorship["institutions"]
        if i["country_code"]
    }
    countries = set()
    for affiliation in authorship["affiliations"]:
        if SWISS_RAW_AFFILIATION.search(affiliation["raw_affiliation_string"]):
            countries.add("CH")
        else:
            countries |= {
                institution_country[i]
                for i in affiliation["institution_ids"]
                if i in institution_country
            }
    return countries


def authorship_rows(key: str, work: dict) -> list[dict]:
    """Flatten a work's authorships with countries after the Swiss raw-affiliation override."""
    rows = []
    n = len(work["authorships"])
    for position, a in enumerate(work["authorships"]):
        countries = authorship_countries(a)
        rows.append(
            {
                "key": key,
                "openalex_id": work["id"].removeprefix("https://openalex.org/"),
                "position": position,
                "n_authors": n,
                "author_id": (a["author"]["id"] or "").removeprefix(
                    "https://openalex.org/"
                ),
                "author_name": a["author"]["display_name"],
                "institutions": " | ".join(
                    i["display_name"] for i in a["institutions"]
                ),
                "countries": "|".join(sorted(countries)),
                "country_source": "paper" if countries else "",
                "raw_affiliations": " | ".join(a["raw_affiliation_strings"]),
                "swiss_override": "CH" in countries and "CH" not in a["countries"],
            }
        )
    return rows


def author_countries_by_year(author_ids: list[str]) -> dict[str, dict[int, set[str]]]:
    """Map OpenAlex author id to {year: countries of the institutions listed for that year}."""
    by_author: dict[str, dict[int, set[str]]] = {}
    for i in tqdm(range(0, len(author_ids), IDS_PER_REQUEST), desc="Author batches"):
        batch = author_ids[i : i + IDS_PER_REQUEST]
        for author in get_all(
            "authors", "ids.openalex:" + "|".join(batch), AUTHOR_FIELDS
        ):
            years = by_author.setdefault(
                author["id"].removeprefix("https://openalex.org/"), {}
            )
            for affiliation in author["affiliations"]:
                country = affiliation["institution"]["country_code"]
                for year in affiliation["years"]:
                    if country:
                        years.setdefault(year, set()).add(country)
    return by_author


def profile_countries(profile: dict[int, set[str]], year: int) -> set[str]:
    """Countries in the paper year, else the year before (work often predates publication)."""
    for y in (year, year - 1):
        if y in profile:
            return profile[y]
    return set()


def fill_from_author_profiles(
    authorships: pd.DataFrame, years: pd.Series
) -> pd.DataFrame:
    """Fill authorships without a paper-level country from the author's profile in that year.

    OpenAlex author profiles list institutions per year, aggregated over all of the author's
    works.

    Args:
        authorships: Output of `authorship_rows` for all papers.
        years: Paper year indexed by DBLP key.

    Returns:
        A copy with `countries` and `country_source` ('author_profile') filled where possible.
    """
    df = authorships.copy()
    missing = (df.countries == "") & (df.author_id != "")
    profiles = author_countries_by_year(sorted(set(df.author_id[missing])))
    for idx in df.index[missing]:
        author_id = df.at[idx, "author_id"]
        # Merged author ids come back under their new id, so some ids have no profile.
        profile = profiles[author_id] if author_id in profiles else {}
        countries = profile_countries(profile, years[df.at[idx, "key"]])
        if countries:
            df.at[idx, "countries"] = "|".join(sorted(countries))
            df.at[idx, "country_source"] = "author_profile"
    return df


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    papers = pd.read_csv(DATA / "papers.csv", keep_default_na=False)
    # Venue-years on OpenReview take their countries from OpenReview profiles instead.
    venue_year = pd.MultiIndex.from_arrays([papers.venue, papers.year])
    papers = papers[~venue_year.isin(list(OPENREVIEW_VENUES))]
    matched = match(papers)
    rows = [row for key, work in matched.items() for row in authorship_rows(key, work)]
    authorships = fill_from_author_profiles(
        pd.DataFrame(rows), papers.set_index("key").year
    )
    authorships.to_csv(AUTHORSHIPS, index=False)

    # Coverage report per venue and year: paper match rate and authorships with a country.
    papers["matched"] = papers.key.isin(matched)
    papers.to_csv(MATCHES, index=False, columns=["key", "venue", "year", "matched"])
    known = authorships.assign(known=authorships.countries != "").merge(
        papers[["key", "venue", "year"]]
    )
    report = pd.concat(
        [
            papers.groupby(["venue", "year"]).matched.mean().rename("match_rate"),
            known.groupby(["venue", "year"]).known.mean().rename("country_known"),
        ],
        axis=1,
    )
    log.info(report.round(2).to_string())
    log.info(f"Country sources:\n{authorships.country_source.value_counts()}")
    log.info(
        f"Swiss raw-affiliation overrides: {authorships.swiss_override.sum()} authorships"
    )


if __name__ == "__main__":
    main()

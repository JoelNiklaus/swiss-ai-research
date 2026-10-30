"""Main-track papers and author countries from the ACL Anthology, for venue-years DBLP lacks.

DBLP and OpenAlex index new ACL proceedings with a delay of weeks, so recent *ACL venue-years
take both their paper list and their author countries from the Anthology XML instead (one
source per venue-year, as for OpenReview). The XML gives each author an affiliation string and
often an ORCID. Affiliation strings map to countries through ROR: the affiliation matcher's
chosen match, else organisations named exactly like the string if they share one country, with
the same Swiss-city override as for OpenAlex.
Authors without an affiliation take the countries of their affiliation on another paper of the
same volume, else their OpenAlex profile (found by ORCID) in the paper year or the year before.
"""

import hashlib
import json
import logging
import re
import time
from collections.abc import Callable
from xml.etree import ElementTree

import httpx
import pandas as pd
from joblib import Parallel, delayed
from tqdm import tqdm

from swiss_ai.openalex import (
    SWISS_RAW_AFFILIATION,
    get_all,
    normalize_title,
    profile_countries,
)
from swiss_ai.paths import CACHE, DATA

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

PAPERS = DATA / "anthology_papers.csv"
AUTHORSHIPS = DATA / "anthology_authorships.csv"
XML_URL = (
    "https://raw.githubusercontent.com/acl-org/acl-anthology/master/data/xml/{}.xml"
)
ROR_API = "https://api.ror.org/v2/organizations"
ANTHOLOGY_CACHE = CACHE / "anthology"
ROR_CACHE = CACHE / "ror"
# (venue, year) -> (Anthology collection, main-track volume).
VENUES = {("EMNLP", 2026): ("2026.emnlp", "main")}
# Joint affiliations are written "A and B"; names such as "University of Science and
# Technology of China" contain the same word, see `affiliation_countries`.
AND = re.compile(r"\s+and\s+")
ORCIDS_PER_REQUEST = 50
ROR_THREADS = 4
RETRIES = 5


def parse_volume(
    xml: str, volume: str, venue: str, year: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Papers and authorships of one volume of an Anthology collection.

    Returns:
        papers: key (Anthology id), venue, year, title, authors, doi ("" if none).
        authorships: key, year, position, n_authors, author_id, author_name, orcid and
            affiliation ("" where the XML has none).
    """
    root = ElementTree.fromstring(xml.encode())
    collection = root.get("id")
    element = next(v for v in root.findall("volume") if v.get("id") == volume)
    papers, authorships = [], []
    for paper in element.findall("paper"):
        key = f"{collection}-{volume}.{paper.get('id')}"
        authors = paper.findall("author")
        names = [
            f"{a.findtext('first') or ''} {a.findtext('last') or ''}".strip()
            for a in authors
        ]
        title = paper.find("title")
        papers.append(
            {
                "key": key,
                "venue": venue,
                "year": year,
                "title": "" if title is None else "".join(title.itertext()).strip(),
                "authors": "; ".join(names),
                "doi": paper.findtext("doi") or "",
            }
        )
        for position, (author, name) in enumerate(zip(authors, names, strict=True)):
            authorships.append(
                {
                    "key": key,
                    "year": year,
                    "position": position,
                    "n_authors": len(authors),
                    "author_id": author.get("id") or "",
                    "author_name": name,
                    "orcid": author.get("orcid") or "",
                    "affiliation": (author.findtext("affiliation") or "").strip(),
                }
            )
    return pd.DataFrame(papers), pd.DataFrame(authorships)


def part_country(part: str, lookup: Callable[[str], str | None]) -> str | None:
    """Country of one organisation name: Switzerland if it names a Swiss place, else ROR's."""
    if SWISS_RAW_AFFILIATION.search(part):
        return "CH"
    return lookup(part)


def affiliation_countries(
    affiliation: str, lookup: Callable[[str], str | None]
) -> set[str]:
    """Countries of an affiliation string, which can join several organisations with "and".

    The string is split on "and" only if every part maps to a country; otherwise the "and" is
    part of a name and the full string is looked up.

    Args:
        affiliation: Raw affiliation string from the Anthology.
        lookup: Maps an organisation name to an ISO2 country code, or None if unknown.
    """
    if not affiliation.strip():
        return set()
    parts = [p for p in AND.split(affiliation.strip()) if p]
    if len(parts) > 1:
        countries = [part_country(p, lookup) for p in parts]
        if all(countries):
            return {c for c in countries if c}
    country = part_country(affiliation.strip(), lookup)
    return {country} if country else set()


def fill_countries(
    authorships: pd.DataFrame, profiles: dict[str, dict[int, set[str]]]
) -> pd.DataFrame:
    """Fill authorships without a country from the same author elsewhere, then by ORCID.

    Args:
        authorships: key, year, author_id, orcid, countries ("|"-joined) and country_source.
        profiles: ORCID to {year: countries} from the author's OpenAlex profile.

    Returns:
        A copy with `countries` and `country_source` ("same_author" or "orcid_profile") filled.
    """
    df = authorships.copy()
    known = df[(df.countries != "") & (df.author_id != "")]
    by_author = known.groupby("author_id").countries.agg(
        lambda s: "|".join(sorted({c for cs in s for c in cs.split("|")}))
    )
    missing = (df.countries == "") & df.author_id.isin(by_author.index)
    df.loc[missing, "countries"] = df.loc[missing, "author_id"].map(by_author)
    df.loc[missing, "country_source"] = "same_author"
    for idx in df.index[(df.countries == "") & df.orcid.isin(profiles)]:
        countries = profile_countries(profiles[df.at[idx, "orcid"]], df.at[idx, "year"])
        if countries:
            df.at[idx, "countries"] = "|".join(sorted(countries))
            df.at[idx, "country_source"] = "orcid_profile"
    return df


def fetch_xml(collection: str) -> str:
    """Anthology XML of a collection, downloaded once into the cache."""
    path = ANTHOLOGY_CACHE / f"{collection}.xml"
    if not path.exists():
        response = httpx.get(
            XML_URL.format(collection), timeout=120, follow_redirects=True
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(response.raise_for_status().text)
    return path.read_text()


def normalize_name(name: str) -> str:
    """Organisation name without parenthesized country suffixes, folded like paper titles."""
    return normalize_title(re.sub(r"\(.*?\)", " ", name))


def unanimous_exact_country(name: str, items: list[dict]) -> str | None:
    """Country of the ROR organisations whose name, acronym or alias equals `name`.

    Returns None when no organisation has exactly that name, or when several do in different
    countries (two "Northeastern University"s, or a company with one ROR entry per country).

    Args:
        name: Organisation name from an affiliation string.
        items: Organisations from the ROR v2 search endpoint.
    """
    wanted = normalize_name(name)
    countries = {
        item["locations"][0]["geonames_details"]["country_code"]
        for item in items
        if wanted in {normalize_name(n["value"]) for n in item["names"]}
    }
    return countries.pop() if len(countries) == 1 else None


def ror_query_text(name: str) -> str:
    """Name with the characters of ROR's Lucene search syntax replaced by spaces."""
    return " ".join(re.sub(r'[+\-&|!(){}\[\]^"~*?:\\/]', " ", name).split())


def ror_get(param: str, name: str) -> dict:
    """GET the ROR organisations endpoint with `param`=`name`, cached on disk."""
    key = name if param == "affiliation" else f"{param}:{name}"
    path = ROR_CACHE / f"{hashlib.sha1(key.encode()).hexdigest()}.json"
    if not path.exists():
        response = httpx.get(ROR_API, params={param: name}, timeout=60)
        # ROR allows 2,000 requests per 5 minutes; back off on rate limits and server errors.
        for attempt in range(RETRIES):
            if response.status_code not in (429, 500, 502, 503, 504):
                break
            time.sleep(2**attempt * 5)
            response = httpx.get(ROR_API, params={param: name}, timeout=60)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(response.raise_for_status().json()))
    return json.loads(path.read_text())


def ror_country(name: str) -> str | None:
    """Country for an organisation name: ROR's chosen affiliation match, else an exact name.

    The affiliation matcher only chooses when it is confident and returns nothing for many
    acronyms and companies ("EPFL", "Tencent"); the search endpoint then finds organisations
    whose name, acronym or alias equals the string, if they all sit in one country.
    """
    chosen = [i for i in ror_get("affiliation", name)["items"] if i["chosen"]]
    if chosen:
        return chosen[0]["organization"]["locations"][0]["geonames_details"][
            "country_code"
        ]
    return unanimous_exact_country(
        name, ror_get("query", ror_query_text(name))["items"]
    )


def ror_lookup(affiliations: list[str]) -> Callable[[str], str | None]:
    """Resolve every name `affiliation_countries` can ask for, in parallel, and return a lookup."""
    names = sorted(
        {a for a in affiliations if a}
        | {p for a in affiliations for p in AND.split(a) if p and AND.search(a)}
    )
    countries = Parallel(n_jobs=ROR_THREADS, prefer="threads")(
        delayed(ror_country)(n) for n in tqdm(names, desc="ROR lookups")
    )
    return dict(zip(names, countries, strict=True)).get


def orcid_profiles(orcids: list[str]) -> dict[str, dict[int, set[str]]]:
    """Map ORCID to {year: countries} from the OpenAlex author with that ORCID."""
    profiles: dict[str, dict[int, set[str]]] = {}
    for i in tqdm(range(0, len(orcids), ORCIDS_PER_REQUEST), desc="ORCID batches"):
        batch = orcids[i : i + ORCIDS_PER_REQUEST]
        for author in get_all(
            "authors", "orcid:" + "|".join(batch), "id,orcid,affiliations"
        ):
            years = profiles.setdefault(author["orcid"].rsplit("/", 1)[-1], {})
            for affiliation in author["affiliations"]:
                country = affiliation["institution"]["country_code"]
                for year in affiliation["years"]:
                    if country:
                        years.setdefault(year, set()).add(country)
    return profiles


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    all_papers, all_authorships = [], []
    for (venue, year), (collection, volume) in VENUES.items():
        papers, authorships = parse_volume(fetch_xml(collection), volume, venue, year)
        lookup = ror_lookup(sorted(set(authorships.affiliation)))
        countries = pd.Series(
            [affiliation_countries(a, lookup) for a in authorships.affiliation],
            index=authorships.index,
        )
        authorships["countries"] = countries.map(lambda c: "|".join(sorted(c)))
        authorships["country_source"] = countries.map(
            lambda c: "affiliation" if c else ""
        )
        missing = authorships[(authorships.countries == "") & (authorships.orcid != "")]
        authorships = fill_countries(
            authorships, orcid_profiles(sorted(set(missing.orcid)))
        )
        all_papers.append(papers)
        all_authorships.append(authorships)
        known = authorships.countries != ""
        papers_known = authorships[known].key.nunique() / len(papers)
        log.info(
            f"{venue} {year}: {len(papers)} papers, {known.mean():.1%} of authorships and "
            f"{papers_known:.1%} of papers with a country\n"
            f"{authorships.country_source.replace('', 'unknown').value_counts().to_string()}"
        )
    pd.concat(all_papers).to_csv(PAPERS, index=False)
    pd.concat(all_authorships).to_csv(AUTHORSHIPS, index=False)


if __name__ == "__main__":
    main()

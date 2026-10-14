"""Accepted papers and author countries for ICLR, NeurIPS, ICML and COLM from OpenReview.

OpenReview profiles record each author's institutions with start and end years and, for most
entries, a country code. That covers papers OpenAlex lacks (OpenReview- or PMLR-only papers
without an arXiv version) and gives the only paper list for COLM, which DBLP does not index.
The API requires a login since 2026 (OPENREVIEW_USERNAME and OPENREVIEW_PASSWORD in `.env`).
"""

import hashlib
import json
import logging
import os
import re
from functools import cache

import httpx
import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

from swiss_ai.paths import CACHE, DATA, ROOT

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

API_V1 = "https://api.openreview.net"
API_V2 = "https://api2.openreview.net"
OR_CACHE = CACHE / "openreview"
PAPERS = DATA / "openreview_papers.csv"
AUTHORSHIPS = DATA / "openreview_authorships.csv"
PAGE = 1000
PROFILES_PER_REQUEST = 50

# (venue, year) -> (API, venue id). Older years use other submission schemes and are left to OpenAlex.
VENUES = {
    **{("ICLR", y): (API_V1, f"ICLR.cc/{y}/Conference") for y in (2022, 2023)},
    **{("ICLR", y): (API_V2, f"ICLR.cc/{y}/Conference") for y in range(2024, 2027)},
    **{("NeurIPS", y): (API_V1, f"NeurIPS.cc/{y}/Conference") for y in (2021, 2022)},
    **{
        ("NeurIPS", y): (API_V2, f"NeurIPS.cc/{y}/Conference")
        for y in range(2023, 2026)
    },
    **{("ICML", y): (API_V2, f"ICML.cc/{y}/Conference") for y in range(2023, 2027)},
    **{
        ("COLM", y): (API_V2, f"colmweb.org/COLM/{y}/Conference")
        for y in range(2024, 2027)
    },
}
# API v1 also tags rejected and withdrawn submissions with the conference venue id, labelled
# e.g. "NeurIPS 2021 Submitted" or "Submitted to ICLR 2023".
NOT_ACCEPTED = re.compile(r"Submitted|Withdrawn|Rejected")
# Generic top-level domains that do not identify a country, except .edu for US universities.
GENERIC_TLDS = {
    "com",
    "org",
    "net",
    "io",
    "ai",
    "info",
    "int",
    "gov",
    "mil",
    "co",
    "dev",
}


@cache
def headers() -> dict[str, str]:
    """Log in once per process and return the bearer-token header."""
    load_dotenv(ROOT / ".env")
    credentials = {
        "id": os.environ["OPENREVIEW_USERNAME"],
        "password": os.environ["OPENREVIEW_PASSWORD"],
    }
    response = httpx.post(f"{API_V2}/login", json=credentials, timeout=60)
    return {"Authorization": f"Bearer {response.raise_for_status().json()['token']}"}


def get(base: str, path: str, params: dict[str, str | int]) -> dict:
    """GET an OpenReview endpoint with on-disk caching keyed by URL and parameters."""
    body = json.dumps({"url": f"{base}{path}", **params}, sort_keys=True)
    cached = OR_CACHE / f"{hashlib.sha1(body.encode()).hexdigest()}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    response = httpx.get(f"{base}{path}", params=params, headers=headers(), timeout=120)
    data = response.raise_for_status().json()
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(data))
    return data


def value(field: str | dict) -> str | list[str]:
    """API v2 wraps every content field in {'value': ...}; API v1 does not."""
    return field["value"] if isinstance(field, dict) else field


def accepted_notes(base: str, venue_id: str) -> list[dict]:
    """Return all accepted papers of a venue, paging through the notes endpoint."""
    notes, offset = [], 0
    while True:
        page = get(
            base,
            "/notes",
            {"content.venueid": venue_id, "limit": PAGE, "offset": offset},
        )
        notes += page["notes"]
        if len(page["notes"]) < PAGE:
            break
        offset += PAGE
    # API v1 can hold several blind copies of one submission; they share the `original` note.
    unique = {
        (n["original"] if "original" in n and n["original"] else n["id"]): n
        for n in notes
    }
    return [
        n
        for n in unique.values()
        if not NOT_ACCEPTED.search(value(n["content"]["venue"]))
    ]


def papers() -> pd.DataFrame:
    """One row per accepted paper with title, ordered author names and OpenReview author ids."""
    rows = []
    for (venue, year), (base, venue_id) in tqdm(VENUES.items(), desc="Venues"):
        for note in accepted_notes(base, venue_id):
            content = note["content"]
            rows.append(
                {
                    "forum": note["forum"],
                    "venue": venue,
                    "year": year,
                    "title": value(content["title"]),
                    "authors": "; ".join(value(content["authors"])),
                    "authorids": "; ".join(value(content["authorids"])),
                }
            )
    return pd.DataFrame(rows)


def profiles(ids: list[str]) -> dict[str, list[dict]]:
    """Map profile id (including aliases like '~Jane_Doe2') to its institution history."""
    history = {}
    for i in tqdm(range(0, len(ids), PROFILES_PER_REQUEST), desc="Profile batches"):
        batch = ids[i : i + PROFILES_PER_REQUEST]
        for profile in get(API_V2, "/profiles", {"ids": ",".join(batch)})["profiles"]:
            # A profile can be requested by any of its names, so register every alias.
            names = [
                n["username"] for n in profile["content"]["names"] if "username" in n
            ]
            for name in {profile["id"], *names}:
                history[name] = (
                    profile["content"]["history"]
                    if "history" in profile["content"]
                    else []
                )
    return history


def institution_country(institution: dict) -> str:
    """Country code of an institution, from its explicit country or else its domain's ccTLD."""
    if "country" in institution and institution["country"]:
        return institution["country"]
    domain = (
        institution["domain"]
        if "domain" in institution and institution["domain"]
        else ""
    )
    tld = domain.rsplit(".", 1)[-1].lower()
    if tld == "edu":
        return "US"
    if len(tld) == 2 and tld not in GENERIC_TLDS:
        return "GB" if tld == "uk" else tld.upper()
    return ""


def countries_in_year(history: list[dict], year: int) -> set[str]:
    """Countries of the positions held in `year`.

    Entries with an end year count while start <= year <= end. Entries without an end year
    are often stale (a degree or a former job never closed in the profile), so an open-ended
    entry only counts if no active entry started later. Missing start years count as 0.
    """
    active = []
    for entry in history:
        if "institution" not in entry:
            continue
        # Years are usually ints, occasionally strings like "2014" or "".
        start = int(entry["start"]) if "start" in entry and entry["start"] else 0
        end = int(entry["end"]) if "end" in entry and entry["end"] else None
        if start <= year and (end is None or year <= end):
            active.append((start, end, entry["institution"]))
    if not active:
        return set()
    latest = max(start for start, _, _ in active)
    countries = {
        institution_country(institution)
        for start, end, institution in active
        if end is not None or start == latest
    }
    return countries - {""}


def authorships(papers_df: pd.DataFrame) -> pd.DataFrame:
    """One row per authorship with countries from the profile history in the paper year."""
    exploded = papers_df.assign(authorid=papers_df.authorids.str.split("; ")).explode(
        "authorid"
    )
    exploded["position"] = exploded.groupby("forum").cumcount()
    exploded["n_authors"] = exploded.groupby("forum").forum.transform("size")
    # Author ids that are emails belong to people without a profile.
    ids = sorted({i for i in exploded.authorid if i.startswith("~")})
    history = profiles(ids)
    exploded["countries"] = [
        "|".join(sorted(countries_in_year(history[a], y))) if a in history else ""
        for a, y in zip(exploded.authorid, exploded.year, strict=True)
    ]
    cols = ["forum", "venue", "year", "position", "n_authors", "authorid", "countries"]
    return exploded[cols].reset_index(drop=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    papers_df = papers()
    papers_df.to_csv(PAPERS, index=False)
    log.info(
        papers_df.groupby(["venue", "year"])
        .size()
        .unstack(0)
        .fillna(0)
        .astype(int)
        .to_string()
    )
    authors_df = authorships(papers_df)
    authors_df.to_csv(AUTHORSHIPS, index=False)
    known = authors_df.assign(known=authors_df.countries != "")
    log.info(
        known.groupby(["venue", "year"]).known.mean().unstack(0).round(2).to_string()
    )


if __name__ == "__main__":
    main()

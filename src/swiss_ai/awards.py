"""Merge the raw award CSVs into one table with Swiss institution / nationality / first-author flags."""

import logging
import re
import unicodedata

import pandas as pd

from swiss_ai.paths import AWARDS

log = logging.getLogger(__name__)

RAW = AWARDS / "raw"
RAW_FILES = ["vision", "nlp", "naacl", "ml", "gaps"]
MAIN_AWARDS = {"best", "outstanding"}
SWISS_STATUSES = {"confirmed_swiss", "probable_swiss"}


def normalize(name: str) -> str:
    """Lowercase, strip accents and middle initials so name variants match across sources."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(t for t in re.split(r"[\s.]+", name.lower()) if len(t) > 1)


def parse_authors(field: str) -> list[str]:
    """Split a '; '-separated author list in paper order, dropping parenthesized affiliations."""
    return [a.strip() for a in re.sub(r"\(.*?\)", "", field).split(";") if a.strip()]


def parse_swiss_affiliations(field: str) -> dict[str, str]:
    """Map normalized author name to affiliation for entries like 'Name (ETH Zurich; high); Other (EPFL)'."""
    affiliations = {}
    # Entries can be grouped as 'A, B, C (Google Zurich)', so split names on ',' and ';' outside parentheses.
    for names, affiliation in re.findall(r"([^()]+?)\s*\(([^()]*)\)", field):
        for name in re.split(r"[;,]", names):
            if name.strip():
                affiliations[normalize(name)] = affiliation.split(";")[0].strip()
    return affiliations


def track(notes: str) -> str:
    """Classify special award tracks that are not main-conference research papers."""
    if re.search(r"Datasets & Benchmarks", notes):
        return "datasets_benchmarks"
    if re.search(r"position track", notes, re.IGNORECASE):
        return "position"
    if re.search(r"demo track", notes, re.IGNORECASE):
        return "demo"
    if re.search(r"industry track", notes, re.IGNORECASE):
        return "industry"
    return "main"


def load_nationality() -> dict[str, str]:
    """Map normalized author name to 'confirmed_swiss' or 'probable_swiss'."""
    nat = pd.read_csv(RAW / "swiss_nationality.csv")
    nat = nat[nat.status.isin(SWISS_STATUSES)]
    return {
        normalize(n): s.removesuffix("_swiss")
        for n, s in zip(nat.name, nat.status, strict=True)
    }


def build() -> pd.DataFrame:
    """Build the flagged award table from the raw CSVs."""
    df = pd.concat(
        [pd.read_csv(RAW / f"{f}.csv", keep_default_na=False) for f in RAW_FILES]
    )
    df = df[df.award_type.isin(MAIN_AWARDS)].copy()
    swiss = load_nationality()

    rows = []
    for r in df.itertuples():
        authors = parse_authors(r.authors)
        affiliations = parse_swiss_affiliations(r.swiss_affiliated_authors)
        inst_authors = [a for a in authors if normalize(a) in affiliations]
        statuses = {a: swiss[normalize(a)] for a in authors if normalize(a) in swiss}
        first = normalize(authors[0])
        first_affiliation = affiliations[first] if first in affiliations else ""
        first_status = swiss[first] if first in swiss else ""
        rows.append(
            {
                "conference": r.conference,
                "year": r.year,
                "award_type": r.award_type,
                "track": track(r.notes),
                "title": r.title,
                "authors": "; ".join(authors),
                "n_authors": len(authors),
                "first_author": authors[0],
                "swiss_institution_authors": "; ".join(
                    f"{a} ({affiliations[normalize(a)]})" for a in inst_authors
                ),
                "swiss_national_authors": "; ".join(
                    f"{a} ({s})" for a, s in statuses.items()
                ),
                "has_swiss_institution": bool(inst_authors),
                "has_swiss_author": bool(statuses),
                "has_confirmed_swiss_author": "confirmed" in statuses.values(),
                "first_author_swiss_institution": first_affiliation,
                "first_author_swiss": first_status,
                "notes": r.notes,
            }
        )
    out = (
        pd.DataFrame(rows)
        .sort_values(["conference", "year", "award_type", "title"])
        .reset_index(drop=True)
    )

    # Every Swiss-affiliation entry must match an author of the paper, otherwise the raw data has a typo.
    n_listed = df.swiss_affiliated_authors.map(
        lambda s: len(parse_swiss_affiliations(s))
    ).sum()
    n_matched = out.swiss_institution_authors.map(
        lambda s: len(s.split("; ")) if s else 0
    ).sum()
    if n_listed != n_matched:
        raise ValueError(
            f"Only {n_matched} of {n_listed} Swiss-affiliated names matched an author list"
        )
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    awards = build()
    awards.to_csv(AWARDS / "awards.csv", index=False)

    # A first author counts as Swiss if they are a Swiss citizen or at a Swiss institution.
    first = awards[
        (awards.first_author_swiss_institution != "")
        | (awards.first_author_swiss != "")
    ]
    cols = [
        "first_author",
        "first_author_swiss",
        "first_author_swiss_institution",
        "conference",
        "year",
        "award_type",
        "track",
        "title",
    ]
    first[cols].sort_values(["first_author", "year"]).to_csv(
        AWARDS / "swiss_first_authors.csv", index=False
    )

    log.info(
        f"{len(awards)} awards, {awards.has_swiss_institution.sum()} with a Swiss institution, "
        f"{awards.has_swiss_author.sum()} with a Swiss author, {len(first)} with a Swiss first author"
    )


if __name__ == "__main__":
    main()

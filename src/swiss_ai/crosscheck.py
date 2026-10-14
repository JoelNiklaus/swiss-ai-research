"""Cross-check the pipeline's country shares against Paper Copilot's independent affiliation data.

Paper Copilot (https://github.com/papercopilot/paperlists) resolves the affiliation of every
author of ICLR, ICML and NeurIPS papers from OpenReview and maps it to a country. For the
venue-years where both sources exist, this module computes fractional and any-author country
shares of accepted main-track papers from Paper Copilot and puts them next to the pipeline's
own shares in `participation.csv`: per venue-year for Switzerland, and pooled for a set of
comparison countries, which shows whether a gap is specific to Switzerland.
"""

import json
import logging

import httpx
import pandas as pd

from swiss_ai.analysis import PARTICIPATION
from swiss_ai.paths import CACHE, DATA

log = logging.getLogger(__name__)

PAPER_COPILOT = (
    "https://raw.githubusercontent.com/papercopilot/paperlists/main/{path}.json"
)
PC_CACHE = CACHE / "papercopilot"
CROSSCHECK = DATA / "papercopilot_crosscheck.csv"
COUNTRY_CROSSCHECK = DATA / "papercopilot_countries.csv"
# Venue-years with a full Paper Copilot file (its ICLR 2025 and 2026 files are empty stubs).
FILES = {
    ("ICLR", 2023): "iclr/iclr2023",
    ("ICLR", 2024): "iclr/iclr2024",
    ("ICML", 2023): "icml/icml2023",
    ("ICML", 2024): "icml/icml2024",
    ("ICML", 2025): "icml/icml2025",
    ("NeurIPS", 2023): "nips/nips2023",
    ("NeurIPS", 2024): "nips/nips2024",
    ("NeurIPS", 2025): "nips/nips2025",
}
ACCEPTED = {"Poster", "Spotlight", "Oral", "Accept"}
SWITZERLAND = "Switzerland"
# ISO2 code -> Paper Copilot country name. Paper Copilot files Hong Kong under China, so the
# pipeline's HK credit is added to CN for the comparison.
PC_NAMES = {
    "CH": "Switzerland",
    "IL": "Israel",
    "SG": "Singapore",
    "NL": "Netherlands",
    "US": "United States",
    "GB": "United Kingdom",
    "DE": "Germany",
    "FR": "France",
    "CA": "Canada",
    "KR": "South Korea",
    "CN": "China",
}


def load(path: str) -> list[dict]:
    """Paper Copilot records for one venue-year, downloaded once into the cache."""
    cached = PC_CACHE / f"{path.replace('/', '_')}.json"
    if not cached.exists():
        PC_CACHE.mkdir(parents=True, exist_ok=True)
        response = httpx.get(PAPER_COPILOT.format(path=path), timeout=300)
        cached.write_bytes(response.raise_for_status().content)
    return json.loads(cached.read_text())


def author_countries(record: dict) -> list[list[str]]:
    """Countries of each author with a resolved affiliation, in author order.

    `aff_country_unique_index` has one entry per author with a non-empty affiliation, pointing
    into the `aff_country_unique` list; an author with several affiliations has entries joined
    by "+" (for example "0+1"). Authors without an affiliation are skipped.
    """
    if "aff_country_unique_index" not in record:
        return []
    names = record["aff_country_unique"].split(";")
    authors = []
    for entry in record["aff_country_unique_index"].split(";"):
        countries = [names[int(i)] for i in entry.split("+") if i != ""]
        countries = [c for c in countries if c != ""]
        if countries:
            authors.append(countries)
    return authors


def accepted_papers(records: list[dict]) -> list[list[list[str]]]:
    """Author countries of each accepted main-track paper with at least one known country."""
    return [
        authors
        for r in records
        if r["track"] == "main" and r["status"] in ACCEPTED
        if (authors := author_countries(r))
    ]


def credit(papers: list[list[list[str]]], country: str) -> tuple[float, int]:
    """Fractional papers and any-author papers of `country`.

    Fractional credit matches the pipeline: each author carries 1 / (authors with a country),
    split equally across that author's countries.
    """
    frac = sum(
        sum(a.count(country) / len(a) for a in authors) / len(authors)
        for authors in papers
    )
    any_author = sum(any(country in a for a in authors) for authors in papers)
    return frac, any_author


def swiss_shares(records: list[dict]) -> dict[str, float]:
    """Swiss fractional and any-author share of accepted main-track papers."""
    papers = accepted_papers(records)
    frac, any_author = credit(papers, SWITZERLAND)
    return {
        "pc_papers": len(papers),
        "pc_frac_share": frac / len(papers),
        "pc_any_share": any_author / len(papers),
    }


def crosscheck() -> pd.DataFrame:
    """Paper Copilot and pipeline Swiss shares side by side, per venue-year and pooled."""
    ours = pd.read_csv(PARTICIPATION, keep_default_na=False)
    ours = ours[ours.country == "CH"].set_index(["venue", "year"])
    rows = []
    for (venue, year), path in FILES.items():
        row = {"venue": venue, "year": year, **swiss_shares(load(path))}
        row["frac_share"] = ours.loc[(venue, year), "frac_share"]
        row["any_share"] = ours.loc[(venue, year), "any_share"]
        row["n_papers"] = ours.loc[(venue, year), "n_papers"]
        rows.append(row)
    df = pd.DataFrame(rows)
    pooled = {
        "venue": "pooled",
        "year": 0,
        "pc_papers": df.pc_papers.sum(),
        "pc_frac_share": (df.pc_frac_share * df.pc_papers).sum() / df.pc_papers.sum(),
        "pc_any_share": (df.pc_any_share * df.pc_papers).sum() / df.pc_papers.sum(),
        "frac_share": (df.frac_share * df.n_papers).sum() / df.n_papers.sum(),
        "any_share": (df.any_share * df.n_papers).sum() / df.n_papers.sum(),
        "n_papers": df.n_papers.sum(),
    }
    return pd.concat([df, pd.DataFrame([pooled])], ignore_index=True)


def country_comparison() -> pd.DataFrame:
    """Fractional papers per country summed over FILES, from Paper Copilot and the pipeline.

    Returns:
        One row per country in PC_NAMES with pc_papers, papers and their ratio.
    """
    ours = pd.read_csv(PARTICIPATION, keep_default_na=False)
    ours = ours.assign(
        papers=ours.frac_share * ours.n_papers,
        country=ours.country.replace({"HK": "CN"}),
    )
    in_files = pd.MultiIndex.from_arrays([ours.venue, ours.year]).isin(list(FILES))
    ours = ours[in_files].groupby("country").papers.sum()
    pc = dict.fromkeys(PC_NAMES, 0.0)
    for path in FILES.values():
        papers = accepted_papers(load(path))
        for code, pc_name in PC_NAMES.items():
            pc[code] += credit(papers, pc_name)[0]
    df = pd.DataFrame({"pc_papers": pd.Series(pc)})
    df["papers"] = ours.reindex(df.index, fill_value=0)
    df["ratio"] = df.papers / df.pc_papers
    return df.rename_axis("country").reset_index()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    df = crosscheck()
    df.to_csv(CROSSCHECK, index=False)
    log.info(df.round(4).to_string(index=False))
    countries = country_comparison()
    countries.to_csv(COUNTRY_CROSSCHECK, index=False)
    log.info(countries.round(2).sort_values("ratio").to_string(index=False))


if __name__ == "__main__":
    main()

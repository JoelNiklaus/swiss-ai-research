"""Citations of main-track papers, normalized within venue and year, by country and for awards.

Citation counts come from OpenAlex for the DBLP papers matched to OpenAlex (OpenReview
venue-years have no OpenAlex id here). Only papers from FIRST_YEAR to LAST_YEAR are used, so every
paper had at least five years to collect citations. Two measures:

- `cites_5y`: citations in the publication year and the four years after, from OpenAlex
  `counts_by_year` (which covers the last ten years, so only for papers from 2016 on).
- `cited_by_count`: all citations so far, ranked within the venue-year so age drops out.

A paper is top-cited when it is in the top TOP_SHARE of its venue-year by citations so far. The
country ratio compares a country's top-cited papers with what its paper share predicts, exactly
like the award ratio in `analysis.award_ratios`.
"""

import logging

import pandas as pd
from joblib import Parallel, delayed
from tqdm import tqdm

from swiss_ai.analysis import GROUPS, poisson_interval, venue_year_shares
from swiss_ai.attribution import FIRST_YEAR, country_credit, load_papers, match_awards
from swiss_ai.openalex import AUTHORSHIPS, IDS_PER_REQUEST, get_all
from swiss_ai.paths import DATA

log = logging.getLogger(__name__)

CITATIONS = DATA / "citations.csv.gz"
CITATION_RATIOS = DATA / "citation_ratios.csv"
AWARD_CITATIONS = DATA / "award_citations.csv"
LAST_YEAR = 2021
FIVE_YEAR_FIRST = 2016
TOP_SHARE = 0.10
FIELDS = "id,publication_year,cited_by_count,counts_by_year"
THREADS = 8


def fetch_batch(ids: list[str]) -> list[dict]:
    """Citation fields for up to IDS_PER_REQUEST OpenAlex work ids (short form, W123)."""
    return get_all("works", "ids.openalex:" + "|".join(ids), FIELDS)


def five_year_citations(work: dict, year: int) -> float:
    """Citations from the paper's year to four years later, or NaN if not covered."""
    if year < FIVE_YEAR_FIRST:
        return float("nan")
    by_year = {c["year"]: c["cited_by_count"] for c in work["counts_by_year"]}
    return float(sum(by_year.get(y, 0) for y in range(year, year + 5)))


def fetch_citations(papers: pd.DataFrame) -> pd.DataFrame:
    """Citation counts for every paper in `papers` with an OpenAlex id.

    Returns:
        paper_id, openalex_id, venue, year, cited_by_count and cites_5y.
    """
    ids = pd.read_csv(AUTHORSHIPS, usecols=["key", "openalex_id"]).drop_duplicates(
        "key"
    )
    ids = ids.rename(columns={"key": "paper_id"}).merge(
        papers[["paper_id", "venue", "year"]]
    )
    ids["openalex_id"] = ids.openalex_id.str.rsplit("/", n=1).str[-1]
    unique = sorted(set(ids.openalex_id))
    batches = [
        unique[i : i + IDS_PER_REQUEST] for i in range(0, len(unique), IDS_PER_REQUEST)
    ]
    results = Parallel(n_jobs=THREADS, prefer="threads")(
        delayed(fetch_batch)(b) for b in tqdm(batches, desc="Citation batches")
    )
    works = {w["id"].rsplit("/", 1)[-1]: w for batch in results for w in batch}
    found = ids[ids.openalex_id.isin(works)].copy()
    found["cited_by_count"] = [works[i]["cited_by_count"] for i in found.openalex_id]
    found["cites_5y"] = [
        five_year_citations(works[i], y)
        for i, y in zip(found.openalex_id, found.year, strict=True)
    ]
    return found


def rank_within_venue_year(citations: pd.DataFrame) -> pd.DataFrame:
    """Add the citation percentile (0 to 1, ties averaged) and the top-cited flag."""
    groups = citations.groupby(["venue", "year"]).cited_by_count
    out = citations.assign(percentile=groups.rank(pct=True, method="average"))
    # A paper is top-cited if fewer than TOP_SHARE of its venue-year are cited more.
    cited_more = groups.rank(ascending=False, method="min") - 1
    out["top_cited"] = cited_more < TOP_SHARE * groups.transform("size")
    return out


def citation_ratios(citations: pd.DataFrame, credit: pd.DataFrame) -> pd.DataFrame:
    """Observed vs expected top-cited papers per country group, fractional and any-author.

    The expected count for a venue-year is its number of top-cited papers times the group's
    share of the venue-year's papers (both over the papers with citations and a known country).

    Returns:
        One row per group with observed and expected counts, ratio and 95% Poisson interval,
        plus the group's mean citation percentile (weighted by fractional credit).
    """
    credit = credit[credit.paper_id.isin(citations.paper_id)]
    papers = citations[citations.paper_id.isin(credit.paper_id)]
    shares = venue_year_shares(papers, credit)
    top = papers[papers.top_cited]
    n_top = top.groupby(["venue", "year"]).size().rename("n_top").reset_index()
    expected = shares.merge(n_top)
    expected["frac"] = expected.frac_share * expected.n_top
    expected["any"] = expected.any_share * expected.n_top
    expected = expected.groupby("country")[["frac", "any"]].sum()
    observed = (
        credit.merge(top[["paper_id"]])
        .groupby("country")
        .agg(frac=("credit", "sum"), any=("paper_id", "nunique"))
    )
    weighted = credit.merge(papers[["paper_id", "percentile"]])
    rows = []
    for group, members in GROUPS.items():
        member_rows = weighted[weighted.country.isin(members)]
        row = {
            "group": group,
            "papers": member_rows.credit.sum(),
            "mean_percentile": (member_rows.percentile * member_rows.credit).sum()
            / member_rows.credit.sum(),
        }
        for measure in ("frac", "any"):
            obs = observed[measure].reindex(members, fill_value=0).sum()
            exp = expected[measure].reindex(members, fill_value=0).sum()
            low, high = poisson_interval(obs)
            row |= {
                f"observed_{measure}": obs,
                f"expected_{measure}": exp,
                f"ratio_{measure}": obs / exp,
                f"ratio_{measure}_low": low / exp,
                f"ratio_{measure}_high": high / exp,
            }
        rows.append(row)
    return pd.DataFrame(rows)


def award_citations(citations: pd.DataFrame, awards: pd.DataFrame) -> pd.DataFrame:
    """Citation percentile of each award paper with citation data, within its venue-year."""
    cols = [
        "paper_id",
        "venue",
        "year",
        "cited_by_count",
        "cites_5y",
        "percentile",
        "top_cited",
    ]
    return awards[["paper_id", "award_type", "has_swiss_institution"]].merge(
        citations[cols]
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    papers, authorships = load_papers()
    papers = papers[papers.year.between(FIRST_YEAR, LAST_YEAR)]
    citations = rank_within_venue_year(fetch_citations(papers))
    citations.to_csv(CITATIONS, index=False)
    log.info(
        f"{len(citations)} of {(papers.source == 'openalex').sum()} DBLP papers "
        f"{FIRST_YEAR}-{LAST_YEAR} have OpenAlex citations"
    )
    credit = country_credit(authorships)
    ratios = citation_ratios(citations, credit)
    ratios.to_csv(CITATION_RATIOS, index=False)
    log.info(
        f"Top {TOP_SHARE:.0%} cited papers per group:\n{ratios.round(2).to_string(index=False)}"
    )
    awarded = award_citations(citations, match_awards(papers))
    awarded.to_csv(AWARD_CITATIONS, index=False)
    log.info(
        f"{len(awarded)} award papers: median citation percentile "
        f"{awarded.percentile.median():.2f}, {awarded.top_cited.mean():.0%} in the top "
        f"{TOP_SHARE:.0%} of their venue-year"
    )


if __name__ == "__main__":
    main()

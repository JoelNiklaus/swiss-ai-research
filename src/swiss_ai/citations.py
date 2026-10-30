"""Citations of main-track papers, ranked within venue and year, by country and for awards.

Citation counts come from OpenAlex for the DBLP papers matched to OpenAlex (OpenReview
venue-years have no OpenAlex id here). Only papers from FIRST_YEAR to LAST_YEAR are used, so every
paper had about five years or more to collect citations. Two measures, each ranked within the
venue-year so that paper age drops out:

- `so_far`: all citations so far (`cited_by_count`).
- `first_five_years`: citations in the publication year and the four years after, from OpenAlex
  `counts_by_year`, which starts in 2012 (so only for papers from FIVE_YEAR_FIRST on).

A paper is top-cited when fewer than TOP_SHARE of its venue-year are cited more. The country
ratio treats top-cited papers exactly like award papers in `analysis.award_ratios`: observed
top-cited papers against what the country's share of the venue-year's papers predicts. For the
award papers themselves, `award_citation_summary` reports where they rank in their venue-year,
overall and by award type, field and Swiss affiliation.
"""

import logging

import pandas as pd
from joblib import Parallel, delayed
from tqdm import tqdm

from swiss_ai.analysis import GROUPS, award_ratios, venue_year_shares
from swiss_ai.attribution import FIRST_YEAR, country_credit, load_papers, match_awards
from swiss_ai.openalex import AUTHORSHIPS, IDS_PER_REQUEST, get_all
from swiss_ai.paths import DATA

log = logging.getLogger(__name__)

CITATIONS = DATA / "citations.csv.gz"
CITATION_RATIOS = DATA / "citation_ratios.csv"
AWARD_CITATIONS = DATA / "award_citations.csv"
AWARD_CITATION_SUMMARY = DATA / "award_citation_summary.csv"
LAST_YEAR = 2021
FIVE_YEAR_FIRST = 2012
TOP_SHARE = 0.10
MEASURES = {"so_far": "cited_by_count", "first_five_years": "cites_5y"}
FIELDS = "id,publication_year,cited_by_count,counts_by_year"
THREADS = 8
# Field of each venue, for the award-citation summary.
FIELDS_BY_VENUE = {
    "CVPR": "vision",
    "ICCV": "vision",
    "ECCV": "vision",
    "ACL": "language",
    "EMNLP": "language",
    "NAACL": "language",
    "NeurIPS": "machine learning",
    "ICML": "machine learning",
    "ICLR": "machine learning",
    "COLM": "language",
    "AAAI": "AAAI",
}


def fetch_batch(ids: list[str]) -> list[dict]:
    """Citation fields for up to IDS_PER_REQUEST OpenAlex work ids (short form, W123)."""
    return get_all("works", "ids.openalex:" + "|".join(ids), FIELDS)


def five_year_citations(work: dict, year: int) -> float:
    """Citations from the paper's year to four years later, or NaN before FIVE_YEAR_FIRST."""
    if year < FIVE_YEAR_FIRST:
        return float("nan")
    by_year = {c["year"]: c["cited_by_count"] for c in work["counts_by_year"]}
    return float(sum(by_year.get(y, 0) for y in range(year, year + 5)))


def fetch_citations(papers: pd.DataFrame) -> pd.DataFrame:
    """Citation counts for every paper in `papers` with an OpenAlex id.

    Returns:
        paper_id, openalex_id (short form), venue, year, cited_by_count and cites_5y.
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
    log.info(f"OpenAlex returned {len(works)} of {len(unique)} requested works")
    found = ids[ids.openalex_id.isin(works)].copy()
    found["cited_by_count"] = [works[i]["cited_by_count"] for i in found.openalex_id]
    found["cites_5y"] = [
        five_year_citations(works[i], y)
        for i, y in zip(found.openalex_id, found.year, strict=True)
    ]
    return found


def rank_within_venue_year(citations: pd.DataFrame, column: str) -> pd.DataFrame:
    """Rank papers by `column` within each venue-year.

    Adds `percentile` (0 to 1, ties averaged), `cited_more_share` (the share of the venue-year's
    papers cited more) and `top_cited` (cited_more_share below TOP_SHARE). Rows where `column`
    is missing are dropped.
    """
    citations = citations.dropna(subset=[column])
    groups = citations.groupby(["venue", "year"])[column]
    cited_more = (groups.rank(ascending=False, method="min") - 1) / groups.transform(
        "size"
    )
    return citations.assign(
        percentile=groups.rank(pct=True, method="average"),
        cited_more_share=cited_more,
        top_cited=cited_more < TOP_SHARE,
    )


def citation_ratios(ranked: pd.DataFrame, credit: pd.DataFrame) -> pd.DataFrame:
    """Observed vs expected top-cited papers per country group, fractional and any-author.

    Args:
        ranked: Output of `rank_within_venue_year`.
        credit: Fractional country credit per paper.

    Returns:
        One row per group as in `analysis.award_ratios` (with `top_cited_papers` for the total),
        plus the group's fractional papers and mean citation percentile.
    """
    credit = credit[credit.paper_id.isin(ranked.paper_id)]
    shares = venue_year_shares(ranked, credit)
    top = ranked[ranked.top_cited].rename(columns={"venue": "conference"})
    out = award_ratios(top, shares, credit).rename(
        columns={"awards": "top_cited_papers"}
    )
    weighted = credit.merge(ranked[["paper_id", "percentile"]])
    weighted["weighted_percentile"] = weighted.percentile * weighted.credit
    for i, members in enumerate(GROUPS.values()):
        rows = weighted[weighted.country.isin(members)]
        out.loc[i, "papers"] = rows.credit.sum()
        # A group without papers in the sample has no mean percentile.
        out.loc[i, "mean_percentile"] = (
            rows.weighted_percentile.sum() / rows.credit.sum()
            if len(rows)
            else float("nan")
        )
    return out


def award_citations(citations: pd.DataFrame, awards: pd.DataFrame) -> pd.DataFrame:
    """Citation counts and venue-year rank of each award paper, for both measures.

    Args:
        citations: Output of `fetch_citations` (not ranked).
        awards: Matched award papers with paper_id, award_type and has_swiss_institution.

    Returns:
        One row per award paper with citations: counts, `percentile`, `cited_more_share` and
        `top_cited` for citations so far, and the same with a `_5y` suffix for the first five
        years (NaN for papers before FIVE_YEAR_FIRST).
    """
    rank_cols = ["percentile", "cited_more_share", "top_cited"]
    so_far = rank_within_venue_year(citations, MEASURES["so_far"])
    five = rank_within_venue_year(citations, MEASURES["first_five_years"])
    five = five[["paper_id", *rank_cols]].rename(
        columns=lambda c: f"{c}_5y" if c in rank_cols else c
    )
    cols = ["paper_id", "venue", "year", "cited_by_count", "cites_5y", *rank_cols]
    return (
        awards[["paper_id", "award_type", "has_swiss_institution"]]
        .merge(so_far[cols])
        .merge(five, how="left")
    )


def award_citation_summary(awarded: pd.DataFrame) -> pd.DataFrame:
    """Where award papers rank by citations in their venue-year, by measure and group.

    Groups: all, best and outstanding awards, each field in FIELDS_BY_VENUE, and papers with a
    Swiss institution. By chance, an award paper lands in the top 10% with probability 0.1 and
    below the median with probability 0.5.

    Returns:
        One row per measure and group with n, median_percentile, share_top_1, share_top_10,
        share_top_25, share_below_median and most_cited (award papers no paper of their
        venue-year out-cites).
    """
    groups = {
        "all": awarded.venue.notna(),
        "best award": awarded.award_type == "best",
        "outstanding award": awarded.award_type == "outstanding",
        **{
            field: awarded.venue.map(FIELDS_BY_VENUE) == field
            for field in dict.fromkeys(FIELDS_BY_VENUE.values())
        },
        "Swiss institution": awarded.has_swiss_institution.astype(bool),
    }
    rows = []
    for measure, suffix in (("so_far", ""), ("first_five_years", "_5y")):
        for group, mask in groups.items():
            df = awarded[mask].dropna(subset=[f"percentile{suffix}"])
            cited_more = df[f"cited_more_share{suffix}"]
            rows.append(
                {
                    "measure": measure,
                    "group": group,
                    "n": len(df),
                    "median_percentile": df[f"percentile{suffix}"].median(),
                    "share_top_1": (cited_more < 0.01).mean(),
                    "share_top_10": (cited_more < 0.10).mean(),
                    "share_top_25": (cited_more < 0.25).mean(),
                    "share_below_median": (df[f"percentile{suffix}"] < 0.5).mean(),
                    "most_cited": int((cited_more == 0).sum()),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    papers, authorships = load_papers()
    papers = papers[papers.year >= FIRST_YEAR]
    window = papers[papers.year <= LAST_YEAR]
    citations = fetch_citations(window)
    log.info(
        f"{len(citations)} of {(window.source == 'openalex').sum()} DBLP papers "
        f"{FIRST_YEAR}-{LAST_YEAR} have OpenAlex citations"
    )
    so_far = rank_within_venue_year(citations, MEASURES["so_far"])
    so_far.to_csv(CITATIONS, index=False)

    credit = country_credit(authorships)
    ratios = pd.concat(
        [
            citation_ratios(rank_within_venue_year(citations, column), credit).assign(
                measure=measure
            )
            for measure, column in MEASURES.items()
        ]
    )
    ratios.to_csv(CITATION_RATIOS, index=False)
    cols = [
        "measure",
        "group",
        "top_cited_papers",
        "observed_any",
        "expected_any",
        "ratio_any",
        "ratio_any_low",
        "ratio_any_high",
        "ratio_frac",
    ]
    log.info(
        f"Top {TOP_SHARE:.0%} cited papers per group:\n{ratios[cols].round(2).to_string(index=False)}"
    )

    awarded = award_citations(citations, match_awards(papers))
    awarded.to_csv(AWARD_CITATIONS, index=False)
    summary = award_citation_summary(awarded)
    summary.to_csv(AWARD_CITATION_SUMMARY, index=False)
    log.info(
        f"Award papers by citation rank:\n{summary.round(3).to_string(index=False)}"
    )


if __name__ == "__main__":
    main()

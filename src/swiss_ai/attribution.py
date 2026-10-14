"""Attribute every main-track paper to countries and match award papers to the paper list.

Each venue-year takes its paper list and author countries from one source: OpenReview where it
covers the venue-year (profiles give country by year), otherwise DBLP papers matched to OpenAlex.
Country credit is fractional: each author with a known country carries 1 / (known authors), split
equally across that author's countries. A paper counts for a country in the any-author measure if
at least one author has that country. Authors without a known country are left out, so the credit
of a paper sums to one over its known authors; papers without any known author are excluded.
"""

import logging

import pandas as pd

from swiss_ai.openalex import AUTHORSHIPS as OPENALEX_AUTHORSHIPS
from swiss_ai.openalex import normalize_title
from swiss_ai.openreview import AUTHORSHIPS as OPENREVIEW_AUTHORSHIPS
from swiss_ai.openreview import PAPERS as OPENREVIEW_PAPERS
from swiss_ai.openreview import VENUES as OPENREVIEW_VENUES
from swiss_ai.paths import AWARDS, DATA

log = logging.getLogger(__name__)

PAPERS = DATA / "papers.csv"
FIRST_YEAR = 2010
# Award papers that DBLP only lists as arXiv preprints, not in the ACL 2024 proceedings.
NOT_IN_DBLP = {
    ("ACL", 2024, "greed is all you need an evaluation of tokenizer inference methods"),
    (
        "ACL",
        2024,
        "getting serious about humor crafting humor datasets with unfunny large language models",
    ),
    (
        "ACL",
        2024,
        "estimating the level of dialectness predicts inter annotator agreement in multi dialect arabic datasets",
    ),
}


def load_papers() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Combine both sources into one paper table and one authorship table.

    Returns:
        papers: paper_id, venue, year, title (normalized), source.
        authorships: paper_id, position, countries ("|"-joined ISO2 codes, "" if unknown).
    """
    dblp = pd.read_csv(PAPERS, keep_default_na=False)
    on_openreview = pd.MultiIndex.from_arrays([dblp.venue, dblp.year]).isin(
        list(OPENREVIEW_VENUES)
    )
    dblp = (
        dblp[~on_openreview]
        .rename(columns={"key": "paper_id"})
        .assign(source="openalex")
    )
    openreview = pd.read_csv(OPENREVIEW_PAPERS, keep_default_na=False)
    openreview = openreview.assign(
        paper_id="openreview:" + openreview.forum, source="openreview"
    )
    cols = ["paper_id", "venue", "year", "title", "source"]
    papers = pd.concat([dblp[cols], openreview[cols]], ignore_index=True)
    papers["title"] = papers.title.map(normalize_title)

    oa = pd.read_csv(OPENALEX_AUTHORSHIPS, keep_default_na=False).rename(
        columns={"key": "paper_id"}
    )
    orv = pd.read_csv(OPENREVIEW_AUTHORSHIPS, keep_default_na=False)
    orv = orv.assign(paper_id="openreview:" + orv.forum)
    cols = ["paper_id", "position", "countries"]
    authorships = pd.concat([oa[cols], orv[cols]], ignore_index=True)
    # Only keep authorships of papers in the combined list (drops OpenAlex rows of OpenReview years).
    return papers, authorships[authorships.paper_id.isin(papers.paper_id)]


def country_credit(authorships: pd.DataFrame) -> pd.DataFrame:
    """Fractional country credit per paper.

    Args:
        authorships: paper_id and countries per authorship.

    Returns:
        One row per paper and country with `credit` (summing to 1 per paper).
    """
    known = authorships[authorships.countries != ""].copy()
    known["n_known"] = known.groupby("paper_id").paper_id.transform("size")
    known["country"] = known.countries.str.split("|")
    long = known.explode("country")
    # An author's weight is split equally across the author's countries.
    long["credit"] = 1 / long.n_known / long.groupby(level=0).country.transform("size")
    return long.groupby(["paper_id", "country"], as_index=False).credit.sum()


def match_awards(papers: pd.DataFrame) -> pd.DataFrame:
    """Attach the paper_id of each main-track award paper since FIRST_YEAR.

    Award venue-years without a paper list (not yet indexed) are dropped with a log line.
    Award papers whose title is not in the paper list of their venue-year raise, because a
    silent drop would bias the observed counts.

    Raises:
        ValueError: If an award paper cannot be matched within a covered venue-year.
    """
    awards = pd.read_csv(AWARDS / "awards.csv", keep_default_na=False)
    awards = awards[(awards.track == "main") & (awards.year >= FIRST_YEAR)].copy()
    awards["title_norm"] = awards.title.map(normalize_title)
    covered = set(zip(papers.venue, papers.year, strict=True))
    has_list = [
        vy in covered for vy in zip(awards.conference, awards.year, strict=True)
    ]
    for (venue, year), n in (
        awards[~pd.Series(has_list, index=awards.index)]
        .groupby(["conference", "year"])
        .size()
        .items()
    ):
        log.info(f"No paper list for {venue} {year}: dropping {n} awards")
    awards = awards[has_list]
    keys = list(zip(awards.conference, awards.year, awards.title_norm, strict=True))
    awards = awards[[k not in NOT_IN_DBLP for k in keys]]
    log.info(
        f"Dropping {len(keys) - len(awards)} award papers missing from DBLP proceedings"
    )
    lookup = (
        papers.drop_duplicates(["venue", "year", "title"])
        .set_index(["venue", "year", "title"])
        .paper_id
    )
    keys = list(zip(awards.conference, awards.year, awards.title_norm, strict=True))
    missing = [k for k in keys if k not in lookup.index]
    if missing:
        raise ValueError(
            f"{len(missing)} award papers not in their paper list: {missing}"
        )
    return awards.assign(paper_id=lookup.loc[keys].to_numpy())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    papers, authorships = load_papers()
    credit = country_credit(authorships)
    papers = papers[papers.year >= FIRST_YEAR]
    papers["known"] = papers.paper_id.isin(credit.paper_id)
    log.info(
        papers.groupby(["venue", "source"])
        .known.agg(["size", "mean"])
        .round(3)
        .to_string()
    )
    awards = match_awards(papers)
    log.info(f"{len(awards)} main-track awards since {FIRST_YEAR} matched to papers")


if __name__ == "__main__":
    main()

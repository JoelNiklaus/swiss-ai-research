"""Top AI conference output against scientific output overall, per resident.

Answers whether Switzerland is strong at top AI conferences beyond its strength in science
overall. OpenAlex counts journal and proceedings articles (type `article`, so arXiv-only preprints
are left out) per author country with full counting: a work counts once for every country among
its authors. The top 11 conference counts use the same any-author rule, from `participation.csv`.
"""

import logging

import pandas as pd

from swiss_ai.analysis import PARTICIPATION, PER_CAPITA_YEARS
from swiss_ai.countries import ALL_PLACES, population
from swiss_ai.openalex import get
from swiss_ai.paths import DATA

log = logging.getLogger(__name__)

SCIENCE_PRIOR = DATA / "science_prior.csv"
YEARS = f"{PER_CAPITA_YEARS.start}-{PER_CAPITA_YEARS.stop - 1}"
BASE_FILTER = f"type:article,publication_year:{YEARS}"
TOP_1_PERCENT = "citation_normalized_percentile.is_in_top_1_percent:true"
# OpenAlex subfields 1702 (Artificial Intelligence) and 1707 (Computer Vision and Pattern
# Recognition), the topics of the top 11 conferences.
AI_TOPICS = "primary_topic.subfield.id:1702|1707"
LEVELS = {
    "all_science": BASE_FILTER,
    "all_science_top1": f"{BASE_FILTER},{TOP_1_PERCENT}",
    "ai_articles": f"{BASE_FILTER},{AI_TOPICS}",
    "ai_articles_top1": f"{BASE_FILTER},{AI_TOPICS},{TOP_1_PERCENT}",
}


def openalex_counts(filter_: str) -> pd.Series:
    """Works per author country (ISO2) for an OpenAlex filter, from one group_by request."""
    data = get(
        "works",
        {"filter": filter_, "group_by": "authorships.countries", "per-page": 200},
    )
    return pd.Series(
        {g["key"].rsplit("/", 1)[-1]: g["count"] for g in data["group_by"]}, dtype=float
    )


def top_conference_counts() -> pd.Series:
    """Any-author main-track papers per country at the top 11 conferences in PER_CAPITA_YEARS."""
    part = pd.read_csv(PARTICIPATION, keep_default_na=False)
    part = part[part.year.isin(PER_CAPITA_YEARS)]
    return (part.any_share * part.n_papers).groupby(part.country).sum()


def prior_table() -> pd.DataFrame:
    """Per-million counts at each level, plus top conference papers per 1,000 articles.

    Returns:
        One row per place in ALL_PLACES, sorted by all-science articles per million.

    Raises:
        ValueError: If a place is missing from the OpenAlex all-science counts.
    """
    places = list(ALL_PLACES)
    counts = pd.DataFrame({level: openalex_counts(f) for level, f in LEVELS.items()})
    # group_by returns the 200 largest countries; every comparison place must be among them.
    missing = sorted(set(places) - set(counts.all_science.dropna().index))
    if missing:
        raise ValueError(f"OpenAlex all-science counts lack {missing}")
    counts = counts.reindex(places)
    counts["top_conferences"] = top_conference_counts().reindex(places)
    per_million = counts.div(population().reindex(places), axis=0) * 1e6
    out = per_million.add_suffix("_per_million")
    out["top_conference_papers_per_1k_articles"] = (
        counts.top_conferences / counts.all_science * 1e3
    )
    return out.sort_values("all_science_per_million", ascending=False)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    df = prior_table()
    df.to_csv(SCIENCE_PRIOR, index_label="country")
    log.info(df.round(1).to_string())
    relative = df.drop(columns="top_conference_papers_per_1k_articles") / df.loc["US"]
    log.info(f"Relative to the US:\n{relative.drop(index='US').round(2).to_string()}")


if __name__ == "__main__":
    main()

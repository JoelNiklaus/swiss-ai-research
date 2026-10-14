"""Private AI investment against AI talent per country, from the AI Index 2026 public data.

Investment and newly funded companies come from Quid (AI Index chapter 4), AI authors and
inventors from Zeki (chapter 1). The CSVs in `data/raw/ai_index/` are the AI Index's own chart
data (https://drive.google.com/drive/folders/1zJTOg0iR0j5SijCwFutwWvDt143lW277), which only
list the top 15 countries per chart.
"""

import logging

import pandas as pd

from swiss_ai.paths import DATA

log = logging.getLogger(__name__)

AI_INDEX = DATA / "raw" / "ai_index"
INVESTMENT = DATA / "investment.csv"

# Census Bureau Vintage 2025 estimate for July 1, 2025 (https://www.census.gov/quickfacts/fact/table/CA/).
CALIFORNIA_POPULATION = 39_355_309
# Nine-county Bay Area, California Department of Finance July 2025 estimate
# (https://www.bayareacouncil.org/economy/regional-population-growth-grinds-to-a-halt/).
BAY_AREA_POPULATION = 7_670_000
# Crunchbase and HumanX AI Funding Report 2025: Bay Area AI funding in 2025 (60% of $211B).
BAY_AREA_INVESTMENT_2025 = 126e9


def read_top15(name: str, value: str) -> pd.Series:
    """Read a two-column AI Index top-15 chart CSV into a Series indexed by country."""
    df = pd.read_csv(AI_INDEX / f"{name}.csv")
    df.columns = [value, "country"]
    return df.set_index("country")[value]


def country_table() -> pd.DataFrame:
    """Join Zeki talent with Quid investment and derive the transfer ratios.

    Population is derived from Zeki's own count and per-capita rate, so both research
    measures use the same denominator. Countries outside a top-15 chart get NaN for it.

    Returns:
        One row per country in Zeki's per-capita chart, sorted by authors per 100k.
    """
    authors = read_top15("fig_1.8.1", "ai_authors") * 1_000
    per_100k = (
        pd.read_csv(AI_INDEX / "fig_1.8.2.csv")
        .drop_duplicates()
        .set_index("country")
        .talent_per_100k.rename("authors_per_100k")
    )
    df = pd.concat(
        [
            per_100k,
            authors,
            read_top15("fig_4.2.12", "investment_2013_2025") * 1e9,
            read_top15("fig_4.2.13", "companies_2013_2025"),
            read_top15("fig_4.2.8", "investment_2025") * 1e9,
        ],
        axis=1,
        join="outer",
    ).loc[per_100k.index]
    df["population"] = df.ai_authors / df.authors_per_100k * 1e5
    df["investment_per_capita_2013_2025"] = df.investment_2013_2025 / df.population
    # Cumulative money divided by the 2025 headcount; Zeki has no earlier counts.
    df["investment_per_author_2013_2025"] = df.investment_2013_2025 / df.ai_authors
    df["companies_per_1k_authors_2013_2025"] = (
        df.companies_2013_2025 / df.ai_authors * 1_000
    )
    df["investment_per_capita_2025"] = df.investment_2025 / df.population
    return df.sort_values("authors_per_100k", ascending=False)


def us_references() -> pd.DataFrame:
    """California (same Quid data as the countries) and the Bay Area (Crunchbase) for 2025."""
    states = pd.read_csv(AI_INDEX / "fig_4.2.15.csv").set_index("state_code")
    refs = pd.DataFrame(
        {
            "investment_2025": [states.total_funding["CA"], BAY_AREA_INVESTMENT_2025],
            "population": [CALIFORNIA_POPULATION, BAY_AREA_POPULATION],
            "source": ["Quid via AI Index 2026", "Crunchbase and HumanX 2025"],
        },
        index=pd.Index(["California", "Bay Area"], name="region"),
    )
    refs["investment_per_capita_2025"] = refs.investment_2025 / refs.population
    return refs


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    df = country_table()
    df.to_csv(INVESTMENT, index_label="country")
    cols = [
        "authors_per_100k",
        "investment_per_capita_2013_2025",
        "investment_per_author_2013_2025",
        "companies_per_1k_authors_2013_2025",
    ]
    log.info(df[cols].round(1).to_string())
    log.info(us_references().round(0).to_string())
    swiss, israel = df.loc["Switzerland"], df.loc["Israel"]
    log.info(
        f"Israel attracts {israel.investment_per_author_2013_2025 / swiss.investment_per_author_2013_2025:.1f}x "
        f"as much private AI investment per AI author as Switzerland (2013 to 2025)"
    )
    # Switzerland is not in the 2025 top-15 chart, so its 2025 value is below the 15th country's.
    floor = read_top15("fig_4.2.8", "investment_2025").min() * 1e9
    log.info(
        f"Swiss 2025 investment < ${floor / 1e9:.2f}B, i.e. < ${floor / swiss.population:.0f} per resident"
    )


if __name__ == "__main__":
    main()

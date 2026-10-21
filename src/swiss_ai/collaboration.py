"""Award ratios of domestic and international papers per country.

For a country, a paper is domestic when every author with a known country lists only that
country, and international when it also has an author from (or with an affiliation in) another
country. Expected awards follow `analysis.award_ratios`: each award adds the group's share of the
papers with a known country in its venue-year. Counts are any-author, since a domestic paper
belongs entirely to one country anyway.
"""

import logging

import pandas as pd

from swiss_ai.analysis import poisson_interval
from swiss_ai.attribution import FIRST_YEAR, load_papers, match_awards
from swiss_ai.countries import COUNTRIES
from swiss_ai.paths import DATA

log = logging.getLogger(__name__)

COLLABORATION = DATA / "collaboration_awards.csv"


def team_types(authorships: pd.DataFrame) -> pd.DataFrame:
    """One row per paper and author country, labelled domestic or international.

    Args:
        authorships: paper_id and "|"-joined countries per authorship ("" if unknown).

    Returns:
        paper_id, country and team ("domestic" or "international").
    """
    known = authorships[authorships.countries != ""]
    countries = (
        known.assign(country=known.countries.str.split("|"))
        .explode("country")
        .groupby("paper_id")
        .country.agg(lambda c: sorted(set(c)))
    )
    out = countries.rename("country").explode().reset_index()
    out["team"] = (
        countries.loc[out.paper_id]
        .str.len()
        .gt(1)
        .map({True: "international", False: "domestic"})
        .to_numpy()
    )
    return out


def collaboration_ratios(
    papers: pd.DataFrame, teams: pd.DataFrame, awards: pd.DataFrame
) -> pd.DataFrame:
    """Observed vs expected awards for the domestic and international papers of each country.

    Returns:
        One row per country and team with the paper count, the team's share of the country's
        papers, observed and expected awards, their ratio and a 95% Poisson interval.
    """
    teams = teams.merge(papers[["paper_id", "venue", "year"]])
    n_papers = teams.groupby(["venue", "year"]).paper_id.nunique().rename("n_papers")
    group_papers = teams.groupby(["country", "team", "venue", "year"]).size()
    shares = (group_papers / n_papers).rename("share").reset_index()
    awards = awards[awards.paper_id.isin(teams.paper_id)]
    expected = (
        awards[["conference", "year"]]
        .rename(columns={"conference": "venue"})
        .merge(shares)
        .groupby(["country", "team"])
        .share.sum()
    )
    observed = (
        teams[teams.paper_id.isin(awards.paper_id)].groupby(["country", "team"]).size()
    )
    totals = teams.groupby(["country", "team"]).size()
    country_totals = totals.groupby(level="country").sum()
    rows = []
    for country in COUNTRIES:
        for team in ("domestic", "international"):
            key = (country, team)
            obs = observed.get(key, 0)
            # A group without papers in any award venue-year has no expectation to compare with.
            exp = expected.get(key, 0.0) or float("nan")
            low, high = poisson_interval(obs)
            rows.append(
                {
                    "country": country,
                    "team": team,
                    "papers": totals.get(key, 0),
                    "share_of_country_papers": totals.get(key, 0)
                    / country_totals.get(country, float("nan")),
                    "observed": obs,
                    "expected": exp,
                    "ratio": obs / exp,
                    "ratio_low": low / exp,
                    "ratio_high": high / exp,
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    papers, authorships = load_papers()
    papers = papers[papers.year >= FIRST_YEAR]
    authorships = authorships[authorships.paper_id.isin(papers.paper_id)]
    ratios = collaboration_ratios(papers, team_types(authorships), match_awards(papers))
    ratios.to_csv(COLLABORATION, index=False)
    log.info(ratios.round(2).to_string(index=False))


if __name__ == "__main__":
    main()

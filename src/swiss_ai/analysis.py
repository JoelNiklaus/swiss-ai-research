"""Participation shares, per-capita output, and expected vs observed awards per country.

Expected awards weight each award by its own venue-year: an award at CVPR 2024 adds the
country's CVPR 2024 participation share to its expected count. Fractional award credit is
compared with fractional participation, and award papers with any author from a country with
the any-author participation share; the two measures are never mixed.
"""

import logging
from collections.abc import Callable

import pandas as pd
from scipy.stats import gamma, poisson

from swiss_ai.attribution import FIRST_YEAR, country_credit, load_papers, match_awards
from swiss_ai.awards import load_nationality, normalize, parse_authors
from swiss_ai.countries import ALL_PLACES, COUNTRIES, population
from swiss_ai.paths import AWARDS, DATA

log = logging.getLogger(__name__)

PARTICIPATION = DATA / "participation.csv"
PER_CAPITA = DATA / "participation_per_capita.csv"
AWARD_RATIOS = DATA / "award_ratios.csv"
CITIZEN_WINNERS = DATA / "citizen_winners.csv"
PER_CAPITA_YEARS = range(2023, 2026)
# Israel and Singapore have enough expected awards to stand alone; the rest are pooled.
SMALL_PEERS = ["NL", "DK", "SE", "AT", "FI"]
SMALL_PEERS_LABEL = "Other small peers"
GROUPS = {**{c: [c] for c in COUNTRIES}, SMALL_PEERS_LABEL: SMALL_PEERS}
SPLIT_YEAR = 2023
AUTHOR = "Joel Niklaus"

# Swiss shares of the relevant world totals; sources in README.md.
NATIONALITY_BASELINES = {
    "world population (7.4M Swiss citizens incl. abroad / 8.23B)": 7.4 / 8232,
    "OECD + China population (7.4M / 2.81B)": 7.4 / 2810,
    "world researchers, all fields (55k / 8.85M)": 0.006,
}

# Award subsets for robustness checks; each maps the matched awards to a boolean mask.
VARIANTS: dict[str, Callable[[pd.DataFrame], pd.Series]] = {
    "all": lambda a: a.year > 0,
    "without Cotterell group": lambda a: ~a.authors.str.contains("Ryan Cotterell"),
    "without the post author's papers": lambda a: ~a.authors.str.contains(AUTHOR),
    "without ACL/EMNLP outstanding 2021+": lambda a: (
        ~(
            a.conference.isin(["ACL", "EMNLP"])
            & (a.award_type == "outstanding")
            & (a.year >= 2021)
        )
    ),
    f"{FIRST_YEAR}-{SPLIT_YEAR - 1}": lambda a: a.year < SPLIT_YEAR,
    f"{SPLIT_YEAR}-2026": lambda a: a.year >= SPLIT_YEAR,
}


def venue_year_shares(papers: pd.DataFrame, credit: pd.DataFrame) -> pd.DataFrame:
    """Fractional and any-author country shares per venue-year, over papers with a known country.

    Returns:
        One row per venue, year and country with frac_share, any_share and n_papers.
    """
    merged = credit.merge(papers[["paper_id", "venue", "year"]])
    n_papers = merged.groupby(["venue", "year"]).paper_id.nunique().rename("n_papers")
    out = merged.groupby(["venue", "year", "country"]).agg(
        frac=("credit", "sum"), any=("paper_id", "nunique")
    )
    out = out.join(n_papers)
    out["frac_share"] = out.frac / out.n_papers
    out["any_share"] = out["any"] / out.n_papers
    return out[["frac_share", "any_share", "n_papers"]].reset_index()


def per_capita(papers: pd.DataFrame, credit: pd.DataFrame) -> pd.DataFrame:
    """Fractional main-track papers per million residents for the comparison places.

    Returns:
        One row per place in ALL_PLACES with papers, share of all papers, and
        papers_per_million, summed over PER_CAPITA_YEARS and all venues.
    """
    window = papers[papers.year.isin(PER_CAPITA_YEARS)]
    merged = credit.merge(window[["paper_id"]])
    total = merged.paper_id.nunique()
    papers_by_country = merged.groupby("country").credit.sum()
    out = (
        papers_by_country.reindex(list(ALL_PLACES), fill_value=0)
        .rename("papers")
        .to_frame()
    )
    out["share"] = out.papers / total
    out["papers_per_million"] = out.papers / population()[out.index] * 1e6
    return out.sort_values("papers_per_million", ascending=False).reset_index()


def poisson_interval(observed: float, alpha: float = 0.05) -> tuple[float, float]:
    """Exact (Garwood) interval for a Poisson mean, continuous in `observed` for fractional counts."""
    lower = gamma.ppf(alpha / 2, observed) if observed > 0 else 0.0
    return lower, gamma.ppf(1 - alpha / 2, observed + 1)


def award_ratios(
    awards: pd.DataFrame, shares: pd.DataFrame, credit: pd.DataFrame
) -> pd.DataFrame:
    """Observed vs expected awards per country group, fractional and any-author.

    Award papers without any author of known country carry no credit, so they are left out of
    both the observed and the expected counts.

    Returns:
        One row per group with observed and expected counts, their ratio and a 95% interval.
    """
    awards = awards[awards.paper_id.isin(credit.paper_id)]
    observed = credit.merge(awards[["paper_id"]])
    observed = observed.groupby("country").agg(
        frac=("credit", "sum"), any=("paper_id", "nunique")
    )
    expected = (
        awards[["conference", "year"]]
        .rename(columns={"conference": "venue"})
        .merge(shares)
    )
    expected = expected.groupby("country")[["frac_share", "any_share"]].sum()
    rows = []
    for group, members in GROUPS.items():
        row = {"group": group, "awards": len(awards)}
        for measure, share in [("frac", "frac_share"), ("any", "any_share")]:
            obs = observed[measure].reindex(members, fill_value=0).sum()
            exp = expected[share].reindex(members, fill_value=0).sum()
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


def curated_vs_pipeline(awards: pd.DataFrame, credit: pd.DataFrame) -> pd.DataFrame:
    """Cross-tabulate the hand-curated Swiss-institution flag with the pipeline's any-author CH."""
    pipeline_ch = awards.paper_id.isin(credit[credit.country == "CH"].paper_id)
    return pd.crosstab(
        awards.has_swiss_institution.rename("curated"), pipeline_ch.rename("pipeline")
    )


def citizen_winners(since: int = FIRST_YEAR) -> pd.DataFrame:
    """Swiss citizens among main-track award winners against population baselines.

    Citizenship was only checked for winners with a Swiss affiliation or a Swiss-sounding
    name, so the observed counts are lower bounds.

    Args:
        since: First award year to include.

    Returns:
        One row per citizenship status set and baseline with the number of distinct winners,
        observed Swiss citizens, the expected count and the Poisson tail probability.
    """
    df = pd.read_csv(AWARDS / "awards.csv", keep_default_na=False)
    df = df[(df.track == "main") & (df.year >= since)]
    people = {normalize(a) for s in df.authors for a in parse_authors(s)}
    swiss = load_nationality()
    rows = []
    for label, statuses in [
        ("confirmed", {"confirmed"}),
        ("confirmed + probable", {"confirmed", "probable"}),
    ]:
        observed = sum(swiss[p] in statuses for p in people if p in swiss)
        for base, share in NATIONALITY_BASELINES.items():
            expected = share * len(people)
            rows.append(
                {
                    "since": since,
                    "award_papers": len(df),
                    "winners": len(people),
                    "status": label,
                    "observed": observed,
                    "baseline": base,
                    "expected": expected,
                    "p_at_least_observed": poisson.sf(observed - 1, expected),
                }
            )
    return pd.DataFrame(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    papers, authorships = load_papers()
    papers = papers[papers.year >= FIRST_YEAR]
    credit = country_credit(authorships)
    credit = credit[credit.paper_id.isin(papers.paper_id)]

    shares = venue_year_shares(papers, credit)
    shares.to_csv(PARTICIPATION, index=False)
    capita = per_capita(papers, credit)
    capita.to_csv(PER_CAPITA, index=False)
    log.info(
        f"Participation {PER_CAPITA_YEARS.start}-{PER_CAPITA_YEARS.stop - 1}:\n{capita.round(4).to_string(index=False)}"
    )

    awards = match_awards(papers)
    ratios = pd.concat(
        [
            award_ratios(awards[mask(awards)], shares, credit).assign(variant=name)
            for name, mask in VARIANTS.items()
        ]
    )
    ratios.to_csv(AWARD_RATIOS, index=False)
    cols = [
        "variant",
        "awards",
        "observed_frac",
        "expected_frac",
        "ratio_frac",
        "ratio_frac_low",
        "ratio_frac_high",
    ]
    log.info(
        f"Award ratios (fractional):\n{ratios[ratios.variant == 'all'][['group', *cols[1:]]].round(2).to_string(index=False)}"
    )
    log.info(
        f"Swiss award ratio by variant:\n{ratios[ratios.group == 'CH'][cols].round(2).to_string(index=False)}"
    )
    any_cols = [
        "variant",
        "observed_any",
        "expected_any",
        "ratio_any",
        "ratio_any_low",
        "ratio_any_high",
    ]
    log.info(
        f"Swiss any-author ratio by variant:\n{ratios[ratios.group == 'CH'][any_cols].round(2).to_string(index=False)}"
    )
    log.info(f"Curated Swiss flag vs pipeline:\n{curated_vs_pipeline(awards, credit)}")
    citizens = pd.concat([citizen_winners(FIRST_YEAR), citizen_winners(0)])
    citizens.to_csv(CITIZEN_WINNERS, index=False)
    log.info(
        f"Swiss citizens among award winners:\n{citizens.round(4).to_string(index=False)}"
    )


if __name__ == "__main__":
    main()

import pandas as pd
import pytest
from scipy.stats import chi2

from swiss_ai import analysis


@pytest.fixture
def toy() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Two venue-years; CH writes one of four CVPR papers and wins the single CVPR award."""
    papers = pd.DataFrame(
        {
            "paper_id": ["a", "b", "c", "d", "e"],
            "venue": ["CVPR"] * 4 + ["ACL"],
            "year": [2024] * 5,
        }
    )
    credit = pd.DataFrame(
        {
            "paper_id": ["a", "a", "b", "c", "d", "e"],
            "country": ["CH", "US", "US", "US", "CN", "IL"],
            "credit": [0.5, 0.5, 1.0, 1.0, 1.0, 1.0],
        }
    )
    return papers, credit


def test_venue_year_shares(toy: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    shares = analysis.venue_year_shares(*toy).set_index(["venue", "country"])
    assert shares.loc[("CVPR", "CH"), "frac_share"] == pytest.approx(0.125)
    assert shares.loc[("CVPR", "CH"), "any_share"] == pytest.approx(0.25)
    assert shares.loc[("CVPR", "US"), "frac_share"] == pytest.approx(0.625)
    assert shares.loc[("ACL", "IL"), "n_papers"] == 1


def test_award_ratios_weight_by_venue_year(
    toy: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    papers, credit = toy
    shares = analysis.venue_year_shares(papers, credit)
    awards = pd.DataFrame(
        {"conference": ["CVPR", "ACL"], "year": [2024, 2024], "paper_id": ["a", "e"]}
    )
    ratios = analysis.award_ratios(awards, shares, credit).set_index("group")
    ch = ratios.loc["CH"]
    assert ch.observed_frac == pytest.approx(0.5)
    assert ch.expected_frac == pytest.approx(0.125)
    assert ch.ratio_frac == pytest.approx(4.0)
    assert ch.observed_any == 1
    assert ch.expected_any == pytest.approx(0.25)
    israel = ratios.loc["IL"]
    assert israel.observed_frac == pytest.approx(1.0)
    assert israel.expected_frac == pytest.approx(1.0)
    small = ratios.loc[analysis.SMALL_PEERS_LABEL]
    assert small.observed_frac == 0
    assert small.expected_frac == 0
    assert (
        ratios.loc["US", "ratio_frac_low"]
        < ratios.loc["US", "ratio_frac"]
        < ratios.loc["US", "ratio_frac_high"]
    )


def test_award_ratios_skip_awards_without_known_authors(
    toy: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    papers, credit = toy
    shares = analysis.venue_year_shares(papers, credit)
    awards = pd.DataFrame(
        {
            "conference": ["CVPR", "CVPR"],
            "year": [2024, 2024],
            "paper_id": ["a", "unknown"],
        }
    )
    assert analysis.award_ratios(awards, shares, credit).awards.iloc[0] == 1


@pytest.mark.parametrize("k", [1, 3, 10])
def test_poisson_interval_matches_garwood(k: int) -> None:
    low, high = analysis.poisson_interval(k)
    assert low == pytest.approx(chi2.ppf(0.025, 2 * k) / 2)
    assert high == pytest.approx(chi2.ppf(0.975, 2 * k + 2) / 2)


def test_poisson_interval_zero() -> None:
    low, high = analysis.poisson_interval(0)
    assert low == 0
    assert high == pytest.approx(3.689, abs=1e-3)


def test_per_capita(
    toy: tuple[pd.DataFrame, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    papers, credit = toy
    population = pd.Series(1e6, index=list(analysis.ALL_PLACES))
    monkeypatch.setattr(analysis, "population", lambda: population)
    df = analysis.per_capita(papers, credit).set_index("country")
    assert df.loc["US", "papers"] == pytest.approx(2.5)
    assert df.loc["US", "share"] == pytest.approx(0.5)
    assert df.loc["CH", "papers_per_million"] == pytest.approx(0.5)
    assert df.loc["SE", "papers"] == 0
    assert df.loc["HK", "papers"] == 0


def test_curated_vs_pipeline(toy: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    _, credit = toy
    awards = pd.DataFrame(
        {"paper_id": ["a", "b"], "has_swiss_institution": [True, True]}
    )
    table = analysis.curated_vs_pipeline(awards, credit)
    assert table.loc[True, True] == 1
    assert table.loc[True, False] == 1


def test_citizen_winners_reports_baselines() -> None:
    df = analysis.citizen_winners()
    assert len(df) == 2 * len(analysis.NATIONALITY_BASELINES)
    assert set(df.status) == {"confirmed", "confirmed + probable"}
    assert (df.since == analysis.FIRST_YEAR).all()
    confirmed = df[df.status == "confirmed"].observed.iloc[0]
    probable = df[df.status == "confirmed + probable"].observed.iloc[0]
    assert 0 < confirmed <= probable
    all_years = analysis.citizen_winners(0)
    assert all_years.winners.iloc[0] >= df.winners.iloc[0]


def test_main_writes_outputs(
    toy: tuple[pd.DataFrame, pd.DataFrame], tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers, credit = toy
    authorships = credit.rename(columns={"country": "countries"})[
        ["paper_id", "countries"]
    ]
    awards = pd.DataFrame(
        {
            "conference": ["CVPR"],
            "year": [2024],
            "paper_id": ["a"],
            "authors": ["X"],
            "award_type": ["best"],
            "has_swiss_institution": [True],
        }
    )
    monkeypatch.setattr(analysis, "load_papers", lambda: (papers, authorships))
    monkeypatch.setattr(analysis, "match_awards", lambda p: awards)
    monkeypatch.setattr(
        analysis, "population", lambda: pd.Series(1e6, index=list(analysis.ALL_PLACES))
    )
    for name in ("PARTICIPATION", "PER_CAPITA", "AWARD_RATIOS", "CITIZEN_WINNERS"):
        monkeypatch.setattr(analysis, name, tmp_path / f"{name}.csv")
    analysis.main()
    ratios = pd.read_csv(tmp_path / "AWARD_RATIOS.csv")
    assert set(ratios.variant) == set(analysis.VARIANTS)
    citizens = pd.read_csv(tmp_path / "CITIZEN_WINNERS.csv")
    assert set(citizens.since) == {analysis.FIRST_YEAR, 0}


def test_variants_partition_years() -> None:
    awards = pd.DataFrame(
        {
            "year": [2015, 2024],
            "authors": ["Ryan Cotterell; X", "Joel Niklaus; Y"],
            "conference": ["ACL", "EMNLP"],
            "award_type": ["best", "outstanding"],
        }
    )
    masks = {name: mask(awards).tolist() for name, mask in analysis.VARIANTS.items()}
    assert masks["all"] == [True, True]
    assert masks["without Cotterell group"] == [False, True]
    assert masks["without the post author's papers"] == [True, False]
    assert masks["without ACL/EMNLP outstanding 2021+"] == [True, False]
    assert masks["2010-2022"] == [True, False]

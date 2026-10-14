from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import pytest

from swiss_ai import figures

RATIO_COLUMNS = [
    f"ratio_{m}{suffix}" for m in ("frac", "any") for suffix in ("", "_low", "_high")
]


def ratio_value(col: str) -> float:
    if col.endswith("_high"):
        return 2.0
    if col.endswith("_low"):
        return 0.5
    return 1.0


@pytest.fixture
def inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    pd.DataFrame({"country": ["CH", "US"], "papers_per_million": [134.2, 51.7]}).to_csv(
        tmp_path / "capita.csv", index=False
    )
    rows = [
        {"group": g, "variant": "all", "awards": 441}
        for g in ["CH", *figures.RATIO_GROUPS]
    ] + [{"group": "CH", "variant": "without Cotterell group", "awards": 430}]
    ratios = pd.DataFrame(rows)
    for col in RATIO_COLUMNS:
        ratios[col] = ratio_value(col)
    ratios.loc[ratios.group == "US", "ratio_frac"] = 1.3
    ratios.to_csv(tmp_path / "ratios.csv", index=False)
    pd.DataFrame(
        {
            "country": ["Switzerland", "Germany"],
            "authors_per_100k": [110, 58],
            "investment_per_author_2013_2025": [474_000, 354_000],
            "investment_per_capita_2013_2025": [523, 205],
        }
    ).to_csv(tmp_path / "investment.csv", index=False)
    funnel = pd.DataFrame(
        [
            {
                "year": y,
                "institution": "All Swiss universities",
                "stage": s,
                "swiss": 100 + y - 2010,
                "foreign": 200,
            }
            for y in range(2010, 2026)
            for s in ("BSc", "MSc", "PhD")
        ]
    )
    funnel.to_csv(tmp_path / "funnel.csv", index=False)
    monkeypatch.setattr(figures, "PER_CAPITA", tmp_path / "capita.csv")
    monkeypatch.setattr(figures, "AWARD_RATIOS", tmp_path / "ratios.csv")
    monkeypatch.setattr(figures, "INVESTMENT", tmp_path / "investment.csv")
    pd.DataFrame(
        {
            "stage": ["Seed", "Series A"],
            "eu_pre_money": [7.0, 32.1],
            "us_pre_money": [16.9, 51.6],
            "eu_round": [2.0, 11.5],
            "us_round": [4.0, 14.9],
        }
    ).to_csv(tmp_path / "vc_terms.csv", index=False)
    monkeypatch.setattr(figures, "FUNNEL", tmp_path / "funnel.csv")
    monkeypatch.setattr(figures, "VC_TERMS", tmp_path / "vc_terms.csv")
    return tmp_path


@pytest.mark.parametrize("name", list(figures.FIGURES_BY_NAME))
def test_figures_build(inputs: Path, name: str) -> None:
    fig = figures.FIGURES_BY_NAME[name]()
    assert isinstance(fig, go.Figure)
    assert fig.data


def test_participation_highlights_switzerland(inputs: Path) -> None:
    bar = figures.participation_figure().data[0]
    assert list(bar.y) == ["United States", "Switzerland"]
    assert list(bar.marker.color) == [figures.GREY, figures.SWISS_RED]


def test_award_rows_put_switzerland_first(inputs: Path) -> None:
    rows = figures.award_rows()
    assert rows.label.iloc[0] == "<b>Switzerland</b>"
    assert "Cotterell" in rows.label.iloc[1]
    assert rows.label.iloc[2] == "United States"
    assert len(rows) == 2 + len(figures.RATIO_GROUPS)


def test_award_figure_uses_legend_not_annotations(inputs: Path) -> None:
    fig = figures.award_ratio_figure()
    assert [trace.name for trace in fig.data] == [
        "Ratio of 1: awards match the paper share",
        "Fractional credit (author share)",
        "Any author from the country",
    ]
    assert not fig.layout.annotations


def test_funnel_indexes_to_base_year(inputs: Path) -> None:
    fig = figures.funnel_figure()
    swiss_phd = next(t for t in fig.data if t.name.startswith("Swiss doctoral"))
    assert swiss_phd.y[0] == pytest.approx(100)
    assert swiss_phd.y[-1] == pytest.approx(115)


def test_name_handles_groups() -> None:
    assert figures.name("CH") == "Switzerland"
    assert figures.name("HK") == "Hong Kong"
    assert figures.name(figures.SMALL_PEERS_LABEL).startswith("Other small peers (NL")
    assert figures.name("Pooled") == "Pooled"


def test_social_figure_matches_countries_by_name(inputs: Path) -> None:
    scatter = figures.social_figure().data[0]
    assert list(scatter.x) == [134.2]
    assert list(scatter.y) == [523]
    assert list(scatter.text) == ["<b>Switzerland</b>"]
    assert list(scatter.marker.color) == [figures.SWISS_RED]


def test_vc_terms_figure_pairs_europe_with_us(inputs: Path) -> None:
    fig = figures.vc_terms_figure()
    assert [t.name for t in fig.data] == ["Europe", "United States"] * 2
    assert list(fig.data[0].y) == [7.0, 32.1]
    assert list(fig.data[3].text) == ["$4.0M", "$14.9M"]
    assert [t.showlegend for t in fig.data] == [True, True, False, False]

from pathlib import Path

import pandas as pd
import pytest

from swiss_ai import citations


def work(wid: str, total: int, by_year: dict[int, int]) -> dict:
    return {
        "id": f"https://openalex.org/{wid}",
        "cited_by_count": total,
        "counts_by_year": [
            {"year": y, "cited_by_count": c} for y, c in by_year.items()
        ],
    }


def test_five_year_citations_window() -> None:
    w = work("W1", 30, {2018: 1, 2019: 2, 2022: 4, 2023: 8})
    assert citations.five_year_citations(w, 2018) == 7  # 2018-2022
    assert pd.isna(citations.five_year_citations(w, citations.FIVE_YEAR_FIRST - 1))


def test_rank_within_venue_year_marks_top_tenth() -> None:
    df = pd.DataFrame(
        {
            "paper_id": [f"p{i}" for i in range(20)] + ["q"],
            "venue": ["ACL"] * 20 + ["CVPR"],
            "year": [2018] * 21,
            "cited_by_count": list(range(20)) + [5],
        }
    )
    ranked = citations.rank_within_venue_year(df, "cited_by_count").set_index(
        "paper_id"
    )
    assert (
        ranked.top_cited.sum() == 3
    )  # the two most cited ACL papers and the lone CVPR one
    assert ranked.loc["p19", "percentile"] == pytest.approx(1.0)
    assert not ranked.loc["p17", "top_cited"]


def test_rank_within_venue_year_drops_missing_values() -> None:
    df = pd.DataFrame(
        {
            "paper_id": ["a", "b"],
            "venue": ["ACL", "ACL"],
            "year": [2014, 2014],
            "cites_5y": [3.0, float("nan")],
        }
    )
    assert citations.rank_within_venue_year(df, "cites_5y").paper_id.tolist() == ["a"]


def test_citation_ratios_mirror_award_ratios() -> None:
    cites = pd.DataFrame(
        {
            "paper_id": ["a", "b", "c", "d"],
            "venue": ["ACL"] * 4,
            "year": [2018] * 4,
            "percentile": [1.0, 0.75, 0.5, 0.25],
            "top_cited": [True, False, False, False],
        }
    )
    credit = pd.DataFrame(
        {
            "paper_id": ["a", "a", "b", "c", "d"],
            "country": ["CH", "US", "US", "US", "CN"],
            "credit": [0.5, 0.5, 1.0, 1.0, 1.0],
        }
    )
    ratios = citations.citation_ratios(cites, credit).set_index("group")
    ch = ratios.loc["CH"]
    assert ch.top_cited_papers == 1
    assert ch.observed_frac == pytest.approx(0.5)
    assert ch.expected_frac == pytest.approx(0.125)
    assert ch.ratio_any == pytest.approx(4.0)
    assert ch.mean_percentile == pytest.approx(1.0)
    assert ratios.loc["US", "mean_percentile"] == pytest.approx(
        (0.5 + 0.75 + 0.5) / 2.5
    )


def test_fetch_citations(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pd.DataFrame(
        {
            "key": ["k1", "k1", "k2", "k3"],
            "openalex_id": ["W1", "W1", "https://openalex.org/W2", "W3"],
        }
    ).to_csv(tmp_path / "authorships.csv", index=False)
    requested: list[str] = []

    def fake_get_all(entity: str, filter_: str, select: str) -> list[dict]:
        requested.append(filter_)
        return [work("W1", 9, {2018: 2, 2019: 3}), work("W2", 4, {})]

    monkeypatch.setattr(citations, "AUTHORSHIPS", tmp_path / "authorships.csv")
    monkeypatch.setattr(citations, "get_all", fake_get_all)
    papers = pd.DataFrame(
        {
            "paper_id": ["k1", "k2", "k3"],
            "venue": ["ACL"] * 3,
            "year": [2018, 2011, 2018],
        }
    )
    out = citations.fetch_citations(papers).set_index("paper_id")
    assert requested == ["ids.openalex:W1|W2|W3"]
    assert out.loc["k1", "cited_by_count"] == 9
    assert out.loc["k1", "cites_5y"] == 5
    assert pd.isna(out.loc["k2", "cites_5y"])
    assert "k3" not in out.index


def test_rank_within_venue_year_reports_share_cited_more() -> None:
    df = pd.DataFrame(
        {
            "paper_id": list("abcd"),
            "venue": ["ACL"] * 4,
            "year": [2018] * 4,
            "cited_by_count": [10, 5, 5, 1],
        }
    )
    ranked = citations.rank_within_venue_year(df, "cited_by_count")
    assert ranked.cited_more_share.tolist() == [0.0, 0.25, 0.25, 0.75]


def test_award_citations_rank_both_measures() -> None:
    cites = pd.DataFrame(
        {
            "paper_id": ["a", "b", "c", "d"],
            "venue": ["ACL"] * 4,
            "year": [2018] * 4,
            "cited_by_count": [10, 20, 1, 5],
            "cites_5y": [8, 2, 1, float("nan")],
        }
    )
    awards = pd.DataFrame(
        {
            "paper_id": ["a"],
            "conference": ["ACL"],
            "award_type": ["best"],
            "has_swiss_institution": [True],
        }
    )
    out = citations.award_citations(cites, awards).iloc[0]
    assert out.cited_more_share == pytest.approx(0.25)
    # Five-year counts rank among the three papers that have them; "a" leads.
    assert out.cited_more_share_5y == 0
    assert out.percentile_5y == 1.0
    assert out.has_swiss_institution


def test_award_citation_summary_by_group() -> None:
    awarded = pd.DataFrame(
        {
            "venue": ["CVPR", "ACL", "ACL", "ICML"],
            "award_type": ["best", "best", "outstanding", "outstanding"],
            "has_swiss_institution": [True, False, False, False],
            "percentile": [1.0, 0.95, 0.3, 0.6],
            "cited_more_share": [0.0, 0.05, 0.7, 0.4],
            "percentile_5y": [0.9, 0.8, 0.2, float("nan")],
            "cited_more_share_5y": [0.08, 0.2, 0.8, float("nan")],
        }
    )
    out = citations.award_citation_summary(awarded).set_index(["measure", "group"])
    everything = out.loc[("so_far", "all")]
    assert everything.n == 4
    assert everything.median_percentile == pytest.approx(0.775)
    assert everything.share_top_10 == pytest.approx(0.5)
    assert everything.share_below_median == pytest.approx(0.25)
    assert everything.most_cited == 1
    assert out.loc[("so_far", "best award")].share_top_10 == 1.0
    assert out.loc[("so_far", "language")].n == 2
    assert out.loc[("so_far", "Swiss institution")].n == 1
    # Papers without five-year counts drop out of that measure only.
    assert out.loc[("first_five_years", "all")].n == 3
    assert out.loc[("first_five_years", "all")].share_top_10 == pytest.approx(1 / 3)

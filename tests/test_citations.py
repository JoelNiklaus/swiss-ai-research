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
    assert pd.isna(citations.five_year_citations(w, 2015))


def test_rank_within_venue_year_marks_top_tenth() -> None:
    df = pd.DataFrame(
        {
            "paper_id": [f"p{i}" for i in range(20)] + ["q"],
            "venue": ["ACL"] * 20 + ["CVPR"],
            "year": [2018] * 21,
            "cited_by_count": list(range(20)) + [5],
        }
    )
    ranked = citations.rank_within_venue_year(df).set_index("paper_id")
    assert (
        ranked.top_cited.sum() == 3
    )  # the two most cited ACL papers and the lone CVPR one
    assert ranked.loc["p19", "percentile"] == pytest.approx(1.0)
    assert not ranked.loc["p17", "top_cited"]


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
            "year": [2018, 2012, 2018],
        }
    )
    out = citations.fetch_citations(papers).set_index("paper_id")
    assert requested == ["ids.openalex:W1|W2|W3"]
    assert out.loc["k1", "cited_by_count"] == 9
    assert out.loc["k1", "cites_5y"] == 5
    assert pd.isna(out.loc["k2", "cites_5y"])
    assert "k3" not in out.index


def test_award_citations_keep_award_columns() -> None:
    cites = pd.DataFrame(
        {
            "paper_id": ["a", "b"],
            "venue": ["ACL", "ACL"],
            "year": [2018, 2018],
            "cited_by_count": [10, 1],
            "cites_5y": [5, 1],
            "percentile": [1.0, 0.5],
            "top_cited": [True, False],
        }
    )
    awards = pd.DataFrame(
        {"paper_id": ["a"], "award_type": ["best"], "has_swiss_institution": [True]}
    )
    out = citations.award_citations(cites, awards)
    assert out.percentile.tolist() == [1.0]
    assert out.has_swiss_institution.tolist() == [True]

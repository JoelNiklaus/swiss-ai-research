from pathlib import Path

import pandas as pd
import pytest

from swiss_ai import collaboration


@pytest.fixture
def toy() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """One venue-year of four papers: a Swiss-only, a Swiss-US, a US-only and an unknown one."""
    papers = pd.DataFrame(
        {"paper_id": ["a", "b", "c", "d"], "venue": ["ACL"] * 4, "year": [2020] * 4}
    )
    authorships = pd.DataFrame(
        {
            "paper_id": ["a", "a", "b", "b", "c", "d"],
            "countries": ["CH", "CH", "CH", "US", "US", ""],
        }
    )
    awards = pd.DataFrame({"conference": ["ACL"], "year": [2020], "paper_id": ["a"]})
    return papers, authorships, awards


def test_team_types_split_domestic_and_international(
    toy: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    teams = collaboration.team_types(toy[1]).set_index(["paper_id", "country"]).team
    assert teams[("a", "CH")] == "domestic"
    assert teams[("b", "CH")] == teams[("b", "US")] == "international"
    assert teams[("c", "US")] == "domestic"
    assert "d" not in teams.index.get_level_values("paper_id")


def test_team_types_count_dual_affiliation_as_international() -> None:
    teams = collaboration.team_types(
        pd.DataFrame({"paper_id": ["x"], "countries": ["CH|US"]})
    )
    assert set(teams.team) == {"international"}


def test_collaboration_ratios(
    toy: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
) -> None:
    papers, authorships, awards = toy
    ratios = collaboration.collaboration_ratios(
        papers, collaboration.team_types(authorships), awards
    ).set_index(["country", "team"])
    domestic = ratios.loc[("CH", "domestic")]
    # Three papers have a known country; the Swiss-only paper is one of them and won.
    assert domestic.expected == pytest.approx(1 / 3)
    assert domestic.observed == 1
    assert domestic.ratio == pytest.approx(3.0)
    assert domestic.share_of_country_papers == pytest.approx(0.5)
    assert ratios.loc[("CH", "international"), "observed"] == 0


def test_main_writes_table(
    toy: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    papers, authorships, awards = toy
    monkeypatch.setattr(collaboration, "load_papers", lambda: (papers, authorships))
    monkeypatch.setattr(collaboration, "match_awards", lambda p: awards)
    monkeypatch.setattr(collaboration, "COLLABORATION", tmp_path / "out.csv")
    collaboration.main()
    out = pd.read_csv(tmp_path / "out.csv")
    assert len(out) == 2 * len(collaboration.COUNTRIES)

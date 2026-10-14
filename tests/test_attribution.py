from pathlib import Path

import pandas as pd
import pytest

from swiss_ai import attribution


def test_country_credit_fractional_and_split() -> None:
    authorships = pd.DataFrame(
        {"paper_id": ["p", "p", "p", "q"], "countries": ["CH", "CH|US", "", "DE"]}
    )
    credit = (
        attribution.country_credit(authorships)
        .set_index(["paper_id", "country"])
        .credit
    )
    # Two known authors on p: 1/2 for the Swiss author, 1/4 + 1/4 for the dual affiliation.
    assert credit["p", "CH"] == pytest.approx(0.75)
    assert credit["p", "US"] == pytest.approx(0.25)
    assert credit["q", "DE"] == pytest.approx(1.0)
    assert credit.groupby(level=0).sum().tolist() == pytest.approx([1.0, 1.0])


AWARDS_CSV = """conference,year,award_type,track,title,authors,has_swiss_institution
ACL,2024,best,main,"Paper One: Results",A,True
ACL,2024,best,demo,Demo Paper,B,False
ACL,2009,best,main,Too Old,C,False
COLM,2025,best,main,Not Indexed,D,False
ACL,2024,outstanding,main,"Greed is All You Need: An Evaluation of Tokenizer Inference Methods",E,False
"""


@pytest.fixture
def awards_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "awards.csv").write_text(AWARDS_CSV)
    monkeypatch.setattr(attribution, "AWARDS", tmp_path)
    return tmp_path


def test_match_awards(awards_dir: Path) -> None:
    papers = pd.DataFrame(
        {
            "paper_id": ["x"],
            "venue": ["ACL"],
            "year": [2024],
            "title": ["paper one results"],
        }
    )
    awards = attribution.match_awards(papers)
    assert awards.paper_id.tolist() == ["x"]


def test_match_awards_raises_on_missing_paper(awards_dir: Path) -> None:
    papers = pd.DataFrame(
        {
            "paper_id": ["x"],
            "venue": ["ACL"],
            "year": [2024],
            "title": ["another paper"],
        }
    )
    with pytest.raises(ValueError, match="paper one results"):
        attribution.match_awards(papers)


def test_load_papers_takes_one_source_per_venue_year(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pd.DataFrame(
        {
            "key": ["d1", "d2"],
            "venue": ["ACL", "ICLR"],
            "year": [2024, 2024],
            "title": ["A Paper", "B Paper"],
        }
    ).to_csv(tmp_path / "papers.csv", index=False)
    pd.DataFrame(
        {"forum": ["f1"], "venue": ["ICLR"], "year": [2024], "title": ["B Paper"]}
    ).to_csv(tmp_path / "or_papers.csv", index=False)
    pd.DataFrame(
        {"key": ["d1", "d2"], "position": [0, 0], "countries": ["CH", "US"]}
    ).to_csv(tmp_path / "oa.csv", index=False)
    pd.DataFrame({"forum": ["f1"], "position": [0], "countries": ["DE"]}).to_csv(
        tmp_path / "or.csv", index=False
    )
    monkeypatch.setattr(attribution, "PAPERS", tmp_path / "papers.csv")
    monkeypatch.setattr(attribution, "OPENREVIEW_PAPERS", tmp_path / "or_papers.csv")
    monkeypatch.setattr(attribution, "OPENALEX_AUTHORSHIPS", tmp_path / "oa.csv")
    monkeypatch.setattr(attribution, "OPENREVIEW_AUTHORSHIPS", tmp_path / "or.csv")
    monkeypatch.setattr(
        attribution, "OPENREVIEW_VENUES", {("ICLR", 2024): ("api", "id")}
    )
    papers, authorships = attribution.load_papers()
    assert sorted(papers.paper_id) == ["d1", "openreview:f1"]
    assert papers.set_index("paper_id").title["openreview:f1"] == "b paper"
    assert authorships.set_index("paper_id").countries.to_dict() == {
        "d1": "CH",
        "openreview:f1": "DE",
    }

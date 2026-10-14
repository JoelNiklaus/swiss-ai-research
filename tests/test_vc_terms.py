from pathlib import Path

import pandas as pd
import pytest

from swiss_ai import vc_terms


@pytest.fixture
def terms(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    rows = [
        ("pre_money_valuation", "Seed", "Europe", 8.0),
        ("pre_money_valuation", "Seed", "United States", 16.0),
        ("round_size", "Seed", "Europe", 2.0),
        ("round_size_vs_us", "Seed", "Europe", 0.5),
        ("established_round_size_vs_us", "Seed", "Europe", 1.2),
    ]
    pd.DataFrame(rows, columns=["measure", "stage", "region", "value"]).to_csv(
        tmp_path / "terms.csv", index=False
    )
    monkeypatch.setattr(vc_terms, "HAND_COLLECTED", tmp_path / "terms.csv")
    monkeypatch.setattr(vc_terms, "STAGES", ["Seed"])
    return tmp_path


def test_stage_table_derives_us_round_and_share_sold(terms: Path) -> None:
    seed = vc_terms.stage_table().loc["Seed"]
    assert seed.us_round == pytest.approx(4.0)
    assert seed.us_valuation_multiple == pytest.approx(2.0)
    assert seed.us_round_multiple == pytest.approx(2.0)
    assert seed.eu_share_sold == pytest.approx(0.2)
    assert seed.us_share_sold == pytest.approx(0.2)


def test_main_writes_table(
    terms: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(vc_terms, "VC_TERMS", tmp_path / "out.csv")
    vc_terms.main()
    assert pd.read_csv(tmp_path / "out.csv").stage.tolist() == ["Seed"]


def test_committed_table_matches_atomico() -> None:
    df = vc_terms.stage_table()
    assert df.index.tolist() == vc_terms.STAGES
    assert df.loc["Seed", "us_valuation_multiple"] == pytest.approx(2.40, abs=0.01)
    assert df.loc["Series A", "us_round"] == pytest.approx(14.95, abs=0.01)

from pathlib import Path

import pandas as pd
import pytest

from swiss_ai import investment


@pytest.fixture
def ai_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    files = {
        "fig_1.8.1": "ai_authors,country\n10,Switzerland\n5,Israel\n",
        "fig_1.8.2": "country,talent_per_100k\nSwitzerland,110\nIsrael,50\nIsrael,50\n",
        "fig_4.2.12": "investment,country\n5,Switzerland\n20,Israel\n",
        "fig_4.2.13": "companies,country\n200,Switzerland\n500,Israel\n",
        "fig_4.2.8": "investment,country\n4,Israel\n2,Sweden\n",
        "fig_4.2.15": "state_code,total_funding\nCA,200000000000\nNY,10\n",
    }
    for name, content in files.items():
        (tmp_path / f"{name}.csv").write_text(content)
    monkeypatch.setattr(investment, "AI_INDEX", tmp_path)
    return tmp_path


def test_country_table_ratios(ai_index: Path) -> None:
    df = investment.country_table()
    ch, il = df.loc["Switzerland"], df.loc["Israel"]
    assert ch.population == pytest.approx(10_000 / 110 * 1e5)
    assert ch.investment_per_author_2013_2025 == pytest.approx(5e9 / 10_000)
    assert il.companies_per_1k_authors_2013_2025 == pytest.approx(100)
    assert pd.isna(ch.investment_2025)
    assert df.index.tolist() == ["Switzerland", "Israel"]


def test_main_writes_table(
    ai_index: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(investment, "INVESTMENT", tmp_path / "investment.csv")
    investment.main()
    assert pd.read_csv(tmp_path / "investment.csv").country.tolist() == [
        "Switzerland",
        "Israel",
    ]


def test_us_references(ai_index: Path) -> None:
    refs = investment.us_references()
    assert refs.loc["California", "investment_per_capita_2025"] == pytest.approx(
        2e11 / investment.CALIFORNIA_POPULATION
    )
    assert (
        refs.loc["Bay Area", "investment_2025"] == investment.BAY_AREA_INVESTMENT_2025
    )

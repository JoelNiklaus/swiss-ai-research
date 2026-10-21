from pathlib import Path

import pandas as pd
import pytest

from swiss_ai import science_prior


@pytest.fixture
def fake_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    def fake_get(entity: str, params: dict) -> dict:
        scale = 10 if science_prior.TOP_1_PERCENT in params["filter"] else 1
        counts = dict.fromkeys(science_prior.ALL_PLACES, 1000) | {
            "CH": 2000,
            "US": 30000,
        }
        return {
            "group_by": [
                {"key": f"https://openalex.org/countries/{c}", "count": n // scale}
                for c, n in counts.items()
            ]
        }

    population = pd.Series(1e6, index=list(science_prior.ALL_PLACES))
    pd.DataFrame(
        {
            "venue": ["ACL", "ACL", "ACL"],
            "year": [2024, 2024, 2019],
            "country": ["CH", "US", "CH"],
            "frac_share": [0.1, 0.5, 0.1],
            "any_share": [0.2, 0.6, 0.2],
            "n_papers": [100, 100, 50],
        }
    ).to_csv(tmp_path / "participation.csv", index=False)
    monkeypatch.setattr(science_prior, "get", fake_get)
    monkeypatch.setattr(science_prior, "population", lambda: population)
    monkeypatch.setattr(science_prior, "PARTICIPATION", tmp_path / "participation.csv")
    return tmp_path


def test_openalex_counts_parse_country_keys(fake_sources: Path) -> None:
    counts = science_prior.openalex_counts(science_prior.BASE_FILTER)
    assert counts["CH"] == 2000
    assert counts["US"] == 30000


def test_top_conference_counts_use_window_and_any_author(fake_sources: Path) -> None:
    counts = science_prior.top_conference_counts()
    assert counts["CH"] == pytest.approx(20)  # 2019 is outside the window
    assert counts["US"] == pytest.approx(60)


def test_prior_table(fake_sources: Path) -> None:
    df = science_prior.prior_table()
    ch = df.loc["CH"]
    assert ch.all_science_per_million == pytest.approx(2000)
    assert ch.all_science_top1_per_million == pytest.approx(200)
    assert ch.top_conferences_per_million == pytest.approx(20)
    assert ch.top_conference_papers_per_1k_articles == pytest.approx(10)
    assert df.index[0] == "US"
    assert pd.isna(df.loc["DE", "top_conferences_per_million"])


def test_prior_table_fails_on_missing_place(
    fake_sources: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def partial_get(entity: str, params: dict) -> dict:
        return {"group_by": [{"key": "https://openalex.org/countries/CH", "count": 5}]}

    monkeypatch.setattr(science_prior, "get", partial_get)
    with pytest.raises(ValueError, match="lack"):
        science_prior.prior_table()


def test_main_writes_table(fake_sources: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(science_prior, "SCIENCE_PRIOR", fake_sources / "out.csv")
    science_prior.main()
    assert pd.read_csv(fake_sources / "out.csv").country.iloc[0] == "US"

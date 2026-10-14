from collections.abc import Iterator
from pathlib import Path

import httpx
import pandas as pd
import pytest

from swiss_ai import countries


def full_payload() -> list:
    return [
        {"page": 1},
        [
            {"country": {"id": c}, "value": 1_000_000 * (i + 1)}
            for i, c in enumerate(countries.ALL_PLACES)
        ],
    ]


@pytest.fixture
def fake_get(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    calls: list[str] = []

    def get(url: str, params: dict, timeout: int) -> httpx.Response:
        calls.append(url)
        return httpx.Response(
            200, json=full_payload(), request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(countries.httpx, "get", get)
    countries.population.cache_clear()
    yield calls
    countries.population.cache_clear()


def test_population_fetches_once_and_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_get: list[str]
) -> None:
    monkeypatch.setattr(countries, "POPULATION_CACHE", tmp_path / "pop.csv")
    assert countries.population()["CH"] == 1_000_000
    countries.population.cache_clear()
    assert countries.population()["HK"] > 0
    assert len(fake_get) == 1


def test_population_refetches_incomplete_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_get: list[str]
) -> None:
    cache_path = tmp_path / "pop.csv"
    pd.DataFrame({"country": ["CH"], "population": [9]}).to_csv(cache_path, index=False)
    monkeypatch.setattr(countries, "POPULATION_CACHE", cache_path)
    assert countries.population()["KR"] > 0
    assert len(fake_get) == 1


def test_iso3_lists() -> None:
    assert len(countries.ISO3) == len(countries.COUNTRIES)
    assert countries.ISO3[0] == "CHE"
    assert len(countries.ALL_ISO3) == len(countries.ALL_PLACES)
    assert "HKG" in countries.ALL_ISO3
    assert "HKG" not in countries.ISO3


def test_researchers_keeps_latest_untransformed_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_path = tmp_path / "msti.csv"
    pd.DataFrame(
        {
            "REF_AREA": ["CHE", "CHE", "CHE", "DEU"],
            "TRANSFORMATION": ["_Z", "_Z", "GY", "_Z"],
            "TIME_PERIOD": [2022, 2023, 2023, 2024],
            "OBS_VALUE": ["50000", "54013", "1.5", "513100"],
        }
    ).to_csv(cache_path, index=False)
    monkeypatch.setattr(countries, "RESEARCHERS_CACHE", cache_path)
    countries.researchers.cache_clear()
    df = countries.researchers()
    countries.researchers.cache_clear()
    assert df.loc["CH", "researchers_fte"] == 54013
    assert df.loc["CH", "researchers_year"] == 2023
    assert df.loc["DE", "researchers_fte"] == 513100

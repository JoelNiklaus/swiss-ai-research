import json
from pathlib import Path

import pandas as pd
import pytest

from swiss_ai import crosscheck


def record(
    index: str, countries: str, status: str = "Poster", track: str = "main"
) -> dict:
    return {
        "track": track,
        "status": status,
        "aff_country_unique_index": index,
        "aff_country_unique": countries,
    }


def test_author_countries_handles_multi_affiliations_and_gaps() -> None:
    assert crosscheck.author_countries(
        record("0;1+0;", "Switzerland;United States")
    ) == [
        ["Switzerland"],
        ["United States", "Switzerland"],
    ]
    assert crosscheck.author_countries({"track": "main"}) == []


def test_swiss_shares_matches_pipeline_credit() -> None:
    records = [
        # Two authors, one Swiss: fractional 0.5, any 1.
        record("0;1", "Switzerland;United States"),
        # One author split between CH and US: fractional 0.5, any 1.
        record("0+1", "Switzerland;United States"),
        # US only.
        record("0", "United States"),
        # Not counted: rejected, other track, no country.
        record("0", "Switzerland", status="Reject"),
        record("0", "Switzerland", track="Position"),
        record("", ""),
    ]
    shares = crosscheck.swiss_shares(records)
    assert shares["pc_papers"] == 3
    assert shares["pc_frac_share"] == pytest.approx(1 / 3)
    assert shares["pc_any_share"] == pytest.approx(2 / 3)


def test_crosscheck_pools_and_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(crosscheck, "PC_CACHE", tmp_path)
    monkeypatch.setattr(crosscheck, "FILES", {("ICLR", 2024): "iclr/iclr2024"})
    (tmp_path / "iclr_iclr2024.json").write_text(
        json.dumps([record("0", "Switzerland"), record("0", "United States")])
    )
    participation = tmp_path / "participation.csv"
    pd.DataFrame(
        {
            "venue": ["ICLR", "ICLR"],
            "year": [2024, 2024],
            "country": ["CH", "US"],
            "frac_share": [0.4, 0.6],
            "any_share": [0.5, 0.7],
            "n_papers": [10, 10],
        }
    ).to_csv(participation, index=False)
    monkeypatch.setattr(crosscheck, "PARTICIPATION", participation)
    df = crosscheck.crosscheck().set_index("venue")
    assert df.loc["ICLR", "pc_frac_share"] == pytest.approx(0.5)
    assert df.loc["ICLR", "frac_share"] == pytest.approx(0.4)
    assert df.loc["pooled", "pc_papers"] == 2


def test_country_comparison_merges_hong_kong_into_china(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(crosscheck, "PC_CACHE", tmp_path)
    monkeypatch.setattr(crosscheck, "FILES", {("ICLR", 2024): "iclr/iclr2024"})
    (tmp_path / "iclr_iclr2024.json").write_text(
        json.dumps([record("0", "China"), record("0", "Switzerland")])
    )
    participation = tmp_path / "participation.csv"
    pd.DataFrame(
        {
            "venue": ["ICLR", "ICLR", "ICLR", "ICML"],
            "year": [2024, 2024, 2024, 2024],
            "country": ["CH", "HK", "CN", "CH"],
            "frac_share": [0.6, 0.1, 0.3, 0.9],
            "any_share": [0.6, 0.1, 0.3, 0.9],
            "n_papers": [10, 10, 10, 10],
        }
    ).to_csv(participation, index=False)
    monkeypatch.setattr(crosscheck, "PARTICIPATION", participation)
    df = crosscheck.country_comparison().set_index("country")
    assert df.loc["CN", "papers"] == pytest.approx(4.0)
    assert df.loc["CH", "papers"] == pytest.approx(6.0)
    assert df.loc["CH", "ratio"] == pytest.approx(6.0)
    assert df.loc["US", "pc_papers"] == 0

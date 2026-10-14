import json
from pathlib import Path

import pandas as pd
import pytest

from swiss_ai import funding


def project(call: str, country: str, subjects: list[str]) -> dict:
    return {
        "id": "101",
        "ecMaxContribution": "1500000",
        "relations": {
            "associations": [
                {
                    "contenttype": "call",
                    "identifier": call,
                    "attributes": {"type": "relatedMasterCall"},
                },
                {
                    "contenttype": "call",
                    "identifier": call,
                    "attributes": {"type": "relatedSubCall"},
                },
                {
                    "contenttype": "organization",
                    "legalName": "ETH ZUERICH",
                    "address": {"country": country},
                    "attributes": {"type": "coordinator"},
                },
                {
                    "contenttype": "organization",
                    "legalName": "OTHER",
                    "address": {"country": "DE"},
                    "attributes": {"type": "participant"},
                },
            ],
            "categories": [
                {"displayCode": s, "attributes": {"classification": "euroSciVoc"}}
                for s in subjects
            ]
            + [{"title": "Project", "attributes": {"classification": "collection"}}],
        },
    }


def write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "project-rcn-1_en.json"
    path.write_text(json.dumps(data))
    return path


def test_parse_project_erc_grant(tmp_path: Path) -> None:
    subjects = [
        "/natural sciences/computer and information sciences/artificial intelligence/machine learning"
    ]
    record = funding.parse_project(
        write(tmp_path, project("ERC-2019-STG", "CH", subjects))
    )
    assert record == {
        "id": "101",
        "call_year": 2019,
        "scheme": "STG",
        "host": "ETH ZUERICH",
        "country": "CH",
        "computer_science": True,
        "ai": True,
        "ec_contribution": 1.5e6,
    }


def test_parse_project_normalizes_scheme_case(tmp_path: Path) -> None:
    for call, scheme in [
        ("ERC-2014-CoG", "COG"),
        ("ERC-2015-AdG", "ADG"),
        ("ERC-2022-SYG", "SyG"),
        ("ERC-2018-SyG", "SyG"),
    ]:
        record = funding.parse_project(write(tmp_path, project(call, "CH", [])))
        assert record is not None
        assert record["scheme"] == scheme


def test_parse_project_maps_uk_and_skips_non_erc(tmp_path: Path) -> None:
    assert (
        funding.parse_project(write(tmp_path, project("ERC-2023-ADG", "UK", [])))[
            "country"
        ]
        == "GB"
    )
    assert (
        funding.parse_project(write(tmp_path, project("ERC-2023-POC", "CH", [])))
        is None
    )
    assert (
        funding.parse_project(write(tmp_path, project("H2020-MSCA-IF-2019", "CH", [])))
        is None
    )


def test_by_country_fills_missing_years(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        funding, "population", lambda: pd.Series({"CH": 2e6, "IL": 1e6})
    )
    grants = pd.DataFrame(
        {
            "id": ["1", "2", "3", "4"],
            "call_year": [2020, 2020, 2021, 2021],
            "country": ["CH", "CH", "IL", "FR"],
            "computer_science": [True, False, False, True],
            "ai": [False, False, False, True],
        }
    )
    df = funding.by_country(grants).set_index(["country", "call_year"])
    assert df.loc[("CH", 2020), "grants"] == 2
    assert df.loc[("CH", 2020), "grants_per_million"] == pytest.approx(1.0)
    assert df.loc[("CH", 2021), "grants"] == 0
    assert "FR" not in df.index.get_level_values(0)


def test_erc_grants_parses_and_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for programme in funding.PROGRAMMES:
        (tmp_path / programme).mkdir()
    write(tmp_path / "h2020", project("ERC-2016-COG", "CH", []))
    monkeypatch.setattr(funding, "CORDIS", tmp_path)
    monkeypatch.setattr(funding, "ERC_RAW", tmp_path / "erc.csv")
    df = funding.erc_grants()
    assert df.scheme.tolist() == ["COG"]
    assert (tmp_path / "erc.csv").exists()


def test_main_writes_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    grants = pd.DataFrame(
        {
            "id": ["1"],
            "call_year": [2019],
            "country": ["CH"],
            "computer_science": [True],
            "ai": [False],
        }
    )
    snsf = pd.DataFrame(
        {"year": [2022], "grants": [2], "chf": [1.0], "erc_replacement": [0]}
    )
    monkeypatch.setattr(funding, "erc_grants", lambda: grants)
    monkeypatch.setattr(funding, "snsf_computer_science", lambda: snsf)
    monkeypatch.setattr(funding, "population", lambda: pd.Series({"CH": 1e6}))
    monkeypatch.setattr(funding, "ERC_BY_COUNTRY", tmp_path / "erc.csv")
    monkeypatch.setattr(funding, "SNSF_CS", tmp_path / "snsf.csv")
    funding.main()
    assert pd.read_csv(tmp_path / "erc.csv").grants.tolist() == [1]


SNSF_CSV = """GrantNumber;MainDiscipline;FundingInstrumentPublished;AmountGrantedAllSets;CallDecisionYear
1;Information Technology;Project funding;100.5;2022
2;Information Technology;SNSF Starting Grants;200;2022
3;Physics;Project funding;300;2022
4;Information Technology;SNSF Advanced Grants;50;2023
"""


def test_snsf_computer_science(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "grants.csv"
    path.write_text("\ufeff" + SNSF_CSV)
    monkeypatch.setattr(funding, "SNSF_GRANTS", path)
    df = funding.snsf_computer_science().set_index("year")
    assert df.loc[2022, "grants"] == 2
    assert df.loc[2022, "chf"] == pytest.approx(300.5)
    assert df.loc[2022, "erc_replacement"] == 1
    assert df.loc[2023, "erc_replacement"] == 1

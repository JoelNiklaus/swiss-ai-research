from pathlib import Path

import pandas as pd
import pytest

from swiss_ai import citizenship
from swiss_ai.citizenship import NATIONALITY


def long_table() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Jahr": ["2024/25"] * 6,
            "Studienstufe": ["Doktorat"] * 6,
            NATIONALITY: ["Schweiz", "Ausland"] * 3,
            "Hochschule": ["ETHZ", "ETHZ", "EPFL", "EPFL", "UZH", "UZH"],
            "value": [20, 80, 10, 90, 50, 50],
        }
    )


def test_swiss_share_per_group() -> None:
    df = citizenship.swiss_share(long_table(), ["Hochschule"]).set_index("Hochschule")
    assert df.loc["ETHZ", "swiss_share"] == pytest.approx(0.2)
    assert df.loc["UZH", "total"] == 100


def test_with_institution_total_labels_and_appends_total() -> None:
    df = citizenship.with_institution_total(long_table())
    shares = (
        citizenship.swiss_share(df, ["institution"])
        .set_index("institution")
        .swiss_share
    )
    assert shares["ETH Zurich"] == pytest.approx(0.2)
    assert shares["Other universities"] == pytest.approx(0.5)
    assert shares["All Swiss universities"] == pytest.approx(80 / 300)


def test_student_funnel_maps_levels_and_years(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(citizenship, "fetch", lambda table, selection: long_table())
    df = citizenship.student_funnel()
    assert set(df.stage) == {"PhD"}
    assert set(df.year) == {2024}


def test_funnel_drops_empty_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    def fetch(table: str, selection: dict[str, list[str]]) -> pd.DataFrame:
        df = long_table()
        if table.endswith("1504040100_103"):
            return df.assign(Jahr="2024", value=0)
        if table.endswith("1502040100_104"):
            return df.drop(columns="Studienstufe")
        return df

    monkeypatch.setattr(citizenship, "fetch", fetch)
    df = citizenship.funnel()
    assert set(df.stage) == {"PhD", "CS, all levels"}


OECD_CSV = """REF_AREA,EDUCATION_FIELD,SEX,TIME_PERIOD,MOBILITY,OBS_VALUE
CHE,F06,_T,2024,_T,1000
CHE,F06,_T,2024,MOB,835
CHE,F06,F,2024,_T,300
ISR,F06,_T,2024,_T,200
ISR,F06,_T,2024,MOB,
NLD,F06,_T,2024,_T,0
NLD,F06,_T,2024,MOB,0
CHE,F02,_T,2024,_T,50
"""


def test_main_writes_outputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mobility = pd.DataFrame(
        {"country": ["CHE"], "field": ["ICT"], "year": [2024], "mobile_share": [0.8]}
    )
    funnel = pd.DataFrame(
        {
            "year": [2024],
            "institution": ["EPFL"],
            "stage": ["PhD"],
            "swiss_share": [0.1],
        }
    )
    monkeypatch.setattr(citizenship, "doctoral_mobility", lambda: mobility)
    monkeypatch.setattr(citizenship, "funnel", lambda: funnel)
    monkeypatch.setattr(citizenship, "DOCTORAL_MOBILITY", tmp_path / "mobility.csv")
    monkeypatch.setattr(citizenship, "FUNNEL", tmp_path / "funnel.csv")
    citizenship.main()
    assert (tmp_path / "funnel.csv").exists()


def test_doctoral_mobility_reads_cache_and_drops_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = tmp_path / "oecd.csv"
    cache.write_text(OECD_CSV)
    monkeypatch.setattr(citizenship, "OECD_CACHE", cache)
    df = citizenship.doctoral_mobility()
    assert df.country.tolist() == ["CHE"]
    assert df.field.tolist() == ["ICT"]
    assert df.mobile_share[0] == pytest.approx(0.835)

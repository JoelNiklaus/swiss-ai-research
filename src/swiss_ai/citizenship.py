"""Swiss share of students and staff by degree level (BFS), and peer doctoral mobility (OECD).

BFS does not publish computer science by degree level by nationality for universities. The
closest public cube is the field "4.1 Exakte Wissenschaften", which contains exactly computer
science, mathematics, physics, astronomy and other exact sciences; computer science is about
half of it at ETH and EPFL. Computer science alone is available by nationality across all levels.

The OECD counts internationally mobile students (who crossed a border to study), not foreign
citizens, so its peer comparison measures a related but different quantity than the BFS funnel.
"""

import logging

import httpx
import pandas as pd

from swiss_ai.bfs import ALL, fetch
from swiss_ai.countries import ISO3
from swiss_ai.paths import CACHE, DATA

log = logging.getLogger(__name__)

FUNNEL = DATA / "citizenship_funnel.csv"
DOCTORAL_MOBILITY = DATA / "doctoral_mobility.csv"
OECD_CACHE = CACHE / "oecd_doctoral_enrolment.csv"
OECD_URL = (
    "https://sdmx.oecd.org/public/rest/data/"
    "OECD.EDU.IMEP,DSD_EAG_UOE_NON_FIN_STUD@DF_UOE_NF_RAW_FIELD,1.1/{key}"
)
OECD_FIELDS = {"F06": "ICT", "F05T07": "STEM"}
NATIONALITY = "Staatsangehörigkeit (Kategorie)"
EXACT_SCIENCES = "4.1 Exakte Wissenschaften"
LEVELS = {"Bachelor": "BSc", "Master": "MSc", "Doktorat": "PhD"}
INSTITUTIONS = {"ETHZ": "ETH Zurich", "EPFL": "EPFL"}


def swiss_share(df: pd.DataFrame, by: list[str]) -> pd.DataFrame:
    """Sum counts per group and nationality and add the Swiss share.

    Args:
        df: Long BFS table with a nationality column, `value`, and the `by` columns.
        by: Grouping columns.

    Returns:
        One row per group with columns swiss, foreign, total and swiss_share.
    """
    wide = df.groupby([*by, NATIONALITY]).value.sum().unstack(NATIONALITY)
    out = pd.DataFrame({"swiss": wide["Schweiz"], "foreign": wide["Ausland"]})
    out["total"] = out.swiss + out.foreign
    out["swiss_share"] = out.swiss / out.total
    return out.reset_index()


def with_institution_total(df: pd.DataFrame) -> pd.DataFrame:
    """Rename ETH and EPFL, label all other universities as such, and append a Switzerland total."""
    named = df.assign(
        institution=df.Hochschule.map(INSTITUTIONS).fillna("Other universities")
    )
    return pd.concat([named, named.assign(institution="All Swiss universities")])


def student_funnel() -> pd.DataFrame:
    """Swiss share of exact-sciences students by year, institution and level (BSc, MSc, PhD)."""
    df = fetch(
        "px-x-1502040100_107",
        {
            "Jahr": ALL,
            "Fachbereich": [EXACT_SCIENCES],
            "Studienstufe": list(LEVELS),
            NATIONALITY: ALL,
            "Hochschule": ALL,
        },
    )
    df = with_institution_total(df.assign(stage=df.Studienstufe.map(LEVELS)))
    # Academic year '2024/25' is reported as its autumn year 2024.
    df["year"] = df.Jahr.str[:4].astype(int)
    return swiss_share(df, ["year", "institution", "stage"])


def staff_share() -> pd.DataFrame:
    """Swiss share of all exact-sciences staff (professors, assistants, PhD employees, technicians)."""
    df = fetch(
        "px-x-1504040100_103",
        {
            "Jahr": ALL,
            "Fachbereich": [EXACT_SCIENCES],
            NATIONALITY: ["Schweiz", "Ausland"],
            "Hochschule": ALL,
        },
    )
    df = with_institution_total(df.assign(stage="Staff", year=df.Jahr.astype(int)))
    return swiss_share(df, ["year", "institution", "stage"])


def computer_science_share() -> pd.DataFrame:
    """Swiss share of computer science students across all levels, by year and institution."""
    df = fetch(
        "px-x-1502040100_104",
        {
            "Jahr": ALL,
            "Fachrichtung": ["Informatik"],
            NATIONALITY: ALL,
            "Hochschule": ALL,
        },
    )
    df = with_institution_total(df.assign(stage="CS, all levels"))
    df["year"] = df.Jahr.str[:4].astype(int)
    return swiss_share(df, ["year", "institution", "stage"])


def funnel() -> pd.DataFrame:
    """Stack students by level, staff and the computer science check into one long table."""
    df = pd.concat([student_funnel(), staff_share(), computer_science_share()])
    return df[df.total > 0].sort_values(["institution", "stage", "year"])


def doctoral_mobility() -> pd.DataFrame:
    """Share of internationally mobile doctoral students in ICT and STEM, per peer and year.

    Returns:
        One row per country, field and year with enrolled, mobile and mobile_share.
    """
    if not OECD_CACHE.exists():
        # Dimension order: area, level, measure, then 12 more; empty positions mean all values.
        key = f"{'+'.join(ISO3)}.ISCED11_8.ENRL............"
        response = httpx.get(
            OECD_URL.format(key=key),
            params={"startPeriod": 2013, "dimensionAtObservation": "AllDimensions"},
            headers={"Accept": "application/vnd.sdmx.data+csv; charset=utf-8"},
            timeout=300,
        )
        OECD_CACHE.parent.mkdir(parents=True, exist_ok=True)
        OECD_CACHE.write_text(response.raise_for_status().text)
    df = pd.read_csv(OECD_CACHE, keep_default_na=False, dtype={"OBS_VALUE": str})
    df["OBS_VALUE"] = pd.to_numeric(df.OBS_VALUE.replace("", None))
    df = df[df.EDUCATION_FIELD.isin(OECD_FIELDS) & (df.SEX == "_T")]
    wide = df.set_index(
        ["REF_AREA", "EDUCATION_FIELD", "TIME_PERIOD", "MOBILITY"]
    ).OBS_VALUE.unstack("MOBILITY")
    out = pd.DataFrame({"enrolled": wide["_T"], "mobile": wide["MOB"]})
    # The OECD leaves cells empty when a country does not report them (status K or O).
    out = out.dropna().query("enrolled > 0").reset_index()
    out = out.rename(columns={"REF_AREA": "country", "TIME_PERIOD": "year"})
    out["field"] = out.pop("EDUCATION_FIELD").map(OECD_FIELDS)
    out["mobile_share"] = out.mobile / out.enrolled
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    mobility = doctoral_mobility()
    mobility.to_csv(DOCTORAL_MOBILITY, index=False)
    latest = mobility[mobility.year == mobility.year.max()]
    log.info(
        latest.pivot(index="country", columns="field", values="mobile_share")
        .sort_values("ICT", ascending=False)
        .round(3)
        .to_string()
    )
    df = funnel()
    df.to_csv(FUNNEL, index=False)
    latest = df[df.year == df[df.stage == "PhD"].year.max()]
    log.info(
        latest.pivot(index="institution", columns="stage", values="swiss_share")
        .round(3)
        .to_string()
    )


if __name__ == "__main__":
    main()

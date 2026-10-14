"""Comparison countries, their populations (World Bank) and researcher counts (OECD MSTI)."""

from functools import cache

import httpx
import pandas as pd

from swiss_ai.paths import CACHE

# ISO2 -> (ISO3, name). Small research-intensive peers first, then the large anchors.
COUNTRIES = {
    "CH": ("CHE", "Switzerland"),
    "IL": ("ISR", "Israel"),
    "SG": ("SGP", "Singapore"),
    "NL": ("NLD", "Netherlands"),
    "DK": ("DNK", "Denmark"),
    "SE": ("SWE", "Sweden"),
    "AT": ("AUT", "Austria"),
    "FI": ("FIN", "Finland"),
    "US": ("USA", "United States"),
    "GB": ("GBR", "United Kingdom"),
    "CN": ("CHN", "China"),
    "DE": ("DEU", "Germany"),
}
# Further places that only appear in the per-capita comparison: Hong Kong is the one place
# with over a million residents besides Singapore that produces more papers per resident than
# Switzerland; South Korea and Canada are large research systems readers expect to see.
PER_CAPITA_EXTRA = {
    "HK": ("HKG", "Hong Kong"),
    "KR": ("KOR", "South Korea"),
    "CA": ("CAN", "Canada"),
}
ALL_PLACES = COUNTRIES | PER_CAPITA_EXTRA
ISO3 = [iso3 for iso3, _ in COUNTRIES.values()]
ALL_ISO3 = [iso3 for iso3, _ in ALL_PLACES.values()]
POPULATION_YEAR = 2024
POPULATION_CACHE = CACHE / f"worldbank_population_{POPULATION_YEAR}.csv"
WORLD_BANK = "https://api.worldbank.org/v2/country/{codes}/indicator/SP.POP.TOTL"


@cache
def population() -> pd.Series:
    """Total population per ISO2 code in POPULATION_YEAR (World Bank SP.POP.TOTL).

    The cache is refetched when it lacks any place in ALL_PLACES.
    """
    if POPULATION_CACHE.exists():
        cached = pd.read_csv(POPULATION_CACHE, keep_default_na=False)
        if set(ALL_PLACES) <= set(cached.country):
            return cached.set_index("country").population
    url = WORLD_BANK.format(codes=";".join(ALL_ISO3))
    params = {"format": "json", "date": POPULATION_YEAR, "per_page": 100}
    _, rows = httpx.get(url, params=params, timeout=60).raise_for_status().json()
    df = pd.DataFrame(
        {
            "country": [r["country"]["id"] for r in rows],
            "population": [r["value"] for r in rows],
        }
    )
    POPULATION_CACHE.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(POPULATION_CACHE, index=False)
    return df.set_index("country").population


MSTI = (
    "https://sdmx.oecd.org/public/rest/data/OECD.STI.STP,DSD_MSTI@DF_MSTI,1.3/"
    "{codes}.A.T_RS.FTE.."
)
MSTI_FIRST_YEAR = 2018
RESEARCHERS_CACHE = CACHE / "oecd_msti_researchers.csv"


@cache
def researchers() -> pd.DataFrame:
    """Latest total researchers (full-time equivalents) per ISO2 code from OECD MSTI.

    MSTI has no total for Israel, the UK (none since 2018) or Hong Kong, so they are missing.

    Returns:
        One row per place with `researchers_fte` and the `researchers_year` it refers to.
    """
    if not RESEARCHERS_CACHE.exists():
        url = MSTI.format(codes="+".join(ALL_ISO3))
        params = {
            "startPeriod": MSTI_FIRST_YEAR,
            "dimensionAtObservation": "AllDimensions",
            "format": "csvfilewithlabels",
        }
        response = httpx.get(url, params=params, timeout=120).raise_for_status()
        RESEARCHERS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        RESEARCHERS_CACHE.write_text(response.text)
    df = pd.read_csv(RESEARCHERS_CACHE, keep_default_na=False)
    df = df[(df.TRANSFORMATION == "_Z") & (df.OBS_VALUE != "")]
    latest = df.sort_values("TIME_PERIOD").groupby("REF_AREA").tail(1)
    iso2 = {iso3: code for code, (iso3, _) in ALL_PLACES.items()}
    return pd.DataFrame(
        {
            "researchers_fte": latest.OBS_VALUE.astype(float).to_numpy(),
            "researchers_year": latest.TIME_PERIOD.astype(int).to_numpy(),
        },
        index=latest.REF_AREA.map(iso2).rename("country"),
    )

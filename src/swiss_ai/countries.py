"""Comparison countries and their populations from the World Bank."""

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

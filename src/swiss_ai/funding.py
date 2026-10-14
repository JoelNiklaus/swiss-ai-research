"""Research funding: ERC grants by host country (CORDIS) and SNSF computer science grants.

CORDIS lists every ERC grant under Horizon 2020 (calls 2014 to 2020) and Horizon Europe (calls
from 2021) with the host institution and euroSciVoc subject tags, but not the ERC panel. Computer
science is therefore approximated by the euroSciVoc branch "computer and information sciences".
Swiss-hosted grants that SERI funded directly during the 2021 to 2024 exclusion are not ERC grants
and do not appear in CORDIS.
"""

import json
import logging
import re
import zipfile
from pathlib import Path

import httpx
import pandas as pd
from joblib import Parallel, delayed
from tqdm import tqdm

from swiss_ai.countries import COUNTRIES, population
from swiss_ai.paths import CACHE, DATA

log = logging.getLogger(__name__)

CORDIS = CACHE / "cordis"
CORDIS_URL = "https://cordis.europa.eu/data/cordis-{programme}projects-json.zip"
PROGRAMMES = ("h2020", "HORIZON")
ERC_RAW = CORDIS / "erc_grants.csv"
ERC_BY_COUNTRY = DATA / "erc_by_country.csv"
# Starting, Consolidator, Advanced and Synergy Grants; Proof of Concept grants are top-ups.
# CORDIS spells the scheme inconsistently (ERC-2014-CoG, ERC-2016-COG, ERC-2022-SYG).
ERC_CALL = re.compile(r"^ERC-(\d{4})-(STG|COG|ADG|SYG)$", re.IGNORECASE)
SCHEMES = {"STG": "STG", "COG": "COG", "ADG": "ADG", "SYG": "SyG"}
CS_BRANCH = "/computer and information sciences/"
# CORDIS uses EU country codes, which differ from ISO2 for the UK and Greece.
EU_TO_ISO2 = {"UK": "GB", "EL": "GR"}
SNSF_URL = "https://data.snf.ch/datasets/grants.csv"
SNSF_GRANTS = CACHE / "snsf" / "grants.csv"
SNSF_CS = DATA / "snsf_computer_science.csv"
ERC_REPLACEMENT = re.compile(r"SNSF (Starting|Consolidator|Advanced) Grants")


def parse_project(path: Path) -> dict[str, str | int | bool] | None:
    """Extract call, host country and subject flags from one CORDIS project file.

    Returns:
        A grant record, or None if the project is not a main ERC grant.
    """
    project = json.loads(path.read_text())
    associations = project["relations"]["associations"]
    calls = [
        a["identifier"]
        for a in associations
        if a["contenttype"] == "call" and a["attributes"]["type"] == "relatedMasterCall"
    ]
    match = next((m for c in calls if (m := ERC_CALL.match(c))), None)
    if match is None:
        return None
    # The coordinator is the host institution; Synergy Grants can have further hosts.
    (host,) = [
        a
        for a in associations
        if a["contenttype"] == "organization"
        and a["attributes"]["type"] == "coordinator"
    ]
    country = host["address"]["country"]
    subjects = [
        c["displayCode"]
        for c in project["relations"]["categories"]
        if c["attributes"]["classification"] == "euroSciVoc"
    ]
    return {
        "id": project["id"],
        "call_year": int(match[1]),
        "scheme": SCHEMES[match[2].upper()],
        "host": host["legalName"],
        "country": EU_TO_ISO2[country] if country in EU_TO_ISO2 else country,
        "computer_science": any(CS_BRANCH in s for s in subjects),
        "ai": any("/artificial intelligence" in s for s in subjects),
        "ec_contribution": float(project["ecMaxContribution"]),
    }


def download_cordis(programme: str) -> None:
    """Download and unpack the CORDIS JSON project export of one framework programme (~1 GB)."""
    archive = CORDIS / f"{programme}.zip"
    with httpx.stream(
        "GET",
        CORDIS_URL.format(programme=programme),
        timeout=600,
        follow_redirects=True,
    ) as r:
        r.raise_for_status()
        with archive.open("wb") as f:
            for chunk in r.iter_bytes():
                f.write(chunk)
    with zipfile.ZipFile(archive) as z:
        z.extractall(CORDIS / programme)
    archive.unlink()


def erc_grants() -> pd.DataFrame:
    """All main ERC grants from Horizon 2020 and Horizon Europe, cached as one CSV."""
    if not ERC_RAW.exists():
        CORDIS.mkdir(parents=True, exist_ok=True)
        for programme in PROGRAMMES:
            if not (CORDIS / programme).exists():
                download_cordis(programme)
        paths = [
            p
            for prog in PROGRAMMES
            for p in sorted((CORDIS / prog).glob("project-rcn-*.json"))
        ]
        records = Parallel(n_jobs=-1, batch_size=256)(
            delayed(parse_project)(p) for p in tqdm(paths, desc="CORDIS projects")
        )
        pd.DataFrame([r for r in records if r is not None]).to_csv(ERC_RAW, index=False)
    return pd.read_csv(ERC_RAW, keep_default_na=False)


def by_country(grants: pd.DataFrame) -> pd.DataFrame:
    """Grant counts per comparison country and call year, overall and in computer science.

    Returns:
        One row per country and call year with grants, cs_grants, ai_grants and their counts
        per million residents.
    """
    peers = grants[grants.country.isin(COUNTRIES)]
    out = peers.groupby(["country", "call_year"]).agg(
        grants=("id", "size"),
        cs_grants=("computer_science", "sum"),
        ai_grants=("ai", "sum"),
    )
    # Countries with zero grants in a call year (Switzerland 2021 to 2024) need explicit rows.
    full = pd.MultiIndex.from_product(
        [sorted(peers.country.unique()), sorted(grants.call_year.unique())],
        names=out.index.names,
    )
    out = out.reindex(full, fill_value=0).reset_index()
    millions = out.country.map(population()) / 1e6
    for col in ["grants", "cs_grants", "ai_grants"]:
        out[f"{col}_per_million"] = out[col] / millions
    return out


def snsf_computer_science() -> pd.DataFrame:
    """SNSF grants in the discipline "Information Technology" per decision year.

    Returns:
        One row per decision year with grants, CHF granted, and the number of SNSF Starting,
        Consolidator and Advanced Grants, the replacement schemes for the ERC calls Swiss hosts
        could not apply to.
    """
    if not SNSF_GRANTS.exists():
        SNSF_GRANTS.parent.mkdir(parents=True, exist_ok=True)
        SNSF_GRANTS.write_bytes(
            httpx.get(SNSF_URL, timeout=300).raise_for_status().content
        )
    grants = pd.read_csv(
        SNSF_GRANTS, sep=";", encoding="utf-8-sig", dtype={"CallDecisionYear": "Int64"}
    )
    cs = grants[grants.MainDiscipline == "Information Technology"]
    cs = cs.assign(
        erc_replacement=cs.FundingInstrumentPublished.str.match(ERC_REPLACEMENT)
    )
    return (
        cs.groupby("CallDecisionYear")
        .agg(
            grants=("GrantNumber", "size"),
            chf=("AmountGrantedAllSets", "sum"),
            erc_replacement=("erc_replacement", "sum"),
        )
        .rename_axis("year")
        .reset_index()
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    snsf = snsf_computer_science()
    snsf.to_csv(SNSF_CS, index=False)
    log.info("SNSF computer science grants:\n%s", snsf.tail(12).to_string(index=False))
    df = by_country(erc_grants())
    df.to_csv(ERC_BY_COUNTRY, index=False)
    log.info(
        df.pivot(index="call_year", columns="country", values="grants").to_string()
    )
    h2020 = df[df.call_year <= 2020].groupby("country")[["grants", "cs_grants"]].sum()
    h2020 = h2020.assign(
        **{
            f"{c}_per_million": h2020[c] / population()[h2020.index] * 1e6
            for c in h2020
        }
    )
    log.info(
        "Horizon 2020 calls (2014-2020):\n%s",
        h2020.sort_values("grants_per_million").round(1).to_string(),
    )


if __name__ == "__main__":
    main()

"""Client for the Swiss Federal Statistical Office (BFS) PxWeb API with an on-disk cache."""

import hashlib
import itertools
import json
import logging
from functools import cache

import httpx
import pandas as pd

from swiss_ai.paths import CACHE

API = "https://www.pxweb.bfs.admin.ch/api/v1/de/{table}/{table}.px"
BFS_CACHE = CACHE / "bfs"
ALL = ["*"]

logging.getLogger("httpx").setLevel(logging.WARNING)


@cache
def metadata(table: str) -> dict[str, dict[str, str]]:
    """Map each variable of a PxWeb table to {label: code}, since queries take codes."""
    variables = httpx.get(API.format(table=table), timeout=60).raise_for_status().json()
    return {
        v["code"]: dict(zip(v["valueTexts"], v["values"], strict=True))
        for v in variables["variables"]
    }


def fetch(table: str, selection: dict[str, list[str]]) -> pd.DataFrame:
    """Download a slice of a PxWeb table as a long DataFrame.

    Variables missing from `selection` are summed over by the API (PxWeb elimination).

    Args:
        table: BFS table id, for example 'px-x-1502040100_107'.
        selection: Variable code to the value labels to keep, for example
            {'Studienstufe': ['Bachelor', 'Master']}, or ALL to keep every value.

    Returns:
        One row per cell with one column per selected variable and a `value` column.
    """
    meta = metadata(table)
    query = {
        "query": [
            {
                "code": var,
                "selection": {"filter": "all", "values": ALL}
                if labels == ALL
                else {
                    "filter": "item",
                    "values": [meta[var][label] for label in labels],
                },
            }
            for var, labels in selection.items()
        ],
        "response": {"format": "json-stat2"},
    }
    body = json.dumps(query, sort_keys=True)
    path = BFS_CACHE / f"{table}_{hashlib.sha1(body.encode()).hexdigest()[:12]}.json"
    if not path.exists():
        response = httpx.post(API.format(table=table), content=body, timeout=120)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(response.raise_for_status().text)
    return parse_jsonstat(json.loads(path.read_text()))


def parse_jsonstat(data: dict) -> pd.DataFrame:
    """Flatten a JSON-stat 2.0 dataset; values are stored row-major over `id`."""
    labels = []
    for dim in data["id"]:
        category = data["dimension"][dim]["category"]
        order = sorted(category["index"], key=category["index"].__getitem__)
        labels.append([category["label"][code] for code in order])
    rows = itertools.product(*labels)
    df = pd.DataFrame(list(rows), columns=data["id"])
    df["value"] = pd.array(data["value"], dtype="Int64").fillna(0)
    return df

import json
from pathlib import Path

import httpx
import pytest

from swiss_ai import bfs

JSONSTAT = {
    "id": ["Jahr", "Staatsangehörigkeit (Kategorie)"],
    "dimension": {
        "Jahr": {
            "category": {"index": {"1": 1, "0": 0}, "label": {"0": "2010", "1": "2011"}}
        },
        "Staatsangehörigkeit (Kategorie)": {
            "category": {
                "index": {"a": 0, "b": 1},
                "label": {"a": "Schweiz", "b": "Ausland"},
            }
        },
    },
    "value": [10, 5, None, 7],
}


def test_parse_jsonstat_orders_by_index_and_fills_missing() -> None:
    df = bfs.parse_jsonstat(JSONSTAT)
    assert df.Jahr.tolist() == ["2010", "2010", "2011", "2011"]
    assert df["Staatsangehörigkeit (Kategorie)"].tolist() == ["Schweiz", "Ausland"] * 2
    assert df.value.tolist() == [10, 5, 0, 7]


def test_fetch_translates_labels_and_caches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bfs, "BFS_CACHE", tmp_path)
    monkeypatch.setattr(
        bfs, "metadata", lambda table: {"Jahr": {"2010": "0", "2011": "1"}}
    )
    bodies = []

    def post(url: str, content: str, timeout: int) -> httpx.Response:
        bodies.append(json.loads(content))
        return httpx.Response(
            200, text=json.dumps(JSONSTAT), request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(bfs.httpx, "post", post)
    selection = {"Jahr": ["2011"], "Staatsangehörigkeit (Kategorie)": bfs.ALL}
    first = bfs.fetch("px-test", selection)
    second = bfs.fetch("px-test", selection)
    assert len(bodies) == 1
    query = bodies[0]["query"]
    assert query[0]["selection"] == {"filter": "item", "values": ["1"]}
    assert query[1]["selection"] == {"filter": "all", "values": ["*"]}
    assert first.equals(second)


def test_metadata_maps_labels_to_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "variables": [
            {"code": "Jahr", "valueTexts": ["2010", "2011"], "values": ["0", "1"]}
        ]
    }

    def get(url: str, timeout: int) -> httpx.Response:
        return httpx.Response(200, json=payload, request=httpx.Request("GET", url))

    monkeypatch.setattr(bfs.httpx, "get", get)
    bfs.metadata.cache_clear()
    assert bfs.metadata("px-meta") == {"Jahr": {"2010": "0", "2011": "1"}}
    bfs.metadata.cache_clear()

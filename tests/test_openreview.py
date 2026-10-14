from pathlib import Path

import httpx
import pandas as pd
import pytest

from swiss_ai import openreview


@pytest.mark.parametrize(
    ("institution", "country"),
    [
        ({"name": "ETH", "domain": "ethz.ch", "country": "CH"}, "CH"),
        ({"name": "ETH", "domain": "ethz.ch"}, "CH"),
        ({"name": "Oxford", "domain": "ox.ac.uk", "country": ""}, "GB"),
        ({"name": "MIT", "domain": "mit.edu"}, "US"),
        ({"name": "Google", "domain": "google.com"}, ""),
        ({"name": "Startup", "domain": "startup.ai"}, ""),
        ({"name": "Unknown"}, ""),
    ],
)
def test_institution_country(institution: dict, country: str) -> None:
    assert openreview.institution_country(institution) == country


def test_countries_in_year_respects_open_and_string_years() -> None:
    history = [
        {"start": 2015, "end": 2019, "institution": {"domain": "ethz.ch"}},
        {"start": "2019", "end": None, "institution": {"country": "US"}},
        {"start": "", "end": "", "institution": {"country": "DE"}},
        {"start": 2020},
    ]
    assert openreview.countries_in_year(history, 2017) == {"CH", "DE"}
    assert openreview.countries_in_year(history, 2024) == {"US", "DE"}


def note(
    note_id: str, venue: str, original: str | None = None, v2: bool = False
) -> dict:
    content = {"title": "T", "authors": ["A"], "authorids": ["~A1"], "venue": venue}
    if v2:
        content = {k: {"value": v} for k, v in content.items()}
    return {"id": note_id, "forum": note_id, "original": original, "content": content}


def test_accepted_notes_dedupes_and_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    notes = [
        note("a", "NeurIPS 2021 Poster", original="o1"),
        note("b", "NeurIPS 2021 Poster", original="o1"),
        note("c", "NeurIPS 2021 Submitted"),
        note("d", "Submitted to ICLR 2023"),
        note("e", "ICLR 2024 oral", v2=True),
    ]
    monkeypatch.setattr(openreview, "get", lambda base, path, params: {"notes": notes})
    assert [n["id"] for n in openreview.accepted_notes("base", "venue")] == ["b", "e"]


def test_accepted_notes_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openreview, "PAGE", 2)
    pages = {
        0: [note("a", "X Poster"), note("b", "X Poster")],
        2: [note("c", "X Poster")],
    }
    monkeypatch.setattr(
        openreview, "get", lambda base, path, params: {"notes": pages[params["offset"]]}
    )
    assert len(openreview.accepted_notes("base", "venue")) == 3


def test_papers_flattens_v1_and_v2(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openreview, "VENUES", {("ICLR", 2024): ("b", "v")})
    monkeypatch.setattr(
        openreview,
        "accepted_notes",
        lambda base, venue_id: [note("x", "ICLR 2024 oral", v2=True)],
    )
    df = openreview.papers()
    assert df.to_dict("records") == [
        {
            "forum": "x",
            "venue": "ICLR",
            "year": 2024,
            "title": "T",
            "authors": "A",
            "authorids": "~A1",
        }
    ]


def test_profiles_registers_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = {
        "id": "~Jane_Doe1",
        "content": {
            "names": [{"username": "~Jane_Doe2"}, {"fullname": "J"}],
            "history": [{"start": 2020}],
        },
    }
    empty = {"id": "~No_History1", "content": {"names": []}}
    monkeypatch.setattr(
        openreview, "get", lambda base, path, params: {"profiles": [profile, empty]}
    )
    history = openreview.profiles(["~Jane_Doe2", "~No_History1"])
    assert history["~Jane_Doe1"] == history["~Jane_Doe2"] == [{"start": 2020}]
    assert history["~No_History1"] == []


def test_authorships_positions_and_countries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openreview,
        "profiles",
        lambda ids: {"~A1": [{"start": 2020, "institution": {"country": "CH"}}]},
    )
    papers = pd.DataFrame(
        {
            "forum": ["f"],
            "venue": ["ICLR"],
            "year": [2024],
            "authorids": ["~A1; jane@x.org; ~B1"],
        }
    )
    df = openreview.authorships(papers)
    assert df.position.tolist() == [0, 1, 2]
    assert df.n_authors.tolist() == [3, 3, 3]
    assert df.countries.tolist() == ["CH", "", ""]


def test_get_caches_with_login(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openreview, "OR_CACHE", tmp_path)
    monkeypatch.setattr(openreview, "headers", lambda: {"Authorization": "Bearer t"})
    calls = []

    def get(url: str, params: dict, headers: dict, timeout: int) -> httpx.Response:
        calls.append(url)
        return httpx.Response(
            200, json={"notes": []}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(openreview.httpx, "get", get)
    assert openreview.get("https://api", "/notes", {"limit": 1}) == {"notes": []}
    assert openreview.get("https://api", "/notes", {"limit": 1}) == {"notes": []}
    assert calls == ["https://api/notes"]


def test_headers_logs_in_with_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENREVIEW_USERNAME", "user")
    monkeypatch.setenv("OPENREVIEW_PASSWORD", "pw")
    sent = []

    def post(url: str, json: dict, timeout: int) -> httpx.Response:
        sent.append(json)
        return httpx.Response(
            200, json={"token": "tok"}, request=httpx.Request("POST", url)
        )

    monkeypatch.setattr(openreview.httpx, "post", post)
    openreview.headers.cache_clear()
    assert openreview.headers() == {"Authorization": "Bearer tok"}
    assert sent == [{"id": "user", "password": "pw"}]
    openreview.headers.cache_clear()

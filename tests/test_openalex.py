from pathlib import Path

import httpx
import pandas as pd
import pytest

from swiss_ai import openalex


def authorship(
    countries: list[str],
    affiliations: list[tuple[str, list[str]]],
    institutions: dict[str, str],
) -> dict:
    return {
        "author": {"id": "https://openalex.org/A1", "display_name": "Jane Doe"},
        "countries": countries,
        "institutions": [
            {"id": i, "display_name": i, "country_code": c}
            for i, c in institutions.items()
        ],
        "affiliations": [
            {"raw_affiliation_string": s, "institution_ids": ids}
            for s, ids in affiliations
        ],
        "raw_affiliation_strings": [s for s, _ in affiliations],
    }


def work(year: int, countries: list[list[str]]) -> dict:
    return {
        "id": f"https://openalex.org/W{year}",
        "publication_year": year,
        "title": "T",
        "authorships": [authorship(c, [], {}) for c in countries],
    }


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Multi³Hate: Hate–Speech", "multi3hate hate speech"),
        ("Nyström's Method", "nystrom s method"),
        ("It’s Not Just Size", "it s not just size"),
        ("  ", ""),
    ],
)
def test_normalize_title(title: str, expected: str) -> None:
    assert openalex.normalize_title(title) == expected


def test_best_version_prefers_country_coverage_within_a_year() -> None:
    preprint = work(2023, [[], []])
    proceedings = work(2024, [["CH"], ["US"]])
    far = work(2019, [["CH"], ["US"], ["DE"]])
    assert openalex.best_version([preprint, proceedings, far], 2024) is proceedings
    assert openalex.best_version([far], 2024) is None


def test_authorship_countries_swiss_override() -> None:
    a = authorship(
        ["US"],
        [
            ("Google Research, Zürich, Switzerland", ["I1"]),
            ("Stanford University", ["I2"]),
        ],
        {"I1": "US", "I2": "US"},
    )
    assert openalex.authorship_countries(a) == {"CH", "US"}


def test_authorship_countries_without_affiliations_uses_work_countries() -> None:
    assert openalex.authorship_countries(authorship(["DE"], [], {})) == {"DE"}


def test_authorship_countries_skips_institutions_without_country() -> None:
    a = authorship([], [("Somewhere", ["I1"])], {"I1": None})
    assert openalex.authorship_countries(a) == set()


def test_authorship_rows_flag_override() -> None:
    w = work(2024, [])
    w["authorships"] = [
        authorship(["US"], [("ETH Zurich", ["I1"])], {"I1": "US"}),
        authorship([], [], {}),
    ]
    rows = openalex.authorship_rows("conf/x", w)
    assert rows[0]["countries"] == "CH"
    assert rows[0]["swiss_override"]
    assert rows[1]["country_source"] == ""
    assert rows[1]["n_authors"] == 2


def test_profile_countries_falls_back_one_year() -> None:
    profile = {2023: {"CH"}}
    assert openalex.profile_countries(profile, 2024) == {"CH"}
    assert openalex.profile_countries(profile, 2026) == set()


def test_fill_from_author_profiles(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openalex, "author_countries_by_year", lambda ids: {"A1": {2024: {"CH"}}}
    )
    df = pd.DataFrame(
        {
            "key": ["p", "p", "p"],
            "author_id": ["A1", "A2", ""],
            "countries": ["", "", ""],
            "country_source": ["", "", ""],
        }
    )
    out = openalex.fill_from_author_profiles(df, pd.Series({"p": 2024}))
    assert out.countries.tolist() == ["CH", "", ""]
    assert out.country_source.tolist() == ["author_profile", "", ""]


def test_author_countries_by_year(monkeypatch: pytest.MonkeyPatch) -> None:
    author = {
        "id": "https://openalex.org/A1",
        "affiliations": [
            {"institution": {"country_code": "CH"}, "years": [2023, 2024]},
            {"institution": {"country_code": None}, "years": [2024]},
        ],
    }
    monkeypatch.setattr(openalex, "get_all", lambda entity, filter_, select: [author])
    assert openalex.author_countries_by_year(["A1"]) == {
        "A1": {2023: {"CH"}, 2024: {"CH"}}
    }


def test_search_batch_keeps_exact_titles(monkeypatch: pytest.MonkeyPatch) -> None:
    results = [
        {"title": "Deep Sets"},
        {"title": "Deep Sets for Graphs"},
        {"title": None},
    ]
    monkeypatch.setattr(openalex, "get_all", lambda *args, **kwargs: results)
    assert openalex.search_batch(["deep sets"]) == [{"title": "Deep Sets"}]


def test_search_titles_isolates_short_titles(monkeypatch: pytest.MonkeyPatch) -> None:
    batches = []

    def search_batch(batch: list[str]) -> list[dict]:
        batches.append(batch)
        return [{"title": t} for t in batch]

    monkeypatch.setattr(openalex, "search_batch", search_batch)
    found = openalex.search_titles(
        ["Deep Sets", "A Much Longer Paper Title", "Another Long Paper Title Here"]
    )
    assert sorted(map(len, batches)) == [1, 2]
    assert set(found) == {
        "deep sets",
        "a much longer paper title",
        "another long paper title here",
    }


def test_match_uses_doi_then_title(monkeypatch: pytest.MonkeyPatch) -> None:
    by_doi = work(2024, [["CH"]])
    by_title = work(2024, [["US"]])
    monkeypatch.setattr(openalex, "lookup_dois", lambda dois: {"10.1/a": by_doi})
    monkeypatch.setattr(
        openalex, "search_titles", lambda titles: {"title b": [by_title]}
    )
    papers = pd.DataFrame(
        {
            "key": ["a", "b", "c"],
            "doi": ["10.1/a", "", ""],
            "title": ["Title A", "Title B", "Title C"],
            "year": [2024] * 3,
        }
    )
    assert openalex.match(papers) == {"a": by_doi, "b": by_title}


def response(
    status: int, payload: dict, headers: dict[str, str] | None = None
) -> httpx.Response:
    return httpx.Response(
        status, json=payload, headers=headers, request=httpx.Request("GET", "https://x")
    )


def test_get_caches_retries_and_raises_on_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(openalex, "OA_CACHE", tmp_path)
    monkeypatch.setattr(openalex, "api_key", lambda: "key")
    monkeypatch.setattr(openalex.time, "sleep", lambda s: None)
    replies = [
        response(504, {}),
        response(200, {"results": [1], "meta": {"next_cursor": None}}),
    ]
    monkeypatch.setattr(openalex.httpx, "get", lambda *a, **k: replies.pop(0))
    assert openalex.get("works", {"filter": "x"})["results"] == [1]
    assert openalex.get("works", {"filter": "x"})["results"] == [1]

    monkeypatch.setattr(
        openalex.httpx,
        "get",
        lambda *a, **k: response(429, {}, {"x-ratelimit-reset": "60"}),
    )
    with pytest.raises(openalex.OpenAlexBudgetError, match="60s"):
        openalex.get("works", {"filter": "y"})


def test_get_all_pages_until_short_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openalex, "PER_PAGE", 2)
    pages = {"*": ([1, 2], "c1"), "c1": ([3], "c2")}
    calls = []

    def get(entity: str, params: dict) -> dict:
        calls.append(params["cursor"])
        results, cursor = pages[params["cursor"]]
        return {"results": results, "meta": {"next_cursor": cursor}}

    monkeypatch.setattr(openalex, "get", get)
    assert openalex.get_all("works", "f", "id") == [1, 2, 3]
    assert calls == ["*", "c1"]
    calls.clear()
    assert openalex.get_all("works", "f", "id", max_pages=1) == [1, 2]
    assert calls == ["*"]


def test_lookup_dois_strips_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        openalex, "get_all", lambda *a: [{"doi": "https://doi.org/10.1/ABC"}]
    )
    assert openalex.lookup_dois(["10.1/abc"]) == {
        "10.1/abc": {"doi": "https://doi.org/10.1/ABC"}
    }

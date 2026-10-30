from pathlib import Path

import pandas as pd
import pytest

from swiss_ai import anthology, attribution

XML = """<?xml version='1.0' encoding='UTF-8'?>
<collection id="2026.emnlp">
  <volume id="main" ingest-date="2026-10-24" type="proceedings">
    <meta><booktitle>Proceedings of EMNLP 2026</booktitle></meta>
    <frontmatter><url>2026.emnlp-main.0</url></frontmatter>
    <paper id="1">
      <title><fixed-case>P</fixed-case>op Resume: A Study</title>
      <author id="ann-a" orcid="0000-0000-0000-0001"><first>Ann</first><last>A</last><affiliation>ETH Zurich</affiliation></author>
      <author id="bob-b"><first>Bob</first><last>B</last></author>
      <doi>10.18653/v1/2026.emnlp-main.1</doi>
    </paper>
    <paper id="2">
      <title>Second Paper</title>
      <author id="bob-b"><first>Bob</first><last>B</last><affiliation>Google</affiliation></author>
      <author id="cy-c" orcid="0000-0000-0000-0003"><first>Cy</first><last>C</last></author>
    </paper>
  </volume>
  <volume id="demos" type="proceedings">
    <meta><booktitle>Demos</booktitle></meta>
    <paper id="1"><title>A Demo</title><author><first>D</first><last>D</last></author></paper>
  </volume>
</collection>
"""


def test_parse_volume_reads_main_papers_and_authorships() -> None:
    papers, authors = anthology.parse_volume(XML, "main", "EMNLP", 2026)
    assert papers.key.tolist() == ["2026.emnlp-main.1", "2026.emnlp-main.2"]
    assert papers.title.tolist() == ["Pop Resume: A Study", "Second Paper"]
    assert papers.authors.tolist() == ["Ann A; Bob B", "Bob B; Cy C"]
    assert papers.doi.tolist() == ["10.18653/v1/2026.emnlp-main.1", ""]
    assert (papers.venue == "EMNLP").all() and (papers.year == 2026).all()
    first = authors[authors.key == "2026.emnlp-main.1"]
    assert first.position.tolist() == [0, 1]
    assert first.n_authors.tolist() == [2, 2]
    assert first.author_id.tolist() == ["ann-a", "bob-b"]
    assert first.orcid.tolist() == ["0000-0000-0000-0001", ""]
    assert first.affiliation.tolist() == ["ETH Zurich", ""]


@pytest.mark.parametrize(
    ("affiliation", "expected"),
    [
        # Every part names a known organisation, so each contributes its country.
        ("ETHZ - ETH Zurich and McGill University", {"CH", "CA"}),
        # A split that leaves an unknown part falls back to the full string.
        ("University of Science and Technology of China", {"CN"}),
        # A Swiss city in a part overrides a US headquarters match, as for OpenAlex.
        ("Google, Zurich", {"CH"}),
        ("Google", {"US"}),
        ("Unknown Lab", set()),
        ("", set()),
    ],
)
def test_affiliation_countries(affiliation: str, expected: set[str]) -> None:
    known = {
        "ETHZ - ETH Zurich": "CH",
        "McGill University": "CA",
        "University of Science and Technology of China": "CN",
        "Google": "US",
        "Google, Zurich": "US",
    }
    assert anthology.affiliation_countries(affiliation, known.get) == expected


def ror_item(names: list[str], country: str) -> dict:
    """An organisation in the shape of the ROR v2 API; the first name is the display name."""
    return {
        "names": [
            {"value": n, "types": ["ror_display"] if i == 0 else ["alias"]}
            for i, n in enumerate(names)
        ],
        "locations": [{"geonames_details": {"country_code": country}}],
    }


@pytest.mark.parametrize(
    ("name", "items", "expected"),
    [
        # An acronym that equals one organisation's alias.
        (
            "EPFL",
            [ror_item(["École Polytechnique Fédérale de Lausanne", "EPFL"], "CH")],
            "CH",
        ),
        # Country suffixes in parentheses do not count as part of the name.
        ("Tencent", [ror_item(["Tencent (China)"], "CN")], "CN"),
        # Two organisations with exactly this name in different countries: ambiguous.
        (
            "Northeastern University",
            [
                ror_item(["Northeastern University"], "CN"),
                ror_item(["Northeastern University"], "US"),
            ],
            None,
        ),
        (
            "Amazon",
            [
                ror_item(["Amazon (Germany)"], "DE"),
                ror_item(["Amazon (United States)"], "US"),
            ],
            None,
        ),
        # Results that only contain the query as a word are not matches.
        ("Independent", [ror_item(["Independent Age"], "GB")], None),
    ],
)
def test_unanimous_exact_country(
    name: str, items: list[dict], expected: str | None
) -> None:
    assert anthology.unanimous_exact_country(name, items) == expected


def test_ror_query_text_drops_search_syntax() -> None:
    # ROR's search endpoint parses Lucene syntax; "/" or "*" in a name is a query error.
    assert anthology.ror_query_text("NBD/Biblion (A*STAR)") == "NBD Biblion A STAR"


def test_fill_countries_from_same_author_then_orcid_profile() -> None:
    authors = pd.DataFrame(
        {
            "key": ["k1", "k1", "k2", "k2", "k3"],
            "year": [2026] * 5,
            "author_id": ["ann", "bob", "bob", "cy", "dee"],
            "orcid": ["", "", "", "0000-3", "0000-4"],
            "countries": ["CH", "", "US", "", ""],
            "country_source": ["affiliation", "", "affiliation", "", ""],
        }
    )
    profiles = {"0000-3": {2025: {"DE"}}, "0000-4": {2019: {"FR"}}}
    out = anthology.fill_countries(authors, profiles).set_index(["key", "author_id"])
    assert out.loc[("k1", "bob"), "countries"] == "US"
    assert out.loc[("k1", "bob"), "country_source"] == "same_author"
    assert out.loc[("k2", "cy"), "countries"] == "DE"
    assert out.loc[("k2", "cy"), "country_source"] == "orcid_profile"
    # A profile entry far from the paper year does not count.
    assert out.loc[("k3", "dee"), "countries"] == ""


@pytest.fixture
def sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    pd.DataFrame(
        {
            "key": ["conf/acl/X24", "conf/emnlp/Y26"],
            "venue": ["ACL", "EMNLP"],
            "year": [2024, 2026],
            "title": ["DBLP Paper", "Duplicate From DBLP"],
        }
    ).to_csv(tmp_path / "papers.csv", index=False)
    pd.DataFrame(
        columns=["forum", "venue", "year", "title"],
    ).to_csv(tmp_path / "or_papers.csv", index=False)
    pd.DataFrame(columns=["forum", "position", "countries"]).to_csv(
        tmp_path / "or_auth.csv", index=False
    )
    pd.DataFrame(
        {"key": ["conf/acl/X24"], "position": [0], "countries": ["CH"]}
    ).to_csv(tmp_path / "oa_auth.csv", index=False)
    pd.DataFrame(
        {
            "key": ["2026.emnlp-main.1"],
            "venue": ["EMNLP"],
            "year": [2026],
            "title": ["Anthology Paper"],
        }
    ).to_csv(tmp_path / "an_papers.csv", index=False)
    pd.DataFrame(
        {"key": ["2026.emnlp-main.1"], "position": [0], "countries": ["CH"]}
    ).to_csv(tmp_path / "an_auth.csv", index=False)
    monkeypatch.setattr(attribution, "PAPERS", tmp_path / "papers.csv")
    monkeypatch.setattr(attribution, "OPENREVIEW_PAPERS", tmp_path / "or_papers.csv")
    monkeypatch.setattr(attribution, "OPENREVIEW_AUTHORSHIPS", tmp_path / "or_auth.csv")
    monkeypatch.setattr(attribution, "OPENALEX_AUTHORSHIPS", tmp_path / "oa_auth.csv")
    monkeypatch.setattr(attribution, "ANTHOLOGY_PAPERS", tmp_path / "an_papers.csv")
    monkeypatch.setattr(attribution, "ANTHOLOGY_AUTHORSHIPS", tmp_path / "an_auth.csv")
    monkeypatch.setattr(attribution, "OPENREVIEW_VENUES", {})
    monkeypatch.setattr(attribution, "ANTHOLOGY_VENUES", {("EMNLP", 2026): "main"})
    return tmp_path


def test_load_papers_takes_anthology_venue_years_from_the_anthology(
    sources: Path,
) -> None:
    papers, authorships = attribution.load_papers()
    by_id = papers.set_index("paper_id")
    assert set(by_id.index) == {"conf/acl/X24", "anthology:2026.emnlp-main.1"}
    assert by_id.loc["anthology:2026.emnlp-main.1", "source"] == "anthology"
    assert by_id.loc["anthology:2026.emnlp-main.1", "title"] == "anthology paper"
    assert set(authorships.paper_id) == {"conf/acl/X24", "anthology:2026.emnlp-main.1"}

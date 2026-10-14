import gzip
from pathlib import Path

import pandas as pd
import pytest

from swiss_ai import papers

DTD = """<!ELEMENT dblp ANY>
<!ENTITY ouml "&#246;">
"""

DUMP = """<?xml version="1.0" encoding="ISO-8859-1"?>
<!DOCTYPE dblp SYSTEM "dblp.dtd">
<dblp>
<proceedings key="conf/acl/2024-1"><title>Proceedings of ACL 2024, Volume 1: Long Papers</title><year>2024</year></proceedings>
<inproceedings key="conf/acl/A24"><author>J&ouml;rg Muster</author><author>Jane Doe</author>
<title>A <i>Swiss</i> Paper.</title><year>2024</year><booktitle>ACL (1)</booktitle><pages>1-10</pages>
<ee>https://doi.org/10.18653/v1/2024.acl-long.1</ee><crossref>conf/acl/2024-1</crossref>
<url>db/conf/acl/acl2024-1.html#A24</url></inproceedings>
<inproceedings key="conf/acl/Old09"><author>Old Author</author><title>Too Old.</title><year>2009</year>
<booktitle>ACL</booktitle></inproceedings>
<inproceedings key="conf/other/X24"><author>Someone</author><title>Other Venue.</title><year>2024</year>
<booktitle>Other</booktitle></inproceedings>
<article key="journals/corr/abs-1"><author>Someone</author><title>Preprint.</title><year>2024</year></article>
</dblp>
"""


@pytest.fixture
def dump(tmp_path: Path) -> Path:
    path = tmp_path / "dblp.xml.gz"
    with gzip.open(path, "wt", encoding="iso-8859-1") as f:
        f.write(DUMP)
    (tmp_path / "dblp.dtd").write_text(DTD)
    return path


def test_extract_keeps_venue_papers_in_window(dump: Path) -> None:
    df = papers.extract(dump)
    assert df.key.tolist() == ["conf/acl/A24"]
    row = df.iloc[0]
    assert row.authors == "Jörg Muster; Jane Doe"
    assert row.title == "A Swiss Paper."
    assert row.volume == "Proceedings of ACL 2024, Volume 1: Long Papers"
    assert row.toc == "db/conf/acl/acl2024-1.html"


def test_load_raw_caches_extraction(
    dump: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(papers, "DBLP_DUMP", dump)
    monkeypatch.setattr(papers, "RAW_PAPERS", tmp_path / "raw.csv")
    assert len(papers.load_raw()) == 1
    assert (tmp_path / "raw.csv").exists()
    assert len(papers.load_raw()) == 1


@pytest.mark.parametrize(
    ("key", "venue"),
    [
        ("conf/nips/X20", "NeurIPS"),
        ("conf/acl/X20", "ACL"),
        ("journals/tacl/X20", None),
        ("conf/foo/X", None),
    ],
)
def test_venue_of(key: str, venue: str | None) -> None:
    assert papers.venue_of(key) == venue


@pytest.mark.parametrize(
    ("pages", "count"), [("1-10", 10), ("5", None), ("", None), ("e1-e5", None)]
)
def test_page_count(pages: str, count: int | None) -> None:
    assert papers.page_count(pages) == count


def record(**kwargs: str | int) -> dict[str, str | int]:
    base = {
        "venue": "ACL",
        "booktitle": "ACL (1)",
        "volume": "Volume 1: Long Papers",
        "ee": "",
        "pages": "1-10",
        "year": 2024,
        "title": "T",
        "authors": "A",
    }
    return base | kwargs


def row(**kwargs: str) -> pd.Series:
    return pd.Series(record(**kwargs))


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({}, True),
        ({"booktitle": "ACL (Findings)"}, False),
        ({"booktitle": "ACL (3)", "volume": "System Demonstrations"}, False),
        ({"booktitle": "ACL (Short Papers)"}, True),
        (
            {
                "venue": "NeurIPS",
                "booktitle": "NeurIPS",
                "ee": "https://x/Datasets_and_Benchmarks/1",
            },
            False,
        ),
        ({"venue": "AAAI", "booktitle": "AAAI", "pages": "1-2"}, False),
        ({"venue": "AAAI", "booktitle": "AAAI", "pages": "1-7"}, True),
        ({"venue": "AAAI", "booktitle": "AAAI", "pages": ""}, False),
        ({"booktitle": ">ACL"}, True),
    ],
)
def test_is_main_track(kwargs: dict[str, str], expected: bool) -> None:
    assert papers.is_main_track(row(**kwargs)) is expected


def test_main_track_extracts_lowercase_doi() -> None:
    doi = "https://doi.org/10.18653/V1/2024.ACL-LONG.1 https://aclanthology.org/x"
    raw = pd.DataFrame(
        [
            record(key="a", ee=doi),
            record(key="b", booktitle="ACL (Findings)"),
            record(key="c"),
        ]
    )
    df = papers.main_track(raw)
    assert df.key.tolist() == ["a", "c"]
    assert df.doi[0] == "10.18653/v1/2024.acl-long.1"
    assert pd.isna(df.doi[1])


def test_main_writes_papers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(papers, "load_raw", lambda: pd.DataFrame([record(key="a")]))
    monkeypatch.setattr(papers, "PAPERS", tmp_path / "papers.csv")
    papers.main()
    assert pd.read_csv(tmp_path / "papers.csv").key.tolist() == ["a"]

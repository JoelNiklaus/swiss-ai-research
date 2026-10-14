"""Main-conference paper lists for 10 of the 11 venues, read from the DBLP XML dump.

DBLP does not index COLM, so COLM paper lists come from OpenReview instead.
"""

import gzip
import logging
import re
from pathlib import Path

import pandas as pd
from lxml import etree
from tqdm import tqdm

from swiss_ai.paths import CACHE, DATA

log = logging.getLogger(__name__)

DBLP_DUMP = CACHE / "dblp" / "dblp.xml.gz"
RAW_PAPERS = CACHE / "dblp" / "papers_raw.csv"
PAPERS = DATA / "papers.csv"
YEARS = range(2010, 2027)

# DBLP key prefix (conf/<prefix>/...) to venue name.
VENUES = {
    "cvpr": "CVPR",
    "iccv": "ICCV",
    "eccv": "ECCV",
    "acl": "ACL",
    "emnlp": "EMNLP",
    "naacl": "NAACL",
    "colm": "COLM",
    "nips": "NeurIPS",
    "icml": "ICML",
    "iclr": "ICLR",
    "aaai": "AAAI",
}
# Booktitles of main-conference volumes after stripping volume suffixes like '(1)'.
MAIN_BOOKTITLES = {
    "AAAI",
    "ACL",
    "ACL/IJCNLP",
    "CVPR",
    "ECCV",
    "EMNLP",
    "EMNLP-CoNLL",
    "EMNLP/IJCNLP",
    "HLT-NAACL",
    "ICCV",
    "ICLR",
    "ICML",
    "NAACL",
    "NAACL-HLT",
    "NIPS",
    "NeurIPS",
}
VOLUME_SUFFIX = re.compile(r"\s*\((\d+|Long Papers|Short Papers|Poster)\)$")
# Numbered ACL volumes ('ACL (3)') are sometimes demos or student workshops; only the title says so.
NON_MAIN_VOLUME = re.compile(
    r"Findings|Demonstration|Student|Tutorial|Industry|Workshop|Shared Task",
    re.IGNORECASE,
)
# AAAI prints student abstracts and demos (2 to 3 pages) in the main proceedings.
AAAI_MIN_PAGES = 5
RECORD_TAGS = (
    "article",
    "inproceedings",
    "proceedings",
    "book",
    "incollection",
    "phdthesis",
    "mastersthesis",
    "www",
    "data",
)


def text(elem: etree._Element, tag: str) -> str:
    """Return the full text of the first child with `tag`, including nested markup like <i>."""
    child = elem.find(tag)
    return "" if child is None else "".join(child.itertext()).strip()


def venue_of(key: str) -> str | None:
    """Map a DBLP key such as 'conf/acl/SmithJ23' to its venue, or None for other venues."""
    parts = key.split("/")
    return VENUES[parts[1]] if parts[0] == "conf" and parts[1] in VENUES else None


def extract(dump: Path) -> pd.DataFrame:
    """Stream the DBLP dump and keep inproceedings of the 11 venues in YEARS.

    Volume titles from the matching <proceedings> records are joined on `crossref`, because
    they are the only place where DBLP says whether a volume is main track, Findings or demos.

    Args:
        dump: Path to `dblp.xml.gz`; `dblp.dtd` must sit next to it to resolve entities.

    Returns:
        One row per paper with key, venue, year, title, authors, booktitle, toc, ee, pages and
        volume (the proceedings title).
    """
    papers, volumes = [], {}
    with gzip.open(dump) as f:
        records = etree.iterparse(
            f, tag=RECORD_TAGS, load_dtd=True, resolve_entities=True, huge_tree=True
        )
        for _, elem in tqdm(records, unit=" records", mininterval=5):
            key = elem.get("key")
            venue = venue_of(key)
            if venue is not None:
                year = int(text(elem, "year"))
                if elem.tag == "proceedings":
                    volumes[key] = text(elem, "title")
                elif elem.tag == "inproceedings" and year in YEARS:
                    ees = ["".join(e.itertext()) for e in elem.findall("ee")]
                    papers.append(
                        {
                            "key": key,
                            "venue": venue,
                            "year": year,
                            "title": text(elem, "title"),
                            "authors": "; ".join(
                                "".join(a.itertext()) for a in elem.findall("author")
                            ),
                            "booktitle": text(elem, "booktitle"),
                            "toc": text(elem, "url").split("#")[0],
                            "crossref": text(elem, "crossref"),
                            "ee": " ".join(ees),
                            "pages": text(elem, "pages"),
                        }
                    )
            # Free each finished record, otherwise the 5 GB tree accumulates in memory.
            elem.clear()
            while elem.getprevious() is not None:
                del elem.getparent()[0]
    df = pd.DataFrame(papers)
    df["volume"] = df.crossref.map(volumes).fillna("")
    return df


def load_raw() -> pd.DataFrame:
    """Return the extracted DBLP rows, parsing the dump only if no cached CSV exists."""
    if not RAW_PAPERS.exists():
        extract(DBLP_DUMP).to_csv(RAW_PAPERS, index=False)
    return pd.read_csv(RAW_PAPERS, keep_default_na=False)


def page_count(pages: str) -> int | None:
    """Return the length of a 'first-last' page range, or None for other formats."""
    match = re.fullmatch(r"(\d+)-(\d+)", pages)
    return int(match[2]) - int(match[1]) + 1 if match else None


def is_main_track(row: pd.Series) -> bool:
    """Decide whether a DBLP paper belongs to the main research track of its venue.

    Drops workshops, Findings, demos, student research workshops, tutorials, industry tracks,
    ICML position papers, NeurIPS Datasets & Benchmarks papers (matching the main-track awards)
    and AAAI student abstracts.
    """
    booktitle = VOLUME_SUFFIX.sub("", row.booktitle.lstrip(">"))
    if booktitle not in MAIN_BOOKTITLES or NON_MAIN_VOLUME.search(row.volume):
        return False
    if "Datasets_and_Benchmarks" in row.ee:
        return False
    if row.venue == "AAAI":
        pages = page_count(row.pages)
        return pages is not None and pages >= AAAI_MIN_PAGES
    return True


def main_track(raw: pd.DataFrame) -> pd.DataFrame:
    """Keep main-track papers and extract the DOI, which OpenAlex matching uses."""
    df = raw[raw.apply(is_main_track, axis=1)].copy()
    df["doi"] = df.ee.str.extract(r"https://doi\.org/(\S+)", expand=False).str.lower()
    cols = ["key", "venue", "year", "title", "authors", "doi", "ee"]
    return df[cols].reset_index(drop=True)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raw = load_raw()
    papers = main_track(raw)
    papers.to_csv(PAPERS, index=False)
    log.info(f"{len(papers)} main-track papers out of {len(raw)} DBLP records")
    counts = papers.pivot_table(
        index="year", columns="venue", values="key", aggfunc="count"
    )
    log.info(counts.fillna(0).astype(int).to_string())
    log.info(
        f"DOI coverage by venue:\n{papers.groupby('venue').doi.count() / papers.groupby('venue').size()}"
    )


if __name__ == "__main__":
    main()

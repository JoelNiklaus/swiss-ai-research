"""Filesystem locations shared by all pipeline modules."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
AWARDS = DATA / "awards"
CACHE = DATA / "cache"
FIGURES = ROOT / "blog" / "figures"

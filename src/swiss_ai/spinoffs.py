"""University venture creation and Venture Kick portfolio counts.

Venture Kick publishes institution totals on its portfolio page; automated fetch
requires browser cookies, so the table below matches the figures cited in PLAN.md
from the Venture Kick portfolio (all sectors, not AI-only). ETH and EPFL rows for
2025 come from the official venture reports.
"""

import logging

import pandas as pd

from swiss_ai.paths import DATA

log = logging.getLogger(__name__)

VENTURE_KICK = DATA / "venture_kick_by_institution.csv"
UNIVERSITY_VENTURES = DATA / "university_ventures_2025.csv"

# https://www.venturekick.ch/index.cfm?kategorie_id=98&page=135353&profilesEntry=1
VENTURE_KICK_COUNTS: dict[str, int] = {
    "ETH Zurich": 300,
    "EPFL": 217,
    "University of Zurich": 54,
    "University of Geneva": 40,
    "ZHAW": 30,
    "University of St. Gallen": 30,
    "University of Bern": 27,
    "University of Basel": 22,
    "University of Lausanne": 11,
    "USI": 7,
}

# ETH Ventures Report 2025; EPFL startup news release 2025.
UNIVERSITY_2025: list[dict[str, object]] = [
    {
        "institution": "ETH Zurich",
        "year": 2025,
        "ventures": 46,
        "capital_chf_m": 540,
        "source": "https://ethz.ch/content/dam/ethz/associates/entrepreneurship-dam/documents/ETH_Ventures_Report_2025.pdf",
        "definition": "ETH official spin-off label",
    },
    {
        "institution": "EPFL",
        "year": 2025,
        "ventures": 39,
        "capital_chf_m": 701,
        "source": "https://actu.epfl.ch/news/epfl-startups-2025-a-record-cohort/",
        "definition": "EPFL startups created in 2025",
    },
]


def venture_kick_table() -> pd.DataFrame:
    """Venture Kick alumni counts by originating institution."""
    rows = [
        {"institution": name, "venture_kick_startups": count}
        for name, count in VENTURE_KICK_COUNTS.items()
    ]
    return pd.DataFrame(rows).sort_values("venture_kick_startups", ascending=False)


def university_ventures() -> pd.DataFrame:
    """Latest official venture counts and capital raised."""
    return pd.DataFrame(UNIVERSITY_2025)


def main() -> None:
    vk = venture_kick_table()
    uv = university_ventures()
    vk.to_csv(VENTURE_KICK, index=False)
    uv.to_csv(UNIVERSITY_VENTURES, index=False)
    log.info("Wrote %s and %s", VENTURE_KICK.name, UNIVERSITY_VENTURES.name)
    print(vk.to_string(index=False))
    print()
    print(uv.to_string(index=False))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()

"""Tests for spin-off statistics tables."""

from swiss_ai.spinoffs import (
    UNIVERSITY_2025,
    VENTURE_KICK_COUNTS,
    university_ventures,
    venture_kick_table,
)


def test_venture_kick_eth_leads() -> None:
    table = venture_kick_table()
    assert table.iloc[0].institution == "ETH Zurich"
    assert table.iloc[0].venture_kick_startups == VENTURE_KICK_COUNTS["ETH Zurich"]


def test_university_2025_totals() -> None:
    uv = university_ventures()
    assert len(uv) == len(UNIVERSITY_2025)
    eth = uv[uv.institution == "ETH Zurich"].iloc[0]
    assert eth.ventures == 46
    assert eth.capital_chf_m == 540

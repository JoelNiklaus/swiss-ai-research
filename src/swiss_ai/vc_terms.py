"""Venture round terms in Europe and the US, from Atomico's State of European Tech 2025.

The values in `data/hand_collected/vc_terms_europe_us.csv` are the chart data behind the
report's "Startup investment trends" chapter (Dealroom data as of 30 September 2025), read from
the report's content API. Atomico's Europe includes Switzerland. The report gives absolute
median round sizes only for Europe, so the US round size is derived from the European median and
the European-to-US ratio.
"""

import logging

import pandas as pd

from swiss_ai.paths import DATA

log = logging.getLogger(__name__)

HAND_COLLECTED = DATA / "hand_collected" / "vc_terms_europe_us.csv"
VC_TERMS = DATA / "vc_terms.csv"
STAGES = ["Seed", "Series A", "Series B", "Series C"]


def stage_table() -> pd.DataFrame:
    """Median valuations and round sizes per stage for Europe and the US.

    The share sold is the median round divided by (median pre-money valuation + median round).
    Both medians come from different sets of rounds, so the share is a rough estimate of the
    typical dilution, not a median of per-round dilution.

    Returns:
        One row per stage, in funding order, with USD millions and ratios.
    """
    raw = pd.read_csv(HAND_COLLECTED)
    wide = raw.pivot_table(
        index="stage", columns=["measure", "region"], values="value"
    ).reindex(STAGES)
    df = pd.DataFrame(
        {
            "eu_pre_money": wide["pre_money_valuation", "Europe"],
            "us_pre_money": wide["pre_money_valuation", "United States"],
            "eu_round": wide["round_size", "Europe"],
            "eu_round_vs_us": wide["round_size_vs_us", "Europe"],
            "eu_established_round_vs_us": wide[
                "established_round_size_vs_us", "Europe"
            ],
        }
    )
    df["us_round"] = df.eu_round / df.eu_round_vs_us
    df["us_valuation_multiple"] = df.us_pre_money / df.eu_pre_money
    df["us_round_multiple"] = df.us_round / df.eu_round
    df["eu_share_sold"] = df.eu_round / (df.eu_pre_money + df.eu_round)
    df["us_share_sold"] = df.us_round / (df.us_pre_money + df.us_round)
    return df


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    df = stage_table()
    df.to_csv(VC_TERMS, index_label="stage")
    log.info(df.round(2).to_string())
    for stage, row in df.iterrows():
        log.info(
            f"{stage}: Europe raises ${row.eu_round:.1f}M at ${row.eu_pre_money:.1f}M pre-money "
            f"(sells {row.eu_share_sold:.0%}), US ${row.us_round:.1f}M at ${row.us_pre_money:.1f}M "
            f"(sells {row.us_share_sold:.0%}); US valuation {row.us_valuation_multiple:.2f}x"
        )


if __name__ == "__main__":
    main()

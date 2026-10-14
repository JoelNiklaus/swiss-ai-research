"""Render the blog figures and the square social-media figure as PNGs into blog/figures/."""

import logging

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from swiss_ai.analysis import (
    AWARD_RATIOS,
    PER_CAPITA,
    PER_CAPITA_YEARS,
    SMALL_PEERS,
    SMALL_PEERS_LABEL,
)
from swiss_ai.attribution import FIRST_YEAR
from swiss_ai.citizenship import FUNNEL
from swiss_ai.countries import ALL_PLACES
from swiss_ai.investment import INVESTMENT
from swiss_ai.paths import FIGURES
from swiss_ai.vc_terms import VC_TERMS

log = logging.getLogger(__name__)
for noisy in ("kaleido", "choreographer"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

SWISS_RED = "#D52B1E"
SWISS_TINT = "rgba(213, 43, 30, 0.10)"
GREY = "#9AA0A6"
DARK = "#3C4043"
LAYOUT = {
    "template": "simple_white",
    "font": {"family": "Inter, Arial", "size": 15},
    "width": 900,
    "height": 520,
}
# Countries and pooled groups shown in the award figure, below the two Swiss rows.
RATIO_GROUPS = ["IL", "GB", "US", "DE", SMALL_PEERS_LABEL, "SG", "CN"]
FUNNEL_BASE_YEAR = FIRST_YEAR
# (stage, citizenship column, legend label, colour, dash, width)
FUNNEL_LINES = [
    ("BSc", "swiss", "Swiss bachelor's students", GREY, "solid", 2),
    ("MSc", "swiss", "Swiss master's students", DARK, "solid", 2),
    ("PhD", "swiss", "Swiss doctoral students", SWISS_RED, "solid", 4),
    ("PhD", "foreign", "Foreign doctoral students", SWISS_RED, "dot", 2),
]
# Scatter labels that would otherwise overlap a neighbour or the plot edge.
LABEL_POSITIONS = {
    "Germany": "bottom center",
    "Canada": "top left",
    "Sweden": "bottom center",
    "Switzerland": "top left",
}


def name(code: str) -> str:
    """Country name for an ISO2 code, or the group label itself."""
    if code == SMALL_PEERS_LABEL:
        return f"{code} ({', '.join(SMALL_PEERS)})"
    return ALL_PLACES[code][1] if code in ALL_PLACES else code


def colors(labels: list[str]) -> list[str]:
    """Highlight Switzerland in red, everything else grey."""
    return [SWISS_RED if label in ("CH", "Switzerland") else GREY for label in labels]


def participation_figure() -> go.Figure:
    """Fractional main-track papers per million residents, comparison places."""
    df = pd.read_csv(PER_CAPITA, keep_default_na=False).sort_values(
        "papers_per_million"
    )
    fig = go.Figure(
        go.Bar(
            x=df.papers_per_million,
            y=df.country.map(name),
            orientation="h",
            marker_color=colors(df.country.tolist()),
            text=df.papers_per_million.round(0).astype(int),
            textposition="outside",
        )
    )
    years = f"{PER_CAPITA_YEARS.start}-{PER_CAPITA_YEARS.stop - 1}"
    return fig.update_layout(
        **LAYOUT | {"height": 600},
        title={
            "text": f"Main-track papers at the top 11 AI conferences per million residents, {years}",
            "subtitle": {
                "text": "Each paper's credit is split equally among its authors with a known country"
            },
        },
        xaxis_title="Papers per million residents",
        margin={"t": 90},
    )


def award_rows() -> pd.DataFrame:
    """Rows of the award figure, top to bottom: Switzerland, Switzerland without the
    Cotterell group, then the other groups by fractional ratio."""
    df = pd.read_csv(AWARD_RATIOS, keep_default_na=False)
    swiss = df[df.group == "CH"].set_index("variant")
    others = (
        df[(df.variant == "all") & df.group.isin(RATIO_GROUPS)]
        .sort_values("ratio_frac", ascending=False)
        .assign(label=lambda d: d.group.map(name))
    )
    top = pd.DataFrame(
        [
            swiss.loc["all"].to_dict() | {"label": "<b>Switzerland</b>"},
            swiss.loc["without Cotterell group"].to_dict()
            | {"label": "<b>Switzerland</b> without Cotterell group"},
        ]
    )
    return pd.concat([top, others], ignore_index=True)


def award_ratio_figure() -> go.Figure:
    """Observed over expected award papers, fractional and any-author, with 95% intervals."""
    df = award_rows()
    n = len(df)
    position = pd.Series(range(n - 1, -1, -1), index=df.index, dtype=float)
    fig = go.Figure()
    # Shade the two Swiss rows.
    fig.add_shape(
        type="rect",
        xref="paper",
        x0=0,
        x1=1,
        y0=n - 2.5,
        y1=n - 0.5,
        fillcolor=SWISS_TINT,
        line_width=0,
        layer="below",
    )
    fig.add_trace(
        go.Scatter(
            x=[1, 1],
            y=[-0.6, n - 0.4],
            mode="lines",
            line={"dash": "dash", "color": GREY, "width": 2},
            name="Ratio of 1: awards match the paper share",
        )
    )
    for measure, label, offset, symbol, color in [
        ("frac", "Fractional credit (author share)", 0.15, "circle", DARK),
        ("any", "Any author from the country", -0.15, "diamond-open", SWISS_RED),
    ]:
        ratio = df[f"ratio_{measure}"]
        fig.add_trace(
            go.Scatter(
                x=ratio,
                y=position + offset,
                mode="markers",
                name=label,
                marker={
                    "symbol": symbol,
                    "size": 11,
                    "color": color,
                    "line": {"width": 2, "color": color},
                },
                error_x={
                    "type": "data",
                    "symmetric": False,
                    "array": df[f"ratio_{measure}_high"] - ratio,
                    "arrayminus": ratio - df[f"ratio_{measure}_low"],
                    "color": color,
                    "thickness": 1.5,
                    "width": 4,
                },
            )
        )
    awards = int(df.awards.iloc[0])
    return fig.update_layout(
        **LAYOUT | {"height": 640},
        title={
            "text": f"Best-paper awards relative to participation, {FIRST_YEAR}-2026",
            "subtitle": {
                "text": f"Observed award papers divided by the number expected from each "
                f"venue-year's paper share ({awards} awards)"
            },
        },
        xaxis={"title": "Observed / expected award papers", "range": [0, 3]},
        yaxis={
            "tickvals": position.tolist(),
            "ticktext": df.label.tolist(),
            "range": [-0.6, n - 0.4],
            "showline": False,
            "ticks": "",
        },
        legend={
            "orientation": "h",
            "x": 0.5,
            "xanchor": "center",
            "y": -0.14,
            "yanchor": "top",
        },
        margin={"t": 90, "b": 150},
    )


def transfer_figure() -> go.Figure:
    """AI authors per capita (Zeki) against private AI investment per AI author (Quid)."""
    df = pd.read_csv(INVESTMENT).dropna(subset=["investment_per_author_2013_2025"])
    fig = go.Figure(
        go.Scatter(
            x=df.authors_per_100k,
            y=df.investment_per_author_2013_2025 / 1e6,
            mode="markers+text",
            text=df.country,
            textposition=[
                LABEL_POSITIONS[c] if c in LABEL_POSITIONS else "top center"
                for c in df.country
            ],
            marker={"size": 13, "color": colors(df.country.tolist())},
        )
    )
    return fig.update_layout(
        **LAYOUT | {"height": 560},
        title={
            "text": "AI talent density against private AI investment per AI author",
            "subtitle": {
                "text": "Private AI investment 2013-2025 (Quid) divided by AI authors and "
                "inventors in 2025 (Zeki), from the AI Index 2026"
            },
        },
        xaxis={
            "title": "AI authors and inventors per 100k residents, 2025",
            "range": [15, 118],
        },
        yaxis={
            "title": "Investment per AI author (USD millions)",
            "range": [0, 4],
        },
        showlegend=False,
        margin={"t": 90},
    )


def funnel_figure() -> go.Figure:
    """Swiss and foreign exact-sciences students by level, indexed to FUNNEL_BASE_YEAR."""
    df = pd.read_csv(FUNNEL)
    df = df[
        (df.institution == "All Swiss universities") & (df.year >= FUNNEL_BASE_YEAR)
    ]
    latest = int(df.year.max())
    fig = go.Figure()
    for stage, column, label, color, dash, width in FUNNEL_LINES:
        series = df[df.stage == stage].set_index("year")[column].sort_index()
        start, end = series.loc[FUNNEL_BASE_YEAR], series.loc[latest]
        fig.add_trace(
            go.Scatter(
                x=series.index,
                y=series / start * 100,
                name=f"{label} ({start:,.0f} to {end:,.0f})",
                mode="lines",
                line={"dash": dash, "color": color, "width": width},
            )
        )
    fig.add_hline(y=100, line_color=GREY, line_width=1)
    return fig.update_layout(
        **LAYOUT | {"height": 560},
        title={
            "text": f"Students in the exact sciences at Swiss universities, {FUNNEL_BASE_YEAR} = 100",
            "subtitle": {
                "text": "Computer science, mathematics, physics and related fields, by citizenship (BFS)"
            },
        },
        yaxis_title=f"Headcount relative to {FUNNEL_BASE_YEAR}",
        legend={"x": 0.01, "y": 0.99, "xanchor": "left", "yanchor": "top"},
        margin={"t": 90},
    )


# Square layout for social posts, which are mostly read on phones.
SOCIAL_LAYOUT = {
    "template": "simple_white",
    "font": {"family": "Inter, Arial", "size": 26},
    "width": 1080,
    "height": 1080,
    "margin": {"t": 240, "b": 230, "l": 130, "r": 50},
}
SOCIAL_LABELS = {
    "Switzerland": "bottom center",
    "Israel": "top center",
    "United States": "middle right",
    "Singapore": "top center",
    "United Kingdom": "top right",
    "Canada": "bottom left",
    "Germany": "bottom center",
    "Sweden": "top center",
}


def social_figure() -> go.Figure:
    """Papers per resident against private AI investment per resident, for a phone screen."""
    papers = pd.read_csv(PER_CAPITA, keep_default_na=False)
    papers = papers.assign(country=papers.country.map(name))
    money = pd.read_csv(INVESTMENT).dropna(subset=["investment_per_capita_2013_2025"])
    df = papers.merge(money, on="country")
    labels = [
        f"<b>{c}</b>" if c in ("Switzerland", "Israel") else c for c in df.country
    ]
    fig = go.Figure(
        go.Scatter(
            x=df.papers_per_million,
            y=df.investment_per_capita_2013_2025,
            mode="markers+text",
            text=labels,
            textposition=[
                SOCIAL_LABELS[c] if c in SOCIAL_LABELS else "top center"
                for c in df.country
            ],
            textfont={"size": 26},
            marker={"size": 26, "color": colors(df.country.tolist())},
            cliponaxis=False,
        )
    )
    years = f"{PER_CAPITA_YEARS.start}-{PER_CAPITA_YEARS.stop - 1}"
    return fig.update_layout(
        **SOCIAL_LAYOUT,
        title={
            "text": "Switzerland writes top AI research<br>but attracts little AI money",
            "font": {"size": 40},
            "x": 0.03,
            "y": 0.95,
            "yanchor": "top",
            "subtitle": {
                "text": "Per resident, in Switzerland and seven comparison countries",
                "font": {"size": 24},
            },
        },
        xaxis={
            "title": f"Top AI conference papers per million residents, {years}",
            "range": [0, 320],
        },
        yaxis={
            "title": "Private AI investment per resident,<br>2013-2025 (USD)",
            "range": [0, 2400],
            "dtick": 500,
            "tickformat": ",",
        },
        showlegend=False,
        annotations=[
            {
                "text": "Papers: top 11 AI conferences, main track (DBLP, OpenReview, OpenAlex). "
                "Investment: AI Index 2026 (Quid).<br>Population: World Bank. "
                "Code and data: github.com/JoelNiklaus/swiss-ai-research",
                "xref": "paper",
                "yref": "paper",
                "x": 0,
                "y": -0.17,
                "xanchor": "left",
                "yanchor": "top",
                "showarrow": False,
                "align": "left",
                "font": {"size": 18, "color": GREY},
            }
        ],
    )


# Stages shown in the venture-terms figure: where Swiss AI startups decide where to build.
VC_STAGES = ["Seed", "Series A"]


def vc_terms_figure() -> go.Figure:
    """Median seed and Series A valuations (left) and round sizes (right), Europe against the US."""
    df = pd.read_csv(VC_TERMS).set_index("stage").loc[VC_STAGES]
    fig = make_subplots(
        rows=1,
        cols=2,
        subplot_titles=["Median pre-money valuation", "Median round size"],
        horizontal_spacing=0.1,
    )
    panels = [("eu_pre_money", "us_pre_money"), ("eu_round", "us_round")]
    for col, (eu, us) in enumerate(panels, start=1):
        for region, column, color in (
            ("Europe", eu, SWISS_RED),
            ("United States", us, GREY),
        ):
            fig.add_trace(
                go.Bar(
                    x=df.index,
                    y=df[column],
                    name=region,
                    marker_color=color,
                    text=[f"${v:.1f}M" for v in df[column]],
                    textposition="outside",
                    textfont={"size": 14},
                    cliponaxis=False,
                    showlegend=col == 1,
                ),
                row=1,
                col=col,
            )
    fig.update_yaxes(showticklabels=False, showline=False, ticks="")
    return fig.update_layout(
        **LAYOUT,
        title={
            "text": "US startups raise more money at higher valuations than European startups",
            "subtitle": {
                "text": "Median seed and Series A rounds in 2025, USD millions"
            },
        },
        barmode="group",
        legend={"orientation": "h", "x": 0, "y": -0.12},
        margin={"t": 130, "b": 80},
    )


FIGURES_BY_NAME = {
    "participation_per_capita": participation_figure,
    "award_ratios": award_ratio_figure,
    "transfer": transfer_figure,
    "vc_terms": vc_terms_figure,
    "swiss_students": funnel_figure,
    "social_research_vs_money": social_figure,
}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    FIGURES.mkdir(parents=True, exist_ok=True)
    for figure_name, build in FIGURES_BY_NAME.items():
        path = FIGURES / f"{figure_name}.png"
        build().write_image(path, scale=2)
        log.info(f"Wrote {path}")


if __name__ == "__main__":
    main()

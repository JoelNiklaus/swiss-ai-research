# Swiss AI research: output, awards, investment and talent

Code and data behind the blog post [Switzerland Does Top AI Research. Too Little of It Stays.](blog/swiss-ai-research.md). The pipeline measures how many main-track papers Swiss institutions write at the top 11 AI conferences (CVPR, ICCV, ECCV, ACL, EMNLP, NAACL, COLM, NeurIPS, ICML, ICLR, AAAI), how many best-paper awards they win relative to that, how many ERC grants and how much private AI investment Switzerland attracts, and how many Swiss citizens study and do doctorates in the exact sciences.

## Setup

```bash
uv sync
uv run pytest
```

Rerunning the network steps needs a `.env` (gitignored) with `OPENALEX_API_KEY` (free key, $1/day budget) and `OPENREVIEW_USERNAME` / `OPENREVIEW_PASSWORD` (the OpenReview API requires a login). Every API response is cached in `data/cache/` (gitignored, about 5 GB), so interrupted runs resume where they stopped. All derived tables are committed, so `analysis` and `figures` run without any credentials.

## Pipeline

Run the modules in this order with `uv run python -m swiss_ai.<module>`:

| Module        | Source                                          | Output in `data/`                                                 |
| ------------- | ----------------------------------------------- | ----------------------------------------------------------------- |
| `awards`      | `data/awards/raw/*.csv` (hand-collected)        | `awards/awards.csv`, `awards/swiss_first_authors.csv`             |
| `papers`      | DBLP XML dump (download to `data/cache/dblp/`)  | `papers.csv` (main-track papers 2010-2026)                        |
| `openreview`  | OpenReview API                                  | `openreview_papers.csv`, `openreview_authorships.csv`             |
| `openalex`    | OpenAlex API                                    | `authorships.csv.gz`, `openalex_matches.csv`                      |
| `attribution` | the four tables above                           | (log only: coverage and award matching)                           |
| `analysis`    | the four tables above, World Bank population    | `participation*.csv`, `award_ratios.csv`, `citizen_winners.csv`   |
| `investment`  | AI Index 2026 chart data (`data/raw/ai_index`)  | `investment.csv`                                                  |
| `funding`     | CORDIS bulk JSON, SNSF Data Portal              | `erc_by_country.csv`, `snsf_computer_science.csv`                 |
| `citizenship` | BFS PxWeb API, OECD SDMX API                    | `citizenship_funnel.csv`, `doctoral_mobility.csv`                 |
| `spinoffs`    | Venture Kick counts, ETH and EPFL 2025 reports  | `venture_kick_by_institution.csv`, `university_ventures_2025.csv` |
| `crosscheck`  | Paper Copilot paper lists, `participation.csv`  | `papercopilot_crosscheck.csv`, `papercopilot_countries.csv`       |
| `figures`     | outputs above                                   | `blog/figures/*.png`                                              |
| `publish`     | `data/`                                         | Hugging Face dataset [`joelniklaus/swiss-ai-research`](https://huggingface.co/datasets/joelniklaus/swiss-ai-research) (`--visibility public/private` to change visibility) |

The DBLP dump needs `dblp.xml.gz` and `dblp.dtd` from https://dblp.org/xml/ in `data/cache/dblp/`.

`data/hand_collected/` holds tables that were collected by hand from public sources, one source URL per row: ERC per-call statistics on Swiss-national vs Swiss-hosted grantees, official ERC host counts, professors by citizenship (BFS), acquisitions of Swiss AI startups, and the 28 best-funded AI startups founded in Switzerland with each founder's citizenship from the commercial register. `data/README.md` describes every table and doubles as the dataset card.

## Method

- **Paper lists:** OpenReview for ICLR 2022-2026, NeurIPS 2021-2025, ICML 2023-2026 and COLM 2024-2026; DBLP for everything else (DBLP does not index COLM). Main track only: no Findings, workshops, demos, industry tracks, NeurIPS Datasets & Benchmarks, or AAAI papers under 5 pages. AAAI still includes its IAAI and EAAI tracks, about 10% more papers than the official main-track count.
- **Countries:** OpenReview venue-years use each author's profile history for the paper year; an open-ended history entry only counts if no active entry started later, because degrees and old jobs are often never closed. DBLP venue-years are matched to OpenAlex by DOI, otherwise by exact normalized title, and use the paper's affiliations, then the author's OpenAlex profile for that year. A raw affiliation naming a Swiss city overrides OpenAlex's mapping of generic Google or Meta affiliations to US headquarters (176 authorships).
- **Cross-check:** for ICLR, ICML and NeurIPS 2023-2025, the pipeline gives Switzerland 19% more fractional papers than Paper Copilot's independent affiliation data, similar to Israel (+25%), Canada (+17%) and France (+24%); the US is 3% lower.
- **Credit:** each author with a known country carries 1 / (known authors), split across the author's countries. The any-author measure counts papers with at least one author from a country.
- **Per capita:** 2023-2025 papers per million residents (World Bank, 2024) and per 1,000 researchers (OECD MSTI, full-time equivalents; no total for Israel, the UK or Hong Kong) for the comparison countries plus Hong Kong, South Korea and Canada.
- **Awards:** an award's expected count for a country is that country's share of its own venue-year. Fractional award credit is compared with fractional participation, any-author with any-author. Intervals are exact Poisson intervals. Robustness variants drop the Cotterell group, the post author's papers, or ACL/EMNLP outstanding papers since 2021, and split before and after 2023. Netherlands, Denmark, Sweden, Austria and Finland are pooled as "Other small peers".
- **Citizen winners:** Swiss citizens among award winners since 2010 and for all years, against three baselines: world population, population of OECD countries and China, and world researchers.
- **ERC:** Starting, Consolidator, Advanced and Synergy Grants by host country in CORDIS (Horizon 2020 and Horizon Europe). CORDIS has no ERC panel, so computer science uses the euroSciVoc branch "computer and information sciences". CORDIS does not list the 2021 Starting and Consolidator and 2024 Advanced grants that SERI funded directly while Switzerland was not associated with Horizon Europe, and it lags the ERC results until grant agreements are signed (for the 2025 Advanced Grants, 188 of 319 were in CORDIS on 2026-10-09). The post's 2025 figures therefore use the ERC's own statistics (`data/hand_collected/erc_official_host_counts.csv`).
- **Citizenship:** BFS has no public cube of computer science by degree level and nationality, so the student figures use the field "4.1 Exakte Wissenschaften" (computer science is about half of it at ETH and EPFL), plus computer science across all levels as a check. The OECD peer comparison counts internationally mobile doctoral students, not foreign citizens.

## Award flags in `awards.csv`

- `has_swiss_institution`: at least one author was affiliated with a Swiss institution or a Switzerland-based industry lab (for example Google Zurich) when the paper was published.
- `has_swiss_author`: at least one author is a confirmed or probable Swiss citizen; `has_confirmed_swiss_author` counts confirmed only.
- `first_author_swiss_institution`: the first author's Swiss affiliation, empty if none.
- `first_author_swiss`: `confirmed` or `probable` if the first author is a Swiss citizen.
- `track`: `main`, `datasets_benchmarks` (NeurIPS), `position` (ICML), `demo` or `industry`. The analysis uses `main` only.

Award lists come from the PAMI TC award pages, the ACL Wiki, [Jeff Huang's best paper list](https://jeffhuang.com/best_paper_awards/), the AAAI awards page and conference blogs. Citizenship comes from ETH and EPFL thesis title pages (which list a Swiss place of origin), Wikipedia/Wikidata and personal pages. The citizen baselines in `analysis.py` use 6.6M Swiss residents with citizenship ([FSO](https://www.bfs.admin.ch/bfs/en/home/statistics/population/effectif-change.html)) plus about 0.8M Swiss abroad, against 8.23B people worldwide (UN WPP 2024).

## Caveats

- Citizenship was only checked for authors with a Swiss affiliation or a Swiss-sounding name, so the Swiss-citizen counts are lower bounds.
- OpenAlex maps a plain "Google Research" or "Meta" affiliation to the US even for Zurich-based authors; the Swiss-city override catches only affiliations that name the city.
- Award venue-years without a paper list are dropped (ICLR before 2017, EMNLP and NAACL 2026), as are three ACL 2024 award papers that DBLP only lists as arXiv preprints.
- Some early award years are unknown (CVPR 1983 to 1993, ICML before 1999, EMNLP before 2002, EMNLP 2022 outstanding papers); see `data/awards/raw/gaps_no_award.md`.

## Data sources and licenses

The code is MIT-licensed (`LICENSE`). The hand-collected award tables in `data/awards/` and the derived tables in `data/` are released under CC BY 4.0. They build on DBLP (CC0), OpenAlex (CC0), OpenReview, CORDIS (CC BY 4.0), the SNSF Data Portal, BFS and OECD statistics, and World Bank population (CC BY 4.0). `data/raw/ai_index/` holds unmodified chart data from the [AI Index 2026](https://hai.stanford.edu/ai-index) (CC BY-ND 4.0).

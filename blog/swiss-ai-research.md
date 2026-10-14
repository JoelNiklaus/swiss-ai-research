---
title: "Switzerland Does Top AI Research. Too Little of It Stays."
authors:
- user: joelniklaus
---

# Switzerland Does Top AI Research. Too Little of It Stays.

**TL;DR:** From 2023 to 2025, Swiss institutions wrote 2.0% of the main-track papers at the top 11 AI conferences, 137 per million residents. Among places with more than a million residents, only Singapore and Hong Kong produce more. Israel attracts 7.5 times as much private AI investment per AI author. Since 2010, Swiss master's students in the exact sciences have more than doubled, while Swiss doctoral students fell by 15%.

In the [AI Index 2026](https://hai.stanford.edu/ai-index), Switzerland has the most AI authors and inventors per capita of the 21 countries in Zeki's data (which excludes China): about 110 per 100,000 residents, essentially tied with Singapore. I wanted to know how much of that output Switzerland keeps. I collected every main-track paper and best-paper award since 2010 at the top 11 AI conferences (CVPR, ICCV, ECCV, ACL, EMNLP, NAACL, COLM, NeurIPS, ICML, ICLR and AAAI) and compared them with investment and enrolment statistics. The research holds up, while the companies and the people leak away.

## The research holds up

Figure 1 splits each paper's credit equally among its authors with a known country, using OpenReview profiles and OpenAlex affiliations.

<figure>
  <img src="figures/participation_per_capita.png" alt="Bar chart of main-track papers per million residents, 2023 to 2025, with Switzerland third behind Singapore and Hong Kong">
  <figcaption>Figure 1: Main-track papers at the top 11 AI conferences per million residents, 2023 to 2025 (World Bank population, 2024). A paper with two Swiss and two US authors adds 0.5 to each country.</figcaption>
</figure>

Swiss institutions wrote 1,231 of 60,338 main-track papers from 2023 to 2025. Among places with more than a million residents, only Singapore (289 per million) and Hong Kong (236) produce more than Switzerland (137). Israel (72), the US (53) and Germany (26) produce far less.

Awards are a weaker signal. I compare each award with the country's paper share at the same venue and year, so a ratio above 1 in Figure 2 means more awards than that share predicts.

<figure>
  <img src="figures/award_ratios.png" alt="Dot plot of observed over expected award papers with 95% intervals for Switzerland, Switzerland without the Cotterell group, and comparison countries">
  <figcaption>Figure 2: Award papers relative to participation, 2010 to 2026 (544 best and outstanding paper awards at the top 11 AI conferences). Filled circles split each award paper among its authors' countries, as in Figure 1; open diamonds count a paper for every country with at least one author. Bars are 95% Poisson intervals. At the dashed line, a country wins exactly as many awards as its paper share predicts.</figcaption>
</figure>

Swiss institutions appear on 35 award papers where their paper share predicts 19.8, a ratio of 1.8 (95% interval 1.2 to 2.5). With fractional credit, as in Figure 1, the ratio is 1.5 (0.9 to 2.5). Ryan Cotterell's group at ETH Zurich has 8 of the 35 papers, and without it both intervals include 1. Most Western countries also sit above 1, because China wins far fewer awards than its paper share predicts (0.5). The Swiss award record is suggestive rather than established.

European Research Council (ERC) grants show the strength more clearly. In the 2014 to 2020 calls, Swiss institutions hosted 52.0 grants per million residents, against 34.9 for Israel, 33.3 for the Netherlands and 14.0 for Germany (Starting, Consolidator, Advanced and Synergy Grants in [CORDIS](https://cordis.europa.eu/)). Swiss hosts were shut out of most 2021 to 2024 calls while Switzerland was not associated with Horizon Europe ([SERI](https://sbfi.admin.ch/en/funding-for-mono-beneficiary-projects-under-2021-2024-horizon-package)). In the 2025 calls, after re-association, they won 92, more than in any year from 2015 to 2020.

The question is how much of that research turns into Swiss companies.

## The companies leak away

Figure 3 takes both axes from the AI Index: AI authors and inventors from Zeki, and private AI investment from Quid divided by the number of AI authors.

<figure>
  <img src="figures/transfer.png" alt="Scatter of AI authors per 100,000 residents against private AI investment per AI author, with Switzerland far right and low">
  <figcaption>Figure 3: AI authors and inventors per 100,000 residents in 2025 (Zeki) against private AI investment from 2013 to 2025 per AI author (Quid), from the AI Index 2026 public data. Countries without both values are not shown.</figcaption>
</figure>

From 2013 to 2025, Switzerland raised $474,000 of private AI investment per AI author, against $3.57M in Israel and $3.43M in the US. Israel, with half Switzerland's talent density, produced 107 newly funded AI companies per 1,000 AI authors, against 19. Per resident, Switzerland ($523) is ahead of the UK ($492) and Germany ($205), so the gap is in money per researcher, not per head. Israel's figures partly reflect defence links and US investors, and Zeki's Swiss count also covers researchers at the Zurich offices of US companies.

In 2025 alone, Switzerland missed the AI Index top 15 for private AI investment, so it raised less than Sweden's $0.97B, under $110 per resident. California raised $5,551 per resident, and the Bay Area $126B, most of it in rounds of $100M or more ([HumanX and Crunchbase](https://www.humanx.co/us/crunchbase-report-download)).

Company formation is not the bottleneck. ETH Zurich recognised 46 new ventures in 2025, more than ever (22 of them under a new start-up label), and ETH ventures raised CHF 540M ([ETH](https://ethz.ch/en/news-and-events/eth-news/news/2026/02/mm-more-new-companies-founded-new-regulations-new-accelerator.html)). EPFL launched a record 39 startups, and EPFL startups raised CHF 701M, but three of the eight major rounds it lists went to companies now based in the US, Denmark and Israel ([Startupticker](https://www.startupticker.ch/en/news/epfl-startups-celebrate-record-2025)). Over 85% of Swiss venture capital comes from abroad, and over 95% at the late stage ([investrends](https://investrends.ch/aktuell/news/zwei-prozent-pflicht-brussel-will-pensionskassen-ins-risikokapital-treiben-und-die-schweiz-schaut-zu/)).

Much of the remaining transfer happens inside US companies. Google, Microsoft and Meta have long had research teams in Zurich, and OpenAI and Anthropic opened offices there in late 2024 ([WSJ](https://www.wsj.com/tech/ai/openai-expands-in-europe-with-zurich-office-f3425003)).

Swiss universities show the same pattern in who does the research.

## The people leak away

The Federal Statistical Office (BFS) does not publish computer science by degree level and citizenship, so Figure 4 uses the exact sciences (computer science, mathematics, physics and related fields; computer science is about half).

<figure>
  <img src="figures/swiss_students.png" alt="Line chart of students in the exact sciences indexed to 2010: Swiss bachelor's and master's students rise, Swiss doctoral students fall, foreign doctoral students rise">
  <figcaption>Figure 4: Students in the exact sciences at Swiss universities by level and citizenship, indexed to 2010 (BFS). The legend gives the headcounts in 2010 and 2025. Dual citizens count as Swiss.</figcaption>
</figure>

From 2010 to 2025, Swiss master's students in these fields grew from 903 to 2,234, while Swiss doctoral students fell from 662 to 564 and foreign doctoral students grew from 1,240 to 2,253. The leak is between the master's degree and the doctorate: Swiss citizens are 36% of master's students and 20% of doctoral students, and 13% of doctoral students at EPFL. The OECD counts 84% of ICT doctoral students in Switzerland as internationally mobile (they moved there to study), against 59% in Sweden, 53% in the UK, 32% in Germany and 4% in Israel ([OECD](https://data-explorer.oecd.org/), 2024).

The Swiss citizens who do go into research win awards at about the rate their population predicts. Since 2010, 7 confirmed Swiss citizens (11 with probable ones) are among 2,490 award winners. Switzerland's share of the population of OECD countries and China predicts 6.6 (world population: 2.2; world researchers, including foreigners working in Switzerland: 14.9). The institutions' award record rests largely on researchers who came from elsewhere.

## Limitations and disclosure

OpenAlex maps a plain "Google Research" affiliation to the US; I reassign it when the raw affiliation names a Swiss city, but some Zurich authors still count as American. AAAI counts include its applied and educational tracks (about 10% extra papers), and I checked citizenship only for winners with a Swiss link, so the citizen counts are lower bounds. I am Swiss, work at Hugging Face and co-authored two of the 35 Swiss award papers: ACL 2024 at the University of Bern, and COLM 2026 at Hugging Face, counted as Swiss through my OpenReview profile. Without them the ratio is 1.7 (1.2 to 2.4).

## What Switzerland should do

These are my opinions. First, keep funding the research. The 2025 ERC results show how fast Swiss hosts compete once they have access, which makes the 2027 relief package's 5% cut to the Swiss National Science Foundation (about CHF 68M a year) a poor trade ([parliament](https://www.parlament.ch/de/services/news/Seiten/2026/20260304182645577194158159026_bsd185.aspx)). Second, build domestic growth capital. Swiss pension funds manage about CHF 1,100B and may put up to 5% into unlisted Swiss companies, yet venture capital was 0.02% of their assets in 2023 ([investrends](https://investrends.ch/aktuell/news/zwei-prozent-pflicht-brussel-will-pensionskassen-ins-risikokapital-treiben-und-die-schweiz-schaut-zu/)). Funds such as the AWI Deep Tech Fund lower that barrier, while the 5% cut to Innosuisse (about CHF 17M a year) goes the other way. Third, bring more Swiss master's students into machine learning doctorates, for example through industry PhD tracks with the Zurich labs, in addition to international recruitment.

Switzerland already pays for the research. It should keep more of what the research produces.

The code, data and figures are on [GitHub](https://github.com/JoelNiklaus/swiss-ai-research).

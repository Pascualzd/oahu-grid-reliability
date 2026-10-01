# Which Lines Overload, and Which Neighbourhoods Lose Power

A linear-programming reliability study of Oʻahu's 138 kV transmission grid, run on
one recorded year (8,760 hours) and on 10,000 random draws from a multivariate
Gaussian fitted to it. The paper is `paper.pdf`; every input and its source is in
`DATA_SOURCES.md` and in Appendix A of the paper.

## The answers, in one table

| Question | Answer (base case) |
|---|---|
| How often can the network not supply demand? | Never with all lines in service (0 of 8,760 hours, 0 of 10,000 draws). Never after any one circuit fails. After two fail: in 7 of 128 cases (10 in the random draws). |
| Which areas are most at risk? | 1. East Honolulu (Pukele) · 2. Downtown · 3. Wahiawā and the North Shore · 4. The windward side with East Honolulu |
| Which lines overload most? | CEIP–Ewa Nui and Kalaeloa–Ewa Nui (the two single circuits carrying the west side's power east), then the downtown feeders |
| Do random draws agree with the recorded year? | Yes on every major finding; they add three rare failures (≤ 0.33 % of draws) |

## Folder map

| Step | File | What it does |
|---|---|---|
| 1 | `build_network.py` | 11 substations, 16 corridors, 25 circuits from HIFLD + utility filings → `data/network_*.csv` |
| 2 | `build_generators.py` | 24 units (EIA-860/923), running cost, substation → `data/generators.csv` |
| 3 | `build_demand.py` (+ `demand_shapes.py`) | hourly demand at each substation, 2021 → `data/bus_hourly_demand.csv` |
| 3b | `build_demand_puc.py` | the same, re-weighted to the 2002 filed shares (sensitivity) |
| 4 | `run_all.jl` | the LP on the recorded hours and the random draws, all lines in service; Gaussian statistics |
| 5 | `contingency.jl` | N-0, N-1 (16 cases), N-2 (128 cases) on every hour and every draw |
| 6 | `stress.jl` | demand × 1.0 … 2.0, with and without line limits |
| 7 | `redispatch.jl` | what the optimiser does when an export line is lost |
| 7b | `noise_stats.jl` | what the local wiggle (`NOISE`) does to the demand inputs |
| 8 | `summarize.py` | every number and table in the text → `out/summary.txt`, `out/paper_numbers.json` |
| 9 | `makefigs.py` | the five figures → `figs/` |
| 10 | `check_numbers.py` | recomputes the quoted numbers and checks them against `paper.tex` |

Shared: `case.jl` (loads the data; switches `RATING=low|base|high`, `DEMAND=model|puc`,
`NOISE=0|0.10|0.25|0.50`), `summarize_labels.py`.

## How substation demand is built (paper §2.1)

    d_b(t) = k_b,res · N_res(t) + k_b,com · N_com(t) + k_b,ind · N_ind(t)      i.e.  D = K N

`N_s(t)` is the island's hourly load of sector s (homes, businesses, industry) and
`k_b,s` is substation b's fixed share of the island's people, commercial jobs or
industrial jobs. Because D = K N with only three sectors, the covariance matrix of
the ten substations with load has **rank 3**. That is an artefact of the construction:
metered substation data would be full rank. `NOISE=f` adds an independent wiggle of
f·σ_b to every substation, which makes the covariance full rank; the paper's §4.7
(Table 6) shows the answers hold for f = 0.10, 0.25 and 0.50.

## Reproduce

```bash
python3 build_network.py && python3 build_generators.py
python3 build_demand.py  && python3 build_demand_puc.py      # downloads census/EIA/OpenEI files once
julia run_all.jl
julia contingency.jl                                          # base  -> out/
RATING=low  julia contingency.jl                              #       -> out_low/
RATING=high julia contingency.jl                              #       -> out_high/
DEMAND=puc  julia contingency.jl                              #       -> out_puc/
for f in 0.10 0.25 0.50; do NOISE=$f julia contingency.jl; done   #   -> out_noise10/25/50/
julia stress.jl && julia redispatch.jl
NOISE=0.50 julia stress.jl && julia noise_stats.jl
python3 summarize.py > out/summary.txt && python3 makefigs.py && python3 check_numbers.py
pdflatex paper.tex && pdflatex paper.tex && pdflatex paper.tex
```

Julia packages: JuMP, HiGHS, CSV, DataFrames. Python: numpy, pandas, openpyxl,
matplotlib, pyshp (only to re-extract the Census shoreline). The contingency runs take
about 12 minutes each on one core.

## Stand-ins (not Oʻahu's own published values)

| Input | Value | Why a stand-in | Sensitivity |
|---|---|---|---|
| Line rating | 209.9 MW per circuit (795 AAC, 878 A) | not published | 150 MW and 318.6 MW |
| Line reactance | 0.48 Ω/km | not published | cancels out of the flows |
| Substation split of demand | census people + jobs | not published | 2002 filed shares |
| Local variation per substation | none (three-factor demand, rank 3) | metered substation load not published | f = 0.10, 0.25, 0.50 of σ |
| Variable O&M | utility values for new units; EPA for steam/waste | not published for existing units | changes no merit order |
| Penalty for unserved demand | $10,000/MWh | MISO's value | only needs to exceed every plant's cost |

Large per-hour matrices from `run_all.jl` and downloaded source files in
`sources/cache/` are not committed (see `.gitignore`); the scripts regenerate them.

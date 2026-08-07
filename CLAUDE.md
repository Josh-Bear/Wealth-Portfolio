# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## What this project is

A **walk-forward backtest** for Thai dividend-yield portfolios. Four scoring methods assign each
stock a yield-based score; scores become portfolio weights via **capped proportional weighting**
(no LP). Each method produces one portfolio per entry point, **bought once and measured at 4
checkpoints** (3/6/9/12 months). Capital 100M THB.

> This is the **v3** design (`thai_dividend_backtest_plan_v3.md`). It replaced the earlier
> LP corner-solution approach (v1 quarterly / v2 monthly) — those files have been removed.

## Universe

| group | tickers | floor | ceiling |
|---|---|---|---|
| core (mandatory) | AOT, OR, KTB, PTT, PTTEP | 5% | 30% |
| secondary (optional) | SCB, BBL, KBANK, TTB, BAY | 0% | 30% |

`Σ w_i = 1`. Real baht per stock = `w_i × 100,000,000`. In the dashboard a secondary stock that is
toggled **off is excluded from the formula entirely** (not scored as 0).

## The 4 scoring methods (all on YIELD, walk-forward — only data before entry)

1. **avg_yield** — mean of per-dividend yields (`dps / price near ex-date`); optional `trim_outliers`
   drops yields above the 95th percentile (top-only; toggle in the dashboard).
2. **latest_yield** — the single most-recent dividend's yield (reactive, noisier).
3. **avg_total_return** — mean of rolling 12-month total returns `(divs + capital gain)/start price`;
   uses a shorter window when <12m of history exists; `raw_score = max(mean, 0)`.
4. **growth_trend** — linear trend of annual yield projected one period ahead; `max(proj, 0)`.

`weight_i (pre-cap) = raw_score_i / Σ raw_score`.

## Capping (water-filling — `weighting.py`)

Surplus above floors is distributed proportionally to `raw_score`, capped at each 30% ceiling.
When the free stocks all have score 0, the leftover is filled **core-first** (equal), then secondary.
Feasibility is guaranteed (5 core alone give 1.25 total headroom > 1). See `water_fill()` self-tests
(`python3 src/weighting.py`).

## Data & correctness rules (important)

- **Source:** `yfinance` primary (Yahoo, deep, split-adjusted). Yahoo raw HTTP is IP-blocked (429) —
  always go through the `yfinance` client. StockAnalysis.com was the cross-check (core matched 6/6).
- **Price basis:** `price_history.close_price` = split-adjusted to current share basis, NOT
  dividend-adjusted. `dps_amount` is on the same basis → yields & gains are consistent. All splits
  (AOT 2017, PTT 2018, PTTEP 2006) pre-date the window.
- **Walk-forward:** every score at an entry uses ONLY ex-dividend dates strictly before that entry.
- **Availability:** stocks without data/history at an entry are excluded (OR before 2021-02,
  SCB/SCBX before 2022-04 → SCB scoreable from ~2023Q1). Core keeps its 5% floor if it trades.
- **Pending:** a checkpoint whose end date is after `TODAY` (2026-08-07) is `pending`, excluded from
  realized averages.
- **No fabrication:** missing data stays missing.

## Pipeline — run in order (from repo root)

```bash
python3 src/fetch_data.py    # Phase 1-2: fetch + validate 10 stocks -> data/*.csv, raw/*
python3 src/engine.py        # score (4 methods) + water-fill + realized -> data/v3_*.csv
streamlit run src/dashboard.py   # interactive dashboard (port 8501)
```

`engine.py` writes per-stock, universe-independent tables (`v3_scores.csv`, `v3_realized.csv`) plus a
default full-universe reference (`v3_weights.csv`, `v3_results.csv`). The dashboard reads the per-stock
tables and **recomputes water-filling live** for the selected universe / trim setting (fast, cached).

## Layout

- `src/common.py` — loaders, quarterly entry points, price lookups, constants (`CORE`, `SECONDARY`,
  `ALL_TICKERS`, `CAPITAL`, `TODAY`), `price_near`/`price_asof_*`.
- `src/weighting.py` — `water_fill()` capped-proportional allocator (+ self-tests).
- `src/engine.py` — the 4 scores, realized-per-checkpoint, batch backtest.
- `src/dashboard.py` — Streamlit dashboard (live universe/trim, baht view, transparency of scores).
- `src/fetch_data.py` — Phase 1-2 data collection (yfinance primary, StockAnalysis cross-check).
- `data/` — inputs (`price_history`, `dividend_history`, `stock_master`, `data_completeness`,
  `source_crosscheck`) + v3 outputs (`v3_scores`, `v3_realized`, `v3_weights`, `v3_results`).
- `raw/` — untouched API payloads (provenance/cross-check).

## Conventions

- Python 3.12; pandas/numpy/scipy/yfinance/streamlit/plotly. See `requirements.txt`.
- Run scripts from repo root or `src/` (paths resolve relative to the file).
- Entry points: **quarterly, 20** from 2021Q3 → 2026Q2. Checkpoints: 3/6/9/12 months.
- Reproducible end-to-end from `fetch_data.py`.

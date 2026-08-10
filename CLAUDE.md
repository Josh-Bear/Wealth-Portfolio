# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## What this project is

A **walk-forward backtest** for Thai dividend-yield portfolios. Four scoring methods assign each
stock a yield-based score; scores become portfolio weights via **capped proportional weighting**
(no LP). Each method produces one portfolio per entry point, **bought once and measured at 4
checkpoints** (3/6/9/12 months). Capital 100M THB.

> Design notes live in `thai_dividend_backtest_plan_v4.md`. Key choices: **monthly** entries, yield
> priced **strictly before** each ex-date, and a dashboard focused on a **single selected entry**
> (no cross-entry KPI averages, no average-weight chart). An earlier LP corner-solution approach was
> replaced by the capped proportional weighting described here.

## Universe

| group | tickers | floor | ceiling |
|---|---|---|---|
| core (mandatory) | AOT, OR, KTB, PTT, PTTEP | 5% | 30% |
| secondary (optional) | SCB, BBL, KBANK, TTB, BAY | 0% | 30% |

`Σ w_i = 1`. Real baht per stock = `w_i × 100,000,000`. In the dashboard a secondary stock that is
toggled **off is excluded from the formula entirely** (not scored as 0).

## Yield basis (important)

Every method works on a **yield_history**: for each past dividend,
`yield = dps_amount / close STRICTLY BEFORE its ex-date` (`common.price_before_strict`, date `<`
ex-date). Rationale: the ex-date's own close is already ex-drop, so the pre-ex close is the right
denominator. A dividend with **no price strictly before its ex-date** (i.e. it predates
`price_history`, which starts 2014 while `dividend_history` goes back to ~2000) is **skipped, not
fabricated** with a later price.

## The 4 scoring methods (all on YIELD, walk-forward — only ex-dates before entry)

1. **avg_yield** — mean of the per-dividend yields; optional `trim_outliers` drops yields above the
   95th percentile (top-only; toggle in the dashboard).
2. **latest_yield** — the single most-recent dividend's yield (reactive, noisier).
3. **avg_total_return** — mean of rolling 12-month total returns `(divs + capital gain)/start price`;
   uses a shorter window when <12m of history exists; `raw_score = max(mean, 0)`.
4. **growth_trend** — linear trend fit on the per-dividend yield series (ordinal date → yield),
   projected to the entry date; `max(proj, 0)`; falls back to latest yield when <2 points.

`weight_i (pre-cap) = raw_score_i / Σ raw_score`.

## Capping (water-filling — `weighting.py`)

Surplus above floors is distributed proportionally to `raw_score`, capped at each 30% ceiling.
When the free stocks all have score 0, the leftover is filled **core-first** (equal), then secondary.
Feasibility is guaranteed (5 core alone give 1.25 total headroom > 1). See `water_fill()` self-tests
(`python3 src/weighting.py`).

## Realized measurement (per checkpoint)

For holding h ∈ {3,6,9,12} months: `realized_div = Σ dps with ex-date in (entry, entry+h] / price_entry`
— note **strictly after entry** (buying at the entry-day close does not earn a same-day ex-date
dividend). `capital_gain = (price_{entry+h} − price_entry)/price_entry`. A checkpoint whose end date
is after `TODAY` (2026-08-07) is `pending`; the dashboard shows `*` for it.

## Data & correctness rules

- **Source:** `yfinance` primary (Yahoo, deep, split-adjusted). Yahoo raw HTTP is IP-blocked (429) —
  always go through the `yfinance` client. StockAnalysis.com was the cross-check (core matched 6/6).
- **Price basis:** `price_history.close_price` = split-adjusted to current share basis, NOT
  dividend-adjusted. `dps_amount` is on the same basis → yields & gains are consistent. All splits
  (AOT 2017, PTT 2018, PTTEP 2006) pre-date the window.
- **Walk-forward:** every score at an entry uses ONLY ex-dividend dates strictly before that entry.
- **Availability:** stocks without a price/history at an entry are excluded (OR before 2021-02,
  SCB/SCBX before ~2022-11). Core keeps its 5% floor if it trades.
- **No fabrication:** missing data stays missing (dividends predating price history are skipped).

## Pipeline — run in order (from repo root)

```bash
python3 src/fetch_data.py    # Phase 1-2: fetch + validate 10 stocks -> data/*.csv, raw/*
python3 src/engine.py        # score (4 methods) + water-fill + realized -> data/{scores,realized,weights,results}.csv
streamlit run src/dashboard.py   # interactive dashboard (port 8501)
```

`engine.py` writes per-stock, universe-independent tables (`scores.csv`, `realized.csv`) plus a
default full-universe reference (`weights.csv`, `results.csv`). The dashboard reads the per-stock
tables and **recomputes water-filling live** for the
selected universe / trim setting via the shared `engine.enabled_smap` + `engine.build_portfolio`
(so batch and live cannot drift).

## Layout

- `src/common.py` — loaders; entry points (`quarter_starts`, `month_starts`,
  `build_entry_points_monthly`); `parse_entry_id` (sorts `YYYYQn` and `YYYY-MM`); price lookups
  (`price_before_strict`, `price_near`, `price_asof_*`); constants (`CORE`, `SECONDARY`,
  `ALL_TICKERS`, `CAPITAL`, `TODAY`).
- `src/weighting.py` — `water_fill()` capped-proportional allocator (+ self-tests).
- `src/engine.py` — the 4 scores, realized-per-checkpoint, shared `enabled_smap`/`build_portfolio`,
  batch backtest.
- `src/dashboard.py` — Streamlit dashboard (live universe/trim, single-entry focus, `*` for pending,
  baht view, score transparency).
- `src/fetch_data.py` — Phase 1-2 data collection (yfinance primary, StockAnalysis cross-check).
- `data/` — inputs (`price_history`, `dividend_history`, `stock_master`, `data_completeness`,
  `source_crosscheck`) + engine outputs (`scores`, `realized`, `weights`, `results`).
- `raw/` — untouched API payloads (provenance/cross-check).

## Conventions

- Python 3.12; pandas/numpy/scipy/yfinance/streamlit/plotly. See `requirements.txt`.
- Run scripts from repo root or `src/` (paths resolve relative to the file).
- Entry points: **monthly, 60** from 2021-09 → 2026-08. Checkpoints: 3/6/9/12 months.
- Reproducible end-to-end from `fetch_data.py`.

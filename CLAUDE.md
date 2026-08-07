# CLAUDE.md

Guidance for Claude Code (and humans) working in this repository.

## What this project is

A **walk-forward backtest system** for Thai dividend-yield portfolios. It searches for stock
weights that **maximize expected dividend income** over 3/6/9/12-month holding periods, tested at
rolling entry points over ~5 years, comparing 4 dividend-forecast methods and reporting both the
forecast dividend return and the realized total return (dividends + capital gain), split out.

Two spec versions drive it:
- **v1** (`thai_dividend_backtest_plan.md`): 5 core stocks, **quarterly** entries (20), 320 LP runs.
- **v2** (`thai_dividend_backtest_plan_v2.md`, current): adds 5 secondary stocks, **monthly**
  entries (60), 100M THB capital, 960 LP runs. The engine now runs v2 (10 stocks, monthly).

## Universe

| group | tickers | weight constraint |
|---|---|---|
| core (mandatory) | AOT, OR, KTB, PTT, PTTEP | each `w_i ≥ 5%` |
| secondary (optional) | SCB, BBL, KBANK, TTB, BAY | `w_i ≥ 0` (0..unbounded) |

`Σ w_i = 1`. Real baht per stock = `w_i × 100,000,000`.

## Data & correctness rules (important)

- **Source:** `yfinance` is primary (Yahoo, deep history, split-adjusted). `StockAnalysis.com` is a
  cross-check (recent dividends matched 6/6 for core). Yahoo raw HTTP is IP-blocked (429) — always
  go through the `yfinance` client, not `requests` to `query1/2.finance.yahoo.com`.
- **Price basis:** `price_history.close_price` = **split-adjusted to current share basis, NOT
  dividend-adjusted**. Dividends (`dps_amount`) are on the same current-share basis. This keeps
  yields and capital gains on one consistent basis. All splits (AOT 2017, PTT 2018, PTTEP 2006)
  predate the backtest window, so raw price movement inside the window is already clean.
- **Walk-forward:** at any entry date, forecasts use **only** ex-dividend dates strictly before that
  date. Realized measurement uses actual data inside the holding window.
- **No fabrication:** missing data stays missing (never interpolate/guess dividends).
- **Availability:** stocks that hadn't IPO'd at an entry (OR before 2021-02, SCB/SCBX before
  2022-04) are excluded from that entry's optimization — core floors are not forced on them.
- **Pending:** holding windows ending after `TODAY` (2026-08-07) are marked `pending` and excluded
  from realized averages.
- **LP is a corner solution** by design (linear objective, no risk penalty): the highest-forecast-
  yield stock takes the max allowable weight. This is expected, not a bug.

## Pipeline — run in order (from repo root)

```bash
python3 src/fetch_data.py         # Phase 1-2: fetch + validate -> data/*.csv, raw/*
python3 src/phase34_forecast.py   # Phase 3-4: dividend slots + 4-method forecast (monthly, 10 stocks)
python3 src/phase56_backtest.py   # Phase 5-6: LP optimize + realized eval -> backtest_results etc.
python3 src/phase78_report.py     # Phase 7-8: summary tables + charts + xlsx workbook
python3 src/make_pdf_report.py    # PDF report via headless Google Chrome (renders Thai fonts)
```

Interactive dashboards (Streamlit + Plotly):

```bash
streamlit run src/dashboard_v2.py   # v2: add/remove secondary stocks live, baht view (port 8502)
streamlit run src/dashboard.py      # v1: 5-core explorer (port 8501)
```

`dashboard_v2` recomputes the LP live per selected universe; per-stock forecast/realized are
precomputed (universe-independent), so only the weight allocation is recomputed — fast & cached.

## Layout

- `src/common.py` — loaders, entry-point generators (quarterly + monthly), price lookups, constants
  (`CORE`, `SECONDARY`, `CAPITAL`, `HOLDING_PERIODS`, `METHODS`, `TODAY`).
- `src/phase34_forecast.py` — slot extraction (month clustering) + per-slot 4-method forecasts.
- `src/phase56_backtest.py` — `linprog` optimizer + realized dividend/capital/total return.
- `src/phase78_report.py` / `src/make_pdf_report.py` — reporting.
- `data/` — validated inputs + all intermediate/final CSVs (schemas in the plan docs, section 4).
- `output/` — generated reports, charts, xlsx, PDF (regenerate with phase78 + make_pdf_report).
- `raw/` — untouched API payloads kept for provenance/cross-check.

## Conventions

- Python 3.12, stdlib + pandas/numpy/scipy/yfinance/matplotlib/openpyxl/streamlit/plotly. See
  `requirements.txt`.
- Run scripts from the repo root (or from `src/` — they resolve paths relative to the file).
- Forecast methods (`METHODS`): `naive`, `avg_3_5y`, `yield_based`, `growth_trend`. Per-stock
  accuracy so far: **naive is most accurate** (lowest MAE).
- Charts use English titles (matplotlib Thai glyphs are unreliable); the PDF uses Chrome so its Thai
  renders correctly.
- Everything is reproducible end-to-end from `fetch_data.py`.

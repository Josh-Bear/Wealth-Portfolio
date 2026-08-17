# CLAUDE.md — Dividend Maximizer

Guidance for working in `dividend_maximizer/`. This tool is **separate in method** from the backtest
next door: pick **at least 5** of the 10-stock universe (each target weight in `[FLOOR, CEILING]`) to
**maximize the total baht dividend** received in one chosen half-year, then convert the target weights
into **real board lots**, charge commission, and keep the leftover cash. Greedy corner-solution — NOT
the backtest's water-fill.

## Shared, no drift

Reads `../thai-dividend-backtest/data/*.csv` and imports that project's `common.py` (via
`../thai-dividend-backtest/src` on `sys.path`), so prices, dividends, universe, `CAPITAL`, and `TODAY`
are the same objects the backtest uses. Do **not** copy data or constants in here.

## Why ranking is by YIELD, not baht/share (core idea)

`total dividend = shares × dps = (capital × weight / price) × dps = capital × weight × (dps/price)`.
With capital fixed, the objective is linear in `weight × yield`, so the optimum is a **corner**: pour
the ceiling into the highest-**yield** names first. Ranking by dps/share would pick expensive
low-yield stocks and does NOT maximize baht received. Forecasts still return **baht/share** (needed
for share counts and realized dividends); the allocator's score is `forecast_dps / price`.

## Constants (`optimizer.py`; commission/lot/capital overridable in the UI)

`MIN_STOCKS=5 · FLOOR=5% · CEILING=25% · LOT_SIZE=100 · COMMISSION=0.257% · LOOKBACK=5y`.
Greedy shape with these = **25/25/25/20/5** (k names at ceiling, one partial, rest at floor). Ties in
score are broken **alphabetically by ticker** (deterministic).

## Forecasts (3 methods, baht/share, walk-forward — only data before entry)

Each forecasts the **target half's** remaining dividend = a full-year baseline **minus the most
recently known half** (`prev_half_actual`), clamped ≥ 0:
- **`avg3y`** — mean annual total over up to 3 most-recent *available* prior calendar years.
- **`lastyear`** — the most-recent available prior year's annual total.
- **`linreg`** — linear trend on (year → annual total) projected to the target year; falls back to
  `avg3y` when < 2 points.

Half handling (`prev_half_actual`): **H2(Y)** subtracts **H1(Y)** (same year); **H1(Y)** subtracts
**H2(Y-1)** (previous year — chronologically the last known half). Annual totals are **calendar-year**
(Jan 1–Dec 31), not fiscal. `years_available()` drops a stock's first partial listing year (e.g. OR
2021, SCB 2022) so it isn't read as a zero-dividend year.

## Allocation → real shares

`greedy_allocate()` returns target weights summing to 1. `to_shares()` floors each holding to a whole
multiple of `LOT_SIZE` against the **commission-inclusive** price, so `Σ total_cost ≤ capital` and
there is always leftover cash (shown, never hidden). Invariant: `invest + commission + leftover =
capital`.

## Realized dividend & pending (`realized_half_dps`)

Actual dividend per share = ex-date **strictly after entry** (bought-ex) and on/before the half's last
day. Split by `C.TODAY` (currently **2026-08-07**): ex-date ≤ TODAY → realized; ex-date > TODAY, or
the half hasn't fully elapsed → **pending**. The UI shows a per-stock "ปันผลจริง" (`-` while pending)
and the summary card mirrors the same pending flag. No guessed numbers for pending periods.

## Correctness rules (same spirit as the backtest)

- **Walk-forward:** a forecast at an entry uses only prior calendar years + the already-known half.
- **No fabrication:** pending/future dividends are never estimated; they show `-`.
- **Empty universe:** if no ticker trades at the entry, `run()` returns an empty portfolio (no crash).

## Run

```bash
python3 dividend_maximizer/optimizer.py   # core logic + self-tests (regression numbers, greedy,
                                          # money conservation, run(), backtest 2023-2026)
streamlit run dividend_maximizer/app.py   # UI (single entry / compare 3 methods / backtest)
```

## Files & conventions

- `optimizer.py` — all logic + `if __name__ == "__main__"` self-tests (the test convention here, like
  `thai-dividend-backtest/src/weighting.py`). Keep tests green after any change.
- `app.py` — Streamlit UI. It caches the CSVs (`_prices()`/`_divs()`) and passes them into
  `run()`/`run_backtest(..., prices=, divs=)`; keep threading preloaded frames so a rerun does not
  re-read the CSVs per call.
- `README.md` — user-facing assumptions.
- Backtest years are 2023–2026 (H2). The forecast/realized code is half-generic (H1 or H2).

"""
Engine — capped proportional weighting (scores -> water-filled weights, no LP).

Paradigm: 4 methods score each stock directly (on YIELD, not DPS), scores -> weights via
water-filling (weighting.py). One portfolio per (entry, method), bought once, measured at
4 checkpoints (3/6/9/12m). Monthly entries, 60 points 2021-09 .. 2026-08.

Walk-forward: every score at an entry uses ONLY dividends/prices strictly before that entry.

Outputs (per-stock, universe-independent -> dashboard recomputes weights live):
  data/scores.csv    entry_id,ticker,method,trim,raw_score,price_entry,has_history
  data/realized.csv  entry_id,ticker,checkpoint,price_entry,price_end,realized_div_return,capital_gain,pending
Reference default-universe result (all 10 on, trim=True):
  data/weights.csv   entry_id,method,ticker,weight
  data/results.csv   entry_id,method,checkpoint,realized_div_return,capital_gain,total_return,status
"""
import os
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
import common as C
from weighting import water_fill

CHECKPOINTS = [3, 6, 9, 12]
METHODS = ["avg_yield", "latest_yield", "avg_total_return", "growth_trend"]
TRIM_PCTL = 95
TR_WINDOW_M = 12          # rolling total-return window (shorter if history < this)
TR_MIN_DAYS = 60          # ignore windows shorter than this


# ---------- entry points: monthly, 60 points 2021-09 ..-2026-08 ----------
def build_entries(prices):
    return C.build_entry_points_monthly(prices, n=60, last_ym=(2026, 8))[["entry_id", "entry_date"]]


# ---------- per-dividend yields before entry (yield_history) ----------
def yields_before(divs_t, prices_t, entry):
    """yield of each past dividend = dps / close STRICTLY BEFORE its ex-date.
    Dividends with no price strictly before their ex-date (predate price history) are skipped
    (not fabricated with a later price). Returns chronological list of (ex_date, yield)."""
    out = []
    hist = divs_t[divs_t["ex_dividend_date"] < entry]
    for _, r in hist.iterrows():
        _, px = C.price_before_strict(prices_t, r["ex_dividend_date"])
        if px and px > 0:
            out.append((r["ex_dividend_date"], float(r["dps_amount"]) / px))
    return out  # list of (ex_date, yield)


# ---------- the 4 scores ----------
def m_avg_yield(yh, trim):
    ys = [y for _, y in yh]
    if not ys:
        return 0.0
    if trim and len(ys) >= 5:
        cut = np.percentile(ys, TRIM_PCTL)
        ys = [y for y in ys if y <= cut] or ys
    return float(np.mean(ys))


def m_latest_yield(yh):
    return float(yh[-1][1]) if yh else 0.0


def m_avg_total_return(divs_t, prices_t, entry):
    first = prices_t["date"].min()
    if pd.isna(first):
        return 0.0
    trs = []
    k = 1
    while True:
        end = entry - relativedelta(months=k)
        if end <= first:
            break
        start = max(end - relativedelta(months=TR_WINDOW_M), first)
        if (end - start).days < TR_MIN_DAYS:
            k += 1
            continue
        _, ps = C.price_near(prices_t, start)
        _, pe = C.price_near(prices_t, end)
        if ps and pe and ps > 0:
            dsum = divs_t[(divs_t["ex_dividend_date"] > start) &
                          (divs_t["ex_dividend_date"] <= end)]["dps_amount"].sum()
            trs.append((float(dsum) + (pe - ps)) / ps)
        k += 1
        if k > 200:
            break
    return max(float(np.mean(trs)), 0.0) if trs else 0.0


def m_growth_trend(yh, entry, fallback):
    """Linear trend of the per-dividend yield series over time -> project to the entry date.
    Fits on yield_history directly (same strictly-before-ex prices as the other methods), so it
    inherits the pre-history skip and has no partial-calendar-year bias. Fallback if <2 points."""
    if len(yh) < 2:
        return max(fallback, 0.0)
    xs = np.array([pd.Timestamp(d).toordinal() for d, _ in yh], float)
    ys = np.array([y for _, y in yh], float)
    m, b = np.polyfit(xs - xs[0], ys, 1)
    proj = m * (pd.Timestamp(entry).toordinal() - xs[0]) + b
    return max(float(proj), 0.0)


# ---------- realized per checkpoint ----------
def realized(divs_t, prices_t, entry, months, p_entry, last_day):
    end = entry + relativedelta(months=months)
    if end > last_day:
        return None  # pending (window not fully elapsed)
    # ex-date strictly AFTER entry: buying at the entry-day close does not earn a dividend
    # whose ex-date is that same day (bought ex); include ex-dates up to and including the checkpoint.
    dsum = divs_t[(divs_t["ex_dividend_date"] > entry) &
                  (divs_t["ex_dividend_date"] <= end)]["dps_amount"].sum()
    _, p_end, _ = C.holding_end_price(prices_t, entry, months)
    if not p_end:
        return None
    return {"realized_div_return": float(dsum) / p_entry,
            "capital_gain": (p_end - p_entry) / p_entry, "p_end": p_end}


# ---------- shared: enabled set + water-fill + per-checkpoint aggregation ----------
# (imported by dashboard.py so the batch and the live dashboard cannot drift)
def enabled_smap(sub_indexed, universe, core_set):
    """From a ticker-indexed score frame (one entry×method×trim), return (enabled, score map).
    Enabled = trades at entry (price_entry not NaN) AND (is core OR has dividend history)."""
    enabled, smap = [], {}
    for t in universe:
        if t not in sub_indexed.index:
            continue
        if pd.isna(sub_indexed.loc[t, "price_entry"]):
            continue
        if (t not in core_set) and (not bool(sub_indexed.loc[t, "has_history"])):
            continue
        enabled.append(t)
        smap[t] = float(sub_indexed.loc[t, "raw_score"])
    return enabled, smap


def build_portfolio(smap, enabled, core_set, entry_id, real_lookup, checkpoints=CHECKPOINTS):
    """Water-fill weights, then realized results per checkpoint. real_lookup maps
    (entry_id, ticker, checkpoint) -> record with .pending/.realized_div_return/.capital_gain.
    Returns (weights dict, list of per-checkpoint result dicts)."""
    w = water_fill(smap, enabled, core_set)
    results = []
    for h in checkpoints:
        recs = {t: real_lookup.get((entry_id, t, h)) for t in w}
        if any(r is None or r.pending for r in recs.values()):
            results.append({"checkpoint": h, "realized_div_return": np.nan, "capital_gain": np.nan,
                            "total_return": np.nan, "status": "pending"})
        else:
            rdr = sum(wt * recs[t].realized_div_return for t, wt in w.items())
            cap = sum(wt * recs[t].capital_gain for t, wt in w.items())
            results.append({"checkpoint": h, "realized_div_return": rdr, "capital_gain": cap,
                            "total_return": rdr + cap, "status": "realized"})
    return w, results


def main():
    prices = C.load_prices()
    divs = C.load_dividends()
    ep = build_entries(prices)
    last_day = prices["date"].max()
    print("entries:", len(ep), "->", ep.entry_id.iloc[0], "..", ep.entry_id.iloc[-1])

    score_rows, real_rows = [], []
    for _, e in ep.iterrows():
        eid, edate = e["entry_id"], e["entry_date"]
        for tk in C.ALL_TICKERS:
            pt = prices[prices["ticker"] == tk]
            dt = divs[divs["ticker"] == tk]
            _, p_entry = C.price_at_entry(pt, edate)
            yh = yields_before(dt, pt, pd.Timestamp(edate)) if p_entry else []
            has_hist = len(yh) > 0
            latest = m_latest_yield(yh)
            sc = {
                "latest_yield": latest,
                "avg_total_return": m_avg_total_return(dt, pt, pd.Timestamp(edate)) if p_entry else 0.0,
                "growth_trend": m_growth_trend(yh, pd.Timestamp(edate), latest) if p_entry else 0.0,
            }
            for trim in (True, False):
                sc_avg = m_avg_yield(yh, trim)
                for method in METHODS:
                    val = sc_avg if method == "avg_yield" else sc[method]
                    score_rows.append({"entry_id": eid, "ticker": tk, "method": method,
                                       "trim": trim, "raw_score": round(val, 8),
                                       "price_entry": p_entry, "has_history": has_hist})
            # realized per checkpoint (universe-independent)
            for h in CHECKPOINTS:
                rec = realized(dt, pt, pd.Timestamp(edate), h, p_entry, last_day) if p_entry else None
                real_rows.append({"entry_id": eid, "ticker": tk, "checkpoint": h,
                                  "price_entry": p_entry,
                                  "price_end": rec["p_end"] if rec else np.nan,
                                  "realized_div_return": rec["realized_div_return"] if rec else np.nan,
                                  "capital_gain": rec["capital_gain"] if rec else np.nan,
                                  "pending": rec is None})

    scores = pd.DataFrame(score_rows); scores.to_csv(os.path.join(C.DATA, "scores.csv"), index=False)
    realdf = pd.DataFrame(real_rows); realdf.to_csv(os.path.join(C.DATA, "realized.csv"), index=False)
    print(f"WROTE scores ({len(scores)}), realized ({len(realdf)})")

    # -------- default reference backtest: all 10 enabled, trim=True (uses shared helpers) --------
    core_set = set(C.CORE)
    wrows, rrows = [], []
    real_key = {(r.entry_id, r.ticker, r.checkpoint): r for r in realdf.itertuples()}
    for eid in ep.entry_id:
        for method in METHODS:
            subi = scores[(scores.entry_id == eid) & (scores.method == method) &
                          (scores.trim == True)].set_index("ticker")
            enabled, smap = enabled_smap(subi, C.ALL_TICKERS, core_set)
            w, results = build_portfolio(smap, enabled, core_set, eid, real_key)
            for t, wt in w.items():
                wrows.append({"entry_id": eid, "method": method, "ticker": t, "weight": round(wt, 6)})
            for r in results:
                rrows.append({"entry_id": eid, "method": method, "checkpoint": r["checkpoint"],
                              "realized_div_return": None if r["status"] == "pending" else round(r["realized_div_return"], 6),
                              "capital_gain": None if r["status"] == "pending" else round(r["capital_gain"], 6),
                              "total_return": None if r["status"] == "pending" else round(r["total_return"], 6),
                              "status": r["status"]})
    pd.DataFrame(wrows).to_csv(os.path.join(C.DATA, "weights.csv"), index=False)
    pd.DataFrame(rrows).to_csv(os.path.join(C.DATA, "results.csv"), index=False)
    print(f"WROTE weights ({len(wrows)}), results ({len(rrows)})")


if __name__ == "__main__":
    main()

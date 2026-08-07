"""
v3 engine — capped proportional weighting (replaces the v1/v2 LP corner-solution approach).

Paradigm: 4 methods score each stock directly (on YIELD, not DPS), scores -> weights via
water-filling (weighting.py). One portfolio per (entry, method), bought once, measured at
4 checkpoints (3/6/9/12m). Quarterly entries, 20 points from 2021Q3 (data complete for all 10).

Walk-forward: every score at an entry uses ONLY dividends/prices strictly before that entry.

Outputs (per-stock, universe-independent -> dashboard recomputes weights live):
  data/v3_scores.csv    entry_id,ticker,method,trim,raw_score,price_entry,has_history
  data/v3_realized.csv  entry_id,ticker,checkpoint,price_entry,price_end,realized_div_return,capital_gain,pending
Reference default-universe result (all 10 on, trim=True):
  data/v3_weights.csv   entry_id,method,ticker,weight
  data/v3_results.csv   entry_id,method,checkpoint,realized_div_return,capital_gain,total_return,status
"""
import os
import numpy as np
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
import common as C
from weighting import water_fill

CHECKPOINTS = [3, 6, 9, 12]
METHODS = ["avg_yield", "latest_yield", "avg_total_return", "growth_trend"]
TRIM_PCTL = 95
TR_WINDOW_M = 12          # rolling total-return window (shorter if history < this)
TR_MIN_DAYS = 60          # ignore windows shorter than this


# ---------- entry points: quarterly 2021Q3 .. 2026Q2 ----------
def v3_entries(prices):
    tdays = pd.Index(sorted(prices["date"].unique()))
    rows = []
    for eid, qs in C.quarter_starts("2021Q3", "2026Q2"):
        pos = tdays.searchsorted(pd.Timestamp(qs), side="left")
        if pos < len(tdays):
            rows.append({"entry_id": eid, "entry_date": tdays[pos]})
    return pd.DataFrame(rows)


# ---------- per-dividend yields before entry ----------
def yields_before(divs_t, prices_t, entry):
    out = []
    hist = divs_t[divs_t["ex_dividend_date"] < entry]
    for _, r in hist.iterrows():
        _, px = C.price_near(prices_t, r["ex_dividend_date"])
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


def m_growth_trend(divs_t, prices_t, entry, fallback):
    """Linear trend of annual yield -> project to entry year; fallback (latest yield) if <2 yrs."""
    hist = divs_t[divs_t["ex_dividend_date"] < entry].copy()
    if hist.empty:
        return 0.0
    hist["year"] = hist["ex_dividend_date"].dt.year
    yrs, yls = [], []
    for yr, g in hist.groupby("year"):
        _, p0 = C.price_near(prices_t, date(int(yr), 1, 1))
        if p0 and p0 > 0:
            yrs.append(int(yr))
            yls.append(float(g["dps_amount"].sum()) / p0)
    if len(yrs) < 2:
        return max(fallback, 0.0)
    yrs = np.array(yrs, float); yls = np.array(yls, float)
    m, b = np.polyfit(yrs - yrs[0], yls, 1)
    return max(float(m * (entry.year - yrs[0]) + b), 0.0)


# ---------- realized per checkpoint ----------
def realized(divs_t, prices_t, entry, months, p_entry, last_day):
    if entry + relativedelta(months=months) > last_day:
        return None  # pending
    end = entry + relativedelta(months=months)
    dsum = divs_t[(divs_t["ex_dividend_date"] >= entry) &
                  (divs_t["ex_dividend_date"] <= end)]["dps_amount"].sum()
    _, p_end, _ = C.holding_end_price(prices_t, entry, months)
    if not p_end:
        return None
    return {"realized_div_return": float(dsum) / p_entry,
            "capital_gain": (p_end - p_entry) / p_entry, "p_end": p_end}


def main():
    prices = C.load_prices()
    divs = C.load_dividends()
    ep = v3_entries(prices)
    last_day = prices["date"].max()
    print("v3 entries:", len(ep), "->", ep.entry_id.iloc[0], "..", ep.entry_id.iloc[-1])

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
                "growth_trend": m_growth_trend(dt, pt, pd.Timestamp(edate), latest) if p_entry else 0.0,
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

    scores = pd.DataFrame(score_rows); scores.to_csv(os.path.join(C.DATA, "v3_scores.csv"), index=False)
    realdf = pd.DataFrame(real_rows); realdf.to_csv(os.path.join(C.DATA, "v3_realized.csv"), index=False)
    print(f"WROTE v3_scores ({len(scores)}), v3_realized ({len(realdf)})")

    # -------- default reference backtest: all 10 enabled, trim=True --------
    core_set = set(C.CORE)
    wrows, rrows = [], []
    real_key = {(r.entry_id, r.ticker, r.checkpoint): r for r in realdf.itertuples()}
    for eid in ep.entry_id:
        for method in METHODS:
            sub = scores[(scores.entry_id == eid) & (scores.method == method) & (scores.trim == True)]
            enabled = [t for t in C.ALL_TICKERS
                       if (t in core_set) or bool(sub[sub.ticker == t]["has_history"].iloc[0])]
            enabled = [t for t in enabled if pd.notna(sub[sub.ticker == t]["price_entry"].iloc[0])]
            smap = {t: float(sub[sub.ticker == t]["raw_score"].iloc[0]) for t in enabled}
            w = water_fill(smap, enabled, core_set)
            for t, wt in w.items():
                wrows.append({"entry_id": eid, "method": method, "ticker": t, "weight": round(wt, 6)})
            for h in CHECKPOINTS:
                recs = {t: real_key.get((eid, t, h)) for t in w}
                if any(r is None or r.pending for r in recs.values()):
                    rrows.append({"entry_id": eid, "method": method, "checkpoint": h,
                                  "realized_div_return": np.nan, "capital_gain": np.nan,
                                  "total_return": np.nan, "status": "pending"})
                    continue
                rdr = sum(wt * recs[t].realized_div_return for t, wt in w.items())
                cap = sum(wt * recs[t].capital_gain for t, wt in w.items())
                rrows.append({"entry_id": eid, "method": method, "checkpoint": h,
                              "realized_div_return": round(rdr, 6), "capital_gain": round(cap, 6),
                              "total_return": round(rdr + cap, 6), "status": "realized"})
    pd.DataFrame(wrows).to_csv(os.path.join(C.DATA, "v3_weights.csv"), index=False)
    pd.DataFrame(rrows).to_csv(os.path.join(C.DATA, "v3_results.csv"), index=False)
    print(f"WROTE v3_weights ({len(wrows)}), v3_results ({len(rrows)})")


if __name__ == "__main__":
    main()

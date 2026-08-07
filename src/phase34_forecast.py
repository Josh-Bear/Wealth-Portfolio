"""
Phase 3 — Dividend timing pattern extraction  (expected dividend "slots" per ticker/entry)
Phase 4 — Forecast engine (4 methods, walk-forward: only ex-dates strictly BEFORE entry_date)

Model: each stock pays through a small set of recurring annual "slots" (e.g. PTTEP = {Feb final,
Aug interim}). At each entry we (1) identify slots from trailing history, (2) forecast each slot's
DPS four ways, then (3) for each holding window decide which slots' expected ex-date falls inside
[entry, entry+h] and sum their forecast DPS -> forecast_dividend_return.

Outputs:
  data/entry_points.csv
  data/expected_dividend_months.csv   (Phase 3 audit: slots per entry/ticker)
  data/forecast_events.csv            (every expected event: entry,ticker,holding,method,date,dps)
  data/forecast_return.csv            (solver input: forecast_dividend_return per entry×ticker×holding×method)
"""
import os
import numpy as np
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta
import common as C

ID_LOOKBACK_Y = 5      # window to identify recurring slots
METHOD_LOOKBACK_Y = 5  # trailing years for avg / yield
GROWTH_MAX_PTS = 6     # yearly points for trend fit
MIN_PRESENCE = 0.5     # a slot must appear in >=50% of observed trailing years (when >=3 yrs seen)


# ---------- month clustering (adjacency within 1 month, wrap-around Dec-Jan) ----------
def cluster_months(months):
    ms = sorted(set(int(m) for m in months))
    if not ms:
        return []
    clusters, cur = [], [ms[0]]
    for m in ms[1:]:
        if m - cur[-1] <= 1:
            cur.append(m)
        else:
            clusters.append(cur); cur = [m]
    clusters.append(cur)
    # wrap-around: merge Dec(12) with Jan(1) cluster
    if len(clusters) > 1 and clusters[0][0] == 1 and clusters[-1][-1] == 12:
        clusters[0] = clusters[-1] + clusters[0]
        clusters.pop()
    return [set(c) for c in clusters]


# ---------- slot extraction for one ticker at one entry (walk-forward) ----------
def extract_slots(div_t, entry_date):
    entry = pd.Timestamp(entry_date)
    hist = div_t[div_t["ex_dividend_date"] < entry]
    if hist.empty:
        return []
    id_start = entry - relativedelta(years=ID_LOOKBACK_Y)
    idh = hist[hist["ex_dividend_date"] >= id_start]
    if idh.empty:
        idh = hist
    n_obs_years = idh["ex_dividend_date"].dt.year.nunique()

    slots = []
    for cl in cluster_months(idh["ex_dividend_date"].dt.month.tolist()):
        id_in = idh[idh["ex_dividend_date"].dt.month.isin(cl)]
        years_present = id_in["ex_dividend_date"].dt.year.nunique()
        presence = years_present / max(n_obs_years, 1)
        if n_obs_years >= 3 and presence < MIN_PRESENCE:
            continue  # sporadic / one-off (e.g. special) -> not a recurring forecast slot
        rep_month = int(round(id_in["ex_dividend_date"].dt.month.median()))
        rep_day = min(int(round(id_in["ex_dividend_date"].dt.day.median())), 28)
        # full trailing yearly series (sum within cluster per year) for the methods
        cl_all = hist[hist["ex_dividend_date"].dt.month.isin(cl)]
        yearly = cl_all.groupby(cl_all["ex_dividend_date"].dt.year)["dps_amount"].sum()
        slots.append({
            "months": sorted(cl), "rep_month": rep_month, "rep_day": rep_day,
            "presence": round(presence, 2), "years_present": int(years_present),
            "yearly": yearly.sort_index(),  # pd.Series indexed by year
        })
    return slots


# ---------- per-slot forecasts ----------
def forecast_slot_amounts(slot, price_entry, annual_yield_avg, slot_share):
    y = slot["yearly"]
    years = list(y.index)
    vals = list(y.values)
    last = float(vals[-1])

    naive = last
    avg = float(np.mean(vals[-METHOD_LOOKBACK_Y:]))
    # growth: linear trend on up to GROWTH_MAX_PTS recent yearly points -> project to last_year+1
    if len(vals) >= 2:
        yy = np.array(years[-GROWTH_MAX_PTS:], float)
        vv = np.array(vals[-GROWTH_MAX_PTS:], float)
        m, b = np.polyfit(yy - yy[0], vv, 1)
        growth = max(0.0, float(m * (years[-1] + 1 - yy[0]) + b))
    else:
        growth = naive
    # yield-based: annual yield forecast * price, distributed to this slot by its avg share
    yield_based = max(0.0, annual_yield_avg * price_entry * slot_share) if price_entry else 0.0
    return {"naive": naive, "avg_3_5y": avg, "growth_trend": growth, "yield_based": yield_based}


def slot_expected_date_in_window(slot, entry_date, months):
    """Return expected ex-date if the slot's annual occurrence falls in [entry, entry+h], else None."""
    entry = pd.Timestamp(entry_date)
    end = entry + relativedelta(months=months)
    for yr in range(entry.year - 1, entry.year + 3):
        try:
            cand = pd.Timestamp(date(yr, slot["rep_month"], slot["rep_day"]))
        except ValueError:
            continue
        if entry <= cand <= end:
            return cand
    return None


# ---------- annual yield history (kept-slot basis) for the yield method ----------
def annual_yield_and_shares(slots, prices_t, entry_date):
    """avg yearly yield (sum kept-slot annual dps / price at that year's start), plus per-slot avg share."""
    entry = pd.Timestamp(entry_date)
    # union of trailing years present across kept slots, limited to method lookback
    years = sorted({yr for s in slots for yr in s["yearly"].index
                    if yr >= entry.year - METHOD_LOOKBACK_Y and yr < entry.year})
    yields, share_acc = [], {i: [] for i in range(len(slots))}
    for yr in years:
        yr_start = pd.Timestamp(date(yr, 1, 1))
        _, px = C.price_asof_onafter(prices_t, yr_start)
        if not px:
            continue
        amts = [float(s["yearly"].get(yr, 0.0)) for s in slots]
        tot = sum(amts)
        if tot <= 0:
            continue
        yields.append(tot / px)
        for i, a in enumerate(amts):
            share_acc[i].append(a / tot)
    avg_yield = float(np.mean(yields)) if yields else 0.0
    shares = [float(np.mean(share_acc[i])) if share_acc[i] else (1.0 / len(slots)) for i in range(len(slots))]
    return avg_yield, shares


def main():
    prices = C.load_prices()
    divs = C.load_dividends()
    ep = C.build_entry_points_monthly(prices, n=60, last_ym=(2026, 8))   # v2: 60 monthly entries
    ep.to_csv(os.path.join(C.DATA, "entry_points.csv"), index=False)
    print("entry points:", len(ep), "->", ep["entry_id"].iloc[0], "..", ep["entry_id"].iloc[-1])
    UNIVERSE = C.ALL_TICKERS   # v2: all 10 stocks (5 core + 5 secondary); per-stock, universe-independent

    slot_rows, event_rows, ret_rows = [], [], []

    for _, e in ep.iterrows():
        eid, edate = e["entry_id"], e["entry_date"]
        for tk in UNIVERSE:
            pt = prices[prices["ticker"] == tk]
            dt = divs[divs["ticker"] == tk]
            _, price_entry = C.price_at_entry(pt, edate)

            slots = extract_slots(dt, edate)
            if not slots or not price_entry:
                # no forecast basis (e.g. no prior dividends) -> forecast 0 for all windows/methods
                for h in C.HOLDING_PERIODS:
                    for m in C.METHODS:
                        ret_rows.append({"entry_id": eid, "ticker": tk, "holding_period": h,
                                         "method": m, "price_entry": price_entry,
                                         "forecast_dividend_return": 0.0, "n_expected_events": 0})
                slot_rows.append({"entry_id": eid, "ticker": tk, "price_entry": price_entry,
                                  "n_slots": 0, "slots": "[]"})
                continue

            avg_yield, shares = annual_yield_and_shares(slots, pt, edate)
            # attach per-method forecast amounts to each slot
            for i, s in enumerate(slots):
                s["fc"] = forecast_slot_amounts(s, price_entry, avg_yield, shares[i])

            slot_rows.append({
                "entry_id": eid, "ticker": tk, "price_entry": round(price_entry, 4),
                "n_slots": len(slots),
                "slots": "; ".join(f"m{s['rep_month']:02d}(day{s['rep_day']},pres{s['presence']},"
                                   f"last={float(s['yearly'].values[-1]):.3f})" for s in slots),
            })

            # build events + returns per holding × method
            for h in C.HOLDING_PERIODS:
                for m in C.METHODS:
                    tot_dps, n_ev = 0.0, 0
                    for s in slots:
                        cand = slot_expected_date_in_window(s, edate, h)
                        if cand is None:
                            continue
                        dps = float(s["fc"][m])
                        tot_dps += dps; n_ev += 1
                        event_rows.append({"entry_id": eid, "ticker": tk, "holding_period": h,
                                           "method": m, "expected_ex_date": cand.date(),
                                           "rep_month": s["rep_month"], "forecast_dps": round(dps, 4)})
                    ret_rows.append({"entry_id": eid, "ticker": tk, "holding_period": h, "method": m,
                                     "price_entry": round(price_entry, 4),
                                     "forecast_dividend_return": round(tot_dps / price_entry, 6),
                                     "n_expected_events": n_ev})

    pd.DataFrame(slot_rows).to_csv(os.path.join(C.DATA, "expected_dividend_months.csv"), index=False)
    pd.DataFrame(event_rows).to_csv(os.path.join(C.DATA, "forecast_events.csv"), index=False)
    pd.DataFrame(ret_rows).to_csv(os.path.join(C.DATA, "forecast_return.csv"), index=False)
    print(f"WROTE expected_dividend_months ({len(slot_rows)}), forecast_events ({len(event_rows)}), "
          f"forecast_return ({len(ret_rows)})")


if __name__ == "__main__":
    main()

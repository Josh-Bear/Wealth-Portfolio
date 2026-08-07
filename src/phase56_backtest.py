"""
Phase 5 — Portfolio optimization (LP, scipy.optimize.linprog)
Phase 6 — Backtest evaluation (realized dividend return, capital gain, total return, forecast error)

For each (entry_id × holding_period × forecast_method):
  maximize  Σ w_i * forecast_dividend_return_i
  s.t.      Σ w_i = 1 ,  w_i ≥ 0.05  (all 5 are core mandatory)  ->  corner solution: best gets 0.80.

Realized (walk-forward measurement uses ACTUAL data in the window):
  realized_dividend_return_i = Σ actual dps (ex-date in [entry, entry+h]) / price_entry   (specials included)
  capital_gain_i             = (price_{entry+h} - price_entry) / price_entry
Windows whose end date is after the last trading day (2026-08-06) are marked PENDING (not yet realized).

Outputs:
  data/portfolio_weights.csv
  data/realized_by_stock.csv
  data/backtest_results.csv
"""
import os
import numpy as np
import pandas as pd
from dateutil.relativedelta import relativedelta
from scipy.optimize import linprog
import common as C

def optimize_weights(returns, universe, core_set, available=None):
    """LP over `universe`. core stocks floor CORE_MIN_WEIGHT, others floor 0. sum(w)=1.
    `available`: optional set of tickers that actually trade at this entry; unavailable core
    stocks are dropped (can't be forced to 5% if they don't exist yet). Returns dict t->weight."""
    if available is None:
        available = set(universe)
    tickers = [t for t in universe if t in available]
    if not tickers:
        return {}
    r = np.array([returns.get(t, 0.0) for t in tickers], float)
    lo = np.array([C.CORE_MIN_WEIGHT if t in core_set else 0.0 for t in tickers])
    if lo.sum() > 1.0:  # too many core floors for the available set (shouldn't happen with <=5 core)
        lo = lo * (0.999 / lo.sum())
    c = -r
    res = linprog(c, A_eq=np.ones((1, len(tickers))), b_eq=[1.0],
                  bounds=list(zip(lo, [1.0] * len(tickers))), method="highs")
    w = res.x if res.success else np.where(np.arange(len(tickers)) == int(np.argmax(r)),
                                           1.0 - lo.sum() + lo, lo)
    return {t: float(round(wi, 6)) for t, wi in zip(tickers, w)}


def realized_dividend_return(div_t, entry_date, months, price_entry):
    entry = pd.Timestamp(entry_date)
    end = entry + relativedelta(months=months)
    win = div_t[(div_t["ex_dividend_date"] >= entry) & (div_t["ex_dividend_date"] <= end)]
    dps = float(win["dps_amount"].sum())
    return dps / price_entry, len(win), dps


def main():
    prices = C.load_prices()
    divs = C.load_dividends()
    ep = C.build_entry_points_monthly(prices, n=60, last_ym=(2026, 8))   # v2: monthly
    fret = pd.read_csv(os.path.join(C.DATA, "forecast_return.csv"))
    UNIVERSE = C.ALL_TICKERS
    core_set = set(C.CORE)

    last_day = prices["date"].max()
    weight_rows, byrows, result_rows = [], [], []

    for _, e in ep.iterrows():
        eid, edate = e["entry_id"], e["entry_date"]
        # price + realized pieces per ticker (independent of method / universe choice)
        pinfo = {}
        for tk in UNIVERSE:
            pt = prices[prices["ticker"] == tk]
            dt = divs[divs["ticker"] == tk]
            _, p_entry = C.price_at_entry(pt, edate)
            pinfo[tk] = {"pt": pt, "dt": dt, "p_entry": p_entry}
        available = {tk for tk in UNIVERSE if pinfo[tk]["p_entry"]}

        for h in C.HOLDING_PERIODS:
            # realized per ticker for this holding
            realized = {}
            end_target = pd.Timestamp(edate) + relativedelta(months=h)
            pending = end_target > last_day
            for tk in UNIVERSE:
                pi = pinfo[tk]; p_entry = pi["p_entry"]
                rec = {"realized_div_ret": np.nan, "capital_gain": np.nan,
                       "n_div": 0, "dps_sum": np.nan, "p_end": np.nan}
                if p_entry and not pending:
                    rdr, ndiv, dsum = realized_dividend_return(pi["dt"], edate, h, p_entry)
                    _, p_end, _ = C.holding_end_price(pi["pt"], edate, h)
                    rec.update({"realized_div_ret": rdr, "n_div": ndiv, "dps_sum": dsum,
                                "capital_gain": (p_end - p_entry) / p_entry if p_end else np.nan,
                                "p_end": p_end})
                realized[tk] = rec
                byrows.append({"entry_id": eid, "holding_period": h, "ticker": tk,
                               "price_entry": p_entry, "price_end": rec["p_end"],
                               "n_div_realized": rec["n_div"], "dps_sum_realized": rec["dps_sum"],
                               "realized_div_return": rec["realized_div_ret"],
                               "capital_gain": rec["capital_gain"], "pending": pending})

            for m in C.METHODS:
                sub = fret[(fret.entry_id == eid) & (fret.holding_period == h) & (fret.method == m)]
                fmap = dict(zip(sub.ticker, sub.forecast_dividend_return))
                # default reference backtest = full 10-stock universe (secondaries floor 0)
                w = optimize_weights(fmap, UNIVERSE, core_set, available=available)
                for tk in UNIVERSE:
                    weight_rows.append({"entry_id": eid, "holding_period": h, "forecast_method": m,
                                        "ticker": tk, "weight": w.get(tk, 0.0)})

                # portfolio-level aggregation (over the weighted tickers)
                port_fc = sum(wt * fmap.get(tk, 0.0) for tk, wt in w.items())
                if pending:
                    port_rdr = np.nan; port_cap = np.nan; port_tot = np.nan; ferr = np.nan
                    status = "pending"
                else:
                    port_rdr = sum(wt * realized[tk]["realized_div_ret"] for tk, wt in w.items())
                    port_cap = sum(wt * realized[tk]["capital_gain"] for tk, wt in w.items())
                    port_tot = port_rdr + port_cap
                    ferr = port_rdr - port_fc
                    status = "realized"

                result_rows.append({
                    "entry_id": eid, "entry_date": pd.Timestamp(edate).date(),
                    "holding_period": h, "forecast_method": m,
                    "forecast_dividend_return": round(port_fc, 6),
                    "realized_dividend_return": None if pending else round(port_rdr, 6),
                    "capital_gain_loss": None if pending else round(port_cap, 6),
                    "total_return": None if pending else round(port_tot, 6),
                    "forecast_error": None if pending else round(ferr, 6),
                    "status": status,
                })

    pd.DataFrame(weight_rows).to_csv(os.path.join(C.DATA, "portfolio_weights.csv"), index=False)
    pd.DataFrame(byrows).to_csv(os.path.join(C.DATA, "realized_by_stock.csv"), index=False)
    res = pd.DataFrame(result_rows)
    res.to_csv(os.path.join(C.DATA, "backtest_results.csv"), index=False)

    n_real = (res.status == "realized").sum(); n_pend = (res.status == "pending").sum()
    print(f"LP runs: {len(res)} (realized {n_real}, pending {n_pend})")
    print(f"WROTE portfolio_weights ({len(weight_rows)}), realized_by_stock ({len(byrows)}), backtest_results ({len(res)})")


if __name__ == "__main__":
    main()

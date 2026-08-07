"""
Phase 1 — Data Collection  (v2: yfinance primary, StockAnalysis cross-validation)

Why yfinance is primary:
  * Yahoo raw HTTP returns 429, but the yfinance client (own cookie/crumb handling) works.
  * Deeper history than StockAnalysis (2000-2005 starts vs 2015-2016).
  * Verified: history(auto_adjust=False)['Close'] is ALREADY split-adjusted to the current
    share basis (AOT 2016 ~39.5 not ~400), but NOT dividend-adjusted -> ideal price series:
        - split-consistent across all history (handles edge case #4 automatically)
        - still reflects true price movement for capital-gain calc
  * yfinance .dividends are on the same current-share (split-adjusted) basis (AOT 0.683, PTT 1.2).
  * Cross-checked against StockAnalysis (source=fmp): recent ex-dates & amounts match exactly.

Outputs (schema per plan section 4):
  raw/yf_price_{TICKER}.csv, raw/yf_div_{TICKER}.csv   (audit copies)
  data/stock_master.csv
  data/price_history.csv     ticker,date,close_price,adj_close   (close_price = split-adj, div-unadj)
  data/dividend_history.csv  ticker,announcement_date,ex_dividend_date,payment_date,dividend_type,dps_amount
  data/data_completeness.csv
  data/source_crosscheck.csv (yfinance vs StockAnalysis recent-dividend agreement)

No fabrication / interpolation. Missing stays missing.
StockAnalysis raw JSONs from v1 (raw/div_*.json) are retained as the cross-validation source.
"""
import os, json, csv
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "raw"); DATA = os.path.join(HERE, "data")
os.makedirs(RAW, exist_ok=True); os.makedirs(DATA, exist_ok=True)

PRICE_START = "2014-01-01"   # enough trailing for 5y yield history at earliest entry (2021Q4)

STOCKS = [
    # ---- core (mandatory, weight >= 5%) ----
    ("AOT",   "core", "บมจ. ท่าอากาศยานไทย",                 "Transportation"),
    ("OR",    "core", "บมจ. ปตท. น้ำมันและการค้าปลีก",       "Energy/Retail"),
    ("KTB",   "core", "ธนาคารกรุงไทย",                        "Banking"),
    ("PTT",   "core", "บมจ. ปตท.",                            "Energy"),
    ("PTTEP", "core", "บมจ. ปตท. สำรวจและผลิตปิโตรเลียม",     "Energy"),
    # ---- secondary (optional, weight 0..unbounded) ----
    ("SCB",   "secondary", "บมจ. เอสซีบี เอกซ์ (SCBX)",       "Banking"),
    ("BBL",   "secondary", "ธนาคารกรุงเทพ",                    "Banking"),
    ("KBANK", "secondary", "ธนาคารกสิกรไทย",                   "Banking"),
    ("TTB",   "secondary", "ธนาคารทหารไทยธนชาต",               "Banking"),
    ("BAY",   "secondary", "ธนาคารกรุงศรีอยุธยา",              "Banking"),
]

def load_sa_dividends(ticker):
    """Load StockAnalysis fmp dividends saved in v1 (raw/div_{ticker}.json) for cross-check."""
    p = os.path.join(RAW, f"div_{ticker}.json")
    if not os.path.exists(p):
        return {}
    d = json.load(open(p))
    out = {}
    for h in d.get("data", {}).get("history", []):
        ex = h.get("dt")
        if not ex or ex == "n/a":
            continue
        out[ex] = round(float(str(h.get("amt")).split()[0].replace(",", "")), 4)
    return out

def main():
    price_rows, div_rows, completeness, crosscheck = [], [], [], []

    for ticker, group, name_th, sector in STOCKS:
        tk = yf.Ticker(f"{ticker}.BK")

        # ---- PRICE (split-adjusted current basis; not dividend-adjusted) ----
        h = tk.history(period="max", auto_adjust=False)
        h.index = pd.to_datetime(h.index).tz_localize(None)
        h = h[h.index >= PRICE_START]
        h.to_csv(os.path.join(RAW, f"yf_price_{ticker}.csv"))
        p_dates = []
        for dt, row in h.iterrows():
            d = dt.strftime("%Y-%m-%d")
            price_rows.append((ticker, d, round(float(row["Close"]), 4), round(float(row["Adj Close"]), 4)))
            p_dates.append(d)

        # ---- DIVIDENDS (full depth, current-share basis) ----
        dv = tk.dividends.copy()
        dv.index = pd.to_datetime(dv.index).tz_localize(None)
        dv.to_csv(os.path.join(RAW, f"yf_div_{ticker}.csv"))
        d_dates, yf_recent = [], {}
        for dt, amt in dv.items():
            ex = dt.strftime("%Y-%m-%d")
            amt = round(float(amt), 4)
            div_rows.append((ticker, "", ex, "", "", amt))  # announce/pay/type unknown from yf
            d_dates.append(ex)
        for dt, amt in dv.tail(6).items():
            yf_recent[dt.strftime("%Y-%m-%d")] = round(float(amt), 4)

        # ---- CROSS-CHECK vs StockAnalysis on overlapping ex-dates ----
        sa = load_sa_dividends(ticker)
        overlap = sorted(set(yf_recent) & set(sa))
        agree = sum(1 for k in overlap if abs(yf_recent[k] - sa[k]) < 1e-6)
        for k in overlap:
            crosscheck.append({"ticker": ticker, "ex_date": k,
                               "yf_dps": yf_recent[k], "sa_dps": sa[k],
                               "match": abs(yf_recent[k] - sa[k]) < 1e-6})

        completeness.append({
            "ticker": ticker, "group": group,
            "n_price_days": len(p_dates),
            "price_start": min(p_dates) if p_dates else "",
            "price_end": max(p_dates) if p_dates else "",
            "n_dividends": len(d_dates),
            "div_start": min(d_dates) if d_dates else "",
            "div_end": max(d_dates) if d_dates else "",
            "sa_overlap_checked": len(overlap), "sa_agree": agree,
        })
        print(f"[{ticker}] price {len(p_dates)} ({min(p_dates)}..{max(p_dates)}) | "
              f"div {len(d_dates)} ({min(d_dates)}..{max(d_dates)}) | "
              f"crosscheck {agree}/{len(overlap)} match", flush=True)

    # ---- WRITE CSVs ----
    with open(os.path.join(DATA, "stock_master.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["ticker", "group", "name_th", "sector"])
        for t, g, n, s in STOCKS: w.writerow([t, g, n, s])

    price_rows.sort(key=lambda r: (r[0], r[1]))
    with open(os.path.join(DATA, "price_history.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["ticker", "date", "close_price", "adj_close"]); w.writerows(price_rows)

    div_rows.sort(key=lambda r: (r[0], r[2]))
    with open(os.path.join(DATA, "dividend_history.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "announcement_date", "ex_dividend_date", "payment_date", "dividend_type", "dps_amount"])
        w.writerows(div_rows)

    with open(os.path.join(DATA, "data_completeness.csv"), "w", newline="") as f:
        cols = ["ticker","group","n_price_days","price_start","price_end",
                "n_dividends","div_start","div_end","sa_overlap_checked","sa_agree"]
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(completeness)

    with open(os.path.join(DATA, "source_crosscheck.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker","ex_date","yf_dps","sa_dps","match"])
        w.writeheader(); w.writerows(crosscheck)

    print(f"\nWROTE price_history {len(price_rows)} rows, dividend_history {len(div_rows)} rows")

if __name__ == "__main__":
    main()

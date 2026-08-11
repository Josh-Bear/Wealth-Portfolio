"""
Phase 1 — Data Collection (yfinance primary, StockAnalysis cross-validation)

Why yfinance is primary:
  * Yahoo raw HTTP returns 429, but the yfinance client (own cookie/crumb handling) works.
  * Deeper history than StockAnalysis (2000-2005 starts vs 2015-2016).
  * Verified: history(auto_adjust=False)['Close'] is ALREADY split-adjusted to the current
    share basis (AOT 2016 ~39.5 not ~400), but NOT dividend-adjusted -> ideal price series:
        - split-consistent across all history (handles edge case #4 automatically)
        - still reflects true price movement for capital-gain calc
  * yfinance .dividends are on the same current-share (split-adjusted) basis (AOT 0.683, PTT 1.2).
  * Cross-checked against StockAnalysis (source=fmp): recent ex-dates & amounts match exactly.

Dividend field provenance (dividend_history.csv):
  * ex_dividend_date, dps_amount : yfinance (deep, ~20y, all 10 tickers) -- authoritative.
  * payment_date : merged from StockAnalysis fmp (raw/div_{TICKER}.json), matched to each
    yfinance ex-date (exact, else nearest within PAY_MATCH_TOL days). Coverage is RECENT ONLY
    (StockAnalysis fmp free depth ~2016+); older dividends have no payment_date -> left blank.
  * dividend_type : DERIVED (heuristic), not sourced -- no free feed carries an interim/final
    marker. Inferred from the ex-date half-year (final = H1 ex-date ~Feb-May from full-year AGM
    results; interim = H2 ex-date ~Aug-Nov from half-year results), with AOT forced to "final"
    (Sep fiscal year -> single Dec distribution). See classify_dividend_type(). Special or
    off-schedule dividends can be mislabeled -- treat as an estimate, not a sourced fact.
  * announcement_date : NO free source we can reach (SET corporate-action API is IP/policy-
    blocked; StockAnalysis returns declaration "n/a"). Left BLANK on purpose -- per the
    no-fabrication rule we do not invent it. A licensed feed (SETSMART / Refinitiv) can backfill.

Outputs (schema per plan section 4):
  raw/yf_price_{TICKER}.csv, raw/yf_div_{TICKER}.csv   (audit copies)
  raw/div_{TICKER}.json      (StockAnalysis fmp payload -- payment dates + cross-check)
  data/stock_master.csv
  data/price_history.csv     ticker,date,close_price,adj_close   (close_price = split-adj, div-unadj)
  data/dividend_history.csv  ticker,announcement_date,ex_dividend_date,payment_date,dividend_type,dps_amount
  data/data_completeness.csv (adds n_payment_dates = how many ex-dates got a payment_date)
  data/source_crosscheck.csv (yfinance vs StockAnalysis recent-dividend agreement)

No fabrication / interpolation. Missing stays missing.
"""
import os, json, csv, urllib.request, urllib.error
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(HERE, "raw"); DATA = os.path.join(HERE, "data")
os.makedirs(RAW, exist_ok=True); os.makedirs(DATA, exist_ok=True)

PRICE_START = "2014-01-01"   # enough trailing for 5y yield history at earliest entry (2021Q4)
SA_URL = "https://stockanalysis.com/api/symbol/a/BKK-{ticker}/dividend?source=fmp"
SA_HEADERS = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
PAY_MATCH_TOL = 4            # days: yfinance ex-date vs StockAnalysis ex-date may differ slightly

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

def fetch_sa_dividends(ticker):
    """StockAnalysis fmp dividend history for one ticker.
    Fetches live and refreshes raw/div_{ticker}.json; falls back to the saved copy on any
    network error so an offline re-run still merges whatever was cached. Returns the parsed
    'history' list (each item: {dt(ex), amt, dec, record, pay}) -- or [] if nothing available."""
    p = os.path.join(RAW, f"div_{ticker}.json")
    try:
        req = urllib.request.Request(SA_URL.format(ticker=ticker), headers=SA_HEADERS)
        raw = urllib.request.urlopen(req, timeout=25).read()
        json.loads(raw)                      # validate before persisting
        with open(p, "wb") as f:
            f.write(raw)
    except (urllib.error.URLError, ValueError, TimeoutError) as e:
        print(f"  [SA] {ticker}: live fetch failed ({type(e).__name__}); using cached copy", flush=True)
    if not os.path.exists(p):
        return []
    return json.load(open(p)).get("data", {}).get("history", [])


def sa_amount(h):
    """Parse a StockAnalysis amount like '0.810 THB' -> 0.81 (or None)."""
    a = h.get("amt")
    if a in (None, "n/a", ""):
        return None
    try:
        return round(float(str(a).split()[0].replace(",", "")), 4)
    except ValueError:
        return None


def build_sa_maps(history):
    """From SA history build {ex_date_ts -> amount} (cross-check) and {ex_date_ts -> pay_date_str}."""
    amt_map, pay_map = {}, {}
    for h in history:
        ex = h.get("dt")
        if not ex or ex == "n/a":
            continue
        ex_ts = pd.Timestamp(ex).normalize()
        a = sa_amount(h)
        if a is not None:
            amt_map[ex_ts] = a
        pay = h.get("pay")
        if pay not in (None, "n/a", ""):
            pay_map[ex_ts] = pay
    return amt_map, pay_map


def nearest_payment(pay_map, ex_ts):
    """payment_date for a yfinance ex-date: exact SA ex-date match, else nearest within tol days."""
    if ex_ts in pay_map:
        return pay_map[ex_ts]
    best, best_gap = None, None
    for sa_ex, pay in pay_map.items():
        gap = abs((sa_ex - ex_ts).days)
        if gap <= PAY_MATCH_TOL and (best_gap is None or gap < best_gap):
            best, best_gap = pay, gap
    return best


# StockAnalysis has no interim/final marker, so dividend_type is DERIVED (heuristic), not sourced.
# Thai firms with a Dec fiscal year pay the full-year "final" dividend after the AGM (ex-date ~Feb-May,
# i.e. H1 of the calendar year) and an "interim" from half-year results (ex-date ~Aug-Nov, H2). AOT is
# the known exception: fiscal year ends Sep 30, so its single ~December distribution is the FINAL.
# Caveat: a special dividend or an off-schedule payment can be misclassified -- treat as an estimate.
AOT_ANNUAL_FINAL = {"AOT"}   # Sep fiscal-year-end -> single Dec dividend is the final, not an interim

def classify_dividend_type(ticker, ex_ts):
    """Heuristic interim/final from the ex-date's half of the (Dec-fiscal) calendar year."""
    if ticker in AOT_ANNUAL_FINAL:
        return "final"
    return "final" if ex_ts.month <= 6 else "interim"

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

        # ---- StockAnalysis fmp: payment dates (recent) + cross-check amounts ----
        sa_hist = fetch_sa_dividends(ticker)
        sa_amt, sa_pay = build_sa_maps(sa_hist)

        # ---- DIVIDENDS (full depth, current-share basis; payment_date merged from SA) ----
        dv = tk.dividends.copy()
        dv.index = pd.to_datetime(dv.index).tz_localize(None)
        dv.to_csv(os.path.join(RAW, f"yf_div_{ticker}.csv"))
        d_dates, yf_recent, n_pay = [], {}, 0
        for dt, amt in dv.items():
            ex_ts = pd.Timestamp(dt).normalize()
            ex = ex_ts.strftime("%Y-%m-%d")
            amt = round(float(amt), 4)
            pay = nearest_payment(sa_pay, ex_ts) or ""   # payment_date if SA has it, else blank
            if pay:
                n_pay += 1
            dtype = classify_dividend_type(ticker, ex_ts)  # DERIVED interim/final (heuristic, see above)
            # announcement_date: no reachable source -> intentionally blank
            div_rows.append((ticker, "", ex, pay, dtype, amt))
            d_dates.append(ex)
        for dt, amt in dv.tail(6).items():
            yf_recent[pd.Timestamp(dt).normalize()] = round(float(amt), 4)

        # ---- CROSS-CHECK vs StockAnalysis on overlapping ex-dates ----
        overlap = sorted(set(yf_recent) & set(sa_amt))
        agree = sum(1 for k in overlap if abs(yf_recent[k] - sa_amt[k]) < 1e-6)
        for k in overlap:
            crosscheck.append({"ticker": ticker, "ex_date": k.strftime("%Y-%m-%d"),
                               "yf_dps": yf_recent[k], "sa_dps": sa_amt[k],
                               "match": abs(yf_recent[k] - sa_amt[k]) < 1e-6})

        completeness.append({
            "ticker": ticker, "group": group,
            "n_price_days": len(p_dates),
            "price_start": min(p_dates) if p_dates else "",
            "price_end": max(p_dates) if p_dates else "",
            "n_dividends": len(d_dates),
            "div_start": min(d_dates) if d_dates else "",
            "div_end": max(d_dates) if d_dates else "",
            "n_payment_dates": n_pay,
            "sa_overlap_checked": len(overlap), "sa_agree": agree,
        })
        print(f"[{ticker}] price {len(p_dates)} ({min(p_dates)}..{max(p_dates)}) | "
              f"div {len(d_dates)} ({min(d_dates)}..{max(d_dates)}) | "
              f"pay_date {n_pay}/{len(d_dates)} | "
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
                "n_dividends","div_start","div_end","n_payment_dates",
                "sa_overlap_checked","sa_agree"]
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(completeness)

    with open(os.path.join(DATA, "source_crosscheck.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ticker","ex_date","yf_dps","sa_dps","match"])
        w.writeheader(); w.writerows(crosscheck)

    print(f"\nWROTE price_history {len(price_rows)} rows, dividend_history {len(div_rows)} rows")

if __name__ == "__main__":
    main()

"""
Shared helpers for the Thai dividend backtest engine.
Loads validated Phase-1 CSVs and provides walk-forward-safe lookups.

Price basis: price_history.close_price = split-adjusted (current share basis), NOT
dividend-adjusted. dividends dps_amount = same current-share basis. -> yields & gains
are computed on a single consistent basis. All splits pre-date the 2021Q4 window anyway.
"""
import os
import pandas as pd
from datetime import date
from dateutil.relativedelta import relativedelta

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "output")
os.makedirs(OUT, exist_ok=True)

CORE = ["AOT", "OR", "KTB", "PTT", "PTTEP"]
SECONDARY = ["SCB", "BBL", "KBANK", "TTB", "BAY"]
ALL_TICKERS = CORE + SECONDARY
CAPITAL = 100_000_000                        # v2: เงินทุนตั้งต้น 100 ล้านบาท
CORE_MIN_WEIGHT = 0.05                       # หุ้นหลักบังคับ >= 5%
TODAY = pd.Timestamp("2026-08-07")           # session date; anything after = not yet realized
HOLDING_PERIODS = [3, 6, 9, 12]
METHODS = ["naive", "avg_3_5y", "yield_based", "growth_trend"]

# ---------- loaders ----------
def load_prices():
    p = pd.read_csv(os.path.join(DATA, "price_history.csv"), parse_dates=["date"])
    p = p.sort_values(["ticker", "date"]).reset_index(drop=True)
    return p

def load_dividends():
    d = pd.read_csv(os.path.join(DATA, "dividend_history.csv"), parse_dates=["ex_dividend_date"])
    d = d.dropna(subset=["ex_dividend_date"]).sort_values(["ticker", "ex_dividend_date"]).reset_index(drop=True)
    return d

# ---------- entry points: 2021Q4 -> 2026Q3, first trading day of quarter ----------
def quarter_starts(first="2021Q4", last="2026Q3"):
    fy, fq = int(first[:4]), int(first[5])
    ly, lq = int(last[:4]), int(last[5])
    out = []
    y, q = fy, fq
    while (y, q) <= (ly, lq):
        out.append((f"{y}Q{q}", date(y, {1: 1, 2: 4, 3: 7, 4: 10}[q], 1)))
        q += 1
        if q > 4:
            q = 1; y += 1
    return out  # list of (entry_id, quarter_start_date)

def build_entry_points(prices):
    """First actual trading day >= quarter start (any ticker trades that day)."""
    trading_days = pd.Index(sorted(prices["date"].unique()))
    rows = []
    for eid, qs in quarter_starts():
        qs_ts = pd.Timestamp(qs)
        pos = trading_days.searchsorted(qs_ts, side="left")
        if pos >= len(trading_days):
            continue
        rows.append({"entry_id": eid, "quarter_start": qs_ts, "entry_date": trading_days[pos]})
    return pd.DataFrame(rows)


def parse_entry_id(e):
    """Chronological sort key for entry ids. Handles quarterly 'YYYYQn' and monthly 'YYYY-MM'."""
    if "Q" in e:
        y, q = e.split("Q"); return (int(y), int(q))
    y, m = e.split("-"); return (int(y), int(m))


def month_starts(n=60, last_ym=(2026, 8)):
    """n monthly (year, month, day=1) tuples ending at last_ym inclusive -> entry_id 'YYYY-MM'."""
    ly, lm = last_ym
    out = []
    y, m = ly, lm
    for _ in range(n):
        out.append((f"{y}-{m:02d}", date(y, m, 1)))
        m -= 1
        if m == 0:
            m = 12; y -= 1
    return list(reversed(out))  # chronological


def build_entry_points_monthly(prices, n=60, last_ym=(2026, 8)):
    """v2: monthly entries. First actual trading day >= each month start."""
    trading_days = pd.Index(sorted(prices["date"].unique()))
    rows = []
    for eid, ms in month_starts(n, last_ym):
        ms_ts = pd.Timestamp(ms)
        pos = trading_days.searchsorted(ms_ts, side="left")
        if pos >= len(trading_days):
            continue
        rows.append({"entry_id": eid, "month_start": ms_ts, "entry_date": trading_days[pos]})
    return pd.DataFrame(rows)

# ---------- price lookups ----------
def price_asof_onafter(prices_t, target):
    """First trading row for one ticker with date >= target. Returns (date, close) or (None,None)."""
    sub = prices_t[prices_t["date"] >= pd.Timestamp(target)]
    if sub.empty:
        return None, None
    r = sub.iloc[0]
    return r["date"], float(r["close_price"])

def price_asof_onbefore(prices_t, target):
    """Last trading row for one ticker with date <= target (nearest prior). (date, close) or (None,None)."""
    sub = prices_t[prices_t["date"] <= pd.Timestamp(target)]
    if sub.empty:
        return None, None
    r = sub.iloc[-1]
    return r["date"], float(r["close_price"])


def price_before_strict(prices_t, target):
    """Last trading row STRICTLY BEFORE target (date < target). (date, close) or (None, None).
    Used for yields: the ex-dividend day's own close is already ex-drop, and a dividend with no
    price strictly before it (e.g. predates price history) must be skipped, not fabricated."""
    sub = prices_t[prices_t["date"] < pd.Timestamp(target)]
    if sub.empty:
        return None, None
    r = sub.iloc[-1]
    return r["date"], float(r["close_price"])


def price_near(prices_t, target):
    """Price nearest to target: prefer on-or-before, else on-or-after."""
    d, c = price_asof_onbefore(prices_t, target)
    if c is not None:
        return d, c
    return price_asof_onafter(prices_t, target)


def price_at_entry(prices_t, entry_date):
    """Price for a ticker at the entry date; if the ticker didn't trade yet -> (None,None)."""
    return price_asof_onafter(prices_t, entry_date)

def holding_end_price(prices_t, entry_date, months):
    """Price at entry_date + months (first trading day on/after). None if beyond data (pending)."""
    target = pd.Timestamp(entry_date) + relativedelta(months=months)
    if target > prices_t["date"].max():
        return None, None, target
    d, c = price_asof_onafter(prices_t, target)
    return d, c, target

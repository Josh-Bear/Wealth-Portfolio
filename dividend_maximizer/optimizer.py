"""
Dividend Maximizer -- greedy corner-solution allocator (SEPARATE from the water-fill backtest).

Goal: pick at least MIN_STOCKS of the 10-stock universe (each target weight in [FLOOR, CEILING])
to MAXIMIZE the total baht dividend received in the chosen half-year, then convert those target
weights into real board-lot share counts, charge commission, and keep the leftover cash.

Why yield, not baht/share, drives the ranking:
    total dividend = shares * dps = (capital * weight / price) * dps = capital * weight * (dps/price)
so with a fixed capital the objective is linear in `weight * yield`. Maximizing it is therefore a
corner solution: pour CEILING into the highest-YIELD names first. Ranking by dps/share alone would
pick expensive low-yield stocks and does NOT maximize the baht received. Forecasts still return
baht/share (needed for share counts and realized dividends); the ranking score is dps/price.

Shared, no drift: prices/dividends and universe/constants come from the main project via
../thai-dividend-backtest/src/common.py (same files engine.py/dashboard.py use).
"""
import os
import sys
import numpy as np
import pandas as pd

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "thai-dividend-backtest", "src")
sys.path.insert(0, _SRC)
import common as C # type: ignore

# ---- constants specific to this tool ----
LOT_SIZE = 100
COMMISSION = 0.00257        # 0.257% charged on the buy notional
MIN_STOCKS = 5
FLOOR = 0.05
CEILING = 0.25
LOOKBACK = 5                # consider up to this many prior calendar years of history
METHODS = ["avg3y", "lastyear", "linreg"]
MLABEL = {"avg3y": "เฉลี่ย 3 ปี", "lastyear": "ปีล่าสุด", "linreg": "เส้นแนวโน้ม (linreg)"}


# ---------- step 1: calendar-year dividend sums (per ticker) ----------
def annual_total(divs_t, year):
    """Sum of dps whose ex-date falls in the calendar year [Jan 1, Dec 31] of `year`."""
    m = ((divs_t["ex_dividend_date"] >= pd.Timestamp(year, 1, 1)) &
         (divs_t["ex_dividend_date"] <= pd.Timestamp(year, 12, 31)))
    return float(divs_t.loc[m, "dps_amount"].sum())


def h1_actual(divs_t, year):
    """Sum of dps already gone ex in H1 (Jan 1 - Jun 30) of `year` -- subtracted from a full-year
    forecast to leave the expected H2 remainder."""
    m = ((divs_t["ex_dividend_date"] >= pd.Timestamp(year, 1, 1)) &
         (divs_t["ex_dividend_date"] <= pd.Timestamp(year, 6, 30)))
    return float(divs_t.loc[m, "dps_amount"].sum())


def years_available(prices_t, years):
    """Keep only years the stock was already trading before (price history starts on/before Jan 1),
    so a partial first listing year (OR 2021, SCB 2022) is not mistaken for a zero-dividend year."""
    if prices_t.empty:
        return []
    first = prices_t["date"].min()
    return [y for y in years if first <= pd.Timestamp(y, 1, 1)]


def _prior_annuals(divs_t, prices_t, target_year, n=None):
    """(year, annual_total) for available full years strictly before target_year, chronological.
    `n` keeps only the most recent n of them."""
    cand = list(range(target_year - LOOKBACK, target_year))
    yrs = years_available(prices_t, cand)
    if n is not None:
        yrs = yrs[-n:]
    return [(y, annual_total(divs_t, y)) for y in yrs]


# ---------- step 2: three forecasts of the H2 dividend PER SHARE (baht, walk-forward) ----------
def forecast_avg3y(divs_t, prices_t, target_year):
    """mean(annual_total over up to 3 most-recent available years) - H1 already paid, clamp >= 0."""
    hist = _prior_annuals(divs_t, prices_t, target_year, n=3)
    if not hist:
        return 0.0
    mean_annual = sum(v for _, v in hist) / len(hist)
    return max(mean_annual - h1_actual(divs_t, target_year), 0.0)


def forecast_lastyear(divs_t, prices_t, target_year):
    """annual_total of the most recent available prior year - H1 already paid, clamp >= 0."""
    hist = _prior_annuals(divs_t, prices_t, target_year, n=1)
    if not hist:
        return 0.0
    return max(hist[-1][1] - h1_actual(divs_t, target_year), 0.0)


def forecast_linreg(divs_t, prices_t, target_year):
    """Linear trend on (year -> annual_total) projected to target_year, - H1 paid, clamp >= 0.
    Falls back to avg3y when fewer than 2 data points exist."""
    hist = _prior_annuals(divs_t, prices_t, target_year)
    if len(hist) < 2:
        return forecast_avg3y(divs_t, prices_t, target_year)
    xs = np.array([y for y, _ in hist], float)
    ys = np.array([v for _, v in hist], float)
    m, b = np.polyfit(xs, ys, 1)
    proj = m * target_year + b
    return max(float(proj) - h1_actual(divs_t, target_year), 0.0)


FORECASTS = {"avg3y": forecast_avg3y, "lastyear": forecast_lastyear, "linreg": forecast_linreg}


# ---------- step 3: greedy corner-solution allocation (NOT water-fill) ----------
def greedy_allocate(scores, min_stocks=MIN_STOCKS, floor=FLOOR, ceiling=CEILING):
    """Maximize sum(weight_i * score_i) with each chosen weight in [floor, ceiling], at least
    min_stocks chosen, and sum(weight) == 1. Linear objective -> corner solution: rank by score
    (desc; ties broken by ticker asc for determinism), pour ceiling into the best names first,
    floor the rest. Returns {ticker: weight}. Empty in -> empty out.

    Feasibility: needs enough names to both reach 1.0 under the ceiling (>= ceil(1/ceiling)) and
    not overshoot under the floor. The shape is k names at ceiling, one partial, the rest at floor
    (e.g. 5/5%/25% -> 25/25/25/20/5; 5/5%/30% -> 30/30/30/5/5).
    """
    if not scores:
        return {}
    ranked = sorted(scores, key=lambda t: (-scores[t], t))
    n = len(ranked)
    k = min(min_stocks, n)
    while k < n and k * ceiling < 1.0 - 1e-12:   # bump if min_stocks can't reach 1.0 under ceiling
        k += 1
    chosen = ranked[:k]
    if k * floor > 1.0 + 1e-12:                   # too many forced floors to fit in 1.0 (guard)
        w = {t: 1.0 / k for t in chosen}
        return w
    w = {t: floor for t in chosen}
    remaining = 1.0 - floor * k
    for t in chosen:                              # pour ceiling headroom into best-ranked first
        if remaining <= 1e-12:
            break
        add = min(ceiling - floor, remaining)
        w[t] += add
        remaining -= add
    return w


# ---------- step 4: target weights -> real board-lot shares + commission ----------
def to_shares(weights, prices, capital=None, commission=COMMISSION, lot=LOT_SIZE):
    """Convert target weights into whole board lots you can actually buy.
    Shares are floored to a multiple of `lot` against the commission-inclusive price, so the summed
    cost never exceeds capital. Columns: ticker, target_weight, price, shares, invest_value,
    commission_paid, total_cost, actual_weight_pct. Leftover cash = capital - sum(total_cost)."""
    capital = C.CAPITAL if capital is None else capital
    rows = []
    for t, w in weights.items():
        px = prices.get(t)
        target_baht = w * capital
        if not px or px <= 0:
            rows.append({"ticker": t, "target_weight": w, "price": np.nan, "shares": 0,
                         "invest_value": 0.0, "commission_paid": 0.0, "total_cost": 0.0,
                         "actual_weight_pct": 0.0})
            continue
        shares = int((target_baht / (px * (1 + commission))) // lot) * lot
        invest = shares * px
        comm = invest * commission
        total = invest + comm
        rows.append({"ticker": t, "target_weight": w, "price": px, "shares": shares,
                     "invest_value": invest, "commission_paid": comm, "total_cost": total,
                     "actual_weight_pct": total / capital})
    return pd.DataFrame(rows)


# ---------- step 5: score the whole universe at one entry (ranking transparency) ----------
def score_universe(divs, prices, entry, target_year, method, universe=None):
    """Per-ticker DataFrame at one entry: forecast dps (baht/share), entry price, and the ranking
    score = forecast_dps / price (the yield that the allocator maximizes). Only tickers that trade
    at `entry` are eligible. Sorted by score desc, ticker asc."""
    universe = list(C.ALL_TICKERS if universe is None else universe)
    fc = FORECASTS[method]
    rows = []
    for t in universe:
        pt = prices[prices["ticker"] == t]
        dt = divs[divs["ticker"] == t]
        _, px = C.price_at_entry(pt, entry)
        if not px or px <= 0:                      # not trading yet at entry -> not eligible
            continue
        dps = fc(dt, pt, target_year)
        rows.append({"ticker": t, "forecast_dps": dps, "price": float(px),
                     "score_yield": (dps / px) if px else 0.0})
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["score_yield", "ticker"], ascending=[False, True]).reset_index(drop=True)
    return df


# ---------- step 6: realized dividend PER SHARE for one ticker in the chosen half (backtest truth) --
def half_window(year, half="H2"):
    """(start, end) timestamps of the chosen half of `year`. H1 = Jan-Jun, H2 = Jul-Dec."""
    if half == "H1":
        return pd.Timestamp(year, 1, 1), pd.Timestamp(year, 6, 30)
    return pd.Timestamp(year, 7, 1), pd.Timestamp(year, 12, 31)


def realized_h2_dps(divs_t, entry, year, today=None, half="H2"):
    """Actual dividend per share for one ticker in the chosen half: ex-date strictly AFTER entry
    (bought-ex, same rule as engine.py) and on/before the half's last day. Split by `today` (C.TODAY):
      ex-date <= today  -> counted in realized_dps
      ex-date >  today  -> future/unknown -> pending
    pending is also True whenever the half has not fully elapsed (half-end after today).
    Returns realized_dps (baht/share), pending flag, and counts."""
    today = C.TODAY if today is None else today
    _, end = half_window(year, half)
    win = divs_t[(divs_t["ex_dividend_date"] > entry) & (divs_t["ex_dividend_date"] <= end)]
    paid = win[win["ex_dividend_date"] <= today]
    future = win[win["ex_dividend_date"] > today]
    return {"realized_dps": float(paid["dps_amount"].sum()),
            "pending": bool(end > today or len(future) > 0),
            "n_paid": int(len(paid)), "n_pending_or_unknown": int(len(future))}


def half_entry_date(prices, year, half="H2"):
    """First actual trading day on/after the start of the chosen half of `year` (H2 -> Jul 1)."""
    month = 7 if half == "H2" else 1
    days = prices["date"]
    after = days[days >= pd.Timestamp(year, month, 1)]
    return after.min() if not after.empty else None


# ---------- top-level: one entry ----------
def run(entry_date, method, universe=None, capital=None, commission=COMMISSION):
    """Full single-entry pass: score universe -> greedy weights -> real shares -> expected H2
    dividend. Returns a dict the UI can render directly."""
    capital = C.CAPITAL if capital is None else capital
    prices = C.load_prices()
    divs = C.load_dividends()
    entry = pd.Timestamp(entry_date)
    target_year = entry.year
    half = "H2" if entry.month >= 7 else "H1"
    ranking = score_universe(divs, prices, entry, target_year, method, universe)
    scores = dict(zip(ranking["ticker"], ranking["score_yield"]))
    weights = greedy_allocate(scores)
    price_map = dict(zip(ranking["ticker"], ranking["price"]))
    dps_map = dict(zip(ranking["ticker"], ranking["forecast_dps"]))
    shares = to_shares(weights, price_map, capital, commission)
    shares["forecast_dps"] = shares["ticker"].map(dps_map)
    shares["expected_dividend"] = shares["shares"] * shares["forecast_dps"]
    # actual dividend that has already gone ex in this half (per stock); pending until the half elapses
    rz = [realized_h2_dps(divs[divs["ticker"] == t], entry, target_year, C.TODAY, half)
          for t in shares["ticker"]]
    shares["realized_dividend"] = [s * info["realized_dps"] for s, info in zip(shares["shares"], rz)]
    shares["realized_pending"] = [info["pending"] for info in rz]
    total_cost = float(shares["total_cost"].sum())
    return {
        "entry_date": entry, "target_year": target_year, "method": method, "half": half,
        "ranking": ranking, "weights": weights, "portfolio": shares,
        "expected_dividend": float(shares["expected_dividend"].sum()),
        "commission_total": float(shares["commission_paid"].sum()),
        "invested": float(shares["invest_value"].sum()),
        "leftover_cash": capital - total_cost, "capital": capital,
    }


# ---------- top-level: multi-year backtest ----------
def run_backtest(years, method, half="H2", universe=None, capital=None, commission=COMMISSION):
    """Decide the portfolio at each year's H2 entry (walk-forward) and measure the dividend that
    actually landed. Fully-elapsed years show realized baht; the in-progress year shows what has
    paid so far and flags the rest pending. One row per year."""
    capital = C.CAPITAL if capital is None else capital
    prices = C.load_prices()
    divs = C.load_dividends()
    out = []
    for y in years:
        entry = half_entry_date(prices, y, half)
        if entry is None:
            continue
        r = run(entry, method, universe, capital, commission)
        port = r["portfolio"]
        realized_baht, any_pending, chosen = 0.0, False, []
        for _, row in port.iterrows():
            if row["shares"] <= 0:
                continue
            chosen.append(row["ticker"])
            dt = divs[divs["ticker"] == row["ticker"]]
            rz = realized_h2_dps(dt, entry, y, C.TODAY, half)
            realized_baht += row["shares"] * rz["realized_dps"]
            any_pending = any_pending or rz["pending"]
        out.append({
            "year": y, "entry_date": entry.date().isoformat(), "method": method,
            "stocks": ", ".join(chosen),
            "expected_dividend": r["expected_dividend"],
            "realized_dividend": realized_baht,
            "realized_pct": realized_baht / capital * 100.0,
            "status": "pending" if any_pending else "realized",
        })
    return pd.DataFrame(out)


# ================= self-tests (run: python3 optimizer.py) =================
if __name__ == "__main__":
    ok = True
    prices = C.load_prices()
    divs = C.load_dividends()

    # ---- 1) forecast regression vs hand-computed 2023 numbers (entry 2023-07-03) ----
    print("== forecast avg3y, target 2023 (expect PTT=1.10, OR=0.39, KTB=0.00, TTB=0.00) ==")
    expect = {"PTT": 1.10, "OR": 0.39, "KTB": 0.00, "TTB": 0.00}
    for t, exp in expect.items():
        pt = prices[prices["ticker"] == t]
        dt = divs[divs["ticker"] == t]
        got = forecast_avg3y(dt, pt, 2023)
        good = abs(got - exp) < 1e-4
        ok &= good
        print(f"   {t:5s} got={got:.4f} expect={exp:.4f} {'OK' if good else 'BAD'}")

    # ---- 2) greedy_allocate: sum=1, bounds, count, corner shape ----
    print("== greedy_allocate ==")
    sc = {"A": 9, "B": 8, "C": 7, "D": 6, "E": 5, "F": 4, "G": 3}
    w = greedy_allocate(sc)
    s = sum(w.values())
    oksum = abs(s - 1.0) < 1e-9
    okbound = all(FLOOR - 1e-9 <= v <= CEILING + 1e-9 for v in w.values())
    okcount = len(w) >= MIN_STOCKS
    # corner solution: as many names as possible at the ceiling, the remainder poured into one, rest at floor
    n_ceiling = sum(1 for v in w.values() if abs(v - CEILING) < 1e-9)
    n_floor = sum(1 for v in w.values() if abs(v - FLOOR) < 1e-9)
    okcorner = n_ceiling >= 1 and (n_ceiling + n_floor) >= len(w) - 1
    ok &= oksum and okbound and okcount and okcorner
    print(f"   sum={s:.6f} {'OK' if oksum else 'BAD'} | bounds {'OK' if okbound else 'BAD'} | "
          f"count={len(w)} {'OK' if okcount else 'BAD'} | corner {'OK' if okcorner else 'BAD'}")
    print("   ", {k: round(v, 3) for k, v in sorted(w.items(), key=lambda kv: -kv[1])})
    # tie-break determinism (equal scores -> alphabetical): the ceiling names must be the first ones
    w_tie = greedy_allocate({t: 1.0 for t in ["E", "D", "C", "B", "A", "F"]})
    n_ceil = sum(1 for v in w_tie.values() if abs(v - CEILING) < 1e-9)
    tie_ceiling = sorted([t for t, v in w_tie.items() if abs(v - CEILING) < 1e-9])
    oktie = tie_ceiling == sorted(w_tie)[:n_ceil]
    ok &= oktie
    print(f"   tie-break alphabetical (ceiling names first): {'OK' if oktie else 'BAD'} ({tie_ceiling})")

    # ---- 3) to_shares: money conservation + lot multiples ----
    print("== to_shares ==")
    pmap = {"PTT": 33.5, "OR": 21.1, "BAY": 30.75, "BBL": 159.5, "PTTEP": 151.5}
    ws = greedy_allocate({"PTT": 5, "OR": 4, "BAY": 3, "BBL": 2, "PTTEP": 1})
    tdf = to_shares(ws, pmap, capital=100_000_000)
    leftover = 100_000_000 - tdf["total_cost"].sum()
    conserve = abs(tdf["invest_value"].sum() + tdf["commission_paid"].sum() + leftover - 100_000_000) < 1e-3
    lots = all(int(x) % LOT_SIZE == 0 for x in tdf["shares"])
    within = all(tdf["total_cost"] <= tdf["target_weight"] * 100_000_000 + 1e-6)
    ok &= conserve and lots and within
    print(f"   invest+comm+leftover==capital {'OK' if conserve else 'BAD'} | lots {'OK' if lots else 'BAD'} | "
          f"total_cost<=target {'OK' if within else 'BAD'} | leftover={leftover:,.0f}")

    # ---- 4) run() at 2023-07-03, all 3 methods ----
    print("== run() entry 2023-07-03 ==")
    for m in METHODS:
        r = run("2023-07-03", m)
        picked = [row.ticker for row in r["portfolio"].itertuples() if row.shares > 0]
        okrun = (abs(sum(r["weights"].values()) - 1.0) < 1e-9 and len(picked) >= MIN_STOCKS
                 and r["leftover_cash"] >= -1e-6 and r["expected_dividend"] >= 0)
        ok &= okrun
        print(f"   [{m:8s}] picks={picked} exp_div={r['expected_dividend']:,.0f} "
              f"({r['expected_dividend']/r['capital']*100:.2f}%) leftover={r['leftover_cash']:,.0f} "
              f"{'OK' if okrun else 'BAD'}")

    # ---- 5) backtest 2023-2026: past years realized, 2026 pending ----
    print("== run_backtest 2023-2026 (avg3y) ==")
    bt = run_backtest([2023, 2024, 2025, 2026], "avg3y")
    for row in bt.itertuples():
        print(f"   {row.year}: {row.status:8s} realized={row.realized_dividend:,.0f} "
              f"({row.realized_pct:.2f}%) exp={row.expected_dividend:,.0f} | {row.stocks}")
    okstatus = (bt.set_index("year").loc[[2023, 2024, 2025], "status"] == "realized").all() \
        and bt.set_index("year").loc[2026, "status"] == "pending"
    ok &= bool(okstatus)
    print(f"   2023-25 realized & 2026 pending: {'OK' if okstatus else 'BAD'}")

    print("\nALL TESTS", "PASS" if ok else "FAIL")

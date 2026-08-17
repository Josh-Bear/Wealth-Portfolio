"""
data/market_data.py — ราคา, จำนวนหุ้น, market cap
==================================================
  fetch_prices()              -> (adj_close, raw_close) รายเดือน (DataFrame: index=เดือน, cols=ticker)
  fetch_shares_outstanding()  -> DataFrame รายปี (index=fiscal year-end, cols=ticker) จาก balance sheet
  compute_market_cap()        -> market cap ณ วันที่หนึ่ง = ราคา(unadjusted) × shares ล่าสุดที่ประกาศ

หลักการ:
  - return  ใช้ Adj Close (รวมปันผล/แตกพาร์) เพื่อสะท้อน total return
  - market cap ใช้ raw Close × shares (ไม่ใช้ Adj Close เพราะจะบิด mcap ในอดีต)
  - shares มาจาก annual balance sheet ('Ordinary Shares Number') — point-in-time รายปี
"""

from __future__ import annotations

import os
import warnings

import pandas as pd
import yfinance as yf

import config

warnings.simplefilter("ignore")

_SHARES_ROWS = ["Ordinary Shares Number", "Share Issued", "Common Stock Shares Outstanding"]


def _cache_path(name: str) -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR, name)


def fetch_prices(tickers: list[str], use_cache: bool = True
                 ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    ดึงราคารายเดือนของทุก ticker (period=LOOKBACK_YEARS ปี)
    คืน (adj_close, raw_close) ทั้งคู่เป็น DataFrame index=month-end, columns=ticker
    """
    adj_p, raw_p = _cache_path("adj_close.csv"), _cache_path("raw_close.csv")
    if use_cache and os.path.exists(adj_p) and os.path.exists(raw_p):
        adj = pd.read_csv(adj_p, index_col=0, parse_dates=True)
        raw = pd.read_csv(raw_p, index_col=0, parse_dates=True)
        return adj, raw

    df = yf.download(
        tickers, period=f"{config.LOOKBACK_YEARS}y", interval=config.PRICE_INTERVAL,
        auto_adjust=False, progress=False, threads=True, group_by="ticker",
    )
    adj, raw = {}, {}
    for t in tickers:
        try:
            sub = df[t]
        except KeyError:
            continue
        if "Adj Close" in sub and sub["Adj Close"].notna().any():
            adj[t] = sub["Adj Close"]
            raw[t] = sub["Close"]
    adj_df = pd.DataFrame(adj).dropna(how="all")
    raw_df = pd.DataFrame(raw).dropna(how="all")
    adj_df.to_csv(adj_p)
    raw_df.to_csv(raw_p)
    return adj_df, raw_df


def fetch_shares_outstanding(tickers: list[str], use_cache: bool = True) -> pd.DataFrame:
    """
    ดึงจำนวนหุ้นรายปีจาก annual balance sheet ของแต่ละ ticker
    คืน DataFrame: index = fiscal year-end (datetime), columns = ticker, value = shares
    """
    path = _cache_path("shares.csv")
    if use_cache and os.path.exists(path):
        return pd.read_csv(path, index_col=0, parse_dates=True)

    series = {}
    for t in tickers:
        try:
            bs = yf.Ticker(t).balance_sheet  # annual
            if bs is None or bs.empty:
                continue
            row = next((r for r in _SHARES_ROWS if r in bs.index), None)
            if row is None:
                continue
            s = bs.loc[row].dropna()
            s.index = pd.to_datetime(s.index)
            series[t] = s.astype(float)
        except Exception:
            continue
    out = pd.DataFrame(series).sort_index()
    out.to_csv(path)
    return out


def _latest_asof(annual_df: pd.DataFrame, ticker: str, when: pd.Timestamp,
                 lag_months: int) -> float | None:
    """
    ค่ารายปีล่าสุดของ ticker ที่ 'ประกาศแล้ว' ณ วันที่ when
    (fiscal year-end + lag_months <= when) — กัน look-ahead
    """
    if ticker not in annual_df.columns:
        return None
    col = annual_df[ticker].dropna()
    if col.empty:
        return None
    usable = col[col.index + pd.DateOffset(months=lag_months) <= when]
    if usable.empty:
        return None
    return float(usable.iloc[-1])


def compute_market_cap(raw_close: pd.DataFrame, shares: pd.DataFrame,
                       when: pd.Timestamp) -> pd.Series:
    """
    market cap ของทุกหุ้น ณ วัน rebalance `when`
      = ราคา(unadjusted) ล่าสุด <= when  ×  shares ล่าสุดที่ประกาศแล้ว (annual, lag)
    คืน Series (index=ticker) เฉพาะหุ้นที่มีทั้งราคาและ shares
    """
    prices_upto = raw_close[raw_close.index <= when]
    if prices_upto.empty:
        return pd.Series(dtype=float)
    last_price = prices_upto.iloc[-1]

    caps = {}
    for t in raw_close.columns:
        p = last_price.get(t)
        if p is None or pd.isna(p):
            continue
        sh = _latest_asof(shares, t, when, config.REPORT_LAG_MONTHS)
        if sh is None or sh <= 0:
            continue
        caps[t] = float(p) * sh
    return pd.Series(caps, name="market_cap")

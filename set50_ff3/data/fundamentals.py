"""
data/fundamentals.py — Book Equity (annual)
===========================================
  fetch_book_equity()  -> DataFrame รายปี (index=fiscal year-end, cols=ticker)
  book_to_market()     -> B/M ณ วัน rebalance = BE(annual, lag) / market cap(when)

Known simplification (Open Item #4): ใช้ 'Stockholders Equity' ตรงๆ จาก yfinance
โดยไม่ปรับ deferred tax / ITC / preferred stock แยก — ผลต่อ B/M ของหุ้นไทยส่วนใหญ่
น่าจะเล็กน้อย (ไม่ค่อยมี preferred stock ซับซ้อน)

เหตุผลที่ใช้ "annual" ไม่ใช่ "quarterly": probe พบว่า quarterly_balance_sheet ให้แค่
~6 ไตรมาส แต่ annual ลึก 4-5 ปี พอดีกับ backtest window (ตรงแนว FF ต้นฉบับที่ใช้
book equity ปลายปีบัญชี ถือทั้งปี)
"""

from __future__ import annotations

import os
import warnings

import pandas as pd
import yfinance as yf

import config
from data.market_data import _cache_path, _latest_asof

warnings.simplefilter("ignore")

_EQUITY_ROWS = [
    "Stockholders Equity",
    "Total Stockholders Equity",
    "Common Stock Equity",
    "Total Equity Gross Minority Interest",
]


def fetch_book_equity(tickers: list[str], use_cache: bool = True) -> pd.DataFrame:
    """
    ดึง Book Equity รายปีจาก annual balance sheet ของแต่ละ ticker
    คืน DataFrame: index = fiscal year-end, columns = ticker, value = stockholders equity
    """
    path = _cache_path("book_equity.csv")
    if use_cache and os.path.exists(path):
        return pd.read_csv(path, index_col=0, parse_dates=True)

    series = {}
    for t in tickers:
        try:
            bs = yf.Ticker(t).balance_sheet  # annual
            if bs is None or bs.empty:
                continue
            row = next((r for r in _EQUITY_ROWS if r in bs.index), None)
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


def book_to_market(book_equity: pd.DataFrame, market_caps: pd.Series,
                   when: pd.Timestamp) -> pd.Series:
    """
    B/M ของทุกหุ้น ณ วัน rebalance `when`
      = Book Equity รายปีล่าสุดที่ประกาศแล้ว (lag)  /  market cap ณ when
    คืน Series (index=ticker) เฉพาะหุ้นที่มีทั้ง BE (>0) และ market cap
    """
    bm = {}
    for t in market_caps.index:
        be = _latest_asof(book_equity, t, when, config.REPORT_LAG_MONTHS)
        if be is None or be <= 0:
            continue
        mc = market_caps.get(t)
        if mc is None or mc <= 0:
            continue
        bm[t] = be / mc
    return pd.Series(bm, name="book_to_market")

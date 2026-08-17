"""
pipeline.py — orchestrate: annual (June) rebalance -> monthly factor series
===========================================================================
ลำดับ (ตาม Pipeline Logic ข้อ 5 ของแผน, ปรับ reform เป็นรายปีเดือน มิ.ย.):
  1. โหลด universe + ราคา + shares + book equity
  2. หา rebalance date = ทุกเดือน "มิถุนายน" (FF ต้นฉบับ); ที่แต่ละ date -> freeze
     membership (หุ้นไหนอยู่พอร์ตไหน) + formation mcap (ใช้เป็น value-weight)
  3. ทุกเดือน: ใช้ membership ที่ freeze ไว้ (formation < month) -> คำนวณ 6 portfolio
     returns (value-weighted) -> SMB, HML, Mkt-RF
  4. ต่อ time series รายเดือนออกมา + เก็บ portfolio returns 6 พอร์ต + ตาราง membership

จุดสำคัญ: membership freeze ตั้งแต่ ก.ค. ปี t → มิ.ย. ปี t+1; return ของเดือน m ใช้
membership จาก rebalance ก่อนหน้า (formation < m) -> กัน look-ahead
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

import config
from data.constituents import get_set50_constituents
from data.fundamentals import book_to_market, fetch_book_equity
from data.market_data import compute_market_cap, fetch_prices, fetch_shares_outstanding
from data.risk_free import fetch_risk_free_rate
from factors.hml import compute_hml
from factors.market_factor import compute_market_factor, universe_value_weighted_return
from factors.portfolios import PORTFOLIO_LABELS, compute_portfolio_return, form_six_portfolios
from factors.size_factor import assign_size_group
from factors.smb import compute_smb
from factors.value_factor import assign_value_group

MIN_STOCKS_PER_REBALANCE = 20   # ต้องมีหุ้นพร้อมข้อมูลอย่างน้อยเท่านี้จึง form พอร์ต


@dataclass
class PipelineResult:
    """ผลลัพธ์ทั้งหมดจากการรัน pipeline หนึ่งครั้ง (fetch ครั้งเดียว ใช้ต่อได้หลายมุม)"""
    factors: pd.DataFrame          # index=month, cols=[Mkt-RF, SMB, HML, RF, Univ]
    portfolio_returns: pd.DataFrame  # index=month, cols=[SG,SN,SV,BG,BN,BV]
    memberships: dict              # rebalance_date -> {'labels': Series, 'caps': Series}


def _rebalance_dates(months: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """วัน rebalance = ทุกเดือนมิถุนายน (reform รายปีแบบ FF ต้นฉบับ)"""
    return [m for m in months if m.month == config.REBALANCE_MONTH]


def _build_memberships(rebal_dates, raw_close, shares, book_equity):
    """
    ที่แต่ละ rebalance date (มิ.ย.): mcap + B/M -> size/value group -> 6 portfolios
    คืน dict: date -> {'labels': Series(ticker->'SV'..), 'caps': Series(ticker->mcap)}
    ข้าม date ที่หุ้นพร้อมข้อมูลน้อยกว่า MIN_STOCKS_PER_REBALANCE
    """
    memberships = {}
    for d in rebal_dates:
        caps = compute_market_cap(raw_close, shares, d)
        bm = book_to_market(book_equity, caps, d)
        if len(bm) < MIN_STOCKS_PER_REBALANCE:
            continue
        caps_bm = caps.reindex(bm.index)
        size = assign_size_group(caps_bm)
        value = assign_value_group(bm)
        labels = form_six_portfolios(size, value)
        if labels.empty:
            continue
        memberships[d] = {"labels": labels, "caps": caps_bm}
    return memberships


def _formation_for(month, rebal_sorted):
    """หา rebalance date ล่าสุดที่ 'ก่อน' เดือน month (กัน look-ahead)"""
    prior = [d for d in rebal_sorted if d < month]
    return prior[-1] if prior else None


def run(use_cache: bool = True) -> PipelineResult:
    """รัน pipeline ครบวงจร -> PipelineResult (factors + 6-port returns + memberships)"""
    tickers = get_set50_constituents()
    adj_close, raw_close = fetch_prices(tickers, use_cache=use_cache)
    shares = fetch_shares_outstanding(tickers, use_cache=use_cache)
    book_equity = fetch_book_equity(tickers, use_cache=use_cache)

    returns = adj_close.pct_change()               # monthly simple returns
    months = returns.index

    rebal_dates = _rebalance_dates(months)
    memberships = _build_memberships(rebal_dates, raw_close, shares, book_equity)
    rebal_sorted = sorted(memberships.keys())
    if not rebal_sorted:
        raise RuntimeError("ไม่มี rebalance date (มิ.ย.) ที่ form พอร์ตได้ — ตรวจ data availability")

    rf_series = fetch_risk_free_rate(months)

    factor_rows, port_rows = {}, {}
    for m in months:
        f = _formation_for(m, rebal_sorted)
        if f is None:
            continue
        mem = memberships[f]
        labels, caps = mem["labels"], mem["caps"]
        r_m = returns.loc[m]

        port_ret = {
            lab: compute_portfolio_return(r_m, caps, labels, lab)
            for lab in PORTFOLIO_LABELS
        }
        smb = compute_smb(port_ret)
        hml = compute_hml(port_ret)
        univ = universe_value_weighted_return(r_m, caps)
        rf = rf_series.loc[m]
        mkt_rf = compute_market_factor(univ, rf)

        factor_rows[m] = {"Mkt-RF": mkt_rf, "SMB": smb, "HML": hml, "RF": rf, "Univ": univ}
        port_rows[m] = port_ret

    factors = pd.DataFrame.from_dict(factor_rows, orient="index")
    factors = factors.dropna(subset=["Mkt-RF", "SMB", "HML"])
    factors.index.name = "month"

    port_returns = pd.DataFrame.from_dict(port_rows, orient="index")[PORTFOLIO_LABELS]
    port_returns = port_returns.reindex(factors.index)   # align กับเดือนที่มี factor ครบ
    port_returns.index.name = "month"

    return PipelineResult(factors=factors, portfolio_returns=port_returns,
                          memberships=memberships)


def build_factors(use_cache: bool = True) -> pd.DataFrame:
    """เข้ากันได้ย้อนหลัง: คืนเฉพาะ factor DataFrame (ใช้โดย regression/main)"""
    return run(use_cache=use_cache).factors


def save_factors(factors: pd.DataFrame, path: str = "factors_monthly.csv") -> str:
    factors.to_csv(path)
    return path


if __name__ == "__main__":
    res = run()
    f = res.factors
    print(f"factor months: {len(f)}  ({f.index.min().date()} → {f.index.max().date()})")
    print(f.round(4).to_string())
    print("\nsaved ->", save_factors(f))

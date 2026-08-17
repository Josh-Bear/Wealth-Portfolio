"""
factors/market_factor.py — Market factor (Mkt-RF)
=================================================
ยืนยันแล้ว: คำนวณเองจาก value-weighted return ของ 50 หุ้น − rf
(^SET50.BK ไม่มี history ใน yfinance) -> internal consistency กับ universe เดียวกับ SMB/HML
"""

from __future__ import annotations

import math

import pandas as pd


def universe_value_weighted_return(returns: pd.Series, market_caps: pd.Series) -> float:
    """
    Value-weighted return ของทั้ง universe (ทุกหุ้นที่มีข้อมูล) ในเดือนหนึ่ง
    ถ่วงด้วย market cap ณ วัน formation ที่ freeze ไว้ทั้งไตรมาส
    """
    r = returns.reindex(market_caps.index)
    w = market_caps
    valid = r.notna() & w.notna() & (w > 0)
    if not valid.any():
        return float("nan")
    r, w = r[valid], w[valid]
    return float((w / w.sum() * r).sum())


def compute_market_factor(set50_universe_return: float, risk_free: float) -> float:
    """Mkt-RF = value-weighted return ของหุ้นทั้ง universe − risk free"""
    if set50_universe_return is None or math.isnan(set50_universe_return):
        return float("nan")
    return set50_universe_return - risk_free

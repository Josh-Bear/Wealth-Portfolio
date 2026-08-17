"""
factors/portfolios.py — ประกอบ 6 พอร์ต (2x3) และคำนวณผลตอบแทน value-weighted
==========================================================================
  form_six_portfolios()      -> label ต่อหุ้น: 'SG','SN','SV','BG','BN','BV'
  compute_portfolio_return() -> value-weighted return ของพอร์ตเป้าหมายในเดือนหนึ่ง
"""

from __future__ import annotations

import pandas as pd

# map (size, value) -> รหัส 2 ตัวอักษร
_SIZE_CODE = {"Small": "S", "Big": "B"}
_VALUE_CODE = {"Growth": "G", "Neutral": "N", "Value": "V"}

PORTFOLIO_LABELS = ["SG", "SN", "SV", "BG", "BN", "BV"]


def form_six_portfolios(size_group: pd.Series, value_group: pd.Series) -> pd.Series:
    """
    Intersect size x value -> คืน Series label เช่น 'SV' ต่อหุ้น
    (เฉพาะหุ้นที่มีทั้ง size และ value group)
    """
    common = size_group.index.intersection(value_group.index)
    labels = {}
    for t in common:
        s = _SIZE_CODE.get(size_group[t])
        v = _VALUE_CODE.get(value_group[t])
        if s and v:
            labels[t] = s + v
    return pd.Series(labels, name="portfolio")


def compute_portfolio_return(returns: pd.Series, market_caps: pd.Series,
                             portfolio_label: pd.Series, target: str) -> float:
    """
    Value-weighted return ของพอร์ต `target` (เช่น 'SV') ในเดือนนั้น
      = Σ (w_i × r_i),  w_i = mcap_i / Σ mcap  (เฉพาะหุ้นในพอร์ต target)
    ถ่วงด้วย market cap ณ วัน formation (freeze ทั้งไตรมาส) ที่ caller ส่งเข้ามา
    คืน NaN ถ้าพอร์ตว่างหรือไม่มี return/mcap ที่ใช้ได้
    """
    members = portfolio_label[portfolio_label == target].index
    if len(members) == 0:
        return float("nan")

    r = returns.reindex(members)
    w = market_caps.reindex(members)
    valid = r.notna() & w.notna() & (w > 0)
    if not valid.any():
        return float("nan")

    r, w = r[valid], w[valid]
    return float((w / w.sum() * r).sum())

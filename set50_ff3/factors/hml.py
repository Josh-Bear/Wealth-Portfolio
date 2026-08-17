"""factors/hml.py — HML (High Minus Low)"""

from __future__ import annotations

import math


def compute_hml(portfolio_returns: dict) -> float:
    """
    HML = 1/2(SV+BV) − 1/2(SG+BG)
    portfolio_returns: dict {'SV':.., 'BV':.., 'SG':.., 'BG':..} ของเดือนหนึ่ง
    คืน NaN ถ้ามีพอร์ตใดขาด
    """
    high = [portfolio_returns.get(k) for k in ("SV", "BV")]
    low = [portfolio_returns.get(k) for k in ("SG", "BG")]
    vals = high + low
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in vals):
        return float("nan")
    return sum(high) / 2.0 - sum(low) / 2.0

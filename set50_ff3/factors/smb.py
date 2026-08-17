"""factors/smb.py — SMB (Small Minus Big)"""

from __future__ import annotations

import math


def compute_smb(portfolio_returns: dict) -> float:
    """
    SMB = 1/3(SV+SN+SG) − 1/3(BV+BN+BG)
    portfolio_returns: dict {'SV':.., 'SN':.., ...} ของเดือนหนึ่ง
    คืน NaN ถ้ามีพอร์ตใดขาด (คำนวณไม่ครบ)
    """
    small = [portfolio_returns.get(k) for k in ("SV", "SN", "SG")]
    big = [portfolio_returns.get(k) for k in ("BV", "BN", "BG")]
    vals = small + big
    if any(v is None or (isinstance(v, float) and math.isnan(v)) for v in vals):
        return float("nan")
    return sum(small) / 3.0 - sum(big) / 3.0

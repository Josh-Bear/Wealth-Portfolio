"""factors/value_factor.py — แบ่งกลุ่มคุณค่า (Growth/Neutral/Value) ตาม B/M"""

from __future__ import annotations

import pandas as pd

import config


def assign_value_group(book_to_market: pd.Series) -> pd.Series:
    """
    รับ B/M ของหุ้น ณ วัน rebalance หนึ่ง -> คืน Series label 'Growth'/'Neutral'/'Value'
    breakpoint 30/40/30 คำนวณจาก universe เอง (SET50 = universe ทั้งหมดในตัวมันเอง
    ไม่มี NYSE-equivalent ให้อ้างอิงแยก):
        B/M < 30th pct          -> Growth
        30th <= B/M < 70th pct  -> Neutral
        B/M >= 70th pct         -> Value
    """
    bm = book_to_market.dropna()
    if bm.empty:
        return pd.Series(dtype=object)
    lo = bm.quantile(config.VALUE_LOW_PCT)
    hi = bm.quantile(config.VALUE_HIGH_PCT)

    def label(x: float) -> str:
        if x < lo:
            return "Growth"
        if x >= hi:
            return "Value"
        return "Neutral"

    return pd.Series([label(x) for x in bm], index=bm.index, name="value")

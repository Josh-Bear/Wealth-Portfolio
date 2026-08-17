"""factors/size_factor.py — แบ่งกลุ่มขนาด (Small/Big) ตาม market cap"""

from __future__ import annotations

import pandas as pd

import config


def assign_size_group(market_caps: pd.Series) -> pd.Series:
    """
    รับ market cap ของหุ้น ณ วัน rebalance หนึ่ง -> คืน Series label 'Small'/'Big'
    Big   = rank 1..SIZE_BIG_RANK_CUTOFF (mcap มาก -> น้อย)
    Small = rank ที่เหลือ
    (ใช้ rank เพื่อกันปัญหาเมื่อจำนวนหุ้นที่มีข้อมูล < 50; แบ่งครึ่งตาม cutoff ตามสัดส่วน)
    """
    mc = market_caps.dropna()
    if mc.empty:
        return pd.Series(dtype=object)
    # rank 1 = ใหญ่สุด
    rank = mc.rank(ascending=False, method="first")
    cutoff = config.SIZE_BIG_RANK_CUTOFF
    # ถ้าหุ้นน้อยกว่า 50 ให้แบ่งครึ่งตามสัดส่วนแทน hard-coded 25
    if len(mc) < 2 * cutoff:
        cutoff = len(mc) / 2.0
    return pd.Series(["Big" if r <= cutoff else "Small" for r in rank],
                     index=mc.index, name="size")

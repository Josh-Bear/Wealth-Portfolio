"""
significance/subperiod.py — Sub-period split (early vs recent)
=============================================================
ทดสอบ #2 (ตามแผน): premium ยัง "คงอยู่ในช่วงล่าสุด" ไหม หรือจางไปแล้ว

ข้อจำกัด (section 3 ของแผน): ข้อมูลจริง 38 เดือน -> median split ได้ ~19/19 เดือน
statistical power ต่ำ ต้องตีความ p-value อย่างระมัดระวัง
"""

from __future__ import annotations

import pandas as pd

from significance.basic_test import test_all_factors


def split_subperiods(factors_df: pd.DataFrame,
                     split_date: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    แบ่งเป็น (early, recent)
      - ถ้าระบุ split_date: early = index < split_date, recent = index >= split_date
      - ถ้าไม่ระบุ: median split ตามจำนวนแถว (ครึ่งแรก/ครึ่งหลัง)
    """
    df = factors_df.sort_index()
    if split_date is not None:
        cut = pd.Timestamp(split_date)
        early = df[df.index < cut]
        recent = df[df.index >= cut]
    else:
        mid = len(df) // 2
        early = df.iloc[:mid]
        recent = df.iloc[mid:]
    return early, recent


def compare_subperiods(factors_df: pd.DataFrame,
                       split_date: str | None = None,
                       columns=("Mkt-RF", "SMB", "HML")) -> pd.DataFrame:
    """
    รัน test_all_factors() บน full / early / recent แล้วเทียบข้างกันในตารางเดียว
    คอลัมน์: factor | period | n | mean | t_stat | p_value | significant_05
    """
    early, recent = split_subperiods(factors_df, split_date)
    frames = {"full_sample": factors_df, "early_period": early, "recent_period": recent}

    out = []
    for period, sub in frames.items():
        t = test_all_factors(sub, columns=columns)
        t.insert(1, "period", period)
        out.append(t)

    res = pd.concat(out, ignore_index=True)
    # จัดเรียงให้ factor เดียวกันอยู่ติดกัน (full -> early -> recent)
    order = {"full_sample": 0, "early_period": 1, "recent_period": 2}
    res["_o"] = res["period"].map(order)
    res = res.sort_values(["factor", "_o"]).drop(columns="_o").reset_index(drop=True)
    return res[["factor", "period", "n", "mean", "t_stat", "p_value", "significant_05", "sig"]]

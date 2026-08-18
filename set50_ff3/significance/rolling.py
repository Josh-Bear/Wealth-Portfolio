"""
significance/rolling.py — Rolling-window t-stat
===============================================
ทดสอบ #3 (ตามแผน): ดูแนวโน้มความแข็งแรงของ premium ต่อเนื่องตามเวลา (ไม่ใช่แค่ 2 จุด)

ข้อจำกัด (section 3): ข้อมูล 38 เดือน + window 24 + step 3 -> เหลือแค่ ~5 จุด
เห็นเป็น "ไม่กี่จุด" ไม่ใช่เส้น smooth เหมือนงานวิจัยข้อมูล 90+ ปี — ตีความตามนั้น
"""

from __future__ import annotations

import pandas as pd

from significance.basic_test import one_sample_ttest


def rolling_tstat(factor_series: pd.Series, window: int = 24, step: int = 3) -> pd.Series:
    """
    เลื่อนหน้าต่างขนาด window เดือน ทีละ step เดือน -> t-stat ต่อจุด
    index ของผลลัพธ์ = วันที่สิ้นสุด (เดือนสุดท้าย) ของแต่ละ window
    คืน Series ว่างถ้าข้อมูลสั้นกว่า window
    """
    x = pd.Series(factor_series).dropna().astype(float).sort_index()
    n = len(x)
    if n < window:
        return pd.Series(dtype=float, name=f"{factor_series.name}_tstat")

    points = {}
    start = 0
    while start + window <= n:
        win = x.iloc[start:start + window]
        points[win.index[-1]] = one_sample_ttest(win)["t_stat"]
        start += step
    # ให้ window สุดท้ายที่ชิดขอบขวาเสมอถูกรวม (กันตกหล่นเพราะ step ไม่ลงตัว)
    if (n - window) % step != 0:
        win = x.iloc[n - window:n]
        points[win.index[-1]] = one_sample_ttest(win)["t_stat"]

    return pd.Series(points, name=f"{factor_series.name}_tstat").sort_index()


def rolling_tstat_all(factors_df: pd.DataFrame, window: int = 24, step: int = 3,
                      columns=("Mkt-RF", "SMB", "HML")) -> pd.DataFrame:
    """รัน rolling_tstat ทุก factor -> DataFrame (index=วันสิ้น window, cols=factor)"""
    series = {c: rolling_tstat(factors_df[c], window, step)
              for c in columns if c in factors_df.columns}
    return pd.DataFrame(series)

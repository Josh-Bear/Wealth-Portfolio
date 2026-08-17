"""
data/risk_free.py — Risk-free rate ของไทย (Open Item #3)
========================================================
ยืนยันแล้ว: ใช้ "ค่าคงที่ปรับได้" ก่อน (ยังไม่ผูก data source จริง เช่น BOT/investing.com)
-> ให้ pipeline วิ่งได้ครบก่อน แล้วค่อยต่อ endpoint จริงภายหลังโดยแทนที่ฟังก์ชันนี้

แปลงอัตราต่อปี -> รายเดือนแบบ compounding: rf_month = (1+annual)^(1/12) − 1
"""

from __future__ import annotations

import pandas as pd

import config


def monthly_risk_free(annual_rate: float | None = None) -> float:
    """คืน risk-free รายเดือน (สเกลเดียวกับ monthly return) จากอัตราต่อปีคงที่"""
    r = config.RISK_FREE_ANNUAL if annual_rate is None else annual_rate
    return (1.0 + r) ** (1.0 / 12.0) - 1.0


def fetch_risk_free_rate(index: pd.DatetimeIndex,
                         annual_rate: float | None = None) -> pd.Series:
    """
    คืน Series ของ rf รายเดือน ให้ align กับ index (เดือน) ที่ pipeline ใช้
    ตอนนี้เป็นค่าคงที่ทุกเดือน — เปลี่ยนเป็น time-varying ได้โดยแก้ที่นี่ที่เดียว
    """
    rf = monthly_risk_free(annual_rate)
    return pd.Series(rf, index=index, name="rf")

"""
significance/report.py — orchestrate ทั้ง 4 การทดสอบเป็นตารางสรุปเดียว
====================================================================
build_significance_report() รวม:
  - full_sample        (basic_test.one_sample_ttest)
  - early_period       (subperiod, median split เป็น default)
  - recent_period      (subperiod)
  - newey_west_full    (robust_se, HAC-adjusted)
+ rolling t-stat (rolling.py) แนบเป็นตารางแยก (shape ต่างกัน: time series)

วิธีอ่าน (ตามแผน section 5): ดู recent_period ตอบคำถาม "ปัจจุบัน", เทียบ full_sample
ดูว่า significance เปลี่ยนไหม, ดู newey_west_full cross-check ว่า full ยัง robust หลังปรับ SE
"""

from __future__ import annotations

import pandas as pd

from significance.basic_test import _stars
from significance.robust_se import newey_west_all
from significance.rolling import rolling_tstat_all
from significance.subperiod import compare_subperiods

_COLS = ["factor", "test_type", "n", "mean", "se", "t_stat", "p_value", "significant_05", "sig"]


def build_significance_report(factors_df: pd.DataFrame,
                              split_date: str | None = None,
                              window: int = 24,
                              columns=("Mkt-RF", "SMB", "HML")) -> pd.DataFrame:
    """
    ตารางสรุปหลัก — 1 แถวต่อ (factor × test_type)
    test_type: full_sample | early_period | recent_period | newey_west_full
    """
    # --- 3 period tests (full / early / recent) มาจาก compare_subperiods ---
    sub = compare_subperiods(factors_df, split_date, columns=columns)
    sub = sub.rename(columns={"period": "test_type"})
    sub["se"] = sub["mean"] / sub["t_stat"]   # เติม se ให้ครบคอลัมน์ (se = mean/t)

    # --- Newey-West บน full sample ---
    nw = newey_west_all(factors_df, columns=columns)
    nw["test_type"] = "newey_west_full"
    nw["sig"] = nw["p_value"].apply(_stars)

    report = pd.concat([sub[_COLS], nw[_COLS]], ignore_index=True)

    # จัดเรียง: factor เดียวกันติดกัน ตามลำดับ test ที่อ่านง่าย
    order = {"full_sample": 0, "early_period": 1, "recent_period": 2, "newey_west_full": 3}
    report["_o"] = report["test_type"].map(order)
    report = (report.sort_values(["factor", "_o"])
              .drop(columns="_o").reset_index(drop=True))
    return report


def format_report(report: pd.DataFrame) -> str:
    """จัดรูปตารางให้อ่านง่าย: mean เป็น % ต่อเดือน, ปัดเลข, ใส่ ✅/❌"""
    r = report.copy()
    r["mean (%/mo)"] = (r["mean"] * 100).round(3)
    r["t_stat"] = r["t_stat"].round(2)
    r["p_value"] = r["p_value"].round(4)
    r["sig(p<0.05)"] = r["significant_05"].map({True: "✅", False: "❌"})
    show = r[["factor", "test_type", "n", "mean (%/mo)", "t_stat", "p_value", "sig(p<0.05)", "sig"]]
    return show.to_string(index=False)


def build_rolling(factors_df: pd.DataFrame, window: int = 24, step: int = 3,
                  columns=("Mkt-RF", "SMB", "HML")) -> pd.DataFrame:
    """ตาราง rolling t-stat แยก (index = วันสิ้น window, cols = factor)"""
    return rolling_tstat_all(factors_df, window=window, step=step, columns=columns)

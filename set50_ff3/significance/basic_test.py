"""
significance/basic_test.py — Full-sample one-sample t-test
==========================================================
ทดสอบ #1 (ตามแผน): factor แต่ละตัวมี premium จริงตลอดช่วงข้อมูลไหม (H0: mean = 0)

Threshold หลัก p < 0.05 (ตามแผน — ไม่ใช้ 0.001 ที่เข้มไปจนเกิด Type II error);
รายงาน significance ควบทั้ง 0.10 / 0.05 / 0.01 เพื่อบอกระดับความแข็งแรง
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats


def one_sample_ttest(factor_series: pd.Series) -> dict:
    """
    H0: mean(factor) = 0
    t = mean / (std/sqrt(n)),  dof = n-1,  p = two-sided จาก t-distribution
    std ใช้ sample std (ddof=1) ให้สอดคล้องกับ dof
    """
    x = pd.Series(factor_series).dropna().astype(float)
    n = len(x)
    if n < 2:
        return {"n": n, "mean": np.nan, "std": np.nan, "se": np.nan,
                "t_stat": np.nan, "dof": max(n - 1, 0), "p_value": np.nan}

    mean = float(x.mean())
    std = float(x.std(ddof=1))
    se = std / np.sqrt(n)
    dof = n - 1
    t_stat = mean / se if se > 0 else np.nan
    p_value = float(2 * stats.t.sf(abs(t_stat), dof)) if se > 0 else np.nan

    return {"n": n, "mean": mean, "std": std, "se": se,
            "t_stat": t_stat, "dof": dof, "p_value": p_value}


def _stars(p: float) -> str:
    """สัญลักษณ์ระดับ significance: *** <0.01, ** <0.05, * <0.10"""
    if p != p:  # NaN
        return ""
    if p < 0.01:
        return "***"
    if p < 0.05:
        return "**"
    if p < 0.10:
        return "*"
    return ""


def test_all_factors(factors_df: pd.DataFrame,
                     columns=("Mkt-RF", "SMB", "HML")) -> pd.DataFrame:
    """เรียก one_sample_ttest() วนทุก factor คืนตารางเดียว (1 แถว/factor)"""
    rows = []
    for col in columns:
        if col not in factors_df.columns:
            continue
        r = one_sample_ttest(factors_df[col])
        rows.append({
            "factor": col, "n": r["n"], "mean": r["mean"], "se": r["se"],
            "t_stat": r["t_stat"], "p_value": r["p_value"],
            "significant_05": bool(r["p_value"] < 0.05) if r["p_value"] == r["p_value"] else False,
            "sig": _stars(r["p_value"]),
        })
    return pd.DataFrame(rows)

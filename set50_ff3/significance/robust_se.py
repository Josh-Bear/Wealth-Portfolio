"""
significance/robust_se.py — Newey-West (HAC) adjusted t-test
============================================================
ทดสอบ #4 (ตามแผน): แก้ SE ที่อาจ underestimate จาก autocorrelation ของ return รายเดือน

regress factor ~ constant ด้วย HAC covariance -> coefficient = mean, t/p แบบ HAC-adjusted
maxlags default: floor(4*(n/100)^(2/9)) ตามธรรมเนียม Newey-West (1994)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm


def _default_maxlags(n: int) -> int:
    """floor(4*(n/100)^(2/9)) — Newey-West (1994) rule of thumb"""
    return int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0)))


def newey_west_ttest(factor_series: pd.Series, maxlags: int | None = None) -> dict:
    """
    เหมือน one_sample_ttest() แต่ SE/t/p เป็นเวอร์ชัน HAC-adjusted
    Implementation: y ~ const เท่านั้น (coefficient ตัวเดียว = ค่าเฉลี่ย), cov_type='HAC'
    """
    y = pd.Series(factor_series).dropna().astype(float)
    n = len(y)
    if n < 2:
        return {"n": n, "mean": np.nan, "se": np.nan, "t_stat": np.nan,
                "p_value": np.nan, "maxlags": 0}

    if maxlags is None:
        maxlags = _default_maxlags(n)

    X = np.ones((n, 1))   # คอลัมน์ค่าคงที่อย่างเดียว -> coef = mean(y)
    model = sm.OLS(y.values, X).fit(cov_type="HAC", cov_kwds={"maxlags": maxlags})

    return {
        "n": n,
        "mean": float(model.params[0]),
        "se": float(model.bse[0]),
        "t_stat": float(model.tvalues[0]),
        "p_value": float(model.pvalues[0]),
        "maxlags": int(maxlags),
    }


def newey_west_all(factors_df: pd.DataFrame,
                   columns=("Mkt-RF", "SMB", "HML")) -> pd.DataFrame:
    """รัน newey_west_ttest ทุก factor -> ตารางเดียว"""
    rows = []
    for col in columns:
        if col not in factors_df.columns:
            continue
        r = newey_west_ttest(factors_df[col])
        rows.append({
            "factor": col, "n": r["n"], "mean": r["mean"], "se": r["se"],
            "t_stat": r["t_stat"], "p_value": r["p_value"],
            "maxlags": r["maxlags"],
            "significant_05": bool(r["p_value"] < 0.05) if r["p_value"] == r["p_value"] else False,
        })
    return pd.DataFrame(rows)

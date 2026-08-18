"""
tests/test_significance.py — unit test โมดูล significance
========================================================
รัน:  python tests/test_significance.py   (หรือ python -m pytest tests/ -q)
ครอบคลุม: one_sample_ttest (ตรงกับ scipy), test_all_factors, split_subperiods,
          rolling_tstat (จำนวนจุด), newey_west_ttest (recover mean + maxlags rule)
"""

import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from significance.basic_test import one_sample_ttest
from significance.basic_test import test_all_factors as run_all_factors
from significance.robust_se import _default_maxlags, newey_west_ttest
from significance.rolling import rolling_tstat
from significance.subperiod import split_subperiods


def _series(vals, start="2020-01-01"):
    idx = pd.date_range(start, periods=len(vals), freq="MS")
    return pd.Series(vals, index=idx, name="F")


def test_one_sample_ttest_matches_scipy():
    x = _series([0.01, -0.02, 0.03, 0.00, 0.015, -0.005, 0.02, 0.01])
    r = one_sample_ttest(x)
    t_sp, p_sp = stats.ttest_1samp(x.values, 0.0)
    assert abs(r["t_stat"] - t_sp) < 1e-9
    assert abs(r["p_value"] - p_sp) < 1e-9
    assert r["n"] == 8 and r["dof"] == 7


def test_one_sample_ttest_zero_mean_not_significant():
    x = _series([0.02, -0.02, 0.02, -0.02, 0.02, -0.02])  # mean = 0
    r = one_sample_ttest(x)
    assert abs(r["mean"]) < 1e-12
    assert abs(r["t_stat"]) < 1e-9
    assert r["p_value"] > 0.99


def test_test_all_factors_shape():
    df = pd.DataFrame({
        "Mkt-RF": _series([0.05] * 10),   # ค่าเฉลี่ยชัด > 0
        "SMB": _series([0.001, -0.001] * 5),
        "HML": _series(list(np.linspace(-0.02, 0.02, 10))),
    })
    out = run_all_factors(df)
    assert list(out["factor"]) == ["Mkt-RF", "SMB", "HML"]
    assert set(["factor", "n", "mean", "t_stat", "p_value", "significant_05"]).issubset(out.columns)


def test_split_subperiods_median():
    df = pd.DataFrame({"HML": _series(list(range(38)))})  # 38 แถวเหมือนข้อมูลจริง
    early, recent = split_subperiods(df)
    assert len(early) == 19 and len(recent) == 19        # median split ~19/19
    assert early.index.max() < recent.index.min()


def test_split_subperiods_by_date():
    df = pd.DataFrame({"HML": _series(list(range(12)))})  # 2020-01 .. 2020-12
    early, recent = split_subperiods(df, split_date="2020-07-01")
    assert len(early) == 6 and len(recent) == 6


def test_rolling_tstat_point_count():
    # 38 เดือน, window 24, step 3 -> จุดควรอยู่ราว 5-6 (รวม window ชิดขอบขวา)
    x = _series(list(np.random.RandomState(0).normal(0, 0.02, 38)))
    r = rolling_tstat(x, window=24, step=3)
    assert 5 <= len(r) <= 6
    assert r.index.is_monotonic_increasing


def test_newey_west_recovers_mean_and_maxlags():
    x = _series(list(np.random.RandomState(1).normal(0.01, 0.02, 40)))
    r = newey_west_ttest(x)
    assert abs(r["mean"] - float(x.mean())) < 1e-9      # coef = ค่าเฉลี่ย
    assert r["maxlags"] == _default_maxlags(40)         # ใช้กฎ Newey-West (1994)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and getattr(v, "__module__", None) == "__main__"]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ✅ {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")

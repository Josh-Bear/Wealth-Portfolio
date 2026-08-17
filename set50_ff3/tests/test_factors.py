"""
tests/test_factors.py — unit test ระดับฟังก์ชัน (Testing & Validation ข้อ 6)
============================================================================
รัน:  python -m pytest tests/ -q        (หรือ)   python tests/test_factors.py
ครอบคลุม: assign_size_group (25/25), assign_value_group (15/20/15), form_six_portfolios,
          compute_portfolio_return, compute_smb, compute_hml
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from factors.hml import compute_hml
from factors.portfolios import compute_portfolio_return, form_six_portfolios
from factors.size_factor import assign_size_group
from factors.smb import compute_smb
from factors.value_factor import assign_value_group


def test_assign_size_group_25_25():
    # 50 หุ้น market cap = 1..50 -> Big = 25 ตัวใหญ่สุด, Small = 25 ตัวเล็กสุด
    mc = pd.Series({f"S{i}": float(i) for i in range(1, 51)})
    g = assign_size_group(mc)
    assert (g == "Big").sum() == 25
    assert (g == "Small").sum() == 25
    assert g["S50"] == "Big" and g["S1"] == "Small"


def test_assign_value_group_15_20_15():
    # 50 หุ้น B/M = 1..50 -> Growth 30% (15), Neutral 40% (20), Value 30% (15)
    bm = pd.Series({f"S{i}": float(i) for i in range(1, 51)})
    g = assign_value_group(bm)
    assert (g == "Growth").sum() == 15
    assert (g == "Neutral").sum() == 20
    assert (g == "Value").sum() == 15
    assert g["S1"] == "Growth" and g["S50"] == "Value"


def test_form_six_portfolios():
    size = pd.Series({"A": "Small", "B": "Big", "C": "Small"})
    value = pd.Series({"A": "Value", "B": "Growth", "C": "Neutral"})
    lab = form_six_portfolios(size, value)
    assert lab["A"] == "SV" and lab["B"] == "BG" and lab["C"] == "SN"


def test_compute_portfolio_return_value_weighted():
    # พอร์ต SV มี 2 หุ้น: mcap 100 (r=+10%) และ 300 (r=+2%)
    # VW = (100*0.10 + 300*0.02)/400 = (10+6)/400 = 0.04
    returns = pd.Series({"A": 0.10, "B": 0.02, "C": -0.5})
    caps = pd.Series({"A": 100.0, "B": 300.0, "C": 999.0})
    labels = pd.Series({"A": "SV", "B": "SV", "C": "BG"})
    r = compute_portfolio_return(returns, caps, labels, "SV")
    assert abs(r - 0.04) < 1e-9


def test_smb_hml_formulas():
    pr = {"SV": 0.05, "SN": 0.04, "SG": 0.03, "BV": 0.02, "BN": 0.01, "BG": 0.00}
    # SMB = 1/3(0.05+0.04+0.03) - 1/3(0.02+0.01+0.00) = 0.04 - 0.01 = 0.03
    assert abs(compute_smb(pr) - 0.03) < 1e-9
    # HML = 1/2(0.05+0.02) - 1/2(0.03+0.00) = 0.035 - 0.015 = 0.02
    assert abs(compute_hml(pr) - 0.02) < 1e-9


def test_smb_returns_nan_when_incomplete():
    import math
    assert math.isnan(compute_smb({"SV": 0.05}))  # ขาดพอร์ตอื่น


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ✅ {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {fn.__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")

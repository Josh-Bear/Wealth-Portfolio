"""
regression.py — รัน FF3 OLS กับหุ้น/พอร์ตเป้าหมาย
=================================================
ต่อยอดจากแนวสคริปต์ ff3m.py เดิม แต่เปลี่ยน factor source จาก Ken French เป็นไฟล์ที่
สร้างเองจาก pipeline นี้ (factors_monthly.csv)

โมเดล:  (R_i − RF) = α + β_MKT·(Mkt−RF) + β_SMB·SMB + β_HML·HML + ε
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
import yfinance as yf

import config

warnings.simplefilter("ignore")


def fetch_stock_excess_return(ticker: str, rf: pd.Series) -> pd.Series:
    """ดึงราคารายเดือนของหุ้นเป้าหมาย -> excess return (R − RF) align กับ rf"""
    px = yf.download(ticker, period=f"{config.LOOKBACK_YEARS}y",
                     interval=config.PRICE_INTERVAL, auto_adjust=True,
                     progress=False, threads=False)["Close"]
    if isinstance(px, pd.DataFrame):
        px = px.iloc[:, 0]
    r = px.pct_change()
    r.index = pd.to_datetime(r.index)
    aligned = r.reindex(rf.index)
    return (aligned - rf).dropna()


def run_ff3_regression(excess_return: pd.Series, factors: pd.DataFrame) -> dict:
    """
    OLS: excess_return ~ Mkt-RF + SMB + HML
    คืน dict สรุป (alpha, betas, t-stats, R²) + object ผลลัพธ์เต็ม
    """
    df = pd.concat([excess_return.rename("y"), factors[["Mkt-RF", "SMB", "HML"]]],
                   axis=1).dropna()
    if len(df) < 12:
        raise ValueError(f"ข้อมูลทับซ้อนน้อยเกินไป ({len(df)} เดือน) รัน regression ไม่ได้")

    X = sm.add_constant(df[["Mkt-RF", "SMB", "HML"]])
    model = sm.OLS(df["y"], X).fit()

    return {
        "n": int(model.nobs),
        "alpha": float(model.params["const"]),
        "alpha_t": float(model.tvalues["const"]),
        "beta_mkt": float(model.params["Mkt-RF"]),
        "beta_smb": float(model.params["SMB"]),
        "beta_hml": float(model.params["HML"]),
        "t_mkt": float(model.tvalues["Mkt-RF"]),
        "t_smb": float(model.tvalues["SMB"]),
        "t_hml": float(model.tvalues["HML"]),
        "r_squared": float(model.rsquared),
        "adj_r_squared": float(model.rsquared_adj),
        "model": model,
    }


def summarize(ticker: str, res: dict) -> str:
    return (
        f"FF3 regression — {ticker}  (n={res['n']} เดือน)\n"
        f"  alpha    = {res['alpha']:+.4f}  (t={res['alpha_t']:+.2f})  [ต่อเดือน]\n"
        f"  β_Mkt-RF = {res['beta_mkt']:+.3f}  (t={res['t_mkt']:+.2f})\n"
        f"  β_SMB    = {res['beta_smb']:+.3f}  (t={res['t_smb']:+.2f})\n"
        f"  β_HML    = {res['beta_hml']:+.3f}  (t={res['t_hml']:+.2f})\n"
        f"  R²       = {res['r_squared']:.3f}  (adj {res['adj_r_squared']:.3f})"
    )

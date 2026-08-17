"""
export_portfolios.py — ส่งออก CSV ของ 6 พอร์ต (SG SN SV BG BN BV)
==================================================================
สร้าง 2 ไฟล์:
  1) portfolios_membership.csv  — หุ้นแต่ละตัวอยู่พอร์ตไหน + weight ในพอร์ต แยกตาม
     rebalance รายปี (ทุกเดือนมิถุนายน). คอลัมน์:
        rebalance_date, year, portfolio, ticker, market_cap, weight
     weight = value-weight "ภายในพอร์ตของตัวเอง" (รวมกันในแต่ละพอร์ต = 1.0)
  2) portfolio_returns_monthly.csv — return รายเดือนของทั้ง 6 พอร์ต
        month, SG, SN, SV, BG, BN, BV

รัน:  python export_portfolios.py        (หรือผ่าน  python main.py export)
"""

from __future__ import annotations

import pandas as pd

import pipeline
from factors.portfolios import PORTFOLIO_LABELS

MEMBERSHIP_CSV = "portfolios_membership.csv"
RETURNS_CSV = "portfolio_returns_monthly.csv"


def build_membership_table(memberships: dict) -> pd.DataFrame:
    """
    แปลง memberships (rebalance_date -> {labels, caps}) เป็นตารางยาว 1 แถว/หุ้น/รอบ reform
    weight = mcap ของหุ้น / ผลรวม mcap ในพอร์ตเดียวกัน (value-weight ภายในพอร์ต)
    เรียงตาม ปี -> พอร์ต -> weight มากไปน้อย
    """
    rows = []
    for d in sorted(memberships.keys()):
        labels = memberships[d]["labels"]      # ticker -> 'SV'..
        caps = memberships[d]["caps"]          # ticker -> market cap
        for lab in PORTFOLIO_LABELS:
            members = labels[labels == lab].index
            sub = caps.reindex(members).dropna()
            total = sub.sum()
            if total <= 0:
                continue
            for ticker, mc in sub.items():
                rows.append({
                    "rebalance_date": d.date().isoformat(),
                    "year": d.year,
                    "portfolio": lab,
                    "ticker": ticker,
                    "market_cap": round(float(mc), 2),
                    "weight": round(float(mc / total), 6),
                })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values(["year", "portfolio", "weight"],
                          ascending=[True, True, False]).reset_index(drop=True)


def export(use_cache: bool = True) -> dict:
    """รัน pipeline แล้วเขียน CSV ทั้งสองไฟล์ คืน dict สรุป path + ขนาด"""
    res = pipeline.run(use_cache=use_cache)

    membership = build_membership_table(res.memberships)
    membership.to_csv(MEMBERSHIP_CSV, index=False)

    port_ret = res.portfolio_returns.copy()
    port_ret.round(6).to_csv(RETURNS_CSV)

    return {
        "membership_path": MEMBERSHIP_CSV,
        "membership_rows": len(membership),
        "rebalance_dates": sorted({r for r in membership["rebalance_date"]}) if not membership.empty else [],
        "returns_path": RETURNS_CSV,
        "returns_months": len(port_ret),
        "returns_span": (port_ret.index.min(), port_ret.index.max()) if len(port_ret) else None,
        "membership_preview": membership,
        "returns_preview": port_ret,
    }


if __name__ == "__main__":
    info = export()
    print(f"[1] {info['membership_path']}  — {info['membership_rows']} แถว")
    print(f"    reform ปี (มิ.ย.): {info['rebalance_dates']}")
    print(f"[2] {info['returns_path']}  — {info['returns_months']} เดือน "
          f"({info['returns_span'][0].date()} → {info['returns_span'][1].date()})")

    # นับจำนวนหุ้นต่อพอร์ตในแต่ละปี (sanity)
    m = info["membership_preview"]
    print("\nจำนวนหุ้นต่อพอร์ต แยกปี:")
    print(m.pivot_table(index="year", columns="portfolio", values="ticker",
                        aggfunc="count", fill_value=0).to_string())

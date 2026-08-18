"""
main.py — CLI entrypoint
========================
รูปแบบใช้งาน:
  python main.py factors                 # สร้าง factor series รายเดือน + บันทึก CSV
  python main.py factors --no-cache      # บังคับ re-fetch ข้อมูลใหม่จาก yfinance
  python main.py regress PTT.BK          # รัน FF3 regression กับหุ้นเป้าหมาย
  python main.py regress PTT.BK KBANK.BK # หลายตัวได้
  python main.py sanity                  # correlation SMB/HML + cross-check universe vs หุ้น
  python main.py export                  # เขียน CSV: membership+weight (รายปี) และ return 6 พอร์ต
  python main.py significance            # ทดสอบ premium ของ 3 factor (full/sub-period/Newey-West/rolling)
  python main.py significance --window 24 --split-date 2025-02-01
"""

from __future__ import annotations

import argparse

import pandas as pd

import export_portfolios
import pipeline
from data.risk_free import fetch_risk_free_rate
from regression import fetch_stock_excess_return, run_ff3_regression, summarize
from significance.report import build_rolling, build_significance_report, format_report


def _load_or_build_factors(no_cache: bool) -> pd.DataFrame:
    f = pipeline.build_factors(use_cache=not no_cache)
    pipeline.save_factors(f)
    return f


def cmd_factors(args):
    f = _load_or_build_factors(args.no_cache)
    print(f"factor months: {len(f)}  ({f.index.min().date()} → {f.index.max().date()})")
    print(f.round(4).to_string())
    print("\nsaved -> factors_monthly.csv")


def cmd_regress(args):
    f = _load_or_build_factors(args.no_cache)
    rf = fetch_risk_free_rate(f.index)
    for ticker in args.tickers:
        try:
            ex = fetch_stock_excess_return(ticker, rf)
            res = run_ff3_regression(ex, f)
            print("\n" + summarize(ticker, res))
        except Exception as e:
            print(f"\n{ticker}: ❌ {e}")


def cmd_sanity(args):
    f = _load_or_build_factors(args.no_cache)
    corr = f[["Mkt-RF", "SMB", "HML"]].corr()
    print("Correlation matrix (Mkt-RF, SMB, HML):")
    print(corr.round(3).to_string())
    c = corr.loc["SMB", "HML"]
    verdict = "✅ ต่ำตามคาด (< 0.3)" if abs(c) < 0.3 else "⚠️ สูงกว่าคาด"
    print(f"\nSMB–HML corr = {c:+.3f}  {verdict}")
    print(f"\nUniverse VW return เฉลี่ยต่อเดือน = {f['Univ'].mean():+.4f}")
    print(f"Mkt-RF เฉลี่ยต่อเดือน            = {f['Mkt-RF'].mean():+.4f}")


def cmd_export(args):
    info = export_portfolios.export(use_cache=not args.no_cache)
    print(f"[1] {info['membership_path']}  — {info['membership_rows']} แถว "
          f"(หุ้น×รอบ reform)")
    print(f"    reform รายปี (มิ.ย.): {info['rebalance_dates']}")
    print(f"[2] {info['returns_path']}  — {info['returns_months']} เดือน "
          f"({info['returns_span'][0].date()} → {info['returns_span'][1].date()})")
    m = info["membership_preview"]
    print("\nจำนวนหุ้นต่อพอร์ต แยกปี:")
    print(m.pivot_table(index="year", columns="portfolio", values="ticker",
                        aggfunc="count", fill_value=0).to_string())


def cmd_significance(args):
    f = _load_or_build_factors(args.no_cache)
    report = build_significance_report(f, split_date=args.split_date, window=args.window)
    report.to_csv("significance_report.csv", index=False)

    print("=" * 72)
    print(f"FACTOR SIGNIFICANCE — n={len(f)} เดือน ({f.index.min().date()} → {f.index.max().date()})")
    print("Threshold หลัก p<0.05 | sig: *** p<0.01, ** p<0.05, * p<0.10")
    print("=" * 72)
    print(format_report(report))

    roll = build_rolling(f, window=args.window)
    roll.round(2).to_csv("significance_rolling_tstat.csv")
    print(f"\nRolling t-stat (window={args.window}, step=3) — {len(roll)} จุด:")
    print(roll.round(2).to_string())

    print("\nsaved -> significance_report.csv, significance_rolling_tstat.csv")
    print("\nวิธีอ่าน: ดู recent_period ตอบ 'ปัจจุบัน' | เทียบ full_sample | "
          "newey_west_full cross-check ว่ายัง robust หลังปรับ SE (autocorrelation)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SET50 Fama-French 3-Factor pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--no-cache", action="store_true",
                        help="บังคับ re-fetch ข้อมูลจาก yfinance")

    sub.add_parser("factors", parents=[common]).set_defaults(func=cmd_factors)

    rp = sub.add_parser("regress", parents=[common])
    rp.add_argument("tickers", nargs="+", help="เช่น PTT.BK KBANK.BK")
    rp.set_defaults(func=cmd_regress)

    sub.add_parser("sanity", parents=[common]).set_defaults(func=cmd_sanity)
    sub.add_parser("export", parents=[common]).set_defaults(func=cmd_export)

    sp = sub.add_parser("significance", parents=[common])
    sp.add_argument("--window", type=int, default=24, help="rolling window (เดือน), default 24")
    sp.add_argument("--split-date", default=None,
                    help="วันตัด sub-period (เช่น 2025-02-01); ไม่ระบุ = median split ~ครึ่ง")
    sp.set_defaults(func=cmd_significance)
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)

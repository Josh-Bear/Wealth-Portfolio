# CLAUDE.md — set50_ff3

Fama-French **3-factor model** สร้างเองสำหรับ universe **SET50** (ดึงข้อมูลผ่าน `yfinance`).
สร้าง time series ของ **Mkt-RF, SMB, HML** รายเดือน จาก quarterly-rebalanced portfolios
แล้วรัน OLS regression กับหุ้น/พอร์ตเป้าหมาย. ต่อยอดแนวจากสคริปต์ US เดิม `../ff3m.py`
(Ken French) แต่ **สร้าง factor เองจากหุ้นไทย** แทนการดึงจาก Ken French.

## Paradigm

**Annual reform ทุกเดือนมิถุนายน** (แบบ FF ต้นฉบับ): form 6 portfolios (2 size × 3 value) ในเดือน
มิ.ย. ปี t โดยใช้ book equity ปีก่อน → freeze membership → เก็บ monthly value-weighted returns
ตั้งแต่ ก.ค. ปี t ถึง มิ.ย. ปี t+1 → รวมเป็น factor series.

## การตัดสินใจที่ยืนยันแล้ว (จาก plan + probe data availability)

| หัวข้อ | สรุป | เหตุผล |
|---|---|---|
| Universe | SET50 ปัจจุบัน **fixed** | known survivorship bias; ทดสอบ mechanism ก่อน (Open Item #1) |
| Book Equity | งบ **รายปี** (annual) `Stockholders Equity` | probe พบ quarterly ตื้นแค่ ~6 ไตรมาส แต่ annual ลึก 4-5 ปี |
| Market factor | **คำนวณเอง** = VW return 50 หุ้น − rf | `^SET50.BK` ไม่มี history ใน yfinance (probe คืนแค่ 1 แถว) |
| Risk-free | **ค่าคงที่ปรับได้** (`RISK_FREE_ANNUAL`) | ยังไม่ผูก data source จริง (Open Item #3) |
| Size split | Big=rank 1-25, Small=26-50 | by market cap |
| Value split | Growth(<30%)/Neutral/Value(≥70%) ตาม B/M | breakpoint จาก universe เอง |
| Weighting | value-weighted ภายในพอร์ต | ถ่วง market cap |
| Rebalance | **รายปี ทุกเดือนมิถุนายน** (freeze ก.ค.→มิ.ย.) | แบบ FF ต้นฉบับ; เข้ากับ book equity รายปี |

**Known simplifications** (ระบุใน docstring): Book Equity ใช้ `Stockholders Equity` ตรงๆ
ไม่ปรับ deferred tax/ITC/preferred (Open Item #4); rf คงที่; universe fixed.

## Layout

```
set50_ff3/
├── config.py                 # ค่าคงที่กลาง (rf, lag, breakpoints, rebalance) — ปรับที่เดียว
├── data/
│   ├── constituents.py       # get_set50_constituents()  (50 ตัว fixed — แก้รายชื่อที่นี่)
│   ├── market_data.py        # fetch_prices(), fetch_shares_outstanding(), compute_market_cap()
│   ├── fundamentals.py       # fetch_book_equity() [annual], book_to_market()
│   ├── risk_free.py          # fetch_risk_free_rate()  (ค่าคงที่ปรับได้)
│   └── cache/                # ข้อมูลที่ดึงมา (gitignored) — ลบเพื่อ re-fetch
├── factors/
│   ├── size_factor.py        # assign_size_group()
│   ├── value_factor.py       # assign_value_group()
│   ├── portfolios.py         # form_six_portfolios(), compute_portfolio_return()
│   ├── smb.py / hml.py       # compute_smb() / compute_hml()
│   └── market_factor.py      # compute_market_factor()
├── pipeline.py               # run(): annual-June rebalance → factors + 6-port returns + memberships
├── export_portfolios.py      # เขียน portfolios_membership.csv + portfolio_returns_monthly.csv
├── regression.py             # run_ff3_regression() (statsmodels OLS)
├── significance/             # ทดสอบ premium ของ 3 factor (ต่อยอดจาก factor_significance_plan.md)
│   ├── basic_test.py         # one_sample_ttest(), test_all_factors()  (full-sample)
│   ├── subperiod.py          # split_subperiods(), compare_subperiods()  (early vs recent)
│   ├── rolling.py            # rolling_tstat()  (window 24, step 3)
│   ├── robust_se.py          # newey_west_ttest()  (HAC-adjusted SE)
│   └── report.py             # build_significance_report()  (orchestrate 4 tests)
├── main.py                   # CLI: factors | regress <ticker...> | sanity | export | significance
├── tests/test_factors.py     # unit tests (25/25, 15/20/15, VW, SMB/HML)
└── probe_data_availability.py# script probe ก่อนสร้าง pipeline (Next Step ข้อ 7)
```

## รันงาน

```
python probe_data_availability.py      # (ทำครั้งแรก) เช็คว่า yfinance มี field ครบ
python main.py factors                 # สร้าง factor series → factors_monthly.csv
python main.py regress PTT.BK KBANK.BK # FF3 regression กับหุ้นเป้าหมาย
python main.py sanity                  # เช็ค corr(SMB,HML) + universe VW return
python main.py export                  # เขียน CSV membership+weight (รายปี) + return 6 พอร์ต
python main.py significance            # ทดสอบ premium 3 factor (full/sub-period/Newey-West/rolling)
python -m pytest tests/ -q             # unit tests
```

**Factor significance** (`significance`): ทดสอบ H0: mean(factor)=0 ด้วย 4 วิธี — full-sample
t-test, sub-period split (median ~19/19, หรือ `--split-date`), Newey-West HAC (แก้ autocorrelation),
rolling t-stat (`--window`, default 24). Threshold หลัก p<0.05. Output: `significance_report.csv`,
`significance_rolling_tstat.csv`. **ข้อควรระวัง**: n=38 เดือน → power ต่ำ, sub-period ~19/19 ยิ่งต่ำ
→ อ่าน p-value อย่างระมัดระวัง (ดู `factor_significance_plan.md` section 3).

**Output CSV** (จาก `export`):
- `portfolios_membership.csv` — 1 แถว/หุ้น/รอบ reform: `rebalance_date, year, portfolio, ticker,
  market_cap, weight` (weight = value-weight ภายในพอร์ต, รวมกันต่อพอร์ต = 1.0)
- `portfolio_returns_monthly.csv` — return รายเดือนของทั้ง 6 พอร์ต: `month, SG, SN, SV, BG, BN, BV`

`--no-cache` ต่อท้ายเพื่อบังคับ re-fetch จาก yfinance.

## ข้อจำกัดจริง (จาก probe)

- ราคารายเดือน ~60 เดือน; แต่ **factor series ใช้ได้จริง ~38 เดือน** (2023-07 →) เพราะต้องรอ
  book equity รายปีตัวแรกประกาศ (+ lag) ก่อน form พอร์ตได้
- ดัชนีไทยทั้งหมดใน yfinance (`^SET.BK`, `^SET50.BK`, `^SET100.BK`) ไม่มี history → ห้ามพึ่ง
- ต้อง maintain รายชื่อ SET50 เอง (yfinance ไม่มี constituent endpoint)

## Roadmap (phase 2 ถ้าต้องการ research-grade)

point-in-time constituent list (แก้ survivorship bias) · rf time-varying จาก BOT/investing.com ·
book equity ปรับ deferred tax/preferred · หา historical index จริงมา cross-check.

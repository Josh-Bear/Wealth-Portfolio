"""
config.py — ค่าคงที่กลางของ pipeline SET50 FF3 (ปรับที่เดียว ไม่ให้ drift)
=========================================================================
สรุปการตัดสินใจที่ยืนยันแล้ว (จาก set50_ff3_plan.md + probe data availability):
  - Universe        : SET50 ปัจจุบันแบบ fixed (constituents.py) — known survivorship bias
  - Book Equity     : งบ "รายปี" (annual balance sheet) เพราะ quarterly ตื้นแค่ ~6 ไตรมาส
                      แต่ annual ลึก 4-5 ปี พอดีกับ window; ใส่ lag ก่อนใช้ได้ (REPORT_LAG_MONTHS)
  - Market factor   : คำนวณเองจาก value-weighted return ของ 50 หุ้น − rf
                      (^SET50.BK ไม่มี history ใน yfinance — probe แล้วคืนแค่ 1 แถว)
  - Risk-free rate  : ค่าคงที่ปรับได้ (RISK_FREE_ANNUAL) — ยังไม่ผูก data source จริง
  - Size split      : Big = rank 1-25, Small = rank 26-50 (by market cap)
  - Value split     : Growth (ล่าง 30%) / Neutral (กลาง 40%) / Value (บน 30%) ตาม B/M
  - Weighting       : value-weighted ภายในแต่ละพอร์ต (ถ่วงตาม market cap)
  - Rebalance       : รายปี ทุกเดือน "มิถุนายน" แบบ FF ต้นฉบับ (form มิ.ย. ปี t ใช้ book
                      equity ปีก่อน, freeze membership แล้วถือ ก.ค. ปี t → มิ.ย. ปี t+1)
"""

# ---- universe / data window ----------------------------------------------
LOOKBACK_YEARS = 15           # yfinance ให้ราคารายเดือน ~60 เดือน (probe ยืนยันแล้ว)
PRICE_INTERVAL = "1mo"

# ---- risk-free rate (Open Item #3: ค่าคงที่ปรับได้) -----------------------
# อัตราต่อปี (เช่น 0.02 = 2%/ปี). แปลงเป็นรายเดือนใน data/risk_free.py
RISK_FREE_ANNUAL = 0.02

# ---- fundamentals lag (point-in-time discipline) --------------------------
# งบรายปีปิด 31 ธ.ค. ปี Y จะ "ใช้ได้จริง" หลังประกาศ ~REPORT_LAG_MONTHS เดือน
# (บ. ไทยส่วนใหญ่ประกาศงบปีตรวจสอบแล้วราว ก.พ.-มี.ค. ปีถัดไป -> ตั้ง 4 เดือนกันเหลือ)
REPORT_LAG_MONTHS = 4

# ---- factor construction breakpoints -------------------------------------
SIZE_BIG_RANK_CUTOFF = 25    # rank 1-25 = Big, 26-50 = Small
VALUE_LOW_PCT = 0.30         # ล่าง 30% = Growth
VALUE_HIGH_PCT = 0.70        # บน 30% (>=70th) = Value ; กลาง = Neutral

# ---- rebalance cadence ----------------------------------------------------
# reform รายปี ทุกเดือนมิถุนายน (แบบ FF ต้นฉบับ) — form มิ.ย. ปี t, ถือ ก.ค. → มิ.ย. ปีถัดไป
REBALANCE_MONTH = 6          # 6 = มิถุนายน

# ---- cache ----------------------------------------------------------------
CACHE_DIR = "data/cache"     # เก็บข้อมูลที่ดึงมาเพื่อไม่ต้อง re-fetch ทุกครั้ง

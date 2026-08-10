# Thai Dividend Yield Portfolio — Walk-Forward Backtest (v4)

ระบบ backtest หาพอร์ตหุ้นปันผลไทย ด้วย **capped proportional weighting** — 4 วิธีให้คะแนนหุ้นบน yield
แล้วแปลงเป็นน้ำหนักพอร์ตแบบสัดส่วน + floor/ceiling (ไม่มี LP) แต่ละวิธีถือ **1 พอร์ต ซื้อครั้งเดียว
วัดผลที่ 4 checkpoint (3/6/9/12 เดือน)** · เงินทุน 100 ล้านบาท · walk-forward **รายเดือน 60 จุด**
(2021-09 → 2026-08)

## Universe

| กลุ่ม | หุ้น | floor | ceiling |
|---|---|---|---|
| หลัก (บังคับถือ) | AOT, OR, KTB, PTT, PTTEP | 5% | 30% |
| รอง (เลือกได้) | SCB, BBL, KBANK, TTB, BAY | 0% | 30% |

## Yield basis (v4)

ทุกวิธีทำงานบน **yield_history**: ปันผลแต่ละครั้ง `yield = dps / ราคาปิด "ก่อน" วัน ex-date แบบเข้ม
(date < ex-date)` — เพราะราคาปิดวัน ex-date ปรับลง (ex-drop) ไปแล้ว ต้องใช้ราคาก่อนหน้า.
ปันผลที่ไม่มีราคาก่อนวัน ex-date (เก่ากว่าที่ price_history เริ่ม ปี 2014) จะ **ถูกข้าม ไม่เดาราคา**.

## 4 วิธีถ่วงน้ำหนัก (บน yield, walk-forward — ใช้เฉพาะข้อมูลก่อน entry)

1. **avg_yield** — เฉลี่ย yield ทุกงวด (มี toggle ตัด outlier > p95)
2. **latest_yield** — yield งวดล่าสุดตัวเดียว
3. **avg_total_return** — เฉลี่ย total return 12 เดือน rolling (สั้นกว่านั้นถ้าข้อมูลไม่พอ), floor 0
4. **growth_trend** — fit เทรนด์เชิงเส้นบน yield series แล้ว project ไปวัน entry, floor 0

คะแนน → น้ำหนักตามสัดส่วน แล้วบีบด้วย water-filling (floor 5% core / ceiling 30% ทุกตัว, ส่วนเกินเติม core ก่อน)

## วัดผล (per checkpoint)

`realized_div = Σ dps ที่ ex-date อยู่ใน (entry, entry+h] / price_entry` — **เข้มหลัง entry**
(ซื้อวัน entry ไม่ได้ปันผลที่ ex-date ตรงวันนั้น). `capital_gain = (price_{entry+h} − price_entry)/price_entry`.
checkpoint ที่เลยวันปัจจุบัน (2026-08-07) = `pending` → dashboard แสดง `*`.

## Quick start

```bash
pip install -r requirements.txt

python3 src/fetch_data.py        # Phase 1-2: ดึง + validate ข้อมูล 10 หุ้น
python3 src/engine.py            # score + water-fill + realized -> data/v3_*.csv
streamlit run src/dashboard.py   # dashboard interactive (port 8501)
```

## Dashboard

- **กดเพิ่ม/ลดหุ้นรองเองได้** — ปิด = ตัดออกจากสูตรเลย → water-filling คำนวณใหม่สด
- Toggle **trim outliers** (มีผลเฉพาะ avg_yield)
- **โฟกัส entry เดียว**: เลือก entry → ดูน้ำหนัก (%/บาท) + ตารางผล 4 checkpoint (แสดง `*` เมื่อ pending)
- แท็บเสริม: เทียบวิธี × checkpoint, timeline, dividend patterns, raw data

## โครงสร้าง

```
src/  common.py · weighting.py · engine.py · dashboard.py · fetch_data.py
data/ inputs (price_history, dividend_history, ...) + engine outputs (v3_scores/realized/weights/results)
raw/  API payloads ดิบ (provenance)
```

- `engine.py` เขียนตารางระดับหุ้น (`v3_scores`, `v3_realized`) ที่ไม่ขึ้นกับ universe + ผล default
  (`v3_weights`, `v3_results`; ชื่อไฟล์ยังขึ้นต้น `v3_` ตามเดิม) — dashboard อ่านตารางระดับหุ้นแล้ว
  **คำนวณ water-filling สด** ตาม universe/trim ที่เลือก ผ่านฟังก์ชันร่วม `enabled_smap` + `build_portfolio`
  (batch กับ dashboard ใช้โค้ดเดียวกัน ไม่ drift)

รายละเอียดกฎ walk-forward, yield basis และ water-filling ดูใน [CLAUDE.md](CLAUDE.md) และแผน
`thai_dividend_backtest_plan_v4.md`

## หมายเหตุข้อมูล

- ราคา = split-adjusted ฐานหุ้นปัจจุบัน (ไม่ปรับปันผล); ปันผลฐานเดียวกัน → yield ถูกต้อง
- yfinance เป็นหลัก, cross-check StockAnalysis.com; ห้าม interpolate/เดาปันผล
- ปันผลที่เก่ากว่า price history → ข้าม (ไม่ fabricate ราคา)

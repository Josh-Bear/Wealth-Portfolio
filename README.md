# Thai Dividend Yield Portfolio — Walk-Forward Backtest (v3)

ระบบ backtest หาพอร์ตหุ้นปันผลไทย ด้วย **capped proportional weighting** — 4 วิธีให้คะแนนหุ้นบน yield
แล้วแปลงเป็นน้ำหนักพอร์ตแบบสัดส่วน + floor/ceiling (ไม่มี LP) แต่ละวิธีถือ **1 พอร์ต ซื้อครั้งเดียว
วัดผลที่ 4 checkpoint (3/6/9/12 เดือน)** · เงินทุน 100 ล้านบาท · walk-forward รายไตรมาส 20 จุด

## Universe

| กลุ่ม | หุ้น | floor | ceiling |
|---|---|---|---|
| หลัก (บังคับถือ) | AOT, OR, KTB, PTT, PTTEP | 5% | 30% |
| รอง (เลือกได้) | SCB, BBL, KBANK, TTB, BAY | 0% | 30% |

## 4 วิธีถ่วงน้ำหนัก (บน yield, walk-forward)

1. **avg_yield** — เฉลี่ย yield ทุกงวด (มี toggle ตัด outlier > p95)
2. **latest_yield** — yield งวดล่าสุดตัวเดียว
3. **avg_total_return** — เฉลี่ย total return 12 เดือน rolling (สั้นกว่านั้นถ้าข้อมูลไม่พอ)
4. **growth_trend** — เทรนด์ yield project ไปข้างหน้า 1 งวด

คะแนน → น้ำหนักตามสัดส่วน แล้วบีบด้วย water-filling (floor 5% core / ceiling 30% ทุกตัว, ส่วนเกินเติม core ก่อน)

## Quick start

```bash
pip install -r requirements.txt

python3 src/fetch_data.py        # Phase 1-2: ดึง + validate ข้อมูล 10 หุ้น
python3 src/engine.py            # score + water-fill + realized -> data/v3_*.csv
streamlit run src/dashboard.py   # dashboard interactive (port 8501)
```

## Dashboard (interactive)

- **กดเพิ่ม/ลดหุ้นรองเองได้** — ปิด = ตัดออกจากสูตรเลย → water-filling คำนวณใหม่สด
- Toggle **trim outliers** (มีผลเฉพาะ avg_yield)
- ดูน้ำหนัก + เม็ดเงินบาท, ผลตอบแทนต่อ entry/checkpoint, raw scores (โปร่งใส), การกระจายตัว (eff. #หุ้น)

## ผลลัพธ์เด่น

- **พอร์ตกระจายตัวจริง** (eff. ~4-5 หุ้น) ต่างจากแนวทาง LP เดิมที่กระจุกตัวเดียว ~80%
- ceiling 30% + floor 5% ทำให้ไม่มีหุ้นตัวใดครอบงำ

## โครงสร้าง

```
src/  common.py · weighting.py · engine.py · dashboard.py · fetch_data.py
data/ inputs (price_history, dividend_history, ...) + v3 outputs (v3_scores/realized/weights/results)
raw/  API payloads ดิบ (provenance)
```

รายละเอียดกฎ walk-forward, water-filling และ data basis ดูใน [CLAUDE.md](CLAUDE.md) และแผน
`thai_dividend_backtest_plan_v3.md`

## หมายเหตุข้อมูล

- ราคา = split-adjusted ฐานหุ้นปัจจุบัน (ไม่ปรับปันผล); ปันผลฐานเดียวกัน → yield ถูกต้อง
- yfinance เป็นหลัก, cross-check StockAnalysis.com; ห้าม interpolate/เดาปันผล
- checkpoint ที่ยังไม่ครบ ณ 2026-08-07 = pending (ไม่นำมาเฉลี่ย)

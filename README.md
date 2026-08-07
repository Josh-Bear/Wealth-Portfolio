# Thai Dividend Yield Portfolio — Walk-Forward Backtest

ระบบ backtest หาพอร์ตหุ้นปันผลไทยที่ **maximize ผลตอบแทนจากเงินปันผล** เมื่อถือครอง 3/6/9/12 เดือน
ทดสอบแบบ walk-forward rolling ย้อนหลัง ~5 ปี เทียบวิธีพยากรณ์ปันผล 4 วิธี และแยกให้เห็นทั้ง
ผลตอบแทนจากปันผลและกำไร/ขาดทุนราคา (total return)

## Universe

| กลุ่ม | หุ้น | เงื่อนไขน้ำหนัก |
|---|---|---|
| หลัก (บังคับถือ) | AOT, OR, KTB, PTT, PTTEP | แต่ละตัว ≥ 5% |
| รอง (เลือกได้) | SCB, BBL, KBANK, TTB, BAY | 0% – ไม่จำกัด |

เงินทุน 100,000,000 บาท · entry รายเดือน 60 จุด (2021-09 → 2026-08) · 960 LP runs

## Quick start

```bash
pip install -r requirements.txt

# รัน pipeline ตามลำดับ
python3 src/fetch_data.py          # ดึง + validate ข้อมูล (yfinance + StockAnalysis cross-check)
python3 src/phase34_forecast.py    # สกัด dividend slots + forecast 4 วิธี
python3 src/phase56_backtest.py    # LP optimize + วัดผล realized
python3 src/phase78_report.py      # ตารางสรุป + กราฟ + Excel
python3 src/make_pdf_report.py     # รายงาน PDF (ใช้ Google Chrome เรนเดอร์ฟอนต์ไทย)

# Dashboard แบบ interactive
streamlit run src/dashboard_v2.py  # กดเพิ่ม/ลดหุ้นรองเองได้ + ดูเป็นบาท
```

## ผลลัพธ์หลัก (ล่าสุด)

- **วิธี forecast แม่นสุด: `naive`** (MAE ต่ำสุด) — ปันผลหุ้นไทย "เหนียว" เปลี่ยนช้า
- **SCB (SCBX) เพิ่ม return เยอะสุด** ในกลุ่มหุ้นรอง (yield ~8-9%)
- Total return ถูกครอบงำด้วย capital gain มากกว่าคุณภาพ forecast; holding ~9 เดือนเฉลี่ยดีสุด
- พอร์ตกระจุกตัวสูง (corner solution ของ LP ตาม spec)

## โครงสร้าง

```
src/      โค้ด pipeline (fetch → forecast → optimize → report) + dashboards
data/     ข้อมูล validated + ผลลัพธ์ CSV ทั้งหมด
output/   รายงาน/กราฟ/xlsx/PDF (สร้างจาก phase78 + make_pdf_report)
raw/      API payloads ดิบ (provenance / cross-check)
```

รายละเอียดสถาปัตยกรรม กฎ walk-forward และ data basis ดูใน [CLAUDE.md](CLAUDE.md) และแผนงาน
`thai_dividend_backtest_plan.md` / `thai_dividend_backtest_plan_v2.md`

## หมายเหตุข้อมูล

- ราคา = **split-adjusted ฐานหุ้นปัจจุบัน (ไม่ปรับปันผล)**; ปันผลอยู่ฐานเดียวกัน → yield/gain ถูกต้อง
- ห้าม interpolate/เดาปันผล — ข้อมูลขาดบันทึกเป็น missing
- runs ที่ holding ยังไม่ครบ ณ 2026-08-07 = `pending` (ไม่นำมาเฉลี่ย)

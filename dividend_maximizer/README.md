# Dividend Maximizer

เครื่องมือเลือกพอร์ตหุ้นปันผลไทยแบบ **greedy corner-solution** — เลือกหุ้นอย่างน้อย 5 ตัวจาก 10 ตัว
(น้ำหนัก 5–30% ต่อตัว) เพื่อให้ได้ **ปันผลรวมในครึ่งปีที่เลือกสูงสุด** แล้วแปลงเป็นจำนวนหุ้นจริง
(board lot 100) หักค่าคอมมิชชั่น เหลือเงินสดถือไว้

> แยกจากระบบเดิม (`../thai-dividend-backtest/`) ที่ใช้ water-fill กระจายตามสัดส่วน score — อันนี้
> **greedy** ทุ่มน้ำหนักให้ตัวดีสุดก่อน (corner solution) ต่างกันคนละแนวคิด

## รันยังไง

```bash
# core logic + self-tests (เหมือน weighting.py — รันไฟล์ตรง ๆ)
python3 dividend_maximizer/optimizer.py

# UI
streamlit run dividend_maximizer/app.py
```

## แนวคิดหลัก: ทำไม rank ด้วย yield ไม่ใช่บาท/หุ้น

ปันผลรวมที่ได้ = `จำนวนหุ้น × dps = (ทุน × weight ÷ ราคา) × dps = ทุน × weight × (dps/ราคา)`

ทุนคงที่ → objective เป็นเชิงเส้นใน `weight × yield` → maximize ได้ด้วย **corner solution**: ทุ่ม
ceiling (30%) ให้หุ้น **yield คาดสูงสุด** ก่อน ไล่ลงมา ที่เหลือให้ floor (5%) จนครบ ≥5 ตัว
(ผลลัพธ์เสมอ = `3×30% + 2×5% = 100%`)

> ถ้า rank ด้วยบาท/หุ้นจะเลือกหุ้นแพง yield ต่ำผิดตัว เช่น ปี 2023 BBL จ่ายคาด 1.17 บาท/หุ้น (บาท/หุ้น
> อันดับ 1) แต่ราคา 159.50 → yield แค่ 0.73% ส่วน PTT จ่าย 1.10 ราคา 33.50 → yield 3.28% ลงทุนเท่ากัน
> PTT ได้ปันผลมากกว่าหลายเท่า

## 3 วิธีพยากรณ์ปันผล H2 (บาท/หุ้น, walk-forward — ใช้เฉพาะข้อมูลก่อน entry)

ทุกวิธีพยากรณ์ **ยอดทั้งปี** แล้ว **ลบด้วยปันผลที่จ่ายไปแล้วใน H1** ของปีนั้น เหลือเป็นส่วน H2 (clamp ≥ 0):

| วิธี | สูตร |
|---|---|
| `avg3y` | เฉลี่ยยอดทั้งปีของ **3 ปีล่าสุดที่ available** − H1 ที่จ่ายแล้ว |
| `lastyear` | ยอดทั้งปีของ **ปีล่าสุดที่ available** − H1 ที่จ่ายแล้ว |
| `linreg` | fit เส้นตรง (ปี → ยอดทั้งปี) project ไปปีเป้าหมาย − H1 · <2 จุด → fallback เป็น `avg3y` |

## สมมติฐาน (assumptions)

| เรื่อง | ค่า |
|---|---|
| ปฏิทินยอดปี | **calendar year** (1 ม.ค.–31 ธ.ค.) ไม่ปรับตามรอบบัญชี |
| ค่าคงที่ | min 5 ตัว · floor 5% · ceiling 30% · lot 100 หุ้น · commission 0.257% (ปรับใน UI ได้) |
| ทุน | 100,000,000 บาท (จาก `common.CAPITAL`) |
| ราคาซื้อ | ราคาปิดวันเทรดแรก ≥ ต้นครึ่งปี (H2 = 1 ก.ค. → วันเทรดแรก) |
| `years_available` | นับเฉพาะปีที่หุ้นเทรดมาก่อน 1 ม.ค.ของปีนั้น (กัน OR/SCB ปีแรกที่ยังไม่เต็มปี) |
| score ติดลบ | จ่าย H1 เกินยอดคาดทั้งปี (เช่น KTB payer รายปี) → clamp เป็น 0 |
| tie-break | score เท่ากัน → เรียงชื่อ ticker (deterministic) |
| board lot | ปัดลงเป็นจำนวนเต็ม lot → มีเงินสดเหลือเสมอ (แสดงชัด ไม่ซ่อน) |
| realized/pending | ใช้ `common.TODAY` (2026-08-07) เป็น cutoff — ex-date หลัง entry & ≤ TODAY = realized, > TODAY = pending |

## Backtest 2023–2026 (H2)

เข้าต้น ก.ค.แต่ละปี พยากรณ์ (walk-forward) → เลือกพอร์ต → วัดปันผลที่ได้จริง:
- **2023–2025**: H2 จบแล้ว (TODAY อยู่หลัง) → realized เต็มจำนวน (เทียบคาด vs จริงได้)
- **2026**: H2 เพิ่งเริ่ม → แสดง weight/หุ้น/เม็ดเงินได้ทันที แต่ปันผล mark **pending** (ยังไม่มี ex-date H2
  2026 ณ วันนี้ — โค้ด handle แบบ generic จะขึ้น realized เองเมื่อมีข้อมูลจริง)

## ไฟล์

- `optimizer.py` — core logic (forecast + greedy + board-lot/commission + backtest) + self-tests
- `app.py` — Streamlit UI (พอร์ตจุดเดียว / เทียบ 3 วิธี / backtest)
- อ่านข้อมูลจาก `../thai-dividend-backtest/data/*.csv` และ import `common.py` ตัวเดียวกับโปรเจกต์หลัก
  (shared, no drift)

# FF5 Factor Model — สรุปผล Core Run

> สรุปสิ่งที่ทำจริงในรอบนี้ (Core scope) ตามแผนใน [`FF5_Factor_Model_Testing_Plan.md`](FF5_Factor_Model_Testing_Plan.md)
> วันที่รัน: 2026-08-18 · โค้ด: [`ff5_core.py`](ff5_core.py)

---

## 1. สิ่งที่ทำไปแล้ว

| ขั้นตอน | สถานะ | รายละเอียด |
|---|---|---|
| เตรียมข้อมูล (Y — test assets) | ✅ | `6_Portfolios_2x3.csv` → section **Average Value Weighted Returns -- Monthly** |
| เตรียมข้อมูล (X — factors) | ✅ | โหลดเองจาก Ken French → `F-F_Research_Data_5_Factors_2x3.csv` (Mkt-RF, SMB, HML, RMW, CMA, RF) |
| Cleaning | ✅ | filter แถว YYYYMM, replace `-99.99 / -999` เป็น NaN, inner-join บน date, dropna |
| Excess return | ✅ | `R_it − RF_t` ต่อพอร์ต |
| Time-series regression | ✅ | OLS 6 พอร์ต, **Newey-West (HAC) SE, maxlags=6** |
| ตารางสรุป α/β/t-stat/R² | ✅ | 6 แถว |
| GRS joint test | ✅ | เขียนฟังก์ชันเองด้วย numpy (Gibbons-Ross-Shanken 1989) |
| สรุปผ่าน/ไม่ผ่าน | ✅ | ตัดสินที่ระดับนัยสำคัญ 5% |

**ยังไม่ได้ทำ (อยู่นอก Core):** diagnostics (DW / Ljung-Box / VIF), visualization (heatmap, alpha CI, actual-vs-fitted), เทียบ CAPM/FF3, sub-period / test asset อื่น (Robustness หัวข้อ 6)

---

## 2. Sample

- ช่วงเวลา: **1963-07 → 2026-06**
- จำนวนเดือน (T): **756**
- Y: 6 พอร์ต — `SMALL LoBM, ME1 BM2, SMALL HiBM, BIG LoBM, ME2 BM2, BIG HiBM`
- X: 5 ปัจจัย (Mkt-RF, SMB, HML, RMW, CMA) + RF
- inner-join ตัดช่วงก่อนที่ RMW/CMA จะเริ่ม (ก่อน 1963-07) ออกอัตโนมัติ

---

## 3. ตารางสรุป Regression (Newey-West HAC, maxlags=6)

α และ β เป็น **% ต่อเดือน**

| พอร์ต | α | t(α) | Mkt-RF | SMB | HML | RMW | CMA | R² |
|---|---|---|---|---|---|---|---|---|
| SMALL LoBM | **−0.079** | **−2.50** | 1.055 | 1.013 | −0.338 | −0.200 | −0.094 | 0.985 |
| ME1 BM2 | **+0.064** | **+2.38** | 0.964 | 0.845 | 0.202 | 0.048 | 0.025 | 0.984 |
| SMALL HiBM | +0.028 | +1.31 | 1.001 | 0.883 | 0.538 | 0.043 | 0.070 | 0.989 |
| BIG LoBM | **+0.075** | **+3.20** | 1.001 | −0.109 | −0.249 | 0.145 | −0.037 | 0.983 |
| ME2 BM2 | **−0.135** | **−2.81** | 0.987 | −0.065 | 0.276 | 0.075 | 0.155 | 0.925 |
| BIG HiBM | −0.031 | −0.83 | 1.055 | 0.021 | 0.876 | −0.098 | −0.201 | 0.956 |

- พอร์ตที่ |t(α)| > 1.96: **4 / 6**
- mean |α| = 0.069% ต่อเดือน (≈ 0.82% ต่อปี)

---

## 4. GRS Joint Test

**H0:** α ทั้ง 6 พอร์ต = 0 พร้อมกัน

| ค่า | ผล |
|---|---|
| GRS statistic | **4.57** ~ F(6, 745) |
| p-value | **0.0001** |
| การตัดสิน (5%) | **FAIL → ปฏิเสธ H0** — ยังมี mispricing เหลืออยู่ |

---

## 5. การตีความ

- **β ตรงตามทฤษฎีทุกตัว:** Mkt-RF ≈ 1 ทุกพอร์ต; SMB สูงในกลุ่ม SMALL (~0.85–1.0) ต่ำ/ติดลบในกลุ่ม BIG; HML เพิ่มตาม BM (LoBM ติดลบ → HiBM +0.5 ถึง +0.9) — โครงสร้าง factor loading ถูกต้อง
- **R² สูงมาก (0.92–0.99):** ปัจจัยอธิบาย variance ได้เกือบหมด แต่ R² สูง ≠ α = 0 (คนละเรื่องกับ pricing)
- **ตัวปัญหาคลาสสิก:** `SMALL LoBM` (small-growth) α = −0.079, t = −2.50 — ตรงกับงานวิจัย FF ที่โมเดลอธิบาย small-growth ไม่หมด; `ME2 BM2` α = −0.135, t = −2.81 ก็มีนัยสำคัญ
- 4 ใน 6 พอร์ต α มีนัยสำคัญ → เป็นเหตุให้ GRS reject

> ⚠️ **ข้อควรระวัง (ตามแผนหัวข้อ 1):** 6 พอร์ตนี้เป็น "วัตถุดิบ" ที่ใช้สร้าง SMB/HML เอง จึง **ไม่ใช่ independent test set** — ผล FAIL นี้ควรตีความในฐานะ exercise เพื่อเข้าใจกลไก ถ้าจะทดสอบจริงจังต้องใช้ test asset อื่น (25 Portfolios 5×5, Industry Portfolios) ตาม Robustness หัวข้อ 6

---

## 6. ไฟล์ในโฟลเดอร์

| ไฟล์ | คือ |
|---|---|
| `FF5_Factor_Model_Testing_Plan.md` | แผนทดสอบ (ตั้งต้น) |
| `6_Portfolios_2x3.csv` | ข้อมูล Y — 6 พอร์ต (มีมาแต่แรก) |
| `F-F_Research_Data_5_Factors_2x3.csv` | ข้อมูล X — 5 ปัจจัย (โหลดเพิ่มรอบนี้) |
| `ff5_core.py` | โค้ด Core |
| `FF5_Core_Results.md` | ไฟล์สรุปนี้ |

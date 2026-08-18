# แผนทดสอบ Fama-French 5-Factor Model
## ด้วยข้อมูล 6 Portfolios Formed on Size and Book-to-Market (2×3) — รายเดือน, Python

---

## 1. เป้าหมายและกรอบทดสอบ

**สมมติฐานหลัก (Null Hypothesis):** โมเดล 5-Factor สามารถอธิบายผลตอบแทนส่วนเกิน (excess return) ของทั้ง 6 พอร์ตได้หมด — นั่นคือ **alpha (α) ของทุกพอร์ตต้องไม่แตกต่างจาก 0 อย่างมีนัยสำคัญ**

สมการถดถอย (time-series regression) สำหรับพอร์ต i:

```
R_it - RF_t = α_i + β_i(Mkt-RF)_t + s_i·SMB_t + h_i·HML_t + r_i·RMW_t + c_i·CMA_t + ε_it
```

ทำแบบนี้ทีละพอร์ต (6 สมการ) แล้วดูว่า α ทั้ง 6 ตัวรวมกันเป็นศูนย์หรือไม่ (GRS test)

> ⚠️ **ข้อควรระวังสำคัญ**: 6 พอร์ตนี้เป็นชุดที่ Fama-French ใช้เป็นวัตถุดิบสร้าง SMB และ HML เอง (แม้จะไม่ตรงเป๊ะกับ 2x3 sort ที่ใช้สร้างปัจจัยจริง แต่ก็ใกล้เคียงมาก) ดังนั้นการทดสอบแบบนี้จะ**เอนเอียงไปทาง "ผ่าน" ง่ายกว่าปกติ** (ไม่ใช่ independent test set) — เหมาะเป็น **exercise เพื่อเข้าใจกลไก** แต่ถ้าจะทดสอบจริงจังควรใช้ test asset อื่นเสริม เช่น 25 Portfolios (5×5), Industry Portfolios หรือ 32 Portfolios (2x4x4) — ดูหัวข้อ 6 (Robustness Checks)

---

## 2. ข้อมูลที่ต้องใช้

| ชุดข้อมูล | ไฟล์บน Ken French Library | ใช้ทำอะไร |
|---|---|---|
| Test assets | `6_Portfolios_2x3_CSV.zip` | ตัวแปรตาม (Y) — ผลตอบแทน 6 พอร์ต |
| Factors | `F-F_Research_Data_5_Factors_2x3_CSV.zip` | ตัวแปรอิสระ (X) — Mkt-RF, SMB, HML, RMW, CMA, RF |

ทั้งสองไฟล์เป็นรายเดือน ต้อง**match ช่วงเวลาให้ตรงกัน** (factor file มักเริ่มก่อน เพราะ RMW/CMA เริ่มเก็บทีหลัง SMB/HML — ให้เช็ควันที่เริ่มต้นจริงหลังโหลดข้อมูล)

---

## 3. ขั้นตอนเตรียมข้อมูล (Data Cleaning)

1. **อ่านไฟล์ CSV** — ไฟล์ของ Ken French มักมี header/footer อธิบายข้อความปนอยู่ ต้อง skip แถวที่ไม่ใช่ข้อมูล (ใช้ `pd.read_csv(..., skiprows=..., nrows=...)` หรืออ่านแล้ว filter แถวที่ column แรกไม่ใช่ตัวเลข YYYYMM)
2. **แปลง date column** (`YYYYMM`) เป็น `datetime` หรือ `Period('M')`
3. **จัดการ missing value** — Ken French ใช้ `-99.99` หรือ `-999` แทนค่าที่ไม่มีข้อมูล ต้อง replace เป็น `NaN`
4. **หน่วยข้อมูล** — ตัวเลขเป็น % อยู่แล้ว (เช่น 1.23 = 1.23%) ถ้าจะทำ regression ใช้เป็นทศนิยม (÷100) หรือใช้เป็น % ตรงๆ ก็ได้ แค่ให้สอดคล้องกันทั้งสองไฟล์
5. **Merge** สองตาราง (portfolios + factors) ด้วย date, inner join เพื่อตัดช่วงที่ไม่ตรงกันออก
6. **คำนวณ excess return** ของแต่ละพอร์ต: `R_it - RF_t`
7. เช็ค **จำนวนช่วงเวลา (T)** ที่เหลือหลัง merge — ต้องมากพอ (อย่างน้อยหลายสิบปีสำหรับ FF5 เพราะ RMW/CMA เริ่มปี 1963 เป็นต้นไป)

---

## 4. ระเบียบวิธีวิเคราะห์ (Methodology)

### 4.1 Time-Series Regression (ทีละพอร์ต)
- รัน OLS 6 ครั้ง (พอร์ตละครั้ง) ด้วย `statsmodels`
- ใช้ **Newey-West (HAC) standard errors** แทน OLS ธรรมดา เพราะผลตอบแทนรายเดือนมักมี autocorrelation/heteroskedasticity เล็กน้อย
- เก็บผลลัพธ์: α, β(Mkt), s(SMB), h(HML), r(RMW), c(CMA), t-stat ของแต่ละตัว, R²

### 4.2 GRS Test (Joint test ว่า α ทั้งหมด = 0 พร้อมกัน)

สูตร GRS (Gibbons, Ross, Shanken 1989):

```
GRS = [(T - N - K) / N] × [1 + μ̂_f' Σ̂_f⁻¹ μ̂_f]⁻¹ × α̂' Σ̂⁻¹ α̂  ~ F(N, T-N-K)
```

- T = จำนวนเดือน, N = จำนวนพอร์ต (6), K = จำนวนปัจจัย (5)
- μ̂_f, Σ̂_f = mean และ covariance ของปัจจัยทั้ง 5
- α̂ = vector ของ alpha ทั้ง 6 พอร์ต, Σ̂ = covariance matrix ของ residuals

ไม่มี package สำเร็จรูป ดังนั้นต้อง**เขียนฟังก์ชันเองด้วย numpy** (ไม่ยาก ~15-20 บรรทัด)

### 4.3 เกณฑ์การตัดสิน
- p-value ของ GRS test > 0.05 → ไม่ปฏิเสธ H0 → โมเดลอธิบายได้ดี (ผ่าน)
- ดู alpha รายพอร์ตควบคู่ — ถ้ามีบางพอร์ต alpha นัยสำคัญ ให้ดูว่าเป็นกลุ่มไหน (small-value มักเป็นจุดที่โมเดลอธิบายไม่หมดในหลายงานวิจัย)
- ดู R² — ถ้าสูง (>0.85-0.95) แปลว่าปัจจัยอธิบาย variance ของผลตอบแทนได้มาก (แต่ไม่ได้แปลว่า pricing ถูกต้อง — R² สูงไม่เท่ากับ alpha=0)

---

## 5. แผนการเขียนโค้ด Python (เป็นขั้นตอน)

```
1. โหลดและทำความสะอาดข้อมูล
   - load_ff_csv(path) -> DataFrame (จัดการ skiprows, -99.99, date parsing)
   - merge portfolios + factors on date

2. คำนวณ excess return
   - excess_ret[port] = ret[port] - RF

3. รัน time-series regression ทีละพอร์ต
   for port in portfolio_list:
       X = sm.add_constant(factors[['Mkt-RF','SMB','HML','RMW','CMA']])
       y = excess_ret[port]
       model = sm.OLS(y, X).fit(cov_type='HAC', cov_kwds={'maxlags': 6})
       เก็บ params, tvalues, rsquared, resid

4. รวมผลเป็นตารางสรุป (alpha, beta ทั้งหมด, t-stat, R² ต่อพอร์ต)

5. เขียนฟังก์ชัน GRS test
   - รับ alpha vector, residual covariance matrix, factor mean/cov
   - คืนค่า GRS statistic, p-value (จาก scipy.stats.f)

6. Diagnostic checks
   - Residual plots (เช็ค heteroskedasticity)
   - Durbin-Watson หรือ Ljung-Box (เช็ค autocorrelation)
   - VIF ของปัจจัย (เช็ค multicollinearity ระหว่าง SMB/HML/RMW/CMA)

7. Visualization
   - Heatmap ของ factor loadings (6 พอร์ต × 5 betas)
   - Bar chart alpha พร้อม confidence interval
   - Actual vs Fitted return scatter

8. (Optional) เปรียบเทียบกับ CAPM / FF3
   - รันโมเดลที่เล็กกว่าเทียบ nested F-test / GRS เทียบกัน
   - ดูว่า RMW, CMA เพิ่ม explanatory power จริงไหม
```

ไลบรารีหลักที่ใช้: `pandas`, `numpy`, `statsmodels`, `scipy.stats`, `matplotlib`/`seaborn`

---

## 6. Robustness Checks (แนะนำเสริม)

| อย่างไร | ทำไม | สถานะ |
|---|---|---|
| แบ่ง sub-period (เช่น pre/post 2000, pre/post GFC) | เช็คว่าโมเดล stable ตลอดเวลาหรือ perform ต่างกันในแต่ละยุค | ✅ **ทำแล้ว** — ดูผลหัวข้อ 6.1 |
| ทดสอบด้วย test asset อื่น (25 Portfolios 5×5, Industry Portfolios) | แก้ปัญหา circularity ที่กล่าวถึงในหัวข้อ 1 | ⬜ ยังไม่ทำ |
| เทียบ FF5 vs FF3 vs CAPM | ดูว่าปัจจัยเพิ่ม (RMW, CMA) ช่วยจริงไหม หรือแค่ overfitting | ⬜ ยังไม่ทำ |
| ใช้ Fama-MacBeth cross-sectional regression แทน/เสริม | ทดสอบ risk premium ของแต่ละปัจจัยว่า priced จริงหรือไม่ (ต่างมุมจาก time-series test) | ⬜ ยังไม่ทำ |

### 6.1 ผล Sub-period Analysis (ทำแล้ว — 2026-08-18)

รันสมการเดิม (time-series regression 6 พอร์ต + Newey-West HAC + GRS test) ซ้ำแยก 3 ช่วงเวลา เพื่อเช็คว่าโมเดล stable ตลอดช่วง 1963-2026 หรือ perform ต่างกันในยุคหลังๆ:

| ช่วงเวลา | T (เดือน) | GRS statistic | p-value | ผล (5%) | จำนวนพอร์ตที่ α significant |
|---|---|---|---|---|---|
| Full (1963-07 – 2026-06) | 756 | 4.5708 | 0.000145 | FAIL | 4/6 |
| 2000-01 – 2026-06 | 318 | 2.7741 | 0.012165 | FAIL | 1/6 |
| 2016-01 – 2026-06 | 126 | 3.1205 | 0.00719 | FAIL | 1/6 |

**ข้อสังเกต:**
- GRS test **FAIL ทั้ง 3 ช่วง** (p < 0.05 ตลอด) — โมเดลยังไม่ผ่านในทุกช่วงเวลาที่ลองแบ่ง
- แต่จำนวนพอร์ตที่มี α significant รายตัว **ลดลงชัดเจน** จาก 4/6 (full sample) เหลือ 1/6 ในทั้งสองช่วงหลัง — mispricing เฉพาะพอร์ตดูอ่อนลงในยุคหลัง แม้การทดสอบร่วม (joint test) จะยังปฏิเสธโมเดลอยู่ก็ตาม
- พอร์ตที่มีปัญหาซ้ำในทุกช่วงเวลาคือ **BIG LoBM** (α เป็นบวกและ significant ทุกช่วง: t=3.20 → 3.42 → 3.40) ต่างจาก small-growth ที่มักเป็นปัญหาคลาสสิกในงานวิจัยทั่วไป
- β ยังตรงตามทฤษฎีในทุกช่วง (Mkt-RF≈1, SMB สูงในกลุ่ม SMALL, HML เพิ่มตาม BM) และ R² ยังสูงมาก (0.92-0.99) ทุกช่วง

**หมายเหตุการทำงาน:** การทดสอบนี้รันเป็น**สคริปต์แยกต่างหาก** (ไม่ได้แก้ไข `ff5_core.py` ซึ่งยังคงเป็น core script สำหรับ full-sample run) และมี**กราฟเปรียบเทียบ** (alpha รายพอร์ต × 3 ช่วงเวลา + GRS chart พร้อมตารางเต็ม) ส่งให้ดูแล้วในแชท — ยังไม่ได้เก็บไฟล์กราฟ/สคริปต์ไว้ในโฟลเดอร์นี้ถาวร (รอ confirm ว่าจะเก็บเป็นไฟล์ถาวรในโปรเจกต์ไหม)

---

## 7. ผลลัพธ์ที่ควรได้ตอนจบ

1. ตาราง regression summary (α, β ทั้ง 5 ตัว, t-stat, R² — 6 แถว)
2. ค่า GRS statistic + p-value + สรุปผลผ่าน/ไม่ผ่าน
3. กราฟ diagnostic (residual, factor loading heatmap)
4. ข้อสรุปเชิงเนื้อหา: โมเดลอธิบายได้ดีแค่ไหน มีพอร์ตไหนที่ยัง mispricing อยู่

---

## ข้อมูลอ้างอิง

- Ken French Data Library: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html
- Gibbons, Ross, Shanken (1989), "A Test of the Efficiency of a Given Portfolio", *Econometrica*
- Fama, Eugene F., and Kenneth R. French (2015), "A five-factor asset pricing model", *Journal of Financial Economics*

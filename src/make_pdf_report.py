"""
Build a print-quality Thai PDF report:  summary CSVs + charts -> styled HTML -> Chrome headless -> PDF.
Chrome renders Thai (Sukhumvit Set / Thonburi) natively, handles tables/page-breaks/embedded images.
"""
import os, base64, subprocess
import pandas as pd
import common as C

OUT = C.OUT
HTML = os.path.join(OUT, "report.html")
PDF = os.path.join(OUT, "Thai_Dividend_Backtest_Report.pdf")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def img64(name):
    with open(os.path.join(OUT, name), "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def df_table(df, pct_cols=(), highlight_row=None):
    head = "".join(f"<th>{c}</th>" for c in df.columns)
    rows = []
    for i, (_, r) in enumerate(df.iterrows()):
        cells = []
        for c in df.columns:
            v = r[c]
            if isinstance(v, float):
                v = f"{v:,.3f}" if abs(v) < 100 else f"{v:,.2f}"
            cells.append(f"<td>{v}</td>")
        cls = ' class="hl"' if highlight_row is not None and i == highlight_row else ""
        rows.append(f"<tr{cls}>{''.join(cells)}</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def main():
    cmp_ = pd.read_csv(os.path.join(OUT, "summary_method_comparison.csv"))
    acc = pd.read_csv(os.path.join(OUT, "summary_forecast_accuracy_overall.csv"))
    acch = pd.read_csv(os.path.join(OUT, "summary_forecast_accuracy_by_holding.csv"))
    wts = pd.read_csv(os.path.join(OUT, "summary_avg_weights.csv"))
    res = pd.read_csv(os.path.join(C.DATA, "backtest_results.csv"))
    comp = pd.read_csv(os.path.join(C.DATA, "data_completeness.csv"))

    n_real = int((res.status == "realized").sum()); n_pend = int((res.status == "pending").sum())
    # overall avg weight table
    wov = wts.copy()

    # method comparison — keep key cols, rename Thai
    cmpv = cmp_[["forecast_method", "holding_period", "n", "mean_forecast_div",
                 "mean_realized_div", "mean_capital_gain", "mean_total_return"]].copy()
    cmpv.columns = ["วิธี", "ถือ(เดือน)", "n", "ปันผล forecast", "ปันผล realized", "capital gain", "total return"]

    accv = acc.copy(); accv.columns = ["วิธี", "n", "Bias (pp)", "MAE (pp)", "RMSE (pp)"]

    css = """
    @page { size: A4; margin: 16mm 14mm; }
    * { box-sizing: border-box; }
    body { font-family: "Sukhumvit Set","Thonburi","Helvetica Neue",sans-serif; color:#1a1a2e;
           font-size: 11px; line-height: 1.55; margin:0; }
    h1 { font-size: 23px; margin:0 0 2px; color:#0f2b46; }
    h2 { font-size: 15px; margin:20px 0 8px; color:#0f2b46; border-bottom:2px solid #55A868; padding-bottom:3px; }
    h3 { font-size: 12.5px; margin:14px 0 5px; color:#334; }
    .sub { color:#667; font-size:11px; margin-bottom:2px; }
    .meta { color:#889; font-size:10px; }
    table { border-collapse: collapse; width:100%; margin:6px 0 10px; font-size:10px; }
    th { background:#0f2b46; color:#fff; text-align:left; padding:5px 7px; font-weight:600; }
    td { padding:4px 7px; border-bottom:1px solid #e3e7ee; }
    tbody tr:nth-child(even){ background:#f6f8fb; }
    tr.hl td { background:#e8f5ec; font-weight:700; }
    .kpi-row { display:flex; gap:10px; margin:10px 0; }
    .kpi { flex:1; background:#f6f8fb; border:1px solid #e3e7ee; border-left:4px solid #55A868;
           border-radius:6px; padding:9px 11px; }
    .kpi .big { font-size:18px; font-weight:700; color:#0f2b46; }
    .kpi .lbl { font-size:9.5px; color:#667; }
    ol.find { margin:6px 0 6px 16px; padding:0; } ol.find li { margin:5px 0; }
    .callout { background:#eef6f1; border:1px solid #cfe6d8; border-radius:6px; padding:9px 12px; margin:10px 0; }
    .chart { text-align:center; margin:8px 0 4px; } .chart img { width:100%; max-width:640px; border:1px solid #e3e7ee; border-radius:6px; }
    .cap { font-size:9px; color:#889; text-align:center; margin-bottom:8px; }
    .warn li { margin:4px 0; }
    .pb { page-break-before: always; }
    .foot { margin-top:14px; padding-top:6px; border-top:1px solid #e3e7ee; font-size:9px; color:#99a; }
    code { background:#eef; padding:1px 4px; border-radius:3px; font-size:9.5px; }
    """

    html = f"""<!doctype html><html lang="th"><head><meta charset="utf-8"><style>{css}</style></head><body>

    <h1>รายงานผล — Thai Dividend Yield Portfolio</h1>
    <div class="sub">ระบบ Walk-Forward Backtest หาพอร์ตหุ้นปันผลที่ maximize ผลตอบแทนจากเงินปันผล</div>
    <div class="meta">วันที่รัน 2026-08-06 · Universe: AOT, OR, KTB, PTT, PTTEP (หุ้นหลักบังคับถือ ≥5%) ·
       Entry 20 จุด (2021Q4→2026Q3) · Holding 3/6/9/12 เดือน · 4 วิธี forecast · 320 LP runs</div>

    <div class="kpi-row">
      <div class="kpi"><div class="big">naive</div><div class="lbl">วิธี forecast ที่แม่นสุด (MAE 0.69pp)</div></div>
      <div class="kpi"><div class="big">~9 เดือน</div><div class="lbl">holding ที่ total return เฉลี่ยดีสุด</div></div>
      <div class="kpi"><div class="big">PTTEP 39%</div><div class="lbl">น้ำหนักเฉลี่ยสูงสุด (พอร์ตกระจุก)</div></div>
      <div class="kpi"><div class="big">{n_real}/{n_real+n_pend}</div><div class="lbl">runs ที่ realized ครบ ({n_pend} pending)</div></div>
    </div>

    <h2>1. ข้อสรุปสำคัญ</h2>
    <ol class="find">
      <li><b>วิธีพยากรณ์ปันผลที่แม่นสุดคือ <code>naive</code></b> (ใช้ปันผลงวดเดียวกันล่าสุด) — MAE ต่ำสุด 0.69pp,
          RMSE 1.21pp สอดคล้องกับปันผลหุ้นไทยที่ "เหนียว" เปลี่ยนช้า</li>
      <li><b>ทุกวิธี under-forecast เล็กน้อย</b> (bias +0.4 ถึง +0.7pp) เพราะปันผลจริงช่วง 2022–2026 ฟื้นหลัง COVID เร็วกว่าประวัติ</li>
      <li><b>Total return ถูกครอบงำด้วย capital gain ไม่ใช่คุณภาพ forecast</b> — <code>yield_based</code> ให้ total return
          เฉลี่ยสูงสุด แต่เป็นเพราะบังเอิญ concentrate เข้าหุ้นที่ราคาขึ้นแรง (ผลพลอยได้ ไม่ใช่ทักษะ forecast)</li>
      <li><b>Holding ~9 เดือน total return เฉลี่ยดีสุด</b>; 12 เดือนแย่ลงเพราะเจอช่วงราคาย่อคืน</li>
      <li><b>พอร์ตกระจุกตัวสูง</b> (PTTEP 39%, OR ติด floor 5% เสมอ) — เป็น corner solution ของ LP ตาม spec ไม่ใช่บั๊ก</li>
    </ol>
    <div class="callout"><b>คำตอบตรงคำถามตั้งต้น:</b> ถ้าเป้าหมายคือ <b>พยากรณ์ปันผลให้แม่น</b> → ใช้ <b>naive</b>.
       ถ้าดูจาก <b>total return ในอดีต</b> → yield_based เด่นสุด แต่มาจากการเดาถูกด้าน capital gain
       ซึ่งไม่ใช่สิ่งที่ระบบตั้งใจ optimize และไม่การันตีว่าจะซ้ำ</div>

    <h2>2. ความแม่นของ Forecast ปันผล (ต่อหุ้น, ไม่ขึ้นกับน้ำหนัก)</h2>
    <div class="sub">วัดจาก realized − forecast dividend return ต่อ (entry × ticker × holding) หน่วย percentage point (pp) · MAE ต่ำ = แม่นกว่า</div>
    {df_table(accv, highlight_row=0)}

    <div class="chart"><img src="{img64('boxplot_total_return.png')}"></div>
    <div class="cap">รูป 1 — การกระจาย total return ต่อ holding period และวิธี forecast</div>

    <div class="pb"></div>
    <h2>3. เปรียบเทียบ 4 วิธี × Holding Period (พอร์ตหลัง optimize, %)</h2>
    <div class="sub">เฉลี่ยเฉพาะ run ที่ realized ครบแล้ว ({n_real} จาก {n_real+n_pend} runs)</div>
    {df_table(cmpv)}

    <h2>4. น้ำหนักพอร์ตเฉลี่ยต่อหุ้น</h2>
    {df_table(wov)}
    <div class="chart"><img src="{img64('avg_weights.png')}"></div>
    <div class="cap">รูป 2 — น้ำหนักเฉลี่ยต่อหุ้น แยกตามวิธี forecast (เส้นประแดง = ขั้นต่ำ 5%)</div>

    <div class="chart"><img src="{img64('timeline_6m.png')}"></div>
    <div class="cap">รูป 3 — total return จริงเทียบ forecast ปันผล รายไตรมาส (holding 6 เดือน)</div>

    <div class="pb"></div>
    <h2>5. คุณภาพข้อมูล (Data Completeness)</h2>
    {df_table(comp[['ticker','n_price_days','price_start','price_end','n_dividends','div_start','div_end','sa_agree']])}
    <div class="sub">คอลัมน์ sa_agree = จำนวนรายการปันผลล่าสุดที่ yfinance ตรงกับ StockAnalysis.com (cross-check ผ่าน 6/6 ทุกตัว)</div>

    <h2>6. ข้อควรระวัง &amp; Assumptions</h2>
    <ol class="find warn">
      <li><b>ราคา split-adjusted ฐานปัจจุบัน ไม่ปรับปันผล</b> — จัดการ stock split อัตโนมัติ (AOT 2017, PTT 2018, PTTEP 2006 ทั้งหมดก่อนหน้าต่าง backtest)</li>
      <li><b>AOT จ่ายปันผลปีละครั้ง (ธ.ค.) จริง</b> — ยืนยันด้วย yfinance ย้อนถึง 2005 (ไม่ได้ขาด interim); gap 2021–22 = งดจ่ายช่วง COVID</li>
      <li><b>Special dividend</b> ไม่รวมใน forecast (คาดไม่ได้) แต่รวมใน realized เสมอ</li>
      <li><b>{n_pend} runs เป็น pending</b> — holding window ยังไม่ครบ ณ 6 ส.ค. 2026 ไม่นำมาเฉลี่ย</li>
      <li><b>LP corner solution → พอร์ตกระจุกตัว</b> เป็นไปตาม spec (ไม่มี risk penalty / weight cap)</li>
      <li><b>forecast_error ในตารางข้อ 3 เป็นระดับพอร์ต</b> (ขึ้นกับ weight) ต่างจากความแม่นต่อหุ้นในข้อ 2 — ใช้ข้อ 2 ตัดสิน "วิธีไหนแม่น"</li>
    </ol>

    <div class="foot">Thai Dividend Yield Portfolio — Walk-Forward Backtest · แหล่งข้อมูล: yfinance (หลัก) +
       StockAnalysis.com (cross-check) · reproducible ด้วย src/fetch_data.py → phase34 → phase56 → phase78 ·
       ไฟล์ผลลัพธ์เต็ม: output/thai_dividend_backtest.xlsx</div>
    </body></html>"""

    with open(HTML, "w", encoding="utf-8") as f:
        f.write(html)

    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={PDF}", f"file://{HTML}"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("WROTE", PDF, "(", os.path.getsize(PDF), "bytes )")


if __name__ == "__main__":
    main()

"""
probe_data_availability.py — ทดสอบ data availability จาก yfinance ก่อนสร้าง pipeline เต็ม
=========================================================================================
ตาม Next Step (ข้อ 7) ของแผน: เขียน script สั้นๆ ดึงข้อมูล 3-5 หุ้นตัวอย่าง เช็คว่า field
ที่ pipeline ต้องใช้จริงมีข้อมูลและย้อนหลังได้กี่ไตรมาส ก่อนลงมือสร้าง pipeline เต็มรูปแบบ

เช็ค 4 อย่างต่อหุ้น:
  1) ราคาปิด adjusted รายเดือน (interval="1mo")           -> ใช้คำนวณ return + market cap
  2) quarterly_balance_sheet -> "Stockholders Equity"      -> ใช้เป็น Book Equity (B/M)
  3) sharesOutstanding (info + balance sheet shares)       -> ใช้คำนวณ market cap
  4) ^SET50.BK index รายเดือน                              -> ใช้เป็น market factor (Mkt-RF)

รัน:  python probe_data_availability.py
ผลลัพธ์จะบอกว่า Open Item #2 (lookback ลึกกี่ไตรมาส) และ field ต่างๆ ใช้ได้จริงแค่ไหน
"""

import warnings

import pandas as pd
import yfinance as yf

warnings.simplefilter("ignore")
pd.set_option("display.width", 120)

# หุ้นตัวอย่างจาก SET50 คนละเซกเตอร์ (พลังงาน/แบงก์/ค้าปลีก/สื่อสาร/อาหาร)
SAMPLE_TICKERS = ["PTT.BK", "KBANK.BK", "CPALL.BK", "ADVANC.BK", "CPF.BK"]
INDEX_TICKER = "^SET50.BK"

# ชื่อแถวที่เป็นไปได้สำหรับ book equity ใน balance sheet ของ yfinance (จะลองไล่ตามลำดับ)
EQUITY_ROW_CANDIDATES = [
    "Stockholders Equity",
    "Total Stockholders Equity",
    "Common Stock Equity",
    "Total Equity Gross Minority Interest",
]
SHARES_ROW_CANDIDATES = [
    "Ordinary Shares Number",
    "Share Issued",
    "Common Stock Shares Outstanding",
]


def probe_prices(ticker: str) -> str:
    """ดึงราคารายเดือน 5 ปี เช็คจำนวนเดือน + ช่วงวันที่"""
    try:
        df = yf.download(
            ticker, period="5y", interval="1mo",
            auto_adjust=True, progress=False, threads=False,
        )
        if df is None or df.empty:
            return "  [prices] ❌ ว่างเปล่า"
        close = df["Close"].dropna()
        n = len(close)
        first = close.index.min().date()
        last = close.index.max().date()
        return f"  [prices] ✅ {n} เดือน  ({first} → {last})"
    except Exception as e:
        return f"  [prices] ❌ error: {e}"


def probe_balance_sheet(tk: yf.Ticker) -> str:
    """เช็ค quarterly_balance_sheet: หา equity row + shares row + ความลึก (กี่ไตรมาส)"""
    try:
        qbs = tk.quarterly_balance_sheet
        if qbs is None or qbs.empty:
            return "  [balance] ❌ quarterly_balance_sheet ว่าง"
        cols = list(qbs.columns)  # แต่ละ column = วันที่ปิดงบหนึ่งไตรมาส
        n_q = len(cols)
        span = f"{min(cols).date()} → {max(cols).date()}" if cols else "-"

        eq_row = next((r for r in EQUITY_ROW_CANDIDATES if r in qbs.index), None)
        sh_row = next((r for r in SHARES_ROW_CANDIDATES if r in qbs.index), None)

        lines = [f"  [balance] ✅ {n_q} ไตรมาส  ({span})"]
        if eq_row:
            vals = qbs.loc[eq_row].dropna()
            lines.append(f"    equity  row = '{eq_row}'  ({len(vals)}/{n_q} มีค่า)")
        else:
            lines.append(f"    equity  ❌ ไม่พบใน {EQUITY_ROW_CANDIDATES}")
            lines.append(f"    (rows ที่มี: {list(qbs.index)[:12]} ...)")
        if sh_row:
            vals = qbs.loc[sh_row].dropna()
            lines.append(f"    shares  row = '{sh_row}'  ({len(vals)}/{n_q} มีค่า)")
        else:
            lines.append(f"    shares  ⚠️  ไม่พบใน balance sheet {SHARES_ROW_CANDIDATES}")
        return "\n".join(lines)
    except Exception as e:
        return f"  [balance] ❌ error: {e}"


def probe_shares_info(tk: yf.Ticker) -> str:
    """เช็ค sharesOutstanding จาก .info (ค่า ณ ปัจจุบันเท่านั้น — ใช้เป็น fallback)"""
    try:
        info = tk.info
        so = info.get("sharesOutstanding")
        mc = info.get("marketCap")
        return f"  [info]    sharesOutstanding={so:,}  marketCap={mc:,}" if so else \
               "  [info]    ⚠️  ไม่มี sharesOutstanding ใน .info"
    except Exception as e:
        return f"  [info]    ❌ error: {e}"


def main():
    print("=" * 78)
    print("PROBE: data availability สำหรับ SET50 FF3 pipeline (yfinance 1.3.0)")
    print("=" * 78)

    for ticker in SAMPLE_TICKERS:
        print(f"\n### {ticker}")
        print(probe_prices(ticker))
        tk = yf.Ticker(ticker)
        print(probe_balance_sheet(tk))
        print(probe_shares_info(tk))

    print(f"\n### INDEX {INDEX_TICKER} (market factor)")
    print(probe_prices(INDEX_TICKER))

    print("\n" + "=" * 78)
    print("สรุป: ดูว่า [balance] ลึกกี่ไตรมาส = ตัวจำกัด backtest window จริง (Open Item #2)")
    print("=" * 78)


if __name__ == "__main__":
    main()

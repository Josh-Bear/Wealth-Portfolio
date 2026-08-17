"""
data/constituents.py — รายชื่อ SET50 (fixed current universe)
=============================================================
ตาม Open Item #1 (ยืนยันแล้ว): ใช้รายชื่อ SET50 "ปัจจุบัน" แบบ fixed ทั้ง backtest
-> มี survivorship bias โดยตั้งใจ (หุ้นที่เคยหลุด SET50 จะไม่ปรากฏ) — เป็น known
   simplification เพื่อทดสอบ mechanism ก่อน; อยากได้ research-grade ค่อยเพิ่ม
   point-in-time constituent list เป็น phase 2

หมายเหตุ: Yahoo ไม่มี endpoint รายชื่อ SET50 -> ต้อง hardcode/maintain เอง
ปรับรายชื่อได้ตรงนี้ที่เดียว (แก้ SET50_TICKERS) แล้วทั้ง pipeline จะตามอัตโนมัติ
"""

# 50 ตัว (สัญลักษณ์ SET) — เติม suffix .BK ให้อัตโนมัติใน get_set50_constituents()
# อ้างอิงองค์ประกอบ SET50 รอบล่าสุด ณ เวลาเขียน — ผู้ใช้ควร verify/ปรับให้ตรงงวดที่ต้องการ
_SET50_SYMBOLS = [
    "ADVANC", "AOT", "AWC", "BANPU", "BBL", "BDMS", "BEM", "BGRIM", "BH", "BTS",
    "CBG", "CENTEL", "COM7", "CPALL", "CPF", "CPN", "CRC", "DELTA", "EA", "EGCO",
    "GLOBAL", "GPSC", "GULF", "HMPRO", "IVL", "KBANK", "KCE", "KTB", "KTC", "LH",
    "MINT", "MTC", "OR", "OSP", "PTT", "PTTEP", "PTTGC", "RATCH", "SAWAD", "SCB",
    "SCC", "SCGP", "TIDLOR", "TISCO", "TLI", "TOP", "TRUE", "TTB", "TU", "WHA",
]


def get_set50_constituents() -> list[str]:
    """
    คืน list ของ ticker รูปแบบ yfinance ('XXXX.BK') สำหรับ universe SET50 ปัจจุบัน
    (fixed ตลอด backtest ตาม Open Item #1)
    """
    return [f"{s}.BK" for s in _SET50_SYMBOLS]


if __name__ == "__main__":
    tickers = get_set50_constituents()
    print(f"SET50 fixed universe: {len(tickers)} ตัว")
    print(", ".join(tickers))

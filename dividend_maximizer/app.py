"""
Dividend Maximizer -- Streamlit UI over optimizer.py.

Two modes on one page:
  * single entry  : pick a year + half + forecast method -> ranking, chosen portfolio (real board
    lots), expected dividend, leftover cash. "เทียบทั้ง 3 วิธี" shows the three side by side.
  * backtest      : 2023-2026 H2, decision weights vs the dividend that actually landed
    (past years realized, the in-progress year flagged pending).

Run:  streamlit run dividend_maximizer/app.py
Data + constants come from the main project via optimizer.py (which imports its common.py).
"""
import os
import sys
import pandas as pd
import streamlit as st
import plotly.express as px

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optimizer as O  # noqa: E402
import common as C    # type: ignore

st.set_page_config(page_title="Dividend Maximizer", layout="wide")

NAMES = {"AOT": "ท่าอากาศยานไทย", "OR": "ปตท.น้ำมันฯ(OR)", "KTB": "กรุงไทย", "PTT": "ปตท.",
         "PTTEP": "ปตท.สผ.", "SCB": "SCBX", "BBL": "กรุงเทพ", "KBANK": "กสิกรไทย",
         "TTB": "ทหารไทยธนชาต", "BAY": "กรุงศรีฯ"}
BACKTEST_YEARS = [2023, 2024, 2025, 2026]


@st.cache_data
def _prices():
    return C.load_prices()


def _year_options():
    yrs = sorted(_prices()["date"].dt.year.unique())
    return [int(y) for y in yrs if y >= yrs[0] + 5]   # need a few prior years for a forecast


# ---------------- sidebar ----------------
st.sidebar.title("Dividend Maximizer")
st.sidebar.caption("เลือกหุ้น ≥5 ตัว (5–30%) ให้ได้ปันผลครึ่งปีสูงสุด · greedy (คนละแบบกับ water-fill เดิม)")

year_opts = _year_options()
year = st.sidebar.selectbox("ปี", year_opts, index=len(year_opts) - 1)
half = st.sidebar.radio("ครึ่งปี", ["H2", "H1"], index=0, horizontal=True,
                        help="H2 = เข้าต้น ก.ค. · H1 = เข้าต้น ม.ค.")
method_choice = st.sidebar.radio("วิธีพยากรณ์", O.METHODS + ["เทียบทั้ง 3 วิธี"],
                                 format_func=lambda m: O.MLABEL.get(m, m))
st.sidebar.markdown("---")
capital = st.sidebar.number_input("เงินทุน (บาท)", value=C.CAPITAL, step=10_000_000, format="%d")
commission = st.sidebar.number_input("ค่าคอมมิชชั่น (%)", value=O.COMMISSION * 100, step=0.001,
                                     format="%.3f") / 100.0
lot = st.sidebar.number_input("Board lot (หุ้น)", value=O.LOT_SIZE, step=100, format="%d")

prices = _prices()
entry = O.half_entry_date(prices, year, half)
if entry is None:
    st.error(f"ไม่มีวันเทรดในครึ่งปี {half} ของปี {year}")
    st.stop()

st.title("Dividend Maximizer — พอร์ตปันผลครึ่งปีสูงสุด")
st.caption(f"Entry: **{entry.date()}** ({half} {year}) · ทุน **{capital:,.0f}** บาท · "
           f"commission **{commission*100:.3f}%** · lot **{lot}** · เลือกอย่างน้อย {O.MIN_STOCKS} ตัว "
           f"(น้ำหนัก {O.FLOOR*100:.0f}–{O.CEILING*100:.0f}%)")

tab_single, tab_backtest = st.tabs(["🎯 พอร์ตจุดเดียว", "📅 Backtest 2023–2026"])


def _fmt_portfolio(port):
    """Prettify a portfolio frame (only bought rows) for display."""
    p = port[port["shares"] > 0].copy()
    p["หุ้น"] = p["ticker"].map(lambda t: f"{t} — {NAMES.get(t, t)}")
    p["น้ำหนักเป้า"] = (p["target_weight"] * 100).map(lambda v: f"{v:.0f}%")
    p["น้ำหนักจริง"] = (p["actual_weight_pct"] * 100).map(lambda v: f"{v:.2f}%")
    p["ราคา"] = p["price"].map(lambda v: f"{v:,.2f}")
    p["จำนวนหุ้น"] = p["shares"].map(lambda v: f"{int(v):,}")
    p["เงินลงทุน"] = p["invest_value"].map(lambda v: f"{v:,.0f}")
    p["ค่าคอม"] = p["commission_paid"].map(lambda v: f"{v:,.0f}")
    p["ปันผลคาด"] = p["expected_dividend"].map(lambda v: f"{v:,.0f}")
    # actual dividend if this half has already paid it; "-" while the half is still pending
    p["ปันผลจริง"] = ["-" if pend else f"{v:,.0f}"
                     for v, pend in zip(p["realized_dividend"], p["realized_pending"])]
    return p[["หุ้น", "น้ำหนักเป้า", "น้ำหนักจริง", "ราคา", "จำนวนหุ้น", "เงินลงทุน", "ค่าคอม",
              "ปันผลคาด", "ปันผลจริง"]]


def _summary_row(r):
    c = st.columns(4)
    c[0].metric("ปันผลคาดรวม", f"{r['expected_dividend']:,.0f}", f"{r['expected_dividend']/r['capital']*100:.2f}% ของทุน")
    c[1].metric("เงินลงทุนจริง", f"{r['invested']:,.0f}")
    c[2].metric("ค่าคอมรวม", f"{r['commission_total']:,.0f}")
    c[3].metric("เงินสดคงเหลือ", f"{r['leftover_cash']:,.0f}")


def _render_single(method):
    r = O.run(entry, method, capital=capital, commission=commission)
    _summary_row(r)
    st.subheader("พอร์ตที่เลือก")
    st.dataframe(_fmt_portfolio(r["portfolio"]), use_container_width=True, hide_index=True)
    with st.expander("อันดับหุ้นทั้งหมด (ทำไมเลือก/ไม่เลือก) — score = yield ที่พยากรณ์"):
        rk = r["ranking"].copy()
        rk["forecast_dps"] = rk["forecast_dps"].map(lambda v: f"{v:.4f}")
        rk["score_yield"] = (rk["score_yield"] * 100).map(lambda v: f"{v:.2f}%")
        rk = rk.rename(columns={"ticker": "หุ้น", "forecast_dps": "ปันผลคาด(บาท/หุ้น)",
                                "price": "ราคา", "score_yield": "yield คาด"})
        st.dataframe(rk, use_container_width=True, hide_index=True)
    st.download_button("⬇️ ดาวน์โหลดพอร์ต (CSV)",
                       r["portfolio"][r["portfolio"]["shares"] > 0].to_csv(index=False).encode("utf-8"),
                       f"portfolio_{year}{half}_{method}.csv", "text/csv")


with tab_single:
    if method_choice == "เทียบทั้ง 3 วิธี":
        st.subheader("เทียบ 3 วิธีพยากรณ์")
        runs = {m: O.run(entry, m, capital=capital, commission=commission) for m in O.METHODS}
        comp = pd.DataFrame([{"วิธี": O.MLABEL[m], "ปันผลคาด": runs[m]["expected_dividend"],
                              "% ของทุน": runs[m]["expected_dividend"] / capital * 100,
                              "เงินสดเหลือ": runs[m]["leftover_cash"]} for m in O.METHODS])
        fig = px.bar(comp, x="วิธี", y="ปันผลคาด", color="วิธี", text_auto=".2s",
                     title="ปันผลคาดรวมแต่ละวิธี")
        fig.update_layout(height=340, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        cols = st.columns(3)
        for col, m in zip(cols, O.METHODS):
            with col:
                st.markdown(f"**{O.MLABEL[m]}**")
                rr = runs[m]
                st.caption(f"ปันผลคาด {rr['expected_dividend']:,.0f} ({rr['expected_dividend']/capital*100:.2f}%)")
                st.dataframe(_fmt_portfolio(rr["portfolio"])[["หุ้น", "น้ำหนักเป้า", "จำนวนหุ้น", "ปันผลคาด"]],
                             use_container_width=True, hide_index=True)
    else:
        _render_single(method_choice)


with tab_backtest:
    st.subheader("Backtest 2023–2026 (H2) — ตัดสินใจ vs ปันผลที่ได้จริง")
    bt_method = method_choice if method_choice in O.METHODS else "avg3y"
    st.caption(f"วิธีพยากรณ์: **{O.MLABEL[bt_method]}** · TODAY = {C.TODAY.date()} "
               f"(ปีที่ยังไม่จบครึ่งปี = pending, ไม่ใส่เลขเดา)")
    bt = O.run_backtest(BACKTEST_YEARS, bt_method, capital=capital, commission=commission)
    show = bt.copy()
    show["ปันผลจริง"] = [f"{v:,.0f} ({p:.2f}%)" if s == "realized" else "⏳ pending"
                        for v, p, s in zip(show["realized_dividend"], show["realized_pct"], show["status"])]
    show["ปันผลคาด"] = show["expected_dividend"].map(lambda v: f"{v:,.0f}")
    show["year"] = show["year"].astype(str)   # avoid the "2,023" thousands-separator on the year
    show = show.rename(columns={"year": "ปี", "entry_date": "วันเข้า", "stocks": "หุ้นที่เลือก",
                                "status": "สถานะ"})
    st.dataframe(show[["ปี", "วันเข้า", "หุ้นที่เลือก", "ปันผลคาด", "ปันผลจริง", "สถานะ"]],
                 use_container_width=True, hide_index=True)
    done = bt[bt["status"] == "realized"]
    if not done.empty:
        fig2 = px.bar(done, x="year", y=["expected_dividend", "realized_dividend"], barmode="group",
                      title="คาด vs จริง (เฉพาะปีที่จบแล้ว)", labels={"value": "บาท", "year": "ปี"})
        fig2.update_layout(height=340)
        st.plotly_chart(fig2, use_container_width=True)

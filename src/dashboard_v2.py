"""
Interactive dashboard v2 — เลือกหุ้นรองเข้า/ออกเองได้ (add/remove) แล้ว LP + backtest คำนวณใหม่สด ๆ.
เงินทุน 100 ล้านบาท · entry รายเดือน (60 จุด) · หุ้นหลัก 5 ตัวบังคับ >=5% · หุ้นรอง 5 ตัวเลือกได้.

per-stock forecast return / realized ถูก precompute ไว้แล้ว (ไม่ขึ้นกับ universe) →
มีแค่ LP จัดน้ำหนักที่คำนวณสดตามหุ้นที่เลือก → เร็ว & interactive จริง.

Run:  streamlit run src/dashboard_v2.py
"""
import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from scipy.optimize import linprog

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")

CORE = ["AOT", "OR", "KTB", "PTT", "PTTEP"]
SECONDARY = ["SCB", "BBL", "KBANK", "TTB", "BAY"]
MORDER = ["naive", "avg_3_5y", "yield_based", "growth_trend"]
MCOLORS = {"naive": "#4C72B0", "avg_3_5y": "#DD8452", "yield_based": "#55A868", "growth_trend": "#C44E52"}
HOLDINGS = [3, 6, 9, 12]
CORE_MIN = 0.05
NAMES = {"AOT": "ท่าอากาศยานไทย", "OR": "ปตท.น้ำมันฯ(OR)", "KTB": "กรุงไทย", "PTT": "ปตท.",
         "PTTEP": "ปตท.สผ.", "SCB": "SCBX", "BBL": "กรุงเทพ", "KBANK": "กสิกรไทย",
         "TTB": "ทหารไทยธนชาต", "BAY": "กรุงศรีฯ"}

st.set_page_config(page_title="Thai Dividend Backtest v2", page_icon="💰", layout="wide")


def eorder(s):  # 'YYYY-MM' chronological sort key
    return s.map(lambda e: (int(e[:4]), int(e[5:7])))


@st.cache_data
def load_base():
    fr = pd.read_csv(os.path.join(DATA, "forecast_return.csv"))
    rbs = pd.read_csv(os.path.join(DATA, "realized_by_stock.csv"))
    div = pd.read_csv(os.path.join(DATA, "dividend_history.csv"), parse_dates=["ex_dividend_date"])
    price = pd.read_csv(os.path.join(DATA, "price_history.csv"), parse_dates=["date"])
    slots = pd.read_csv(os.path.join(DATA, "expected_dividend_months.csv"))
    # index helpers
    fr_key = {k: g.set_index("ticker") for k, g in fr.groupby(["entry_id", "holding_period", "method"])}
    rbs_key = {k: g.set_index("ticker") for k, g in rbs.groupby(["entry_id", "holding_period"])}
    entries = sorted(fr.entry_id.unique(), key=lambda e: (int(e[:4]), int(e[5:7])))
    return fr, rbs, div, price, slots, fr_key, rbs_key, entries


def lp_weights(fmap, universe, available):
    tickers = [t for t in universe if t in available]
    if not tickers:
        return {}
    r = np.array([fmap.get(t, 0.0) for t in tickers], float)
    lo = np.array([CORE_MIN if t in CORE else 0.0 for t in tickers])
    if lo.sum() > 1:
        lo = lo * (0.999 / lo.sum())
    res = linprog(-r, A_eq=np.ones((1, len(tickers))), b_eq=[1.0],
                  bounds=list(zip(lo, [1.0] * len(tickers))), method="highs")
    w = res.x if res.success else lo
    return {t: float(wi) for t, wi in zip(tickers, w)}


@st.cache_data(show_spinner="กำลังรัน LP + backtest ใหม่ตาม universe ที่เลือก...")
def run_backtest(selected_secondaries, _fr_key, _rbs_key):
    """LP live over CORE + selected secondaries for every entry×holding×method."""
    universe = CORE + list(selected_secondaries)
    wrows, rrows = [], []
    for (eid, h, m), fg in _fr_key.items():
        fmap = fg["forecast_dividend_return"].to_dict()
        pentry = fg["price_entry"].to_dict()
        available = {t for t in universe if t in pentry and pd.notna(pentry[t])}
        w = lp_weights(fmap, universe, available)
        rg = _rbs_key.get((eid, h))
        pending = bool(rg["pending"].iloc[0]) if rg is not None and len(rg) else True
        port_fc = sum(wt * fmap.get(t, 0.0) for t, wt in w.items())
        for t, wt in w.items():
            wrows.append({"entry_id": eid, "holding_period": h, "forecast_method": m,
                          "ticker": t, "weight": wt})
        if pending or rg is None:
            rrows.append({"entry_id": eid, "holding_period": h, "forecast_method": m,
                          "forecast_dividend_return": port_fc, "realized_dividend_return": np.nan,
                          "capital_gain_loss": np.nan, "total_return": np.nan,
                          "forecast_error": np.nan, "status": "pending"})
        else:
            rdr = sum(wt * rg.loc[t, "realized_div_return"] for t, wt in w.items() if t in rg.index)
            cap = sum(wt * rg.loc[t, "capital_gain"] for t, wt in w.items() if t in rg.index)
            rrows.append({"entry_id": eid, "holding_period": h, "forecast_method": m,
                          "forecast_dividend_return": port_fc, "realized_dividend_return": rdr,
                          "capital_gain_loss": cap, "total_return": rdr + cap,
                          "forecast_error": rdr - port_fc, "status": "realized"})
    return pd.DataFrame(wrows), pd.DataFrame(rrows)


FR, RBS, DIV, PRICE, SLOTS, FR_KEY, RBS_KEY, ENTRIES = load_base()

# ---------------- Sidebar: the interactive universe control ----------------
st.sidebar.title("💰 Thai Dividend Backtest v2")
st.sidebar.caption("ทุน 100 ล้านบาท · entry รายเดือน 60 จุด (2021-09→2026-08)")
st.sidebar.markdown("### 🏢 หุ้นหลัก (บังคับถือ ≥5%)")
st.sidebar.write("· " + " · ".join(CORE))
st.sidebar.markdown("### ➕➖ หุ้นรอง (กดเพิ่ม/ลดได้เอง)")
sel_sec = []
for s in SECONDARY:
    default = (s == "SCB")  # เริ่มด้วย SCB ติ๊กไว้ให้เห็น effect
    if st.sidebar.checkbox(f"{s} — {NAMES[s]}", value=default, key=f"sec_{s}"):
        sel_sec.append(s)
qc = st.sidebar.columns(2)
if qc[0].button("เลือกทั้งหมด", use_container_width=True):
    for s in SECONDARY: st.session_state[f"sec_{s}"] = True
    st.rerun()
if qc[1].button("ล้างหุ้นรอง", use_container_width=True):
    for s in SECONDARY: st.session_state[f"sec_{s}"] = False
    st.rerun()
st.sidebar.markdown("---")
capital = st.sidebar.number_input("เงินทุน (บาท)", value=100_000_000, step=10_000_000, format="%d")
methods = st.sidebar.multiselect("วิธี forecast", MORDER, default=MORDER) or MORDER
holds = st.sidebar.multiselect("Holding (เดือน)", HOLDINGS, default=HOLDINGS) or HOLDINGS
freq = st.sidebar.radio("ความถี่ entry", ["รายเดือน (60)", "รายไตรมาส (20)"], index=0)
show_pending = st.sidebar.checkbox("รวม runs pending", value=False)

universe = CORE + sel_sec
W, R = run_backtest(tuple(sel_sec), FR_KEY, RBS_KEY)

# apply filters
Q_MONTHS = {1, 4, 7, 10}
def apply_freq(df):
    if freq.startswith("รายไตรมาส"):
        return df[df.entry_id.str[5:7].astype(int).isin(Q_MONTHS)]
    return df
W = apply_freq(W); R = apply_freq(R)
Rf = R[R.forecast_method.isin(methods) & R.holding_period.isin(holds)].copy()
Wf = W[W.forecast_method.isin(methods) & W.holding_period.isin(holds)].copy()
Rr = Rf[Rf.status == "realized"].copy()
Rview = Rf if show_pending else Rr

st.title("Backtest พอร์ตหุ้นปันผลไทย — เลือกหุ้นรองเองได้")
st.caption(f"Universe ปัจจุบัน: **{len(universe)} ตัว** = 5 หุ้นหลัก + หุ้นรองที่เลือก "
           f"({', '.join(sel_sec) if sel_sec else 'ไม่เลือกเลย'})")

# ---------------- KPI ----------------
avg_div_baht = Rr.realized_dividend_return.mean() * capital if len(Rr) else 0
avg_tot_baht = Rr.total_return.mean() * capital if len(Rr) else 0
k = st.columns(4)
k[0].metric("จำนวนหุ้นใน universe", f"{len(universe)} ตัว", f"+{len(sel_sec)} รอง")
k[1].metric("ปันผล realized เฉลี่ย", f"{Rr.realized_dividend_return.mean()*100:,.2f}%" if len(Rr) else "—",
            f"≈ {avg_div_baht:,.0f} บาท")
k[2].metric("Total return เฉลี่ย", f"{Rr.total_return.mean()*100:,.2f}%" if len(Rr) else "—",
            f"≈ {avg_tot_baht:,.0f} บาท")
k[3].metric("Runs (realized/รวม)", f"{len(Rr)}/{len(Rf)}")

tabs = st.tabs(["🎛️ Universe & น้ำหนัก (บาท)", "📊 เทียบวิธี & ผลตอบแทน", "🎯 ความแม่น forecast",
                "📈 Timeline", "📅 Dividend patterns", "🔢 Raw data"])

# ============ Tab 1: universe & weights in baht ============
with tabs[0]:
    st.subheader("น้ำหนักพอร์ต + เม็ดเงินจริง (บาท) ต่อ 1 run")
    c = st.columns(3)
    sel_e = c[0].selectbox("Entry point", ENTRIES if freq.startswith("รายเดือน")
                           else [e for e in ENTRIES if int(e[5:7]) in Q_MONTHS], index=0)
    sel_h = c[1].selectbox("Holding (เดือน)", holds)
    sel_m = c[2].selectbox("วิธี forecast", methods)
    ws = W[(W.entry_id == sel_e) & (W.holding_period == sel_h) & (W.forecast_method == sel_m)].copy()
    ws["ตัวเต็ม"] = ws.ticker.map(NAMES)
    ws["กลุ่ม"] = ws.ticker.map(lambda t: "หลัก" if t in CORE else "รอง")
    ws["เงินลงทุน (บาท)"] = (ws.weight * capital).round(0)
    ws = ws.sort_values("weight", ascending=False)
    cc = st.columns([1.4, 1])
    with cc[0]:
        figw = px.bar(ws, x="ticker", y="weight", color="กลุ่ม",
                      color_discrete_map={"หลัก": "#0f2b46", "รอง": "#55A868"},
                      text=ws.weight.map(lambda v: f"{v*100:.1f}%"),
                      hover_data={"เงินลงทุน (บาท)": ":,.0f", "ตัวเต็ม": True})
        figw.add_hline(y=0.05, line_dash="dash", line_color="red", annotation_text="floor 5%")
        figw.update_layout(height=400, yaxis_tickformat=".0%", title=f"{sel_e} · {sel_h}m · {sel_m}")
        st.plotly_chart(figw, use_container_width=True)
    with cc[1]:
        st.dataframe(ws[["ticker", "กลุ่ม", "weight", "เงินลงทุน (บาท)"]]
                     .assign(weight=lambda d: (d.weight*100).round(2)),
                     use_container_width=True, hide_index=True, height=400)
    rr = R[(R.entry_id == sel_e) & (R.holding_period == sel_h) & (R.forecast_method == sel_m)]
    if len(rr) and rr.status.iloc[0] == "realized":
        r0 = rr.iloc[0]
        m = st.columns(4)
        m[0].metric("ปันผล forecast", f"{r0.forecast_dividend_return*100:.2f}%", f"{r0.forecast_dividend_return*capital:,.0f} บาท")
        m[1].metric("ปันผล realized", f"{r0.realized_dividend_return*100:.2f}%", f"{r0.realized_dividend_return*capital:,.0f} บาท")
        m[2].metric("Capital gain", f"{r0.capital_gain_loss*100:.2f}%", f"{r0.capital_gain_loss*capital:,.0f} บาท")
        m[3].metric("Total return", f"{r0.total_return*100:.2f}%", f"{r0.total_return*capital:,.0f} บาท")
    else:
        st.info("run นี้ยัง pending (holding window ยังไม่ครบ ณ ส.ค. 2026)")

    st.subheader("น้ำหนักเฉลี่ยต่อหุ้น (universe ปัจจุบัน)")
    avgw = Wf.groupby("ticker").weight.mean().reindex(universe).reset_index()
    avgw["กลุ่ม"] = avgw.ticker.map(lambda t: "หลัก" if t in CORE else "รอง")
    avgw["เงินเฉลี่ย (บาท)"] = (avgw.weight * capital).round(0)
    figa = px.bar(avgw.sort_values("weight", ascending=False), x="ticker", y="weight", color="กลุ่ม",
                  color_discrete_map={"หลัก": "#0f2b46", "รอง": "#55A868"},
                  text=avgw.sort_values("weight", ascending=False).weight.map(lambda v: f"{v*100:.1f}%"),
                  hover_data={"เงินเฉลี่ย (บาท)": ":,.0f"})
    figa.update_layout(height=360, yaxis_tickformat=".0%")
    st.plotly_chart(figa, use_container_width=True)

# ============ Tab 2: comparison ============
with tabs[1]:
    st.subheader("เปรียบเทียบวิธี × holding period")
    unit = st.radio("หน่วย", ["% ผลตอบแทน", "บาท (จากทุน)"], horizontal=True)
    metric = st.radio("ตัวชี้วัด", ["total_return", "realized_dividend_return", "capital_gain_loss",
                                    "forecast_dividend_return"], horizontal=True)
    agg = Rr.groupby(["holding_period", "forecast_method"])[metric].mean().reset_index()
    agg["val"] = agg[metric] * (capital if unit.startswith("บาท") else 100)
    fig = px.bar(agg, x="holding_period", y="val", color="forecast_method", barmode="group",
                 color_discrete_map=MCOLORS, category_orders={"forecast_method": MORDER},
                 labels={"holding_period": "Holding (เดือน)", "val": unit})
    fig.update_layout(height=430, legend_title="วิธี")
    st.plotly_chart(fig, use_container_width=True)
    st.subheader("การกระจาย total return")
    bx = Rr.copy(); bx["v"] = bx.total_return * 100
    figb = px.box(bx, x="holding_period", y="v", color="forecast_method", points=False,
                  color_discrete_map=MCOLORS, category_orders={"forecast_method": MORDER},
                  labels={"holding_period": "Holding (เดือน)", "v": "total return (%)"})
    figb.update_layout(height=430)
    st.plotly_chart(figb, use_container_width=True)

# ============ Tab 3: accuracy ============
with tabs[2]:
    st.subheader("ความแม่น forecast ปันผล (ต่อหุ้น, ไม่ขึ้นกับน้ำหนัก)")
    m = FR.merge(RBS[RBS.pending == False][["entry_id", "holding_period", "ticker", "realized_div_return"]],
                 on=["entry_id", "holding_period", "ticker"], how="inner")
    m = m[m.ticker.isin(universe) & m.method.isin(methods) & m.holding_period.isin(holds)]
    m["error"] = m.realized_div_return - m.forecast_dividend_return
    ov = m.groupby("method").agg(n=("error", "size"),
                                 bias_pp=("error", lambda s: round(s.mean()*100, 3)),
                                 MAE_pp=("error", lambda s: round(s.abs().mean()*100, 3)),
                                 RMSE_pp=("error", lambda s: round(np.sqrt((s**2).mean())*100, 3))
                                 ).reset_index().sort_values("MAE_pp")
    c1, c2 = st.columns([1, 1.2])
    c1.dataframe(ov, use_container_width=True, hide_index=True)
    fga = px.bar(ov, x="method", y="MAE_pp", color="method", color_discrete_map=MCOLORS,
                 category_orders={"method": MORDER}, title="MAE ต่อวิธี (ต่ำ=แม่นกว่า)")
    fga.update_layout(height=340, showlegend=False)
    c2.plotly_chart(fga, use_container_width=True)
    st.caption(f"วิธีแม่นสุดใน universe นี้: **{ov.iloc[0].method}** (MAE {ov.iloc[0].MAE_pp} pp)")

# ============ Tab 4: timeline ============
with tabs[3]:
    st.subheader("Timeline: total return จริง เทียบ forecast ปันผล (รายเดือน)")
    th = st.select_slider("Holding (เดือน)", options=HOLDINGS, value=6)
    tl = R[(R.holding_period == th) & (R.forecast_method.isin(methods)) & (R.status == "realized")].copy()
    tl = apply_freq(tl)
    order = sorted(tl.entry_id.unique(), key=lambda e: (int(e[:4]), int(e[5:7])))
    fig = go.Figure()
    if methods:
        subf = tl[tl.forecast_method == methods[0]].sort_values("entry_id", key=eorder)
        fig.add_bar(x=subf.entry_id, y=subf.forecast_dividend_return*100, name="forecast div",
                    marker_color="lightgrey", opacity=0.5)
    for mm in methods:
        s = tl[tl.forecast_method == mm].sort_values("entry_id", key=eorder)
        fig.add_trace(go.Scatter(x=s.entry_id, y=s.total_return*100, mode="lines+markers",
                                 name=f"{mm}", line=dict(color=MCOLORS[mm])))
    fig.update_layout(height=470, xaxis={"categoryorder": "array", "categoryarray": order},
                      yaxis_title="Return (%)")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(Rview.sort_values(["entry_id", "holding_period", "forecast_method"]),
                 use_container_width=True, hide_index=True, height=300)
    st.download_button("⬇️ ดาวน์โหลดผล (universe นี้)", Rview.to_csv(index=False).encode("utf-8"),
                       f"backtest_{'_'.join(sel_sec) or 'core'}.csv", "text/csv")

# ============ Tab 5: dividend patterns ============
with tabs[4]:
    tk = st.selectbox("เลือกหุ้น", universe, format_func=lambda t: f"{t} — {NAMES[t]}")
    dv = DIV[DIV.ticker == tk].copy(); dv["month"] = dv.ex_dividend_date.dt.month
    figd = px.scatter(dv, x="ex_dividend_date", y="dps_amount", size="dps_amount", color="month",
                      color_continuous_scale="Turbo", title=f"{tk} — ประวัติปันผล (ex-date)",
                      labels={"ex_dividend_date": "วัน XD", "dps_amount": "DPS (บาท)"})
    figd.update_layout(height=340)
    st.plotly_chart(figd, use_container_width=True)
    c = st.columns(2)
    c[0].caption("ราคาย้อนหลัง (split-adjusted)")
    c[0].line_chart(PRICE[PRICE.ticker == tk].set_index("date")["close_price"])
    c[1].caption("จำนวนครั้งจ่ายต่อเดือน")
    c[1].bar_chart(dv.pivot_table(index="month", values="dps_amount", aggfunc="count").reindex(range(1, 13), fill_value=0))

# ============ Tab 6: raw ============
with tabs[5]:
    which = st.selectbox("ตาราง", ["ผล backtest (universe นี้)", "น้ำหนัก (universe นี้)",
                                    "forecast_return (10 ตัว)", "realized_by_stock (10 ตัว)"])
    dmap = {"ผล backtest (universe นี้)": R, "น้ำหนัก (universe นี้)": W,
            "forecast_return (10 ตัว)": FR, "realized_by_stock (10 ตัว)": RBS}
    st.dataframe(dmap[which], use_container_width=True, hide_index=True, height=460)

"""
Interactive Streamlit dashboard for the Thai Dividend Yield Portfolio backtest.
Run:  streamlit run src/dashboard.py
"""
import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "output")

CORE = ["AOT", "OR", "KTB", "PTT", "PTTEP"]
MORDER = ["naive", "avg_3_5y", "yield_based", "growth_trend"]
MCOLORS = {"naive": "#4C72B0", "avg_3_5y": "#DD8452", "yield_based": "#55A868", "growth_trend": "#C44E52"}
HOLDINGS = [3, 6, 9, 12]

st.set_page_config(page_title="Thai Dividend Backtest", page_icon="📈", layout="wide")


def eorder(s):
    return s.map(lambda e: (int(e[:4]), int(e[5])))


@st.cache_data
def load():
    d = {}
    d["res"] = pd.read_csv(os.path.join(DATA, "backtest_results.csv"))
    d["w"] = pd.read_csv(os.path.join(DATA, "portfolio_weights.csv"))
    d["fr"] = pd.read_csv(os.path.join(DATA, "forecast_return.csv"))
    d["rbs"] = pd.read_csv(os.path.join(DATA, "realized_by_stock.csv"))
    d["slots"] = pd.read_csv(os.path.join(DATA, "expected_dividend_months.csv"))
    d["div"] = pd.read_csv(os.path.join(DATA, "dividend_history.csv"), parse_dates=["ex_dividend_date"])
    d["price"] = pd.read_csv(os.path.join(DATA, "price_history.csv"), parse_dates=["date"])
    d["comp"] = pd.read_csv(os.path.join(DATA, "data_completeness.csv"))
    # per-stock accuracy (weight-independent)
    m = d["fr"].merge(d["rbs"][d["rbs"].pending == False][["entry_id", "holding_period", "ticker", "realized_div_return"]],
                      on=["entry_id", "holding_period", "ticker"], how="inner")
    m["error"] = m["realized_div_return"] - m["forecast_dividend_return"]
    d["acc"] = m
    return d


D = load()
res_all = D["res"]

# ---------------- Sidebar ----------------
st.sidebar.title("📈 Thai Dividend Backtest")
st.sidebar.caption("Walk-forward · 5 หุ้นหลัก · 2021Q4→2026Q3")
methods = st.sidebar.multiselect("วิธี forecast", MORDER, default=MORDER)
holds = st.sidebar.multiselect("Holding period (เดือน)", HOLDINGS, default=HOLDINGS)
show_pending = st.sidebar.checkbox("รวม runs ที่ pending (ยังถือไม่ครบ)", value=False)
st.sidebar.markdown("---")
st.sidebar.caption("แหล่งข้อมูล: yfinance (หลัก) + StockAnalysis.com (cross-check 6/6). "
                   "ราคา split-adjusted ฐานปัจจุบัน ไม่ปรับปันผล.")

if not methods: methods = MORDER
if not holds: holds = HOLDINGS

res = res_all[res_all.forecast_method.isin(methods) & res_all.holding_period.isin(holds)].copy()
res_r = res[res.status == "realized"].copy()
view = res if show_pending else res_r

st.title("รายงานผล Backtest — พอร์ตหุ้นปันผลไทย")
st.caption("Interactive dashboard · maximize ผลตอบแทนจากเงินปันผล · หุ้นหลักบังคับถือ ≥5%")

# ---------------- KPI row ----------------
acc_f = D["acc"][D["acc"].method.isin(methods) & D["acc"].holding_period.isin(holds)]
best_method = acc_f.groupby("method").error.apply(lambda s: s.abs().mean()).sort_values().index[0] if len(acc_f) else "-"
k = st.columns(4)
k[0].metric("วิธี forecast แม่นสุด", best_method,
            help="MAE ต่ำสุดของ realized−forecast dividend return ต่อหุ้น")
k[1].metric("Total return เฉลี่ย", f"{res_r.total_return.mean()*100:,.2f}%" if len(res_r) else "—")
k[2].metric("ปันผล realized เฉลี่ย", f"{res_r.realized_dividend_return.mean()*100:,.2f}%" if len(res_r) else "—")
k[3].metric("Runs (realized/รวม)", f"{(res.status=='realized').sum()}/{len(res)}")

tabs = st.tabs(["📊 ภาพรวม & เทียบวิธี", "🎯 ความแม่น Forecast", "💼 น้ำหนักพอร์ต",
                "📈 Backtest Timeline", "📅 Dividend Patterns", "🔢 Raw Data"])

# ================= Tab 1: Overview / method comparison =================
with tabs[0]:
    st.subheader("เปรียบเทียบ 4 วิธี × Holding period")
    metric = st.radio("เลือกตัวชี้วัด", ["total_return", "realized_dividend_return", "capital_gain_loss",
                      "forecast_dividend_return"], horizontal=True, key="cmp_metric")
    agg = res_r.groupby(["holding_period", "forecast_method"])[metric].mean().reset_index()
    agg[metric] = agg[metric] * 100
    fig = px.bar(agg, x="holding_period", y=metric, color="forecast_method", barmode="group",
                 color_discrete_map=MCOLORS, category_orders={"forecast_method": MORDER},
                 labels={"holding_period": "Holding (เดือน)", metric: f"{metric} (%)"})
    fig.update_layout(height=430, legend_title="วิธี")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("การกระจาย (distribution)")
    valcol = st.selectbox("ตัวแปร", ["total_return", "realized_dividend_return", "capital_gain_loss"], key="box")
    bx = res_r.copy(); bx[valcol] = bx[valcol] * 100
    figb = px.box(bx, x="holding_period", y=valcol, color="forecast_method",
                  color_discrete_map=MCOLORS, category_orders={"forecast_method": MORDER},
                  labels={"holding_period": "Holding (เดือน)", valcol: f"{valcol} (%)"}, points=False)
    figb.update_layout(height=430, legend_title="วิธี")
    st.plotly_chart(figb, use_container_width=True)

# ================= Tab 2: Forecast accuracy =================
with tabs[1]:
    st.subheader("ความแม่นของ forecast ปันผล (ต่อหุ้น, ไม่ขึ้นกับน้ำหนัก)")
    st.caption("error = realized − forecast dividend return (pp). MAE ต่ำ = แม่นกว่า")
    a = acc_f.copy()
    ov = a.groupby("method").agg(n=("error", "size"),
                                 bias_pp=("error", lambda s: s.mean()*100),
                                 MAE_pp=("error", lambda s: s.abs().mean()*100),
                                 RMSE_pp=("error", lambda s: np.sqrt((s**2).mean())*100)).reset_index().sort_values("MAE_pp")
    c1, c2 = st.columns([1, 1.3])
    with c1:
        st.dataframe(ov.round(3), use_container_width=True, hide_index=True)
    with c2:
        figa = px.bar(ov, x="method", y="MAE_pp", color="method", color_discrete_map=MCOLORS,
                      category_orders={"method": MORDER}, labels={"MAE_pp": "MAE (pp)"})
        figa.update_layout(height=340, showlegend=False, title="MAE ต่อวิธี (ต่ำ=ดี)")
        st.plotly_chart(figa, use_container_width=True)

    st.subheader("MAE แยกตาม holding period")
    byh = a.groupby(["method", "holding_period"]).error.apply(lambda s: s.abs().mean()*100).reset_index(name="MAE_pp")
    figh = px.line(byh, x="holding_period", y="MAE_pp", color="method", markers=True,
                   color_discrete_map=MCOLORS, category_orders={"method": MORDER},
                   labels={"holding_period": "Holding (เดือน)", "MAE_pp": "MAE (pp)"})
    figh.update_layout(height=380)
    st.plotly_chart(figh, use_container_width=True)

    st.subheader("Forecast vs Realized (รายจุด)")
    sc = a.copy()
    fig_sc = px.scatter(sc, x="forecast_dividend_return", y="realized_div_return", color="ticker",
                        symbol="method", hover_data=["entry_id", "holding_period"],
                        labels={"forecast_dividend_return": "forecast div return",
                                "realized_div_return": "realized div return"})
    mx = max(sc.forecast_dividend_return.max(), sc.realized_div_return.max()) if len(sc) else 0.1
    fig_sc.add_trace(go.Scatter(x=[0, mx], y=[0, mx], mode="lines", line=dict(dash="dash", color="grey"),
                                name="perfect", showlegend=True))
    fig_sc.update_layout(height=460)
    st.plotly_chart(fig_sc, use_container_width=True)

# ================= Tab 3: Portfolio weights =================
with tabs[2]:
    st.subheader("น้ำหนักพอร์ตต่อ run")
    c = st.columns(3)
    ep_list = sorted(res_all.entry_id.unique(), key=lambda e: (int(e[:4]), int(e[5])))
    sel_e = c[0].selectbox("Entry point", ep_list, index=len(ep_list)-1)
    sel_h = c[1].selectbox("Holding (เดือน)", holds)
    sel_m = c[2].selectbox("วิธี forecast", methods)
    wsub = D["w"][(D["w"].entry_id == sel_e) & (D["w"].holding_period == sel_h) & (D["w"].forecast_method == sel_m)]
    wsub = wsub.set_index("ticker").reindex(CORE).reset_index()
    figw = px.bar(wsub, x="ticker", y="weight", color="ticker", text=wsub.weight.map(lambda v: f"{v*100:.0f}%"))
    figw.add_hline(y=0.05, line_dash="dash", line_color="red", annotation_text="floor 5%")
    figw.update_layout(height=360, showlegend=False, yaxis_tickformat=".0%",
                       title=f"{sel_e} · {sel_h}m · {sel_m}")
    st.plotly_chart(figw, use_container_width=True)

    st.subheader("น้ำหนักเฉลี่ย (heatmap: หุ้น × วิธี)")
    wf = D["w"][D["w"].forecast_method.isin(methods) & D["w"].holding_period.isin(holds)]
    hm = wf.pivot_table(index="ticker", columns="forecast_method", values="weight", aggfunc="mean").reindex(CORE)[methods]
    fighm = px.imshow(hm*100, text_auto=".1f", color_continuous_scale="Greens", aspect="auto",
                      labels=dict(color="avg wt %"))
    fighm.update_layout(height=360)
    st.plotly_chart(fighm, use_container_width=True)

    st.subheader("น้ำหนักเฉลี่ยรวมต่อหุ้น")
    ov_w = wf.groupby("ticker").weight.mean().reindex(CORE).reset_index()
    figo = px.bar(ov_w, x="ticker", y="weight", color="ticker", text=ov_w.weight.map(lambda v: f"{v*100:.1f}%"))
    figo.update_layout(height=320, showlegend=False, yaxis_tickformat=".0%")
    st.plotly_chart(figo, use_container_width=True)

# ================= Tab 4: Timeline =================
with tabs[3]:
    st.subheader("Timeline: total return จริง เทียบ forecast ปันผล")
    th = st.select_slider("Holding period (เดือน)", options=HOLDINGS, value=6)
    tl = res_all[(res_all.holding_period == th) & (res_all.forecast_method.isin(methods)) & (res_all.status == "realized")].copy()
    order = sorted(tl.entry_id.unique(), key=lambda e: (int(e[:4]), int(e[5])))
    fig = go.Figure()
    subf = tl[tl.forecast_method == methods[0]].sort_values("entry_id", key=eorder)
    fig.add_bar(x=subf.entry_id, y=subf.forecast_dividend_return*100, name="forecast div", marker_color="lightgrey", opacity=0.5)
    for m in methods:
        s = tl[tl.forecast_method == m].sort_values("entry_id", key=eorder)
        fig.add_trace(go.Scatter(x=s.entry_id, y=s.total_return*100, mode="lines+markers",
                                 name=f"{m} total", line=dict(color=MCOLORS[m])))
    fig.update_layout(height=470, xaxis={"categoryorder": "array", "categoryarray": order},
                      yaxis_title="Return (%)", legend_title="")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("ตารางผล (filtered)")
    st.dataframe(view.sort_values(["entry_id", "holding_period", "forecast_method"], key=lambda s: eorder(s) if s.name=="entry_id" else s),
                 use_container_width=True, hide_index=True)
    st.download_button("⬇️ ดาวน์โหลด CSV (filtered)", view.to_csv(index=False).encode("utf-8"),
                       "backtest_results_filtered.csv", "text/csv")

# ================= Tab 5: Dividend patterns =================
with tabs[4]:
    st.subheader("รูปแบบการจ่ายปันผล (dividend slots)")
    tk = st.selectbox("เลือกหุ้น", CORE)
    dv = D["div"][D["div"].ticker == tk].copy()
    dv["year"] = dv.ex_dividend_date.dt.year; dv["month"] = dv.ex_dividend_date.dt.month
    figd = px.scatter(dv, x="ex_dividend_date", y="dps_amount", size="dps_amount",
                      color="month", color_continuous_scale="Turbo",
                      labels={"ex_dividend_date": "วัน XD", "dps_amount": "DPS (บาท)"})
    figd.update_layout(height=340, title=f"{tk} — ประวัติปันผล (ex-date)")
    st.plotly_chart(figd, use_container_width=True)
    cc = st.columns(2)
    with cc[0]:
        st.caption("จำนวนครั้งจ่ายต่อเดือน (สกัด slot)")
        mm = dv.pivot_table(index="month", values="dps_amount", aggfunc="count").reindex(range(1,13), fill_value=0)
        st.bar_chart(mm)
    with cc[1]:
        st.caption("Slot ที่ engine สกัดได้ ณ entry ล่าสุด")
        sl = D["slots"][(D["slots"].ticker == tk) & (D["slots"].entry_id == "2026Q3")]
        st.write(sl[["n_slots", "slots"]].to_dict("records"))
    st.caption("ราคาย้อนหลัง (split-adjusted)")
    pc = D["price"][D["price"].ticker == tk]
    st.line_chart(pc.set_index("date")["close_price"])

# ================= Tab 6: Raw data =================
with tabs[5]:
    st.subheader("สำรวจข้อมูลดิบ")
    which = st.selectbox("เลือกตาราง", ["backtest_results", "portfolio_weights", "forecast_return",
                                        "realized_by_stock", "expected_slots", "data_completeness"])
    dmap = {"backtest_results": res_all, "portfolio_weights": D["w"], "forecast_return": D["fr"],
            "realized_by_stock": D["rbs"], "expected_slots": D["slots"], "data_completeness": D["comp"]}
    st.dataframe(dmap[which], use_container_width=True, hide_index=True)
    st.caption("ไฟล์เต็มทั้งหมดอยู่ใน data/ และ output/thai_dividend_backtest.xlsx")

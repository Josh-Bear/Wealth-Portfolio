"""
Dashboard — capped proportional weighting.
Toggle secondary stocks (off = excluded from the formula entirely) + toggle trim_outliers;
weights are recomputed live via water-filling. One portfolio per (entry, method), measured at
4 checkpoints (3/6/9/12m). Capital 100M baht.

Run:  streamlit run src/dashboard.py
"""
import os
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import common as C
from engine import enabled_smap, build_portfolio   # shared with the batch engine (no drift)

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")

CORE = ["AOT", "OR", "KTB", "PTT", "PTTEP"]
SECONDARY = ["SCB", "BBL", "KBANK", "TTB", "BAY"]
CORE_SET = set(CORE)
METHODS = ["avg_yield", "latest_yield", "avg_total_return", "growth_trend"]
MLABEL = {"avg_yield": "Yield เฉลี่ย", "latest_yield": "Yield ล่าสุด",
          "avg_total_return": "Total return เฉลี่ย", "growth_trend": "Growth trend"}
MCOLORS = {"avg_yield": "#4C72B0", "latest_yield": "#DD8452",
           "avg_total_return": "#55A868", "growth_trend": "#C44E52"}
CHECKPOINTS = [3, 6, 9, 12]
NAMES = {"AOT": "ท่าอากาศยานไทย", "OR": "ปตท.น้ำมันฯ(OR)", "KTB": "กรุงไทย", "PTT": "ปตท.",
         "PTTEP": "ปตท.สผ.", "SCB": "SCBX", "BBL": "กรุงเทพ", "KBANK": "กสิกรไทย",
         "TTB": "ทหารไทยธนชาต", "BAY": "กรุงศรีฯ"}

st.set_page_config(page_title="Thai Dividend Backtest", layout="wide")


def eorder(s):
    return s.map(C.parse_entry_id)


@st.cache_resource   # cache_resource: no pickling (rl_key holds itertuples namedtuples)
def load():
    sc = pd.read_csv(os.path.join(DATA, "scores.csv"))
    rl = pd.read_csv(os.path.join(DATA, "realized.csv"))
    div = pd.read_csv(os.path.join(DATA, "dividend_history.csv"), parse_dates=["ex_dividend_date"])
    price = pd.read_csv(os.path.join(DATA, "price_history.csv"), parse_dates=["date"])
    sc_key = {k: g.set_index("ticker") for k, g in sc.groupby(["entry_id", "method", "trim"])}
    rl_key = {(r.entry_id, r.ticker, r.checkpoint): r for r in rl.itertuples()}
    entries = sorted(sc.entry_id.unique(), key=C.parse_entry_id)
    return sc, rl, div, price, sc_key, rl_key, entries


SC, RL, DIV, PRICE, SC_KEY, RL_KEY, ENTRIES = load()


@st.cache_data(show_spinner="คำนวณ water-filling ใหม่ตาม universe/trim ที่เลือก...")
def run_backtest(selected_secondaries, trim, _sc_key, _rl_key):
    universe = CORE + list(selected_secondaries)
    wrows, rrows = [], []
    for eid in ENTRIES:
        for method in METHODS:
            sub = _sc_key.get((eid, method, trim))
            if sub is None:
                continue
            enabled, smap = enabled_smap(sub, universe, CORE_SET)
            w, results = build_portfolio(smap, enabled, CORE_SET, eid, _rl_key)
            for t, wt in w.items():
                wrows.append({"entry_id": eid, "method": method, "ticker": t, "weight": wt,
                              "raw_score": smap.get(t, 0.0)})
            for r in results:
                rrows.append({"entry_id": eid, "method": method, "checkpoint": r["checkpoint"],
                              "realized_dividend_return": r["realized_div_return"],
                              "capital_gain": r["capital_gain"], "total_return": r["total_return"],
                              "status": r["status"]})
    return pd.DataFrame(wrows), pd.DataFrame(rrows)


# ---------------- Sidebar ----------------
st.sidebar.title("Thai Dividend Backtest")
st.sidebar.caption("Capped proportional weighting (floor 5% / ceiling 30%)")
st.sidebar.markdown("### หุ้นหลัก (บังคับถือ 5–30%)")
st.sidebar.write("· " + " · ".join(CORE))
st.sidebar.markdown("### หุ้นรอง (ห้ามถือเกิน 30%)")
sel_sec = [s for s in SECONDARY if st.sidebar.checkbox(f"{s} — {NAMES[s]}", value=(s == "SCB"), key=f"s_{s}")]
# cbtn = st.sidebar.columns(2)
# if cbtn[0].button("เลือกทั้งหมด", use_container_width=True):
#     for s in SECONDARY: st.session_state[f"s_{s}"] = True
#     st.rerun()
# if cbtn[1].button("ล้างหุ้นรอง", use_container_width=True):
#     for s in SECONDARY: st.session_state[f"s_{s}"] = False
#     st.rerun()
st.sidebar.markdown("---")
trim = st.sidebar.toggle("Trim outliers (ตัด yield > p95)", value=True,
                         help="มีผลกับวิธี 'Yield เฉลี่ย' เท่านั้น — ตัดค่า yield สูงผิดปกติออกด้านบน")
capital = st.sidebar.number_input("เงินทุน (บาท)", value=100_000_000, step=10_000_000, format="%d")
methods_sel = st.sidebar.multiselect("วิธีถ่วงน้ำหนัก", METHODS, default=METHODS,
                                     format_func=lambda m: MLABEL[m]) or METHODS
show_pending = st.sidebar.checkbox("รวม checkpoint ที่ pending", value=False)

universe = CORE + sel_sec
W, R = run_backtest(tuple(sel_sec), trim, SC_KEY, RL_KEY)
Wf = W[W.method.isin(methods_sel)]
Rf = R[R.method.isin(methods_sel)]
Rr = Rf[Rf.status == "realized"]
Rview = Rf if show_pending else Rr

st.title("Backtest พอร์ตหุ้นปันผลไทย — Capped Proportional Weighting")
st.caption(f"Universe: **{len(universe)} ตัว** = 5 หลัก + {', '.join(sel_sec) if sel_sec else '(ไม่มีหุ้นรอง)'} · "
           f"trim outliers: **{'เปิด' if trim else 'ปิด'}** · แต่ละวิธีถือ 1 พอร์ต วัดผลที่ 4 checkpoint · "
           f"เลือก entry เพื่อดูผลของจุดนั้นโดยเฉพาะ")

tabs = st.tabs(["🎛️ Universe & น้ำหนัก", "📊 เทียบวิธี × checkpoint", "🧮 Scores (วิธีคำนวณ)",
                "📈 Timeline", "📅 Dividend patterns", "🔢 Raw data"])

# ===== Tab 1: weights =====
with tabs[0]:
    st.subheader("น้ำหนักพอร์ต")

    c = st.columns(2)
    sel_e = c[0].selectbox("Entry point", ENTRIES, index=len(ENTRIES)-1)
    sel_m = c[1].selectbox("วิธี", METHODS, format_func=lambda m: MLABEL[m])
    ws = W[(W.entry_id == sel_e) & (W.method == sel_m)].copy()
    ws["กลุ่ม"] = ws.ticker.map(lambda t: "หลัก" if t in CORE_SET else "รอง")
    ws["บาท"] = (ws.weight * capital).round(0)
    ws = ws.sort_values("weight", ascending=False)
    cc = st.columns([1.5, 1])
    with cc[0]:
        fig = px.bar(ws, x="ticker", y="weight", color="กลุ่ม",
                     color_discrete_map={"หลัก": "#0f2b46", "รอง": "#55A868"},
                     text=ws.weight.map(lambda v: f"{v*100:.1f}%"))
        fig.add_hline(y=0.30, line_dash="dash", line_color="red", annotation_text="ceiling 30%")
        fig.add_hline(y=0.05, line_dash="dot", line_color="orange", annotation_text="core floor 5%")
        fig.update_layout(height=430, yaxis_tickformat=".0%", title=f"{sel_e} · {MLABEL[sel_m]}")
        st.plotly_chart(fig, use_container_width=True)
    with cc[1]:
        st.dataframe(ws[["ticker", "กลุ่ม", "weight", "บาท"]]
                     .assign(weight=lambda d: (d.weight*100).round(2)),
                     use_container_width=True, hide_index=True, height=430)
    st.caption(f"ผลรวมน้ำหนัก = {ws.weight.sum()*100:.1f}% · หุ้นในพอร์ต {len(ws)} ตัว · "
               f"เม็ดเงินรวม {ws['บาท'].sum():,.0f} บาท")

    st.subheader(f"ผลตอบแทนของ entry นี้ ({sel_e} · {MLABEL[sel_m]})")
    st.caption("ซื้อครั้งเดียว ณ entry แล้ววัดผลที่ 4 checkpoint")
    rr = R[(R.entry_id == sel_e) & (R.method == sel_m)].sort_values("checkpoint").copy()
    pend = rr.status == "pending"
    f_pct = lambda v, p: "*" if p else f"{v*100:.2f}%"
    f_baht = lambda v, p: "*" if p else f"{v*capital:,.0f}"
    disp = pd.DataFrame({
        "Checkpoint": rr.checkpoint.map(lambda h: f"{h} เดือน"),
        "ปันผล (realized)": [f_pct(v, p) for v, p in zip(rr.realized_dividend_return, pend)],
        "Capital gain": [f_pct(v, p) for v, p in zip(rr.capital_gain, pend)],
        "Total return": [f_pct(v, p) for v, p in zip(rr.total_return, pend)],
        "Total (บาท)": [f_baht(v, p) for v, p in zip(rr.total_return, pend)],
    })
    st.dataframe(disp, use_container_width=True, hide_index=True)
    if pend.any():
        st.caption("\\* = ยังไม่ถึงวันประเมินผล (checkpoint เลยวันปัจจุบัน 2026-08-07) หรือไม่มีข้อมูลราคา ณ จุดออก "
                   "— ไม่ใส่ตัวเลขเดา")

# ===== Tab 2: comparison =====
with tabs[1]:
    st.subheader("เปรียบเทียบวิธี × checkpoint")
    unit = st.radio("หน่วย", ["% ผลตอบแทน", "บาท"], horizontal=True)
    metric = st.radio("ตัวชี้วัด", ["total_return", "realized_dividend_return", "capital_gain"], horizontal=True)
    agg = Rr.groupby(["checkpoint", "method"])[metric].mean().reset_index()
    agg["val"] = agg[metric] * (capital if unit == "บาท" else 100)
    fig = px.bar(agg, x="checkpoint", y="val", color="method", barmode="group",
                 color_discrete_map=MCOLORS, category_orders={"method": METHODS},
                 labels={"checkpoint": "Checkpoint (เดือน)", "val": unit})
    fig.for_each_trace(lambda t: t.update(name=MLABEL.get(t.name, t.name)))
    fig.update_layout(height=430, legend_title="วิธี")
    st.plotly_chart(fig, use_container_width=True)
    st.subheader("การกระจาย total return")
    bx = Rr.copy(); bx["v"] = bx.total_return*100
    figb = px.box(bx, x="checkpoint", y="v", color="method", points=False,
                  color_discrete_map=MCOLORS, category_orders={"method": METHODS},
                  labels={"checkpoint": "Checkpoint (เดือน)", "v": "total return (%)"})
    figb.for_each_trace(lambda t: t.update(name=MLABEL.get(t.name, t.name)))
    figb.update_layout(height=430)
    st.plotly_chart(figb, use_container_width=True)

# ===== Tab 3: scores =====
with tabs[2]:
    st.subheader("Raw score ต่อหุ้น × วิธี")
    st.caption("score = ค่าที่ใช้ถ่วงน้ำหนักตามสัดส่วน (บน yield). trim outliers มีผลเฉพาะ 'Yield เฉลี่ย'")
    e2 = st.selectbox("Entry point", ENTRIES, index=len(ENTRIES)-1, key="e_scores")
    rows = []
    for m in METHODS:
        sub = SC_KEY.get((e2, m, trim))
        if sub is None: continue
        for t in universe:
            if t in sub.index:
                rows.append({"ticker": t, "method": MLABEL[m], "raw_score": sub.loc[t, "raw_score"]})
    sdf = pd.DataFrame(rows)
    if len(sdf):
        piv = sdf.pivot_table(index="ticker", columns="method", values="raw_score").reindex(universe)
        figh = px.imshow(piv, text_auto=".4f", color_continuous_scale="Blues", aspect="auto",
                         labels=dict(color="raw_score"))
        figh.update_layout(height=420)
        st.plotly_chart(figh, use_container_width=True)
        st.caption("ยิ่ง score สูง → น้ำหนักยิ่งมาก (ก่อนบีบด้วย floor/ceiling)")

# ===== Tab 4: timeline =====
with tabs[3]:
    st.subheader("Timeline: total return ต่อ entry")
    th = st.select_slider("Checkpoint (เดือน)", options=CHECKPOINTS, value=12)
    tl = R[(R.checkpoint == th) & (R.method.isin(methods_sel)) & (R.status == "realized")]
    order = sorted(tl.entry_id.unique(), key=C.parse_entry_id)
    fig = go.Figure()
    for m in methods_sel:
        s = tl[tl.method == m].sort_values("entry_id", key=eorder)
        fig.add_trace(go.Scatter(x=s.entry_id, y=s.total_return*100, mode="lines+markers",
                                 name=MLABEL[m], line=dict(color=MCOLORS[m])))
    fig.update_layout(height=460, xaxis={"categoryorder": "array", "categoryarray": order},
                      yaxis_title="total return (%)")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(Rview.sort_values(["entry_id", "method", "checkpoint"]),
                 use_container_width=True, hide_index=True, height=300)
    st.download_button("⬇️ ดาวน์โหลดผล (universe/trim นี้)", Rview.to_csv(index=False).encode("utf-8"),
                       f"results_{'_'.join(sel_sec) or 'core'}_{'trim' if trim else 'notrim'}.csv", "text/csv")

# ===== Tab 5: dividends =====
with tabs[4]:
    tk = st.selectbox("เลือกหุ้น", universe, format_func=lambda t: f"{t} — {NAMES[t]}")
    dv = DIV[DIV.ticker == tk].copy(); dv["month"] = dv.ex_dividend_date.dt.month
    figd = px.scatter(dv, x="ex_dividend_date", y="dps_amount", size="dps_amount", color="month",
                      color_continuous_scale="Turbo", title=f"{tk} — ประวัติปันผล",
                      labels={"ex_dividend_date": "วัน XD", "dps_amount": "DPS (บาท)"})
    figd.update_layout(height=340)
    st.plotly_chart(figd, use_container_width=True)
    st.caption("ราคาย้อนหลัง (split-adjusted)")
    st.line_chart(PRICE[PRICE.ticker == tk].set_index("date")["close_price"])

# ===== Tab 6: raw =====
with tabs[5]:
    which = st.selectbox("ตาราง", ["weights (universe/trim นี้)", "results (universe/trim นี้)",
                                    "scores (ดิบ)", "realized (ดิบ)"])
    dmap = {"weights (universe/trim นี้)": W, "results (universe/trim นี้)": R,
            "scores (ดิบ)": SC, "realized (ดิบ)": RL}
    st.dataframe(dmap[which], use_container_width=True, hide_index=True, height=460)

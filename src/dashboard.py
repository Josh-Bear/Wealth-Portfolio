"""
Dashboard v3 — capped proportional weighting (replaces the v1/v2 LP dashboards).
Toggle secondary stocks (off = excluded from the formula entirely) + toggle trim_outliers;
weights are recomputed live via water-filling. One portfolio per (entry, method), measured at
4 checkpoints (3/6/9/12m). Capital 100M baht.

Run:  streamlit run src/dashboard.py
"""
import os
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from weighting import water_fill

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

st.set_page_config(page_title="Thai Dividend Backtest v3", page_icon="⚖️", layout="wide")


def eorder(s):
    return s.map(lambda e: (int(e[:4]), int(e[5])))


@st.cache_resource   # cache_resource: no pickling (rl_key holds itertuples namedtuples)
def load():
    sc = pd.read_csv(os.path.join(DATA, "v3_scores.csv"))
    rl = pd.read_csv(os.path.join(DATA, "v3_realized.csv"))
    div = pd.read_csv(os.path.join(DATA, "dividend_history.csv"), parse_dates=["ex_dividend_date"])
    price = pd.read_csv(os.path.join(DATA, "price_history.csv"), parse_dates=["date"])
    sc_key = {k: g.set_index("ticker") for k, g in sc.groupby(["entry_id", "method", "trim"])}
    rl_key = {(r.entry_id, r.ticker, r.checkpoint): r for r in rl.itertuples()}
    entries = sorted(sc.entry_id.unique(), key=lambda e: (int(e[:4]), int(e[5])))
    return sc, rl, div, price, sc_key, rl_key, entries


SC, RL, DIV, PRICE, SC_KEY, RL_KEY, ENTRIES = load()


@st.cache_data(show_spinner="คำนวณ water-filling ใหม่ตาม universe/trim ที่เลือก...")
def run_v3(selected_secondaries, trim, _sc_key, _rl_key):
    universe = CORE + list(selected_secondaries)
    wrows, rrows = [], []
    for eid in ENTRIES:
        for method in METHODS:
            sub = _sc_key.get((eid, method, trim))
            if sub is None:
                continue
            enabled = []
            for t in universe:
                if t not in sub.index:
                    continue
                if pd.isna(sub.loc[t, "price_entry"]):
                    continue
                if (t not in CORE_SET) and (not bool(sub.loc[t, "has_history"])):
                    continue  # secondary needs history to be scored
                enabled.append(t)
            smap = {t: float(sub.loc[t, "raw_score"]) for t in enabled}
            w = water_fill(smap, enabled, CORE_SET)
            for t, wt in w.items():
                wrows.append({"entry_id": eid, "method": method, "ticker": t, "weight": wt,
                              "raw_score": smap.get(t, 0.0)})
            for h in CHECKPOINTS:
                recs = {t: _rl_key.get((eid, t, h)) for t in w}
                if any(r is None or r.pending for r in recs.values()):
                    rrows.append({"entry_id": eid, "method": method, "checkpoint": h,
                                  "realized_dividend_return": np.nan, "capital_gain": np.nan,
                                  "total_return": np.nan, "status": "pending"})
                else:
                    rdr = sum(wt * recs[t].realized_div_return for t, wt in w.items())
                    cap = sum(wt * recs[t].capital_gain for t, wt in w.items())
                    rrows.append({"entry_id": eid, "method": method, "checkpoint": h,
                                  "realized_dividend_return": rdr, "capital_gain": cap,
                                  "total_return": rdr + cap, "status": "realized"})
    return pd.DataFrame(wrows), pd.DataFrame(rrows)


# ---------------- Sidebar ----------------
st.sidebar.title("⚖️ Thai Dividend Backtest v3")
st.sidebar.caption("Capped proportional weighting (floor 5% / ceiling 30%) · ทุน 100 ล้านบาท · "
                   "entry รายไตรมาส 20 จุด (2021Q3→2026Q2)")
st.sidebar.markdown("### 🏢 หุ้นหลัก (บังคับถือ 5–30%)")
st.sidebar.write("· " + " · ".join(CORE))
st.sidebar.markdown("### ➕➖ หุ้นรอง (ปิด = ตัดออกจากสูตร)")
sel_sec = [s for s in SECONDARY if st.sidebar.checkbox(f"{s} — {NAMES[s]}", value=(s == "SCB"), key=f"s_{s}")]
cbtn = st.sidebar.columns(2)
if cbtn[0].button("เลือกทั้งหมด", use_container_width=True):
    for s in SECONDARY: st.session_state[f"s_{s}"] = True
    st.rerun()
if cbtn[1].button("ล้างหุ้นรอง", use_container_width=True):
    for s in SECONDARY: st.session_state[f"s_{s}"] = False
    st.rerun()
st.sidebar.markdown("---")
trim = st.sidebar.toggle("Trim outliers (ตัด yield > p95)", value=True,
                         help="มีผลกับวิธี 'Yield เฉลี่ย' เท่านั้น — ตัดค่า yield สูงผิดปกติออกด้านบน")
capital = st.sidebar.number_input("เงินทุน (บาท)", value=100_000_000, step=10_000_000, format="%d")
methods_sel = st.sidebar.multiselect("วิธีถ่วงน้ำหนัก", METHODS, default=METHODS,
                                     format_func=lambda m: MLABEL[m]) or METHODS
show_pending = st.sidebar.checkbox("รวม checkpoint ที่ pending", value=False)

universe = CORE + sel_sec
W, R = run_v3(tuple(sel_sec), trim, SC_KEY, RL_KEY)
Wf = W[W.method.isin(methods_sel)]
Rf = R[R.method.isin(methods_sel)]
Rr = Rf[Rf.status == "realized"]
Rview = Rf if show_pending else Rr

st.title("Backtest พอร์ตหุ้นปันผลไทย v3 — Capped Proportional Weighting")
st.caption(f"Universe: **{len(universe)} ตัว** = 5 หลัก + {', '.join(sel_sec) if sel_sec else '(ไม่มีหุ้นรอง)'} · "
           f"trim outliers: **{'เปิด' if trim else 'ปิด'}** · แต่ละวิธีถือ 1 พอร์ต วัดผลที่ 4 checkpoint")

# diversification: effective number of stocks (1/HHI), averaged
def eff_n(df):
    return df.groupby(["entry_id", "method"]).weight.apply(lambda s: 1/ (s**2).sum()).mean()
st.markdown("##### 📌 ภาพรวมทั้ง backtest (เฉลี่ยข้าม 20 entries × วิธีที่เลือก × checkpoint)")
k = st.columns(4)
k[0].metric("จำนวนหุ้นใน universe", f"{len(universe)} ตัว")
k[1].metric("ปันผลเฉลี่ย · ทั้ง backtest", f"{Rr.realized_dividend_return.mean()*100:,.2f}%" if len(Rr) else "—",
            f"≈ {Rr.realized_dividend_return.mean()*capital:,.0f} บาท" if len(Rr) else None,
            help="ค่าเฉลี่ยของทุก entry point ไม่ใช่ของ entry ที่เลือกในแท็บด้านล่าง")
k[2].metric("Total return เฉลี่ย · ทั้ง backtest", f"{Rr.total_return.mean()*100:,.2f}%" if len(Rr) else "—",
            f"≈ {Rr.total_return.mean()*capital:,.0f} บาท" if len(Rr) else None,
            help="ค่าเฉลี่ยของทุก entry point ไม่ใช่ของ entry ที่เลือกในแท็บด้านล่าง")
k[3].metric("การกระจายตัว (eff. #หุ้น)", f"{eff_n(Wf):.1f} ตัว",
            help="1/Σw² — ยิ่งสูงยิ่งกระจาย (v1/v2 LP corner ≈ 1.5)")

tabs = st.tabs(["🎛️ Universe & น้ำหนัก", "📊 เทียบวิธี × checkpoint", "🧮 Scores (วิธีคำนวณ)",
                "📈 Timeline", "📅 Dividend patterns", "🔢 Raw data"])

# ===== Tab 1: weights =====
with tabs[0]:
    st.subheader("น้ำหนักพอร์ต")
    st.caption("พอร์ตของ **entry point × วิธี ที่เลือกด้านล่าง** (เฉพาะจุดนี้เท่านั้น ไม่ใช่ค่าเฉลี่ย) — "
               "เปลี่ยน entry เพื่อดูน้ำหนัก + ผลตอบแทนของจุดนั้น")
    c = st.columns(2)
    sel_e = c[0].selectbox("Entry point", ENTRIES, index=len(ENTRIES)-1)
    sel_m = c[1].selectbox("วิธี", methods_sel, format_func=lambda m: MLABEL[m])
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

    st.markdown(f"**ผลตอบแทนของพอร์ตนี้โดยเฉพาะ** ({sel_e} · {MLABEL[sel_m]}) — ซื้อครั้งเดียว วัดที่ 4 checkpoint")
    rr = R[(R.entry_id == sel_e) & (R.method == sel_m)].sort_values("checkpoint").copy()
    disp = pd.DataFrame({
        "checkpoint": rr.checkpoint.map(lambda h: f"{h} เดือน"),
        "ปันผล %": (rr.realized_dividend_return * 100).round(2),
        "capital gain %": (rr.capital_gain * 100).round(2),
        "total return %": (rr.total_return * 100).round(2),
        "total (บาท)": (rr.total_return * capital).round(0),
        "สถานะ": rr.status.map({"realized": "✅ วัดผลแล้ว", "pending": "⏳ ยังไม่ครบ"}),
    })
    st.dataframe(disp, use_container_width=True, hide_index=True)

    st.subheader("น้ำหนักเฉลี่ยต่อหุ้น (เฉลี่ยทั้ง backtest)")
    st.caption("น้ำหนักเฉลี่ยของแต่ละหุ้นตลอด 20 entries × วิธีที่เลือก — บอกว่าหุ้นไหนถูกให้น้ำหนักหนัก/เบาโดยรวม "
               "(ต่างจากกราฟบนที่เป็นพอร์ตของ entry เดียว)")
    aw = Wf.groupby("ticker").weight.mean().reindex(universe).reset_index()
    aw["กลุ่ม"] = aw.ticker.map(lambda t: "หลัก" if t in CORE_SET else "รอง")
    figa = px.bar(aw.sort_values("weight", ascending=False), x="ticker", y="weight", color="กลุ่ม",
                  color_discrete_map={"หลัก": "#0f2b46", "รอง": "#55A868"},
                  text=aw.sort_values("weight", ascending=False).weight.map(lambda v: f"{v*100:.1f}%"))
    figa.update_layout(height=340, yaxis_tickformat=".0%")
    st.plotly_chart(figa, use_container_width=True)

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
    st.subheader("Raw score ต่อหุ้น × วิธี (โปร่งใส — ที่มาของน้ำหนัก)")
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
    order = sorted(tl.entry_id.unique(), key=lambda e: (int(e[:4]), int(e[5])))
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
                       f"v3_results_{'_'.join(sel_sec) or 'core'}_{'trim' if trim else 'notrim'}.csv", "text/csv")

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
                                    "v3_scores (ดิบ)", "v3_realized (ดิบ)"])
    dmap = {"weights (universe/trim นี้)": W, "results (universe/trim นี้)": R,
            "v3_scores (ดิบ)": SC, "v3_realized (ดิบ)": RL}
    st.dataframe(dmap[which], use_container_width=True, hide_index=True, height=460)

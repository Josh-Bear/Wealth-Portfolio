"""
Phase 7 — Aggregation & comparison tables
Phase 8 — Reporting (charts PNG + Excel workbook + markdown summary)

Reads Phase 3-6 outputs; produces the four deliverable views from plan section 9:
  1. 4-method comparison per (method × holding): forecast_error, realized div return, total return
  2. Distribution boxplots (dividend & total return) per holding, by method
  3. Average portfolio weight per stock
  4. Timeline of realized vs forecast per entry
Plus a supplementary PER-STOCK forecast-accuracy table (weight-independent) that most directly
answers "which forecast method predicts dividend yield best".
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import common as C

OUT = C.OUT
MCOLORS = {"naive": "#4C72B0", "avg_3_5y": "#DD8452", "yield_based": "#55A868", "growth_trend": "#C44E52"}
MORDER = ["naive", "avg_3_5y", "yield_based", "growth_trend"]


def load():
    res = pd.read_csv(os.path.join(C.DATA, "backtest_results.csv"))
    w = pd.read_csv(os.path.join(C.DATA, "portfolio_weights.csv"))
    fr = pd.read_csv(os.path.join(C.DATA, "forecast_return.csv"))
    rbs = pd.read_csv(os.path.join(C.DATA, "realized_by_stock.csv"))
    return res, w, fr, rbs


# ---------- Phase 7 tables ----------
def method_comparison(res):
    r = res[res.status == "realized"]
    t = r.groupby(["forecast_method", "holding_period"]).agg(
        n=("total_return", "size"),
        mean_forecast_div=("forecast_dividend_return", "mean"),
        mean_realized_div=("realized_dividend_return", "mean"),
        mean_forecast_error=("forecast_error", "mean"),
        mae_forecast_error=("forecast_error", lambda s: s.abs().mean()),
        mean_capital_gain=("capital_gain_loss", "mean"),
        mean_total_return=("total_return", "mean"),
    ).reset_index()
    for c in t.columns:
        if c.startswith("mean_") or c.startswith("mae_"):
            t[c] = (t[c] * 100).round(3)  # to percent
    return t


def per_stock_accuracy(fr, rbs):
    """Weight-independent: forecast vs realized dividend return per (entry,ticker,holding,method)."""
    m = fr.merge(rbs[rbs.pending == False][["entry_id", "holding_period", "ticker",
                 "realized_div_return"]], on=["entry_id", "holding_period", "ticker"], how="inner")
    m["error"] = m["realized_div_return"] - m["forecast_dividend_return"]
    agg = m.groupby(["method", "holding_period"]).agg(
        n=("error", "size"),
        bias_pp=("error", lambda s: round(s.mean() * 100, 3)),
        mae_pp=("error", lambda s: round(s.abs().mean() * 100, 3)),
        rmse_pp=("error", lambda s: round(np.sqrt((s ** 2).mean()) * 100, 3)),
    ).reset_index()
    overall = m.groupby("method").agg(
        n=("error", "size"),
        bias_pp=("error", lambda s: round(s.mean() * 100, 3)),
        mae_pp=("error", lambda s: round(s.abs().mean() * 100, 3)),
        rmse_pp=("error", lambda s: round(np.sqrt((s ** 2).mean()) * 100, 3)),
    ).reset_index().sort_values("mae_pp")
    return agg, overall


def avg_weights(w):
    overall = w.groupby("ticker").weight.mean().reindex(C.CORE)
    by_method = w.pivot_table(index="ticker", columns="forecast_method", values="weight", aggfunc="mean").reindex(C.CORE)
    return overall, by_method


# ---------- Phase 8 charts ----------
def grouped_boxplot(res, value, title, fname):
    r = res[res.status == "realized"]
    fig, ax = plt.subplots(figsize=(10, 5.5))
    holdings = C.HOLDING_PERIODS
    width = 0.18
    for j, m in enumerate(MORDER):
        data = [r[(r.holding_period == h) & (r.forecast_method == m)][value].dropna().values * 100 for h in holdings]
        pos = [i + (j - 1.5) * width for i in range(len(holdings))]
        bp = ax.boxplot(data, positions=pos, widths=width * 0.9, patch_artist=True,
                        medianprops=dict(color="black"), showfliers=False)
        for patch in bp["boxes"]:
            patch.set_facecolor(MCOLORS[m]); patch.set_alpha(0.8)
    ax.set_xticks(range(len(holdings))); ax.set_xticklabels([f"{h}m" for h in holdings])
    ax.set_xlabel("Holding period"); ax.set_ylabel(f"{title} (%)")
    ax.set_title(title + " distribution by holding period & forecast method")
    ax.axhline(0, color="grey", lw=0.8, ls="--")
    handles = [plt.Rectangle((0, 0), 1, 1, fc=MCOLORS[m], alpha=0.8) for m in MORDER]
    ax.legend(handles, MORDER, title="method", ncol=4, loc="upper left", fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, fname), dpi=130); plt.close(fig)


def weights_bar(overall, by_method, fname):
    fig, ax = plt.subplots(figsize=(9, 5))
    x = np.arange(len(C.CORE)); width = 0.18
    for j, m in enumerate(MORDER):
        ax.bar(x + (j - 1.5) * width, by_method[m].values * 100, width, label=m, color=MCOLORS[m], alpha=0.85)
    ax.plot(x, overall.values * 100, "k_", markersize=22, markeredgewidth=2, label="overall avg")
    ax.set_xticks(x); ax.set_xticklabels(C.CORE)
    ax.set_ylabel("Average weight (%)"); ax.set_title("Average portfolio weight per stock (by forecast method)")
    ax.axhline(5, color="red", lw=0.8, ls="--", label="5% floor")
    ax.legend(ncol=3, fontsize=8); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, fname), dpi=130); plt.close(fig)


def timeline_chart(res, holding, fname):
    r = res[(res.status == "realized") & (res.holding_period == holding)].copy()
    order = sorted(r.entry_id.unique(), key=lambda s: (int(s[:4]), int(s[5])))
    xi = {e: i for i, e in enumerate(order)}
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for m in MORDER:
        sub = r[r.forecast_method == m].sort_values("entry_id", key=lambda s: s.map(lambda e: (int(e[:4]), int(e[5]))))
        ax.plot([xi[e] for e in sub.entry_id], sub.total_return * 100, "-o", ms=4, label=f"{m} total", color=MCOLORS[m], alpha=0.9)
    # forecast dividend return (naive) reference
    subf = r[r.forecast_method == "naive"].sort_values("entry_id", key=lambda s: s.map(lambda e: (int(e[:4]), int(e[5]))))
    ax.bar([xi[e] for e in subf.entry_id], subf.forecast_dividend_return * 100, color="grey", alpha=0.25, label="forecast div (naive)")
    ax.set_xticks(range(len(order))); ax.set_xticklabels(order, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Return (%)"); ax.set_title(f"Realized total return vs forecast dividend by entry — {holding}m holding")
    ax.axhline(0, color="grey", lw=0.8, ls="--"); ax.legend(ncol=3, fontsize=8); ax.grid(axis="y", alpha=0.3)
    fig.tight_layout(); fig.savefig(os.path.join(OUT, fname), dpi=130); plt.close(fig)


# ---------- Phase 8 workbook ----------
def build_xlsx(tables, path):
    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        for name, df in tables.items():
            df.to_excel(xl, sheet_name=name[:31], index=False)
    # insert charts
    from openpyxl import load_workbook
    from openpyxl.drawing.image import Image
    wb = load_workbook(path)
    ws = wb.create_sheet("Charts")
    row = 1
    for img in ["boxplot_total_return.png", "boxplot_div_return.png", "avg_weights.png", "timeline_6m.png"]:
        p = os.path.join(OUT, img)
        if os.path.exists(p):
            ws.add_image(Image(p), f"A{row}"); row += 30
    wb.save(path)


def main():
    res, w, fr, rbs = load()

    t_cmp = method_comparison(res)
    acc_by_h, acc_overall = per_stock_accuracy(fr, rbs)
    ov_w, bym_w = avg_weights(w)
    ov_w_df = ov_w.reset_index().rename(columns={"weight": "avg_weight"})
    ov_w_df["avg_weight"] = (ov_w_df["avg_weight"] * 100).round(2)
    bym_w_df = (bym_w * 100).round(2).reset_index()

    # charts
    grouped_boxplot(res, "total_return", "Total return", "boxplot_total_return.png")
    grouped_boxplot(res, "realized_dividend_return", "Realized dividend return", "boxplot_div_return.png")
    weights_bar(ov_w, bym_w, "avg_weights.png")
    timeline_chart(res, 6, "timeline_6m.png")

    # save summary CSVs
    t_cmp.to_csv(os.path.join(OUT, "summary_method_comparison.csv"), index=False)
    acc_overall.to_csv(os.path.join(OUT, "summary_forecast_accuracy_overall.csv"), index=False)
    acc_by_h.to_csv(os.path.join(OUT, "summary_forecast_accuracy_by_holding.csv"), index=False)
    bym_w_df.to_csv(os.path.join(OUT, "summary_avg_weights.csv"), index=False)

    readme = pd.DataFrame({
        "field": ["generated", "universe", "entries", "holding_periods", "methods", "lp_runs",
                  "price_basis", "sources", "pending_note"],
        "value": ["2026-08-06", "AOT, OR, KTB, PTT, PTTEP (all core, >=5%)",
                  "20 (2021Q4..2026Q3)", "3/6/9/12 months", "naive, avg_3_5y, yield_based, growth_trend",
                  "320 (20x4x4)", "close = split-adjusted (current basis), NOT dividend-adjusted",
                  "yfinance primary, StockAnalysis cross-check (6/6 match)",
                  "40 runs pending (holding window ends after 2026-08-06)"]})

    tables = {
        "README": readme,
        "method_comparison": t_cmp,
        "forecast_accuracy_overall": acc_overall,
        "forecast_accuracy_byholding": acc_by_h,
        "avg_weights_by_method": bym_w_df,
        "backtest_results": res,
        "portfolio_weights": w,
        "forecast_return": fr,
        "realized_by_stock": rbs,
        "expected_slots": pd.read_csv(os.path.join(C.DATA, "expected_dividend_months.csv")),
        "dividend_history": C.load_dividends(),
    }
    xlsx_path = os.path.join(OUT, "thai_dividend_backtest.xlsx")
    build_xlsx(tables, xlsx_path)

    print("=== METHOD COMPARISON (%, realized) ===")
    print(t_cmp.to_string(index=False))
    print("\n=== PER-STOCK FORECAST ACCURACY (overall, pp) — lower MAE = more accurate ===")
    print(acc_overall.to_string(index=False))
    print("\n=== AVG WEIGHT per stock (%) ===")
    print(ov_w_df.to_string(index=False))
    print(f"\nWROTE {xlsx_path} + charts in {OUT}")


if __name__ == "__main__":
    main()

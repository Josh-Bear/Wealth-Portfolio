"""
FF5 Factor Model — Core test (Value-Weighted monthly, 6 Portfolios 2x3)
Implements the "Core" scope of FF5_Factor_Model_Testing_Plan.md:
  data cleaning -> excess returns -> 6 time-series OLS regressions (Newey-West HAC)
  -> summary table (alpha, betas, t-stats, R^2) -> GRS joint test -> pass/fail.

Test assets (Y): 6_Portfolios_2x3.csv  (Average Value Weighted Returns -- Monthly)
Factors   (X):   F-F_Research_Data_5_Factors_2x3.csv  (Mkt-RF, SMB, HML, RMW, CMA, RF)
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

HERE = Path(__file__).parent
PORT_FILE = HERE / "6_Portfolios_2x3.csv"
FACT_FILE = HERE / "F-F_Research_Data_5_Factors_2x3.csv"

FACTORS = ["Mkt-RF", "SMB", "HML", "RMW", "CMA"]
MONTH_RE = re.compile(r"^\s*(\d{6})\s*,")  # YYYYMM at start of a data row


# ---------------------------------------------------------------------------
# 1. Load & clean
# ---------------------------------------------------------------------------
def load_ff_section(path: Path, section_header: str | None) -> pd.DataFrame:
    """Read one monthly block from a Ken French CSV.

    If section_header is given, start right after the line containing it
    (the portfolios file stacks many blocks). Then keep consecutive rows
    whose first field is a 6-digit YYYYMM, stopping at the first row that
    is not (blank line / next section / annual block).
    """
    lines = path.read_text().splitlines()

    start = 0
    if section_header is not None:
        for i, ln in enumerate(lines):
            if section_header in ln:
                start = i + 1
                break
        else:
            raise ValueError(f"section header not found: {section_header!r}")

    # find the column-header line (the one beginning with a comma) at/after start
    hdr_idx = next(i for i in range(start, len(lines)) if lines[i].lstrip().startswith(","))
    columns = [c.strip() for c in lines[hdr_idx].split(",")][1:]

    dates, rows = [], []
    for ln in lines[hdr_idx + 1:]:
        m = MONTH_RE.match(ln)
        if not m:
            if dates:            # we were inside the block -> block ended
                break
            continue             # not started yet
        parts = [p.strip() for p in ln.split(",")]
        dates.append(m.group(1))
        rows.append([float(x) for x in parts[1:1 + len(columns)]])

    df = pd.DataFrame(rows, columns=columns, index=pd.PeriodIndex(dates, freq="M"))
    df.index.name = "date"
    # Ken French missing codes -> NaN
    return df.replace([-99.99, -999.0, -999.99], np.nan)


# ---------------------------------------------------------------------------
# 2. GRS test (Gibbons, Ross, Shanken 1989)
# ---------------------------------------------------------------------------
def grs_test(alphas: np.ndarray, resid: np.ndarray, factors: np.ndarray):
    """
    alphas : (N,)      estimated alphas
    resid  : (T, N)    regression residuals
    factors: (T, K)    the K factor time series
    returns (GRS statistic, p-value, dof1=N, dof2=T-N-K)
    """
    T, N = resid.shape
    K = factors.shape[1]

    Sigma = (resid.T @ resid) / (T - K - 1)          # residual cov (unbiased)
    mu_f = factors.mean(axis=0)
    Omega = np.cov(factors, rowvar=False, bias=True)  # factor cov (MLE, /T)

    sr2_f = mu_f @ np.linalg.solve(Omega, mu_f)       # squared SR of factors
    a_term = alphas @ np.linalg.solve(Sigma, alphas)

    grs = ((T - N - K) / N) * (a_term / (1.0 + sr2_f))
    p = stats.f.sf(grs, N, T - N - K)
    return grs, p, N, T - N - K


# ---------------------------------------------------------------------------
# 3. Run
# ---------------------------------------------------------------------------
def main() -> None:
    ports = load_ff_section(PORT_FILE, "Average Value Weighted Returns -- Monthly")
    facts = load_ff_section(FACT_FILE, None)  # first (monthly) block

    port_cols = list(ports.columns)  # 6 portfolios

    # inner-join on date, drop any month with missing values
    df = ports.join(facts, how="inner").dropna()
    T = len(df)
    print(f"Merged sample: {df.index.min()} .. {df.index.max()}  (T = {T} months)")
    print(f"Portfolios (Y): {port_cols}")
    print(f"Factors    (X): {FACTORS} + RF\n")

    X = sm.add_constant(df[FACTORS])
    results, resid_mat, alphas = {}, [], []

    for p in port_cols:
        y = df[p] - df["RF"]                       # excess return
        m = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": 6})
        results[p] = m
        resid_mat.append(m.resid.values)
        alphas.append(m.params["const"])

    resid_mat = np.column_stack(resid_mat)
    alphas = np.array(alphas)

    # ---- summary table -----------------------------------------------------
    def row(p):
        m = results[p]
        d = {"alpha": m.params["const"], "t(alpha)": m.tvalues["const"]}
        for f in FACTORS:
            d[f] = m.params[f]
            d[f"t({f})"] = m.tvalues[f]
        d["R2"] = m.rsquared
        return d

    summary = pd.DataFrame({p: row(p) for p in port_cols}).T
    pd.set_option("display.width", 200, "display.float_format", lambda x: f"{x:8.3f}")
    print("=== Time-series regression summary (Newey-West HAC, maxlags=6) ===")
    print("alpha & betas in % per month; t-stats in parentheses columns\n")
    print(summary.to_string())

    n_sig = int((summary["t(alpha)"].abs() > 1.96).sum())
    print(f"\nPortfolios with |t(alpha)| > 1.96: {n_sig} / {len(port_cols)}")

    # ---- GRS test ----------------------------------------------------------
    grs, pval, d1, d2 = grs_test(alphas, resid_mat, df[FACTORS].values)
    print("\n=== GRS joint test  (H0: all 6 alphas = 0) ===")
    print(f"GRS statistic = {grs:.4f}   ~ F({d1}, {d2})")
    print(f"p-value       = {pval:.4f}")
    verdict = "PASS  -> do NOT reject H0 (model prices the 6 portfolios)" if pval > 0.05 \
        else "FAIL  -> reject H0 (some alpha != 0, mispricing remains)"
    print(f"Decision (5%) : {verdict}")

    mean_abs_alpha = np.abs(alphas).mean()
    print(f"\nMean |alpha| = {mean_abs_alpha:.4f}% per month   "
          f"(~{mean_abs_alpha*12:.2f}% per year)")


if __name__ == "__main__":
    main()

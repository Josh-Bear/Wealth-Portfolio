"""
Weighting: proportional-to-score with floor/ceiling via iterative water-filling.
Shared by the batch engine (engine.py) and the dashboard (dashboard.py).

Rules:
  - core stocks: floor 5%, ceiling 30%   (mandatory holdings)
  - secondary  : floor 0%, ceiling 30%
  - surplus above floors is distributed proportionally to raw_score, capped at each ceiling
  - if the free stocks all have score 0, the leftover is filled CORE-FIRST (equal), then secondary
    (confirmed choice for the <4-positive-score edge case)
  - Σ weight = 1 exactly; feasibility guaranteed because 5 core alone give 1.25 total headroom > 1
"""

CEILING = 0.30
CORE_FLOOR = 0.05
SEC_FLOOR = 0.0


def water_fill(scores, enabled, core_set, ceiling=CEILING, eps=1e-12, max_iter=200):
    """
    scores : dict ticker -> raw_score (>=0)
    enabled: iterable of tickers actually in play at this entry (have data / toggled on)
    core_set: set of core tickers (get 5% floor)
    returns: dict ticker -> weight  (floor<=w<=ceiling, sum==1)
    """
    enabled = list(enabled)
    if not enabled:
        return {}
    floor = {i: (CORE_FLOOR if i in core_set else SEC_FLOOR) for i in enabled}
    base = sum(floor.values())
    if base > 1.0 + eps:  # too many core floors (can't happen with <=5 core & 30% headroom, but guard)
        scale = 1.0 / base
        return {i: floor[i] * scale for i in enabled}

    w = dict(floor)
    headroom = {i: ceiling - floor[i] for i in enabled}   # core .25, secondary .30
    surplus = 1.0 - base
    frozen = set()

    for _ in range(max_iter):
        if surplus <= eps:
            break
        recv = [i for i in enabled if i not in frozen and headroom[i] > eps]
        if not recv:
            break
        sc = {i: max(scores.get(i, 0.0), 0.0) for i in recv}
        tot = sum(sc.values())
        if tot > eps:
            share = {i: surplus * sc[i] / tot for i in recv}
        else:
            # zero scores among receivers -> fill CORE-FIRST, else remaining receivers
            core_recv = [i for i in recv if i in core_set]
            tgt = core_recv if core_recv else recv
            share = {i: (surplus / len(tgt) if i in tgt else 0.0) for i in recv}

        added = 0.0
        newly = []
        for i in recv:
            add = share[i]
            if add >= headroom[i] - eps:      # hits ceiling -> freeze at ceiling
                add = headroom[i]
                newly.append(i)
            w[i] += add
            headroom[i] -= add
            added += add
        surplus -= added
        for i in newly:
            frozen.add(i)
        if not newly:                          # everything placed this round
            break

    # numerical cleanup: push any tiny residual onto the largest-headroom core (then any) receiver
    resid = 1.0 - sum(w.values())
    if abs(resid) > 1e-9:
        cand = sorted([i for i in enabled if (ceiling - w[i]) > 1e-9],
                      key=lambda i: (i not in core_set, -(ceiling - w[i])))
        if cand:
            w[cand[0]] += resid
    return w


# ----------------- self-test -----------------
if __name__ == "__main__":
    CORE = {"AOT", "OR", "KTB", "PTT", "PTTEP"}
    ALL = list(CORE) + ["SCB", "BBL", "KBANK", "TTB", "BAY"]

    def check(name, scores, enabled):
        w = water_fill(scores, enabled, CORE)
        s = sum(w.values())
        oksum = abs(s - 1.0) < 1e-6
        okcap = all(v <= CEILING + 1e-9 for v in w.values())
        okflr = all(w[i] >= (CORE_FLOOR - 1e-9) for i in enabled if i in CORE)
        print(f"[{name}] sum={s:.6f} {'OK' if oksum else 'BAD'} | "
              f"ceiling {'OK' if okcap else 'BAD'} | core-floor {'OK' if okflr else 'BAD'}")
        print("   " + ", ".join(f"{k}={w[k]*100:.1f}%" for k in enabled))
        return oksum and okcap and okflr

    ok = True
    # 1) all equal scores -> should spread, cores >=5%, none >30%
    ok &= check("equal", {t: 1.0 for t in ALL}, ALL)
    # 2) one dominant -> capped at 30%, rest fills
    ok &= check("one-dominant", {**{t: 0.0 for t in ALL}, "PTTEP": 100.0}, ALL)
    # 3) edge: only 2 positive scores (30%*2=60% < 100%) -> leftover core-first
    ok &= check("two-positive", {**{t: 0.0 for t in ALL}, "PTTEP": 5, "SCB": 5}, ALL)
    # 4) core-only universe (secondaries off)
    ok &= check("core-only", {"AOT": 1, "OR": 2, "KTB": 3, "PTT": 4, "PTTEP": 5}, list(CORE))
    # 5) all zero scores -> core-first equal, sum=1
    ok &= check("all-zero", {t: 0.0 for t in ALL}, ALL)
    print("\nALL TESTS", "PASS" if ok else "FAIL")

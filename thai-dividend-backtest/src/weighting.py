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


def round_to_half_pct(w, core_set, step=0.005, ceiling=CEILING, core_floor=CORE_FLOOR):
    """Round a water_fill() output onto a 0.5pp grid (weights land on x.0% or x.5%
    only), preserving sum==1 exactly.

    Approach: round every ticker to its NEAREST grid point first (min individual
    deviation, <= half a step each). Because both CORE_FLOOR (5%) and CEILING (30%)
    are exact multiples of `step`, nearest-rounding alone can never breach them
    (a raw weight already >= floor rounds to a grid point >= floor; already <=
    ceiling rounds to a grid point <= ceiling). Nearest-rounding of every ticker
    independently will generally leave the total off from 100% by a few units
    (itself always a whole number of steps); that residual is then walked onto the
    tickers whose raw value sat closest to the next grid point in the needed
    direction (largest-remainder tie-break), touching as few tickers as possible
    and respecting floor/ceiling at every step.

    w          : dict ticker -> weight (output of water_fill(), sums to 1)
    core_set   : core tickers (get the 5% floor guard during down-adjustments)
    returns    : dict ticker -> weight, each a multiple of `step`, sum == 1 exactly
    """
    if not w:
        return {}
    total_units = round(1.0 / step)                 # e.g. 200 for step=0.005 (0.5%)
    ceiling_units = round(ceiling / step)            # e.g. 60 for 30%
    floor_units = {i: (round(core_floor / step) if i in core_set else 0) for i in w}
    raw_units = {i: v / step for i, v in w.items()}
    nearest = {i: max(floor_units[i], min(ceiling_units, int(raw_units[i] + 0.5))) for i in w}

    diff = total_units - sum(nearest.values())
    guard = 0
    if diff > 0:
        # need to add `diff` units total -> give them to tickers closest to rounding up
        order = sorted(w, key=lambda i: -(raw_units[i] - nearest[i]))
        while diff > 0 and guard < len(order) * 5:
            i = order[guard % len(order)]
            if nearest[i] < ceiling_units:
                nearest[i] += 1
                diff -= 1
            guard += 1
    elif diff < 0:
        # need to remove `-diff` units total -> take them from tickers closest to rounding down
        order = sorted(w, key=lambda i: -(nearest[i] - raw_units[i]))
        while diff < 0 and guard < len(order) * 5:
            i = order[guard % len(order)]
            if nearest[i] > floor_units[i]:
                nearest[i] -= 1
                diff += 1
            guard += 1
    return {i: nearest[i] * step for i in w}


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

    # ---- round_to_half_pct checks ----
    def check_round(name, scores, enabled):
        w = water_fill(scores, enabled, CORE)
        r = round_to_half_pct(w, CORE)
        s = sum(r.values())
        oksum = abs(s - 1.0) < 1e-9
        okcap = all(v <= CEILING + 1e-9 for v in r.values())
        okflr = all(r[i] >= (CORE_FLOOR - 1e-9) for i in enabled if i in CORE)
        # every value must land on the 0.5pp grid
        okgrid = all(abs(round(v / 0.005) - v / 0.005) < 1e-6 for v in r.values())
        maxdev = max((abs(r[i] - w[i]) for i in enabled), default=0.0)
        okmatch = maxdev <= 0.005 + 1e-9  # no ticker should ever move by more than one full step
        print(f"[round:{name}] sum={s:.6f} {'OK' if oksum else 'BAD'} | "
              f"ceiling {'OK' if okcap else 'BAD'} | core-floor {'OK' if okflr else 'BAD'} | "
              f"grid {'OK' if okgrid else 'BAD'} | max-dev={maxdev*100:.2f}pp {'OK' if okmatch else 'BAD'}")
        print("   raw:     " + ", ".join(f"{k}={w[k]*100:.4f}%" for k in enabled))
        print("   rounded: " + ", ".join(f"{k}={r[k]*100:.1f}%" for k in enabled))
        return oksum and okcap and okflr and okgrid and okmatch

    ok &= check_round("equal", {t: 1.0 for t in ALL}, ALL)
    ok &= check_round("one-dominant", {**{t: 0.0 for t in ALL}, "PTTEP": 100.0}, ALL)
    ok &= check_round("two-positive", {**{t: 0.0 for t in ALL}, "PTTEP": 5, "SCB": 5}, ALL)
    ok &= check_round("core-only", {"AOT": 1, "OR": 2, "KTB": 3, "PTT": 4, "PTTEP": 5}, list(CORE))
    ok &= check_round("all-zero", {t: 0.0 for t in ALL}, ALL)
    # messy scores designed to produce lots of .xx75 raw weights -> stresses the remainder logic
    import random
    random.seed(7)
    for trial in range(20):
        sc = {t: round(random.random() * 10, 4) for t in ALL}
        ok &= check_round(f"random-{trial}", sc, ALL)

    print("\nALL TESTS", "PASS" if ok else "FAIL")

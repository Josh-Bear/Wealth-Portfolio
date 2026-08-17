# CLAUDE.md — Wealth-Portfolio (workspace)

Monorepo root. One git repo holding several related Thai-equity tools, each in its own subfolder.
Personal working-style rules (rethink, ask-before-executing, recheck, reply in Thai) live in the
user-level `~/.claude/CLAUDE.md` and apply here too.

## Projects

| subfolder | what it is | paradigm |
|---|---|---|
| [`thai-dividend-backtest/`](thai-dividend-backtest/CLAUDE.md) | walk-forward dividend-yield **backtest**, 5 scoring methods, measured at 4 checkpoints | capped proportional weighting (water-fill) |
| [`dividend_maximizer/`](dividend_maximizer/CLAUDE.md) | pick ≥5 stocks to **maximize** one half-year's dividend, in real board lots | greedy corner-solution |

Each subfolder has its own `CLAUDE.md` with the details. When working inside a subfolder, Claude Code
loads this root file **plus** that subfolder's file (nearest-ancestor cascade), so keep shared context
here and project specifics there.

## Shared data (no drift)

`thai-dividend-backtest/data/` (`price_history.csv`, `dividend_history.csv`, …) and its
`src/common.py` are the **single source of truth**. `dividend_maximizer/` reads those same files and
imports that `common.py` (via `../thai-dividend-backtest/src`) rather than copying anything — so the
universe, prices, `CAPITAL`, and `TODAY` can never diverge between the two tools.

## Layout

```
Wealth-Portfolio/
├── CLAUDE.md                    (this file — workspace overview)
├── thai-dividend-backtest/      (backtest; owns the data + common.py)
└── dividend_maximizer/          (maximizer; reads the backtest's data + common.py)
```

## Git

Monorepo: `.git` is at this root; both projects share one history and the `Josh-Bear/Wealth-Portfolio`
remote. New sibling tools go in new top-level subfolders with their own `CLAUDE.md`.

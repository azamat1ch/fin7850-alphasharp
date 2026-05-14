# AlphaSharp FIN7850 Trading Bot

BTC/ETH residual mean-reversion pair-trading project for FIN7850 Algorithmic and High-Frequency Trading.

The repo contains the public, non-secret project code and strategy notes:

- `AlphaSharp.py`: ProfitView bot script.
- `scripts/backtest_strategy.py`: Binance BTC/ETH futures proxy backtest.
- `scripts/trigger_audit.py`: trigger-frequency sanity check.
- `scripts/local_relaxed_dry_run.py`: local relaxed replay for state-machine testing.
- `docs/plan.md`: implementation and testing plan.
- `docs/strategy-onepager.md`: strategy summary.
- `docs/operation-checklist.md`: dry-run / paper-test checklist.
- `NEXT_SESSION.md`: short handoff for the next coding session.
- `scratchpad.md`: progress log and decisions.

## Current Status

Implemented, but not live-ready.

Backtests showed enough signal frequency, but strategy quality is not proven: some validation configs looked good while training-period results were negative across tested grids. The correct next step is longer dry-run and tiny WooPaper plumbing tests, not real sizing.

`AlphaSharp.py` defaults to safe mode:

```python
DRY_RUN = True
TEST_MODE = "RELAXED"
```

Do not set `DRY_RUN=False` until the checklist is complete.

## Quick Checks

Syntax check:

```bash
python3 -m py_compile AlphaSharp.py scripts/backtest_strategy.py scripts/trigger_audit.py scripts/local_relaxed_dry_run.py
```

Trigger audit:

```bash
python3 scripts/trigger_audit.py --days 180
```

Backtest:

```bash
python3 scripts/backtest_strategy.py --days 180
python3 scripts/backtest_strategy.py --days 180 --quality-grid
```

Local relaxed replay:

```bash
python3 scripts/local_relaxed_dry_run.py --days 21
```

Scripts print concise summaries by default. Generated reports, cached data, browser snapshots, and credentials are intentionally not committed.

## Public Repo Boundary

Excluded from git:

- ProfitView cookies/session state.
- ProfitView passwords/API tokens/webhook secrets.
- account-specific private notes.
- cached market data.
- Playwright snapshots/logs.
- generated reports and CSV artifacts.

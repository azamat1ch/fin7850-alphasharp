# AlphaSharp FIN7850 Trading Bot

BTC/ETH residual mean-reversion pair-trading project for FIN7850 Algorithmic and High-Frequency Trading.

The repo contains the local project code and strategy notes:

- `AlphaSharp.py`: ProfitView bot script.
- `scripts/backtest_strategy.py`: Binance BTC/ETH futures proxy backtest.
- `scripts/trigger_audit.py`: trigger-frequency sanity check.
- `scripts/local_relaxed_dry_run.py`: local relaxed replay for state-machine testing.
- `docs/plan.md`: original implementation plan, strategy spec, and validation gates.
- `docs/strategy-onepager.md`: strategy summary.
- `docs/operation-checklist.md`: current runbook and operational handoff.
- `docs/api-cli-research.md`: ProfitView API and platform notes.
- `scratchpad.md`: progress log and decisions.

## Current Status

Implemented, but not live-ready.

Backtests showed enough signal frequency, but strategy quality is not proven: some validation configs looked good while training-period results were negative across tested grids. ProfitView relaxed dry-run, real dry-run, and tiny WooPaper order plumbing tests have passed. The correct next step is conservative WooPaper forward testing of the real strategy, not real sizing.

`AlphaSharp.py` defaults to safe mode:

```python
DRY_RUN = True
TEST_MODE = "RELAXED"
```

Do not set `DRY_RUN=False` except for monitored WooPaper forward testing or an explicitly repeated tiny plumbing test.

## Course Context

Team name: AlphaSharp.

| Item | Weight | Due / Window | Practical meaning |
| --- | ---: | --- | --- |
| Project one-pager | 5% | May 5, 2026 | Done; feedback received from Ken Liu. |
| Trading competition | 10% | Jun 1, 2026 00:00 HKT to Jun 14, 2026 23:59 HKT | Participation gets full marks. Winning is by highest Sharpe with positive return, max drawdown within 20%, and at least one trade. |
| Fundraising / final event | 25% | Jun 16, 2026, 19:00-22:00 HKT | Pitch the strategy and results to guest investors. Top 3 teams present for 15 minutes plus Q&A. |

## Platform Notes

- Platform: ProfitView.
- Development / simulation account: `WooPaper`.
- Competition venue/account: `WooLive`, available from the start of the paper trading period.
- Primary products: `PERP_BTC_USDT`, `PERP_ETH_USDT`.
- Initial paper balance: virtual `10,000 USDT`.
- Top-of-book market data subscriptions: max 5 concurrent subscriptions per session.
- Market orders are supported in WooPaper; class notes say limit orders are not supported there.
- Randomized market fill latency: about 200-300 ms.
- Trading fee: 0.05% notional per trade, so roughly 0.10% round trip.
- API request limit from class notes: 60 requests per minute.
- Stopping a script does not close positions. Positions must be explicitly closed.

Professor feedback on the one-pager: trade the BTC/ETH relationship directly, keep the signal on 15-minute candles, avoid fee-heavy short-timeframe churn, treat funding as a manual cost warning, and keep time stops as a safety exit rather than the main alpha idea.

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

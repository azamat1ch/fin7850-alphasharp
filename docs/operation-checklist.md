# AlphaSharp Operation Checklist

Last updated: 2026-05-13

## Current Go / No-Go

Status: implementation ready for dry-run and tiny WooPaper plumbing tests.

Not cleared for real live/competition sizing yet. Historical validation can look good, but train-period backtests were negative across tested grids. The next gate is clean WooPaper forward evidence, not more local optimism.

Latest ProfitView status:

- `AlphaSharp.py` is saved in ProfitView.
- `DRY_RUN=True` and `TEST_MODE="RELAXED"` are the current safe defaults.
- WOO paper BTC/ETH perp markets were selected.
- A short startup dry-run found and fixed ProfitView-specific issues around webhook names, lazy bot state, and quote parsing.
- Bot was stopped cleanly after the short dry-run. Run a longer relaxed soak before enabling any paper orders.

## Before Starting ProfitView

- Confirm `AlphaSharp.py` has `DRY_RUN=True`.
- Confirm `TEST_MODE="RELAXED"` for forced plumbing tests, or `TEST_MODE="REAL"` for real-rule dry-run.
- Confirm selected markets are exactly:
  - `PERP_BTC_USDT`
  - `PERP_ETH_USDT`
- Confirm venue is `WooPaper`.
- Confirm logs are purged or easy to read.
- Confirm no existing BTC/ETH paper positions need manual flattening.

## Relaxed Dry-Run

Purpose: prove the bot starts, gets data, computes signal state, and can walk through fake entries/exits.

- Run `AlphaSharp.py` in ProfitView with `DRY_RUN=True` and `TEST_MODE="RELAXED"`.
- Watch logs for at least 15-60 minutes.
- Expected healthy logs:
  - startup and trading-server login
  - `skip_no_extreme`, `alert`, `wait_hook`, `WOULD_ENTER`, or `WOULD_EXIT`
  - no repeated exception loop
- If no fake trade happens, that is okay for a short run. Use the local replay report as proof that relaxed logic can trigger.

Local relaxed replay:

```bash
python3 scripts/local_relaxed_dry_run.py --days 21
```

It prints the summary to stdout by default. Pass `--report some/path.txt` only if you need a file.

## Real Dry-Run

Purpose: test real strategy rules with orders still disabled.

- Change only `TEST_MODE="REAL"`.
- Keep `DRY_RUN=True`.
- Re-save and restart ProfitView.
- Run for 30-60 minutes minimum, longer if possible.
- It is normal if no real entry triggers in this short window.
- Healthy result means candles, z-score, filters, and logs work without errors.

## Tiny WooPaper Order Test

Only do this after relaxed and real dry-run have no runtime errors.

- Keep venue as `WooPaper`.
- Reduce gross exposure or order sizing to tiny notional.
- Set `DRY_RUN=False` only for the tiny paper test.
- Use relaxed mode first so a controlled fake-quality setup can trigger.
- Verify:
  - BTC leg opens and closes.
  - ETH leg opens and closes.
  - both pair directions can open and close.
  - no duplicate order loop.
  - manual flatten route works.
  - ProfitView positions match the bot state.
- Return to `DRY_RUN=True` immediately after the test unless actively paper-forward-testing.

## WooPaper Forward Test

Purpose: prove the real strategy, not only the code.

- Use `TEST_MODE="REAL"`.
- Use conservative size.
- Track every entry, exit, skip reason, PnL, drawdown, and error.
- Required pass criteria before competition/live sizing:
  - positive net PnL after fees,
  - no duplicate-order bugs,
  - no broken two-leg state,
  - max drawdown stays comfortably below 3-4%,
  - trade count is not excessive,
  - average winner is meaningfully larger than fee drag.

## Competition Rule

Do not loosen thresholds mid-competition just because no trade happened. If a required participation trade is needed, use a tiny controlled contingency trade rather than converting the strategy into an overactive version.

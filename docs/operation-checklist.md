# AlphaSharp Operation Checklist And Handoff

Last updated: 2026-05-14

Current date context: May 14, 2026 HKT.

## Project Status

The project has one strategy now: BTC/ETH residual mean-reversion pair trading.

Implementation exists:

- `AlphaSharp.py`: ProfitView bot.
- `scripts/backtest_strategy.py`: backtest/grid runner.
- `scripts/trigger_audit.py`: trigger-frequency sanity check.
- `scripts/local_relaxed_dry_run.py`: local fake relaxed replay.
- `docs/plan.md`: full execution plan and parameter logic.
- `docs/strategy-onepager.md`: concise strategy narrative.
- `scratchpad.md`: detailed work log.

## Current Go / No-Go

Status: implementation ready for WooPaper forward testing at conservative size.

Do not treat this as strategy-proven or live-ready. Historical validation can look good, but train-period backtests were negative across tested grids. The next gate is clean WooPaper forward evidence, not more local optimism.

Latest ProfitView status:

- `AlphaSharp.py` is saved in ProfitView.
- `DRY_RUN=True` and `TEST_MODE="RELAXED"` are the current safe defaults.
- WOO paper BTC/ETH perp markets were selected.
- ProfitView-specific issues fixed so far:
  - webhook methods must use `get_` / `post_` prefixes;
  - ProfitView may call market callbacks before custom instance state exists, so bot state lazily initializes;
  - quote updates send `bid` / `ask` as `[price, size]`, so the parser extracts the first element;
  - WOO market-order side must be `Buy` / `Sell`, not lowercase.
- Relaxed dry-run on May 14 stayed healthy with live BTC/ETH signal calculation and no new callback error loop.
- Real-rule dry-run on May 14 stayed healthy with orders disabled; no entry triggered, which was expected.
- Tiny WooPaper order tests on May 14 successfully opened and flattened both pair directions after the side-casing fix.
- Final tiny-test state: no open orders, bot returned to safe dry mode, then the script was stopped cleanly.
- Tiny paper test cost: about `-0.54 USDT` across two forced pair round trips. Treat this as fee/spread plumbing cost, not performance evidence.

Immediate next steps:

1. Open ProfitView and confirm `AlphaSharp.py` is still saved.
2. Confirm `DRY_RUN=True`, `TEST_MODE="RELAXED"`, and venue `WooPaper`.
3. Before real forward testing, confirm no BTC/ETH paper positions or open orders exist.
4. Start `TEST_MODE="REAL"` with conservative or tiny size.
5. Set `DRY_RUN=False` only when someone is actively monitoring the first forward-test session.
6. Track each real strategy entry/exit, fees, PnL, drawdown, skipped signals, and any runtime errors.
7. Return to `DRY_RUN=True` or stop the script when not actively monitoring.

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

Completed on May 14, 2026 HKT.

Only repeat this if order plumbing changes.

- Keep venue as `WooPaper`.
- Reduce gross exposure or order sizing to tiny notional.
- Set `DRY_RUN=False` only for the tiny paper test.
- Use the deterministic tiny paper webhooks rather than waiting for natural relaxed-mode triggers:
  - `post_force_tiny_paper`
  - `post_test_short_eth_long_btc`
  - `post_test_long_eth_short_btc`
  - `post_flatten`
  - `post_force_safe_dry`
- Verify:
  - BTC leg opens and closes.
  - ETH leg opens and closes.
  - both pair directions can open and close.
  - no duplicate order loop.
  - manual flatten route works.
  - ProfitView positions match the bot state.
- Return to `DRY_RUN=True` immediately after the test unless actively paper-forward-testing.

Last result:

- Both pair directions opened and closed successfully.
- Four WooPaper leg trades were recorded.
- No open orders remained afterward.
- Script was stopped cleanly.

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

## Useful Commands

Local syntax check:

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

## Reports Policy

Do not generate artifacts by default. The old verbose Markdown reports and trade CSVs were removed.

Use stdout for normal checks. If a file is genuinely useful, pass `--report some/path.txt` or `--trades some/path.csv` explicitly.

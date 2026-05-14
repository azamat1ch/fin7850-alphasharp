# Next Session Handoff

Current date context: May 14, 2026 HKT.

## Status

The project has one strategy now: BTC/ETH residual mean-reversion pair trading.

Implementation exists:

- `AlphaSharp.py`: ProfitView bot.
- `scripts/backtest_strategy.py`: backtest/grid runner.
- `scripts/trigger_audit.py`: trigger-frequency sanity check.
- `scripts/local_relaxed_dry_run.py`: local fake relaxed replay.
- `docs/operation-checklist.md`: runbook.
- `scratchpad.md`: detailed work log.

ProfitView status:

- Bot file `AlphaSharp.py` is saved in ProfitView.
- Selected markets were BTC and ETH WOO paper perps.
- Current safe defaults are `DRY_RUN=True` and `TEST_MODE="RELAXED"`.
- Bot was stopped cleanly after a short dry-run.
- No real orders were enabled.

## Important Truth

Do not treat this as live-ready.

Backtests found enough triggers, but strategy quality is not proven:

- validation had some good-looking configs;
- training period was negative across tested configs;
- conclusion: okay for dry-run and tiny WooPaper plumbing tests, not okay for real sizing yet.

## Next Steps

1. Open ProfitView and confirm `AlphaSharp.py` is still saved.
2. Confirm `DRY_RUN=True`, `TEST_MODE="RELAXED"`, venue `WooPaper`.
3. Start the bot and run a 15-60 minute relaxed dry-run.
4. Watch logs for fresh errors after the last fixes:
   - webhook route naming fixed;
   - lazy state init fixed;
   - quote `[price, size]` parsing fixed.
5. If relaxed dry-run is clean, switch only `TEST_MODE="REAL"` while keeping `DRY_RUN=True`.
6. Run 30-60 minutes real-rule dry-run.
7. Only after clean logs, do tiny WooPaper order tests.

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

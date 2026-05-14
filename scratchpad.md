# AlphaSharp Scratchpad

Last updated: 2026-05-14

## Goal

Implement the FIN7850 AlphaSharp BTC/ETH residual mean-reversion project end to end:

- reusable local strategy/backtest tooling
- historical backtests with reports
- ProfitView `AlphaSharp.py` bot with dry-run/test modes
- relaxed dry-run path where feasible
- follow-up checklist for paper and competition operation

## Current State

- Docs are aligned around one BTC/ETH residual mean-reversion pair strategy.
- Operational handoff lives in `docs/operation-checklist.md`.
- Trigger-frequency audit exists:
  - Script: `scripts/trigger_audit.py`
- Cached Binance proxy data exists for BTC/ETH 15m.
- Local backtest tooling exists:
  - Script: `scripts/backtest_strategy.py`
  - Prints concise summaries by default; file artifacts are optional
- ProfitView bot draft exists:
  - `AlphaSharp.py`

## Work Log

### 2026-05-13

- Created this scratchpad.
- Starting implementation with local backtest tooling before ProfitView bot.
- Added `scripts/backtest_strategy.py`.
- Ran documented-grid backtest with 1 bps slippage.
- Ran quality-grid backtest with stricter z/fee-spread settings and beta method comparison.
- Result: validation can look good, but training is negative across tested configs. Strategy quality is not proven for live trading.
- Added `AlphaSharp.py` with dry-run default, relaxed test mode, state machine, webhooks, pair sizing, exits, risk halts, and logging.
- Uploaded `AlphaSharp.py` into ProfitView as `AlphaSharp.py`, selected WOO paper BTC/ETH perp streams, and started it in `DRY_RUN=True` / `TEST_MODE="RELAXED"`.
- ProfitView dry-run caught platform integration issues and they were fixed:
  - webhook methods must be named with `get_` / `post_` prefixes;
  - ProfitView may call market callbacks before custom instance state exists, so bot state now lazily initializes;
  - quote updates send `bid` / `ask` as `[price, size]`, so the parser now extracts the first element.
- Final short ProfitView restart after fixes logged into the Trading Server with no orders enabled. It was stopped cleanly. A longer 15-60 minute soak is still required before tiny WooPaper order tests.
- Added `docs/operation-checklist.md`.

### 2026-05-14

- Removed generated reports and trade CSV artifacts from `reports/`.
- Changed scripts so reports/trade CSVs are optional and nothing is written by default.
- Removed Python cache folders from the project.
- Deleted the separate next-session handoff file; `docs/operation-checklist.md` is now the single operational handoff/runbook.
- Merged `docs/project-brief.md` into `README.md` and deleted the separate brief.
- Re-scoped `docs/api-cli-research.md` to API/platform reference only.
- Marked `docs/plan.md` as the original implementation plan plus stable strategy spec/validation gates.
- Ran local syntax check and local relaxed replay before platform testing. Syntax passed; local relaxed replay still produced 14 fake trades over 21 days.
- Uploaded patched `AlphaSharp.py` to ProfitView and ran end-to-end tests 1-3:
  - Relaxed dry-run: ran on ProfitView with `DRY_RUN=True`, `TEST_MODE="RELAXED"`, live BTC/ETH signal available, no new callback error loop, no entry because z was only about `-0.18`.
  - Real dry-run: switched through webhook to `TEST_MODE="REAL"` while keeping `DRY_RUN=True`; stayed flat as expected, no runtime error loop.
  - Tiny WooPaper plumbing test: first attempt exposed a WOO/ProfitView requirement that market order side must be `Buy` / `Sell`, not lowercase `buy` / `sell`. No orders filled on the failed attempt.
  - Patched `AlphaSharp.py` to use `Buy` / `Sell`, added deterministic tiny paper routes, safe-mode reset behavior, and basic order-response checks/logging.
  - Retried tiny WooPaper tests successfully in both pair directions with about `0.01x` gross exposure. Four leg trades closed, no open orders remained, bot state returned to `FLAT`, and the script was stopped cleanly.
  - Final paper-test PnL for the two forced pair round trips was about `-0.54 USDT`, which is expected fee/spread drag and not strategy evidence.

## Decisions

- Keep the strategy simple: three strategy filters only.
- Treat stale quotes, failed-leg flattening, manual kill switch, and state machine as execution safety, not extra alpha filters.
- Use Binance futures as long-history proxy when WOO/ProfitView data is unavailable or too short.
- Do not optimize for more trades until quality after fees is understood.
- Do not treat the latest positive validation as enough to go live; train results are still weak.
- For future plumbing tests, use the deterministic tiny paper webhooks rather than waiting for relaxed mode to naturally trigger.

## Open Questions

- Can the strategy be improved without adding complexity or overfitting?
- Should live competition use this strategy only if WooPaper forward test confirms the recent validation behavior? Current answer: yes.
- Can WooPaper forward testing of the real strategy produce positive evidence after fees without execution bugs?

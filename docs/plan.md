# FIN7850 AlphaSharp Plan

Last updated: 2026-05-14

This is the original implementation plan plus the stable strategy spec and validation gates. For the current run order, use `operation-checklist.md`.

## Goal

Original goal: build a real ProfitView trading bot for the FIN7850 paper trading competition.

The goal is not max PnL. The goal is a small positive return with strong Sharpe, low drawdown, and clean execution.

Targets:

- Validation Sharpe: `> 1.5` minimum, `> 2.0` good
- Internal max drawdown target: `< 10%` minimum, `< 4%` good
- Competition max drawdown hard limit: `< 20%`
- Net positive after fees and slippage
- No runaway order loops
- Expected competition activity: `2-8` round trips, not constant trading

Current implementation status:

- Local trigger audit, historical backtest, relaxed replay, and ProfitView bot are implemented.
- ProfitView bot file: `AlphaSharp.py`.
- Default ProfitView mode is safe: `DRY_RUN=True` and `TEST_MODE="RELAXED"`.
- Original implementation layers are done at code level.
- Remaining work is operational validation: longer relaxed dry-run, real-rule dry-run, tiny WooPaper order tests, and WooPaper forward evidence.
- Strategy quality is not proven yet. Recent validation can look good, but training backtests were negative across the tested grids, so this is not cleared for real live trading without WooPaper confirmation.

Competition window:

- Paper trading: Jun 1, 2026 00:00 HKT to Jun 14, 2026 23:59 HKT
- Final fundraising / presentation: Jun 16, 2026 19:00-22:00 HKT

## Primary Strategy

Strategy: BTC/ETH residual mean-reversion pair trade.

Trade the BTC-ETH relative dislocation itself.

Products:

- `PERP_BTC_USDT`
- `PERP_ETH_USDT`

Core idea:

- Estimate the normal BTC/ETH relationship.
- If ETH is unusually rich versus BTC: short ETH, long BTC.
- If ETH is unusually cheap versus BTC: long ETH, short BTC.
- Exit when the relative spread normalizes.

Why this fits the competition:

- It reduces outright crypto beta.
- It trades fewer, larger dislocations than 1-minute BTC noise.
- It is less likely to become a 0.10% round-trip fee grinder.
- It is easier to defend for a Sharpe/drawdown competition.

Professor feedback incorporated:

- ETH relationship matters. We trade BTC and ETH as a pair.
- Do not over-focus on avoiding funding through an overly short fixed time stop.
- Funding is a manual cost warning only for the MVP, not a live bot filter.
- Reduce frequent time-stop exits because fees are 0.05% per trade, about 0.10% per round trip.

## Data Sources

Priority order:

1. ProfitView `fetch_candles`
   - Best match to the actual platform.
   - May only have recent 1m data, likely latest 7 days from class notes.

2. WOO public API
   - Use for WOO candles, symbol info, funding rate.
   - Docs: https://docs.woox.io/
   - Funding endpoint is already confirmed working.

3. Binance/Bybit public perp data as backup
   - Useful for longer historical research if WOO data is limited.
   - Final validation still needs ProfitView/WOO paper data.

4. Optional deeper execution data
   - Tardis or similar historical WOO data if we need quote/BBO/trade replay.
   - Useful for slippage and two-leg execution simulation, not required for the first backtest.

## Backtest Periods

If enough data is available:

- Main history: Jan 1-May 13, 2026
- Training/tuning: Jan 1-Mar 31, 2026
- Validation: Apr 1-May 13, 2026

If data is limited:

- Training/tuning: Feb 1-Apr 15, 2026
- Validation: Apr 16-May 13, 2026
- Short dry-run safety check: May 14, 2026
- WooPaper forward test with real paper orders: May 15-May 31, 2026

Also test bad regimes manually:

- strong BTC/ETH trend days
- choppy sideways days
- high volatility liquidation days
- ETH-specific repricing days
- dead low-volatility days

## Backtest Metrics

Must report:

- net return after fees
- Sharpe ratio
- max drawdown
- profit factor
- number of trades
- win rate
- average win
- average loss
- average holding time
- fee impact
- gross alpha / fees ratio
- exposure time
- worst single trade
- probability of positive return over random two-week windows

Targets:

| Metric | Minimum | Good |
| --- | ---: | ---: |
| Validation Sharpe | `> 1.5` | `> 2.0` |
| Validation max drawdown | `< 10%` | `< 4%` |
| Profit factor | `> 1.15` | `> 1.3` |
| Net return | positive | `0.5-1.5%` in competition-style window |
| Gross alpha / fees | `> 1.5x` | `> 2.0x` |

Prefer boring robustness over peak backtest result.

## Testing Ladder

The strategy is intentionally picky, so testing has to separate signal quality from execution plumbing.

### 0. Trigger Audit

Purpose: check whether the strategy would actually find enough setups in a two-week competition window.

Current tool:

```bash
python3 scripts/trigger_audit.py --days 180
```

Current result from Binance BTC/ETH futures 15m proxy data, Nov 14, 2025-May 13, 2026:

- Default-ish setup `7d` beta / `3d` z window / `2.4` entry z produced `87` entries in 180 days.
- Median entries per rolling 14-day window: `7`.
- Minimum entries per rolling 14-day window: `2`.
- Zero-trade rolling 14-day windows: `0 / 156`.

Interpretation: frequency is not the main problem. Do not make the strategy more active just to force trades. The next question is trade quality after fees and slippage.

### 1. Historical Backtest

Purpose: test whether the strategy makes money after fees/slippage and whether the results are robust.

Use the same core logic as the bot:

- 15m signal candles
- rolling beta
- residual z-score
- hook-confirmed entry
- three strategy filters
- pair sizing
- mean-reversion exit
- stop loss, z-stop, and time stop

This is where PnL, Sharpe, drawdown, win/loss, trade count, and fee drag matter.

Current tools:

```bash
python3 scripts/backtest_strategy.py --days 180
python3 scripts/backtest_strategy.py --days 180 --quality-grid
```

Reports and trade CSVs are intentionally not generated by default. Pass `--report some/path.txt` or `--trades some/path.csv` only if a file is genuinely useful.

Current readout:

- Default documented grid found validation winners, but no tested config had positive train performance.
- Quality grid best validation config was strong on Apr-May validation, but train was still negative.
- Conclusion: implementation can proceed through dry-run and tiny paper plumbing tests, but the strategy should not be promoted to real competition/live use until WooPaper forward testing confirms it.

### 2. Forced Dry Run

Purpose: test the bot's brain and state machine without waiting days for a real signal.

Run in ProfitView with orders disabled and temporary test settings:

- easier entry threshold, for example `abs(z) >= 0.5`
- easier exit threshold, for example `abs(z) <= 0.2`
- tiny/fake internal size
- optionally bypass fee filter for this test only

Expected logs:

- `WOULD_ENTER`
- `WOULD_EXIT`
- `SKIP reason`
- state changes: `FLAT -> ALERT -> OPEN -> EXITING -> FLAT`

Do not use forced dry-run PnL as strategy evidence. It only proves the bot logic moves through states correctly.

### 3. Real Dry Run

Purpose: see live ProfitView market data flow through the real strategy rules.

Run with orders disabled and real settings:

- entry z around `2.4`
- hook `0.25`
- real filters on
- real exits/stops on

It is fine if no trade triggers during a short run. This mode should still prove that candles, z-score, filters, fake position state, and logs are sane.

### 4. Forced Tiny Paper Test

Purpose: prove the order plumbing works with paper money.

Run on `WooPaper` with tiny size and either easy thresholds or manual test routes.

Must verify:

- open BTC long/short and close
- open ETH long/short and close
- open pair in both directions and close
- no duplicate entry orders
- flatten if one leg fails
- stop/manual flatten closes both legs
- ProfitView position state matches bot state

Forced tiny paper tests are not performance evidence. They only prove the bot can physically place and manage orders.

### 5. Real WooPaper Forward Test

Purpose: test the real strategy with paper orders over time.

Run with real thresholds and conservative size from May 15-May 31.

Track:

- actual entries/exits
- skipped signals and reasons
- PnL after fees
- drawdown
- trade count
- execution issues
- whether the bot trades too often

### 6. Competition Run

Purpose: execute the tested strategy, not experiment.

Use the same rules as the accepted WooPaper setup. Only change parameters for a clear bug or severe execution issue.

If no strategy trade has happened late in the competition and participation requires at least one trade, use a tiny controlled contingency trade rather than loosening the strategy globally.

## Bot Requirements

`AlphaSharp.py` has been created for ProfitView.

Core features:

- subscribe to BTC and ETH market streams
- maintain 15m signal state and 1m/quote execution state
- calculate rolling BTC/ETH hedge beta
- calculate residual spread: `log(ETH) - beta * log(BTC)`
- calculate residual z-score
- apply hook confirmation before entry
- apply fee/spread-volatility filter
- apply BTC/ETH correlation filter
- apply market-shock filter
- keep funding outside the MVP trading decision; review manually before running real paper/live
- max one pair position
- market orders only
- beta-adjusted pair sizing
- close both legs on residual mean reversion
- stop loss on pair PnL and/or residual expansion
- 8-hour time stop with reset requirement
- immediate flatten if one leg fails
- daily loss halt
- cumulative drawdown halt
- profit lock for competition
- manual pause/resume/flatten webhook
- aggressive logging

State machine:

- `FLAT`
- `ALERT`
- `ENTERING`
- `OPEN`
- `EXITING`
- `HALTED`

The state machine is non-negotiable. It prevents duplicate pair entries and broken two-leg execution.

## Layered Implementation

Layers were implementation order, not optional strategy variants. These are implemented in the local bot/backtest path; current validation status lives in `operation-checklist.md`.

Layer 1: core pair strategy

- rolling beta
- residual z-score
- hook-confirmed entry
- mean-reversion exit
- fees
- basic stop

Layer 2: three strategy filters

- fee/spread-volatility
- BTC/ETH correlation
- market shock

Layer 3: execution safety

- state machine
- no duplicate orders
- both-leg checks
- flatten-on-failure
- stale quote guard
- manual kill switch

Layer 4: competition logic

- daily loss stop
- drawdown halt
- profit lock
- no re-entry until reset

## Starting Parameter Grid

Initial safe parameters for backtest:

- Signal timeframe: 15m
- Execution checks: 1m / quote updates
- Beta lookback: 7d default; 14d as robustness check
- Z-score window: 3d default; 2d as robustness check
- Beta clip: `[0.8, 1.4]`
- Residual z entry alert: `2.2`, `2.4`, `2.6`
- Hook reversal: `0.25` z-units
- Exit z-score: `0.3`, `0.5`, `0.7`
- Minimum expected gross spread reversion: `0.5%`
- Minimum 3d BTC/ETH correlation: `0.70`
- Market shock skip: BTC or ETH move `> 1.5%` in 15m or `> 3.0%` in 1h
- Gross exposure: `0.75x`, `1.0x`
- Pair stop: `-0.25%`, `-0.35%`, `-0.50%` equity
- Emergency z-stop: `abs(z) > 3.4` and still moving against the trade
- Time stop: `8h` if trade is not profitable and z has not moved meaningfully toward zero
- Re-entry reset after time stop: wait until `abs(z) < 1.0`

Initial live defaults after backtest, unless evidence says otherwise:

- Gross exposure: `0.75x` to start
- Max gross exposure: `1.0x`
- Max pair positions: `1`
- Stop trading for day at `-0.75%`
- Reduce size at `-2%` cumulative drawdown
- Halt at `-4%` cumulative drawdown
- Profit lock: reduce size after `+1%`; stop new normal trades after `+1.5%`
- Expected competition frequency: `2-8` round trips

## Original Execution Steps

Status summary:

- Trigger audit and local data path: done.
- Historical backtest/grid runner: done.
- ProfitView bot draft and upload: done.
- Short safe ProfitView dry-run: done.
- Longer relaxed dry-run, real-rule dry-run, tiny WooPaper order test, and WooPaper forward test: still pending.

### 1. Trigger Audit And Data Pull

- Keep `scripts/trigger_audit.py` as the frequency audit.
- Re-run it after any major threshold change.
- Do not optimize on the trigger audit; use it to avoid a strategy that almost never trades.
- Pull BTC/ETH 15m candles for signals.
- Pull BTC/ETH 1m candles for execution simulation.
- Pull funding rate history if available.
- Save raw data locally.
- Check gaps, timezone, duplicates, and candle format.

### 2. Historical Backtest

- Implement vectorized/event-style backtest locally.
- Include fees: 0.05% per trade, 0.10% round trip.
- Include spread/slippage assumption for two market-order legs.
- Grid test pair-trade entry/exit/filter parameters.
- Do train/validation split.
- Pick robust config, not best-looking overfit config.

### 3. Dry-Run Safety Checks

- Build `AlphaSharp.py` with trading disabled. Status: done; current default is still `DRY_RUN=True`.
- First run forced dry-run mode with easy thresholds so entries/exits/stops trigger quickly.
- Then run real dry-run mode with real thresholds.
- Bot logs `would_long_eth_short_btc`, `would_short_eth_long_btc`, `would_close_pair`, skipped signals, and reasons.
- Paste into ProfitView through Playwright.
- Select BTC and ETH market streams.
- Start script and watch logs.
- Confirm data, indicators, signal frequency, fake position state, and logs are sane.
- Do not spend two weeks in dry-run. It is a brakes-and-steering check.

### 4. Tiny Paper Tests

Only after dry-run looks sane:

- enable tiny order size on `WooPaper`
- use forced tiny paper mode or manual test routes first
- test tiny BTC long/close and short/close
- test tiny ETH long/close and short/close
- test tiny pair entry/close in both directions
- verify position state
- verify both-leg handling
- verify flatten-on-failure logic
- verify stop works
- verify no repeated order loop
- verify logs are readable
- then switch back to real thresholds for real WooPaper forward testing

### 5. WooPaper Forward Test

From May 15-May 31, run real paper orders on `WooPaper`.

- Start with tiny size.
- Increase only if logs and account state stay clean.
- Monitor PnL, Sharpe proxy, drawdown, trade count, fee drag, and error logs.
- Track skipped signals and reasons.
- Save trades/PnL snapshots for the final pitch.
- Treat this as the real pre-competition validation, not dry-run.

### 6. Competition Run

- Switch to competition venue only when WooLive is available.
- Start with `0.5x` to `0.75x` gross exposure until WooLive execution is verified.
- Do not chase leaderboard raw return.
- Protect positive PnL with profit lock.
- Monitor drawdown, trade count, and fee drag.
- Save screenshots/results for final deck.

### 7. Final Pitch

Deck should show:

- thesis
- professor feedback incorporated
- strategy logic
- backtest results
- live paper trading results
- Sharpe
- max drawdown
- trade count
- fee impact
- risk controls
- what we would improve next

## Open Decisions

- Exact historical data source if WOO does not provide enough history.
- Exact fee/spread-volatility threshold after data pull.
- Final gross exposure after backtest and WooPaper forward test.

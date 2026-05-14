# FIN7850 Project Brief

Last updated: 2026-05-13 17:05 HKT

## What This Is

FIN7850 group project for Algorithmic and High-Frequency Trading.

The project has three parts:

| Item | Weight | Due / Window | Practical meaning |
| --- | ---: | --- | --- |
| Project one-pager | 5% | May 5, 2026 | Already done. Feedback received from Ken Liu. |
| Trading competition | 10% | Jun 1, 2026 00:00 HKT to Jun 14, 2026 23:59 HKT | Participation gets full marks. Winning is by highest Sharpe with positive return, max drawdown within 20%, and at least one trade. |
| Fundraising / final event | 25% | Jun 16, 2026, 19:00-22:00 HKT | Pitch the trading strategy and results to guest investors. Top 3 teams present for 15 minutes plus Q&A. |

As of May 13, 2026:

- Trading competition starts in 19 days.
- Final fundraising / presentation is in 34 days.

## Team

Team name: AlphaSharp

Team details are intentionally kept out of the public repo. Use the course submission materials for official member/contact information.

## Platform

Platform: ProfitView

Useful links:

- Login: https://profitview.net/login
- Main site: https://profitview.net/
- Trading docs: https://profitview.net/docs/trading/

Trading venue/account:

- Development / simulation account: `WooPaper`
- WooPaper balance: `10,000 USDT`
- Competition venue: `WooLive`, available from the start of the paper trading period
- Primary products: `PERP_BTC_USDT`, `PERP_ETH_USDT`
- Strategy: BTC/ETH residual mean-reversion pair trade
- Both BTC and ETH symbols exist in the ProfitView WOO market list

Platform constraints from course notes:

- Initial paper balance: virtual `10,000 USDT`
- Top-of-book market data subscriptions: max 5 concurrent subscriptions per session
- Supported event callbacks include `quote_update` and `trade_update`
- Market orders are supported in WooPaper; class notes say limit orders are not supported there
- Randomized market fill latency: about 200-300 ms
- Trading fee: 0.05% notional per trade, so roughly 0.10% round trip
- Max position size: 10x paper balance
- API request limit from class notes: 60 requests per minute
- Stopping a script does not close positions. Positions must be explicitly closed.

## Professor Feedback On One-Pager

From course feedback received May 12:

- Thesis is convincing and well-written.
- The BTC/ETH relationship is useful for reducing false signals.
- The time-based exit is reasonable, but funding cost is probably insignificant.
- Funding can be checked as an additional cost/regime warning.
- A short fixed time stop may trigger too often in slow-reversion cases.
- Frequent time stops increase transaction costs because fee is 0.05% per trade and 0.10% per round trip.

Practical interpretation: trade the BTC/ETH relationship directly, keep the signal on 15-minute candles, avoid fee-heavy short-timeframe churn, and treat time stops as a safety exit rather than the main alpha idea.

## What Needs To Be Done

The canonical execution plan is `plan.md`. This brief is the project overview.

### 1. Build Historical Test Harness

- Run trigger-frequency audit with `scripts/trigger_audit.py`.
- Trigger audit prints a concise summary by default; generate a file only with `--report`.
- Current result: the strategy is active enough on six-month Binance BTC/ETH futures proxy data; default-ish settings had median `7` entries per rolling 14-day window and `0 / 156` zero-trade 14-day windows.
- Pull BTC/ETH 15m candles for pair-trade signals.
- Pull BTC/ETH 1m candles for execution simulation.
- Include funding rate, fees, and slippage.
- Backtest BTC/ETH residual pair strategy with train/validation split.
- Target validation Sharpe above `1.5`, max drawdown below `10%`, and positive net return after fees. A Sharpe above `2.0` is the good target, not a promise.

### 2. Build `AlphaSharp.py`

The bot should be real, not just a demo script.

Required features:

- subscribe to BTC and ETH market data
- maintain 15m signal state and 1m execution checks
- calculate rolling hedge beta
- calculate BTC/ETH residual z-score
- apply hook confirmation before entry
- apply three strategy filters: fee/spread-volatility, BTC/ETH correlation, and market shock
- max one pair position
- beta-adjusted pair sizing
- market orders only
- pair mean-reversion exit
- pair stop loss
- emergency z-stop and 8-hour time stop
- re-entry reset after time stop
- flatten-on-failed-leg logic
- manual pause/resume/flatten webhook
- aggressive logs

### 3. Test In ProfitView

- Use Playwright CLI for ProfitView UI operations: paste bot, select streams, start/stop, inspect logs.
- Run forced dry-run first with easy thresholds and orders disabled to prove state transitions.
- Run real dry-run with real thresholds and orders disabled to prove live data and real rules.
- If logs/position state are sane, enable tiny WooPaper orders.
- Run forced tiny paper tests or manual test routes before real-threshold paper trading.
- Use May 15-May 31 as real paper forward validation.

### 4. Competition Run

- Switch to `WooLive` only when the competition venue is available.
- Run conservative sizing.
- Optimize for Sharpe and drawdown, not raw leaderboard gambling.
- Avoid frequent parameter changes unless logs show a real bug.

### 5. Prepare Final Pitch

For Jun 16, the pitch should be about risk-adjusted discipline, not "we invented alpha."

Expected deck/story:

- Problem: crypto perps are noisy, fee-heavy, and trend can kill naive mean reversion.
- Strategy: BTC/ETH residual mean reversion, trading relative dislocations rather than naked direction.
- Risk: beta-adjusted pair sizing, drawdown stop, max one pair position, flatten-on-failure.
- Evidence: competition PnL, Sharpe, max drawdown, trade count, win rate, average win/loss, fee impact.
- Improvement from feedback: direct BTC/ETH relationship, lower turnover, fee-aware entries, and conservative time-stop behavior.

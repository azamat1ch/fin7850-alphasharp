# AlphaSharp Strategy One-Pager

## BTC/ETH Residual Mean Reversion Pair Trade

Team: AlphaSharp  
Course: FIN7850 Algorithmic and High-Frequency Trading

## Thesis

BTC and ETH usually move together, but their relationship temporarily dislocates during short-term flow, liquidation, and volatility events. Instead of betting directionally that BTC will bounce, AlphaSharp trades the relative spread between BTC and ETH.

When ETH is unusually rich versus BTC, we short ETH and long BTC. When ETH is unusually cheap versus BTC, we long ETH and short BTC. The trade exits when the BTC/ETH residual normalizes.

This is aligned with the competition because the objective is Sharpe ratio with drawdown control, not maximum raw PnL. The pair structure reduces broad crypto beta, trades fewer high-quality signals, and avoids fee-heavy 1-minute noise.

## Product And Venue

- Venue: WOO X through ProfitView
- Paper account: `WooPaper`
- Competition account: `WooLive`
- Products: `PERP_BTC_USDT`, `PERP_ETH_USDT`
- Signal timeframe: 15-minute candles
- Execution checks: 1-minute candles / live quote updates

Why this setup:

- BTC and ETH perps are liquid and highly related.
- The two-symbol pair stays well inside ProfitView's 5-market subscription limit.
- A relative-value strategy is less exposed to broad market trend than a single-leg BTC trade.

## Signal Logic

Use log prices:

```text
x = log(BTC price)
y = log(ETH price)
```

Estimate rolling hedge beta from recent 15-minute returns:

```text
beta = cov(dETH, dBTC) / var(dBTC)
```

Clip beta to a stable range, for example:

```text
0.8 <= beta <= 1.4
```

Define residual:

```text
residual = log(ETH) - beta * log(BTC)
```

Compute residual z-score:

```text
z = (residual - rolling_mean) / rolling_std
```

Default windows:

- Beta window: 7 days.
- Z-score window: 3 days.
- Robustness checks: 14-day beta and 2-day z-score window.

## Entry Logic

Use extreme plus hook confirmation.

Alert:

- If `z >= +2.4`, ETH is rich versus BTC.
- If `z <= -2.4`, ETH is cheap versus BTC.

Entry:

- Do not enter immediately.
- Wait for the residual to start moving back toward mean by about `0.25` z-units.
- If `z > 0`: short ETH, long BTC.
- If `z < 0`: long ETH, short BTC.

This avoids catching the first move of a liquidation/trend impulse.

## Filters

Use only three strategy filters:

1. Fee/spread-volatility filter: skip unless expected gross spread reversion is at least about `0.5%`.
2. Correlation filter: 3-day BTC/ETH return correlation must be above `0.70`.
3. Market shock filter: skip new trades if BTC or ETH moved more than `1.5%` in 15 minutes or `3.0%` in 1 hour.

Fee-aware rule:

Because round-trip fee is about `0.10%` before spread/slippage, statistical z-score alone is not enough. The residual move from entry to exit must be economically large enough, not merely statistically large.

Execution guards such as stale quotes, failed-leg flattening, and manual kill switch are still required, but they are not extra alpha filters.

## Position Construction

Use one pair position at a time.

If gross exposure is `G`:

```text
ETH notional = G / (1 + abs(beta))
BTC notional = abs(beta) * G / (1 + abs(beta))
```

Direction:

- `z > 0`: ETH rich, short ETH and long BTC.
- `z < 0`: ETH cheap, long ETH and short BTC.

Starting gross exposure:

- Dry-run: no real orders.
- First paper orders: tiny size only.
- Forward test: about `0.75x` to `1.0x` gross exposure if safe.
- Competition: start around `0.5x` to `0.75x` until WooLive execution is verified; do not exceed `1.0x`.

## Exit Logic

Main exit:

- Close pair when `abs(z) <= 0.5`.

Risk exits:

- Close if pair PnL reaches `-0.35%` of account equity, with `-0.25%` and `-0.50%` checked in backtest.
- Close if residual expands too far, for example `abs(z) >= 3.4` and still moving against us.
- Time stop after `8h` if the trade is not profitable and z has not moved meaningfully toward zero.
- Require `abs(z) < 1.0` before re-entry after a time stop.

Competition profit lock:

- If cumulative return reaches about `+1%`, reduce size.
- If cumulative return reaches about `+1.5%`, stop opening normal trades unless signal quality is exceptional.

This is rational for a short Sharpe-ratio contest.

## Risk Controls

Trade-level:

- Max one pair position.
- State machine: `FLAT`, `ALERT`, `ENTERING`, `OPEN`, `EXITING`, `HALTED`.
- Immediate flatten if one leg fails or state mismatches ProfitView positions.
- No repeated entries without full residual reset.

Daily:

- Stop trading for the day if daily PnL falls below about `-0.75%`.

Cumulative:

- Reduce size around `-2%` drawdown.
- Halt around `-4%` drawdown.
- Do not go anywhere near the competition's 20% max drawdown limit.

Operational:

- Manual pause/resume/flatten webhooks.
- Heartbeat logs.
- Avoid API spam.
- Funding is reviewed manually before real paper/live runs; it is not part of the MVP signal.
- Never assume stopping the script closes positions.
- Expected competition activity is `2-8` round trips. If the bot trades much more often, it is probably overtrading.

## Current Evidence

Trigger frequency is acceptable on the six-month Binance BTC/ETH futures proxy: the default-ish setup produced trades in every rolling two-week window tested.

Performance quality is not proven yet. The best validation runs were positive after fees and slippage, but training-period results were negative across the tested grids. Therefore the strategy is implemented and ready for dry-run plus WooPaper plumbing tests, but not cleared for real competition sizing until forward paper results confirm it.

## Why This Should Work

- Lower broad-market beta than directional crypto trading.
- Larger target moves than 1-minute candle noise.
- Lower turnover, less fee leakage.
- BTC and ETH are traded as a coherent pair, not as a signal plus a confirmation.
- Risk is managed at the pair level.
- Profit lock protects positive competition performance.

## Presentation Angle

AlphaSharp does not chase crypto direction. It trades temporary BTC/ETH relative dislocations with strict fee, regime, and drawdown controls. The strategy is designed for risk-adjusted performance, not leaderboard gambling.

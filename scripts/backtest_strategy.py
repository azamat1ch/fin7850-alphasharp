#!/usr/bin/env python3
"""
Backtest AlphaSharp BTC/ETH residual mean reversion.

The script uses Binance USD-M futures 15m candles as a long-history proxy and
models pair entries/exits, fees, slippage, stops, and train/validation splits.
It intentionally keeps the strategy grid small and aligned with docs/plan.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests


BASE_URL = "https://fapi.binance.com"
INTERVAL_MS = 15 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000
FEE_RATE = 0.0005


@dataclass(frozen=True)
class Candle:
    ts: int
    close: float


@dataclass(frozen=True)
class Point:
    ts: int
    btc: float
    eth: float
    beta: float
    z: float
    resid_sigma: float
    corr: float
    shock: bool


@dataclass(frozen=True)
class Params:
    beta_days: int
    z_days: int
    entry_z: float
    exit_z: float
    gross: float
    stop_loss: float
    hook: float = 0.25
    min_expected_reversion: float = 0.005
    min_corr: float = 0.70
    beta_min: float = 0.8
    beta_max: float = 1.4
    shock_15m: float = 0.015
    shock_1h: float = 0.030
    slippage_rate: float = 0.0001
    beta_method: str = "returns"


@dataclass(frozen=True)
class Trade:
    entry_ts: int
    exit_ts: int
    direction: int
    entry_z: float
    exit_z: float
    entry_btc: float
    entry_eth: float
    exit_btc: float
    exit_eth: float
    gross: float
    beta: float
    bars: int
    reason: str
    pnl: float
    gross_pnl: float
    costs: float


def utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def parse_utc(value: str) -> int:
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def corr(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3 or len(xs) != len(ys):
        return 0.0
    mx = mean(xs)
    my = mean(ys)
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0 or vy <= 0:
        return 0.0
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy)


def hedge_beta(xs: list[float], ys: list[float], lo: float, hi: float) -> float:
    mx = mean(xs)
    my = mean(ys)
    var = sum((x - mx) ** 2 for x in xs)
    if var <= 0:
        return 1.0
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return min(hi, max(lo, cov / var))


def get_server_time() -> int:
    response = requests.get(f"{BASE_URL}/fapi/v1/time", timeout=15)
    response.raise_for_status()
    return int(response.json()["serverTime"])


def fetch_binance_klines(symbol: str, start_ms: int, end_ms: int) -> list[Candle]:
    candles: list[Candle] = []
    cursor = start_ms
    while cursor < end_ms:
        response = requests.get(
            f"{BASE_URL}/fapi/v1/klines",
            params={
                "symbol": symbol,
                "interval": "15m",
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1500,
            },
            timeout=30,
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            break
        candles.extend(Candle(ts=int(row[0]), close=float(row[4])) for row in rows)
        next_cursor = int(rows[-1][0]) + INTERVAL_MS
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        time.sleep(0.08)
    dedup = {c.ts: c for c in candles}
    return [dedup[ts] for ts in sorted(dedup)]


def load_or_fetch(symbol: str, start_ms: int, end_ms: int, cache_dir: Path) -> list[Candle]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"binance_{symbol}_15m_{start_ms}_{end_ms}.csv"
    if path.exists():
        with path.open() as f:
            return [Candle(ts=int(r["ts"]), close=float(r["close"])) for r in csv.DictReader(f)]
    candles = fetch_binance_klines(symbol, start_ms, end_ms)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ts", "close"])
        writer.writeheader()
        for c in candles:
            writer.writerow({"ts": c.ts, "close": c.close})
    return candles


def align(btc: Iterable[Candle], eth: Iterable[Candle]) -> list[tuple[int, float, float]]:
    btc_by_ts = {c.ts: c.close for c in btc}
    eth_by_ts = {c.ts: c.close for c in eth}
    timestamps = sorted(set(btc_by_ts) & set(eth_by_ts))
    return [(ts, btc_by_ts[ts], eth_by_ts[ts]) for ts in timestamps]


def build_points(rows: list[tuple[int, float, float]], params: Params) -> list[Point]:
    beta_n = params.beta_days * 24 * 4
    z_n = params.z_days * 24 * 4
    corr_n = 3 * 24 * 4
    log_btc = [math.log(r[1]) for r in rows]
    log_eth = [math.log(r[2]) for r in rows]
    ret_btc = [0.0] + [log_btc[i] - log_btc[i - 1] for i in range(1, len(rows))]
    ret_eth = [0.0] + [log_eth[i] - log_eth[i - 1] for i in range(1, len(rows))]

    raw: list[tuple[int, float, float, float, float, float, bool]] = []
    warmup = max(beta_n, z_n, corr_n)
    for i in range(warmup, len(rows)):
        if params.beta_method == "levels":
            b = hedge_beta(
                log_btc[i - beta_n + 1 : i + 1],
                log_eth[i - beta_n + 1 : i + 1],
                params.beta_min,
                params.beta_max,
            )
        else:
            b = hedge_beta(
                ret_btc[i - beta_n + 1 : i + 1],
                ret_eth[i - beta_n + 1 : i + 1],
                params.beta_min,
                params.beta_max,
            )
        residual = log_eth[i] - b * log_btc[i]
        c = corr(ret_btc[i - corr_n + 1 : i + 1], ret_eth[i - corr_n + 1 : i + 1])
        btc_15m = abs(ret_btc[i])
        eth_15m = abs(ret_eth[i])
        btc_1h = abs(log_btc[i] - log_btc[i - 4])
        eth_1h = abs(log_eth[i] - log_eth[i - 4])
        shock = max(btc_15m, eth_15m) > params.shock_15m or max(btc_1h, eth_1h) > params.shock_1h
        raw.append((rows[i][0], rows[i][1], rows[i][2], b, residual, c, shock))

    residuals = [r[4] for r in raw]
    points: list[Point] = []
    for i in range(z_n, len(raw)):
        window = residuals[i - z_n + 1 : i + 1]
        sigma = std(window)
        if sigma <= 0:
            continue
        z = (residuals[i] - mean(window)) / sigma
        ts, btc, eth, b, _residual, c, shock = raw[i]
        points.append(Point(ts=ts, btc=btc, eth=eth, beta=b, z=z, resid_sigma=sigma, corr=c, shock=shock))
    return points


def pair_gross_pnl(entry: Point, point: Point, direction: int, gross: float) -> float:
    eth_notional = gross / (1 + abs(entry.beta))
    btc_notional = abs(entry.beta) * gross / (1 + abs(entry.beta))
    btc_ret = point.btc / entry.btc - 1
    eth_ret = point.eth / entry.eth - 1
    if direction > 0:
        return btc_notional * btc_ret - eth_notional * eth_ret
    return eth_notional * eth_ret - btc_notional * btc_ret


def pair_net_pnl(entry: Point, point: Point, direction: int, params: Params) -> tuple[float, float, float]:
    gross_pnl = pair_gross_pnl(entry, point, direction, params.gross)
    costs = 2 * (FEE_RATE + params.slippage_rate) * params.gross
    return gross_pnl - costs, gross_pnl, costs


def filters_ok(point: Point, params: Params) -> bool:
    expected_reversion = max(0.0, (abs(point.z) - params.exit_z) * point.resid_sigma)
    return (
        expected_reversion >= params.min_expected_reversion
        and point.corr >= params.min_corr
        and not point.shock
    )


def simulate(points: list[Point], params: Params, start_ts: int | None = None, end_ts: int | None = None) -> list[Trade]:
    active_points = [p for p in points if (start_ts is None or p.ts >= start_ts) and (end_ts is None or p.ts < end_ts)]
    state = "FLAT"
    direction = 0
    alert_peak = 0.0
    entry: Point | None = None
    entry_index = 0
    previous_abs_z = 0.0
    locked_until_reset = False
    trades: list[Trade] = []

    for i, point in enumerate(active_points):
        if locked_until_reset:
            if abs(point.z) < 1.0:
                locked_until_reset = False
            else:
                continue

        if state == "FLAT":
            if abs(point.z) >= params.entry_z:
                direction = 1 if point.z > 0 else -1
                alert_peak = abs(point.z)
                state = "ALERT"
            continue

        if state == "ALERT":
            same_side = point.z * direction > 0
            if not same_side or abs(point.z) < 1.0:
                state = "FLAT"
                direction = 0
                alert_peak = 0.0
                continue
            alert_peak = max(alert_peak, abs(point.z))
            hook_confirmed = abs(point.z) <= alert_peak - params.hook and abs(point.z) > params.exit_z
            if hook_confirmed:
                if filters_ok(point, params):
                    entry = point
                    entry_index = i
                    previous_abs_z = abs(point.z)
                    state = "OPEN"
                else:
                    state = "FLAT"
                    direction = 0
                    alert_peak = 0.0
            continue

        if state == "OPEN":
            assert entry is not None
            bars = i - entry_index
            net_pnl, gross_pnl, costs = pair_net_pnl(entry, point, direction, params)
            reason = ""
            if abs(point.z) <= params.exit_z:
                reason = "mean_reversion"
            elif net_pnl <= params.stop_loss:
                reason = "stop_loss"
            elif abs(point.z) >= 3.4 and abs(point.z) > previous_abs_z:
                reason = "z_stop"
            elif bars >= 32 and net_pnl <= 0 and abs(point.z) > max(params.exit_z, abs(entry.z) - 0.25):
                reason = "time_stop"

            if reason:
                trades.append(
                    Trade(
                        entry_ts=entry.ts,
                        exit_ts=point.ts,
                        direction=direction,
                        entry_z=entry.z,
                        exit_z=point.z,
                        entry_btc=entry.btc,
                        entry_eth=entry.eth,
                        exit_btc=point.btc,
                        exit_eth=point.eth,
                        gross=params.gross,
                        beta=entry.beta,
                        bars=bars,
                        reason=reason,
                        pnl=net_pnl,
                        gross_pnl=gross_pnl,
                        costs=costs,
                    )
                )
                locked_until_reset = reason == "time_stop"
                state = "FLAT"
                direction = 0
                alert_peak = 0.0
                entry = None
                entry_index = 0
                previous_abs_z = 0.0
            else:
                previous_abs_z = abs(point.z)

    return trades


def sharpe_from_trades(trades: list[Trade], start_ts: int, end_ts: int) -> float:
    days = max((end_ts - start_ts) / DAY_MS, 1)
    if not trades:
        return 0.0
    daily: dict[int, float] = {}
    for trade in trades:
        key = int((trade.exit_ts - start_ts) // DAY_MS)
        daily[key] = daily.get(key, 0.0) + trade.pnl
    returns = [daily.get(i, 0.0) for i in range(math.ceil(days))]
    if len(returns) < 2:
        return 0.0
    sigma = std(returns)
    if sigma <= 0:
        return 0.0
    return mean(returns) / sigma * math.sqrt(365)


def max_drawdown(trades: list[Trade]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for trade in sorted(trades, key=lambda t: t.exit_ts):
        equity += trade.pnl
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def profit_factor(trades: list[Trade]) -> float:
    wins = sum(t.pnl for t in trades if t.pnl > 0)
    losses = -sum(t.pnl for t in trades if t.pnl < 0)
    if losses <= 0:
        return 999.0 if wins > 0 else 0.0
    return wins / losses


def summarize(trades: list[Trade], start_ts: int, end_ts: int) -> dict[str, float | int | str]:
    pnls = [t.pnl for t in trades]
    gross_pnls = [t.gross_pnl for t in trades]
    costs = [t.costs for t in trades]
    reasons: dict[str, int] = {}
    for t in trades:
        reasons[t.reason] = reasons.get(t.reason, 0) + 1
    return {
        "trades": len(trades),
        "net_return_pct": round(100 * sum(pnls), 3),
        "gross_return_pct": round(100 * sum(gross_pnls), 3),
        "cost_pct": round(100 * sum(costs), 3),
        "sharpe": round(sharpe_from_trades(trades, start_ts, end_ts), 3),
        "max_drawdown_pct": round(100 * max_drawdown(trades), 3),
        "profit_factor": round(profit_factor(trades), 3),
        "win_rate_pct": round(100 * sum(1 for p in pnls if p > 0) / len(pnls), 1) if pnls else 0.0,
        "avg_win_pct": round(100 * mean([p for p in pnls if p > 0]), 3) if any(p > 0 for p in pnls) else 0.0,
        "avg_loss_pct": round(100 * mean([p for p in pnls if p < 0]), 3) if any(p < 0 for p in pnls) else 0.0,
        "avg_hold_hours": round(mean([t.bars * 0.25 for t in trades]), 2) if trades else 0.0,
        "exit_reasons": json.dumps(reasons, sort_keys=True),
    }


def write_trades(path: Path, trades: list[Trade]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        fieldnames = list(asdict(trades[0]).keys()) if trades else list(Trade.__dataclass_fields__.keys())
        writer = csv.DictWriter(f, fieldnames=["entry_utc", "exit_utc"] + fieldnames)
        writer.writeheader()
        for trade in trades:
            row = asdict(trade)
            writer.writerow({"entry_utc": utc(trade.entry_ts), "exit_utc": utc(trade.exit_ts), **row})


def param_grid(quality_grid: bool = False) -> list[Params]:
    out: list[Params] = []
    entry_values = [2.2, 2.4, 2.6]
    min_expected_values = [0.005]
    beta_methods = ["returns"]
    if quality_grid:
        entry_values = [2.4, 2.6, 2.8, 3.0]
        min_expected_values = [0.005, 0.0075, 0.010, 0.015]
        beta_methods = ["returns", "levels"]
    for beta_days in [7, 14]:
        for z_days in [2, 3]:
            for entry_z in entry_values:
                for exit_z in [0.3, 0.5, 0.7]:
                    for gross in [0.75, 1.0]:
                        for stop_loss in [-0.0025, -0.0035, -0.0050]:
                            for min_expected in min_expected_values:
                                for beta_method in beta_methods:
                                    out.append(
                                        Params(
                                            beta_days=beta_days,
                                            z_days=z_days,
                                            entry_z=entry_z,
                                            exit_z=exit_z,
                                            gross=gross,
                                            stop_loss=stop_loss,
                                            min_expected_reversion=min_expected,
                                            beta_method=beta_method,
                                        )
                                    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--cache-dir", type=Path, default=Path("data"))
    parser.add_argument("--report", type=Path, default=None, help="optional concise text report path")
    parser.add_argument("--trades", type=Path, default=None, help="optional CSV path for best validation trades")
    parser.add_argument("--slippage-bps", type=float, default=1.0)
    parser.add_argument("--quality-grid", action="store_true", help="test stricter z and fee/spread thresholds")
    args = parser.parse_args()

    end_ts = get_server_time()
    start_ts = end_ts - args.days * DAY_MS
    btc = load_or_fetch("BTCUSDT", start_ts, end_ts, args.cache_dir)
    eth = load_or_fetch("ETHUSDT", start_ts, end_ts, args.cache_dir)
    rows = align(btc, eth)
    if len(rows) < 3000:
        raise SystemExit(f"Not enough aligned candles: {len(rows)}")

    # Use final ~43 days as validation, matching Apr 1-May 13 style split for a 180d run.
    validation_days = 43
    split_ts = rows[-1][0] - validation_days * DAY_MS
    all_results: list[dict[str, object]] = []
    best_key: tuple[float, float, float, int] | None = None
    best_params: Params | None = None
    best_val_trades: list[Trade] = []
    points_cache: dict[tuple[int, int], list[Point]] = {}

    for base_params in param_grid(quality_grid=args.quality_grid):
        params = Params(**{**asdict(base_params), "slippage_rate": args.slippage_bps / 10000})
        cache_key = (params.beta_days, params.z_days, params.beta_method)
        if cache_key not in points_cache:
            points_cache[cache_key] = build_points(rows, params)
        points = points_cache[cache_key]
        train = simulate(points, params, start_ts=points[0].ts, end_ts=split_ts)
        val = simulate(points, params, start_ts=split_ts, end_ts=points[-1].ts + INTERVAL_MS)
        train_summary = summarize(train, points[0].ts, split_ts)
        val_summary = summarize(val, split_ts, points[-1].ts + INTERVAL_MS)
        row = {
            **asdict(params),
            "train": train_summary,
            "validation": val_summary,
        }
        all_results.append(row)

        # Prefer validation quality, but require at least one validation trade.
        if val:
            key = (
                float(val_summary["net_return_pct"]),
                float(val_summary["sharpe"]),
                float(val_summary["max_drawdown_pct"]),
                -int(val_summary["trades"]),
            )
            if best_key is None or key > best_key:
                best_key = key
                best_params = params
                best_val_trades = val

    if best_params is None:
        raise SystemExit("No validation trades found")

    sorted_results = sorted(
        all_results,
        key=lambda r: (
            float(r["validation"]["net_return_pct"]),
            float(r["validation"]["sharpe"]),
            float(r["validation"]["max_drawdown_pct"]),
        ),
        reverse=True,
    )
    lines = [
        "Backtest Summary",
        "================",
        "",
        "Data proxy: Binance USD-M futures 15m BTCUSDT/ETHUSDT",
        f"Raw aligned candles: {len(rows)}",
        f"Raw range UTC: {utc(rows[0][0])} to {utc(rows[-1][0])}",
        f"Train range UTC: derived warmup to {utc(split_ts)}",
        f"Validation range UTC: {utc(split_ts)} to {utc(rows[-1][0])}",
        f"Fee: {FEE_RATE * 100:.3f}% per entry/exit notional",
        f"Slippage assumption: {args.slippage_bps:.1f} bps per entry/exit gross notional",
        f"Quality grid: {args.quality_grid}",
        "",
        "Best Validation Params",
        "----------------------",
        "",
        json.dumps(asdict(best_params), indent=2, sort_keys=True),
        "",
        "Top Validation Results",
        "----------------------",
        "",
        "| rank | beta | zwin | entry | exit | gross | stop | val net | val Sharpe | val MDD | val trades | train net | train Sharpe | train trades |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for rank, result in enumerate(sorted_results[:20], start=1):
        train = result["train"]
        val = result["validation"]
        lines.append(
            "| {rank} | {beta_method}/{beta_days}d | {z_days}d | {entry_z:.1f} | {exit_z:.1f} | {gross:.2f} | {stop:.2f}% | {val_net:.3f}% | {val_sharpe:.2f} | {val_mdd:.3f}% | {val_trades} | {train_net:.3f}% | {train_sharpe:.2f} | {train_trades} |".format(
                rank=rank,
                beta_method=result["beta_method"],
                beta_days=result["beta_days"],
                z_days=result["z_days"],
                entry_z=result["entry_z"],
                exit_z=result["exit_z"],
                gross=result["gross"],
                stop=100 * result["stop_loss"],
                val_net=val["net_return_pct"],
                val_sharpe=val["sharpe"],
                val_mdd=val["max_drawdown_pct"],
                val_trades=val["trades"],
                train_net=train["net_return_pct"],
                train_sharpe=train["sharpe"],
                train_trades=train["trades"],
            )
        )
    lines += ["", "Full grid JSON intentionally omitted. Re-run or inspect the script if needed.", ""]
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text("\n".join(lines))
    if args.trades:
        write_trades(args.trades, best_val_trades)
    if args.report:
        print(args.report)
    else:
        print("\n".join(lines[:30]))
    if args.trades:
        print(args.trades)


if __name__ == "__main__":
    main()

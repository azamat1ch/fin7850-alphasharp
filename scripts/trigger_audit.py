#!/usr/bin/env python3
"""
Audit whether the BTC/ETH residual strategy triggers often enough.

Uses Binance USD-M futures 15m candles as a long-history proxy. WOO/ProfitView
data should still be used for final recent validation, but WOO public klines are
limited enough that Binance is useful for this six-month trigger-frequency test.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import requests


BASE_URL = "https://fapi.binance.com"
INTERVAL_MS = 15 * 60 * 1000
FEE_PER_TRADE = 0.0005


@dataclass
class Candle:
    ts: int
    close: float


@dataclass
class Point:
    ts: int
    btc: float
    eth: float
    beta: float
    z: float
    resid_sigma: float
    corr: float
    shock: bool


@dataclass
class Trade:
    entry_ts: int
    exit_ts: int
    direction: int
    entry_z: float
    exit_z: float
    reason: str
    pnl: float
    bars: int


def utc(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def get_server_time() -> int:
    response = requests.get(f"{BASE_URL}/fapi/v1/time", timeout=15)
    response.raise_for_status()
    return int(response.json()["serverTime"])


def fetch_binance_klines(symbol: str, start_ms: int, end_ms: int) -> list[Candle]:
    out: list[Candle] = []
    cursor = start_ms
    while cursor < end_ms:
        params = {
            "symbol": symbol,
            "interval": "15m",
            "startTime": cursor,
            "endTime": end_ms,
            "limit": 1500,
        }
        response = requests.get(f"{BASE_URL}/fapi/v1/klines", params=params, timeout=30)
        response.raise_for_status()
        rows = response.json()
        if not rows:
            break
        for row in rows:
            out.append(Candle(ts=int(row[0]), close=float(row[4])))
        next_cursor = int(rows[-1][0]) + INTERVAL_MS
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        time.sleep(0.08)
    dedup = {c.ts: c for c in out}
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
    ts_values = sorted(set(btc_by_ts) & set(eth_by_ts))
    return [(ts, btc_by_ts[ts], eth_by_ts[ts]) for ts in ts_values]


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


def beta(ret_btc: list[float], ret_eth: list[float], lo: float = 0.8, hi: float = 1.4) -> float:
    mx = mean(ret_btc)
    my = mean(ret_eth)
    var = sum((x - mx) ** 2 for x in ret_btc)
    if var <= 0:
        return 1.0
    cov = sum((x - mx) * (y - my) for x, y in zip(ret_btc, ret_eth))
    return min(hi, max(lo, cov / var))


def build_points(
    rows: list[tuple[int, float, float]],
    beta_days: int,
    z_days: int,
) -> list[Point]:
    beta_n = beta_days * 24 * 4
    z_n = z_days * 24 * 4
    corr_n = 3 * 24 * 4
    log_btc = [math.log(r[1]) for r in rows]
    log_eth = [math.log(r[2]) for r in rows]
    ret_btc = [0.0] + [log_btc[i] - log_btc[i - 1] for i in range(1, len(rows))]
    ret_eth = [0.0] + [log_eth[i] - log_eth[i - 1] for i in range(1, len(rows))]

    raw: list[tuple[int, float, float, float, float, bool]] = []
    for i in range(max(beta_n, z_n, corr_n), len(rows)):
        b = beta(ret_btc[i - beta_n + 1 : i + 1], ret_eth[i - beta_n + 1 : i + 1])
        residual = log_eth[i] - b * log_btc[i]
        c = corr(ret_btc[i - corr_n + 1 : i + 1], ret_eth[i - corr_n + 1 : i + 1])

        btc_15m = abs(ret_btc[i])
        eth_15m = abs(ret_eth[i])
        btc_1h = abs(log_btc[i] - log_btc[i - 4])
        eth_1h = abs(log_eth[i] - log_eth[i - 4])
        shock = max(btc_15m, eth_15m) > 0.015 or max(btc_1h, eth_1h) > 0.03
        raw.append((rows[i][0], log_btc[i], log_eth[i], b, residual, c, shock))

    points: list[Point] = []
    residuals = [r[4] for r in raw]
    for j in range(z_n, len(raw)):
        window = residuals[j - z_n + 1 : j + 1]
        sigma = std(window)
        if sigma <= 0:
            continue
        z = (residuals[j] - mean(window)) / sigma
        ts, lb, le, b, _resid, c, shock = raw[j]
        points.append(
            Point(ts=ts, btc=math.exp(lb), eth=math.exp(le), beta=b, z=z, resid_sigma=sigma, corr=c, shock=shock)
        )
    return points


def pair_pnl(entry: Point, point: Point, direction: int, gross: float = 1.0, include_close_fee: bool = True) -> float:
    eth_notional = gross / (1 + abs(entry.beta))
    btc_notional = abs(entry.beta) * gross / (1 + abs(entry.beta))
    btc_ret = point.btc / entry.btc - 1
    eth_ret = point.eth / entry.eth - 1
    if direction > 0:
        # z > 0: short ETH, long BTC
        pnl = btc_notional * btc_ret - eth_notional * eth_ret
    else:
        # z < 0: long ETH, short BTC
        pnl = eth_notional * eth_ret - btc_notional * btc_ret
    fee = FEE_PER_TRADE * gross
    if include_close_fee:
        fee *= 2
    return pnl - fee


def simulate(
    points: list[Point],
    entry_z: float,
    exit_z: float,
    hook: float,
    stop_loss: float,
    require_filters: bool,
) -> tuple[list[Trade], dict[str, int]]:
    state = "FLAT"
    direction = 0
    alert_peak = 0.0
    entry_point: Point | None = None
    entry_index = 0
    previous_abs_z = 0.0
    counters = {
        "alerts": 0,
        "hook_confirms": 0,
        "skip_fee": 0,
        "skip_corr": 0,
        "skip_shock": 0,
    }
    trades: list[Trade] = []

    def filters_ok(p: Point) -> bool:
        ok = True
        expected_reversion = max(0.0, (abs(p.z) - exit_z) * p.resid_sigma)
        if expected_reversion < 0.005:
            counters["skip_fee"] += 1
            ok = False
        if p.corr < 0.70:
            counters["skip_corr"] += 1
            ok = False
        if p.shock:
            counters["skip_shock"] += 1
            ok = False
        return ok

    for i, p in enumerate(points):
        if state == "FLAT":
            if abs(p.z) >= entry_z:
                direction = 1 if p.z > 0 else -1
                alert_peak = abs(p.z)
                state = "ALERT"
                counters["alerts"] += 1
            continue

        if state == "ALERT":
            same_side = p.z * direction > 0
            if not same_side or abs(p.z) < 1.0:
                state = "FLAT"
                direction = 0
                alert_peak = 0.0
                continue
            alert_peak = max(alert_peak, abs(p.z))
            if abs(p.z) <= alert_peak - hook and abs(p.z) > exit_z:
                counters["hook_confirms"] += 1
                if (not require_filters) or filters_ok(p):
                    entry_point = p
                    entry_index = i
                    previous_abs_z = abs(p.z)
                    state = "OPEN"
                else:
                    state = "FLAT"
                    direction = 0
                    alert_peak = 0.0
            continue

        if state == "OPEN":
            assert entry_point is not None
            bars = i - entry_index
            pnl = pair_pnl(entry_point, p, direction)
            reason = ""
            if abs(p.z) <= exit_z:
                reason = "mean_reversion"
            elif pnl <= stop_loss:
                reason = "stop_loss"
            elif abs(p.z) >= 3.4 and abs(p.z) > previous_abs_z:
                reason = "z_stop"
            elif bars >= 32 and pnl <= 0 and abs(p.z) > max(exit_z, abs(entry_point.z) - 0.25):
                reason = "time_stop"

            if reason:
                trades.append(
                    Trade(
                        entry_ts=entry_point.ts,
                        exit_ts=p.ts,
                        direction=direction,
                        entry_z=entry_point.z,
                        exit_z=p.z,
                        reason=reason,
                        pnl=pnl,
                        bars=bars,
                    )
                )
                state = "FLAT"
                direction = 0
                alert_peak = 0.0
                entry_point = None
                entry_index = 0
                previous_abs_z = 0.0
            else:
                previous_abs_z = abs(p.z)

    return trades, counters


def rolling_14d_counts(trades: list[Trade], start_ts: int, end_ts: int) -> list[int]:
    window_ms = 14 * 24 * 60 * 60 * 1000
    step_ms = 24 * 60 * 60 * 1000
    entries = [t.entry_ts for t in trades]
    counts = []
    cursor = start_ts
    while cursor + window_ms <= end_ts:
        counts.append(sum(1 for ts in entries if cursor <= ts < cursor + window_ms))
        cursor += step_ms
    return counts


def max_entry_gap_days(trades: list[Trade], start_ts: int, end_ts: int) -> float:
    entries = [start_ts] + [t.entry_ts for t in trades] + [end_ts]
    gaps = [(b - a) / (24 * 60 * 60 * 1000) for a, b in zip(entries, entries[1:])]
    return max(gaps) if gaps else 0.0


def summarize(trades: list[Trade], counters: dict[str, int], start_ts: int, end_ts: int) -> dict[str, object]:
    counts = rolling_14d_counts(trades, start_ts, end_ts)
    pnls = [t.pnl for t in trades]
    reasons: dict[str, int] = {}
    for t in trades:
        reasons[t.reason] = reasons.get(t.reason, 0) + 1
    return {
        "alerts": counters["alerts"],
        "hook_confirms": counters["hook_confirms"],
        "entries": len(trades),
        "avg_pnl_pct": round(100 * mean(pnls), 3) if pnls else 0.0,
        "win_rate_pct": round(100 * sum(1 for p in pnls if p > 0) / len(pnls), 1) if pnls else 0.0,
        "exit_reasons": reasons,
        "min_entries_per_14d": min(counts) if counts else 0,
        "median_entries_per_14d": statistics.median(counts) if counts else 0,
        "zero_trade_14d_windows": sum(1 for c in counts if c == 0),
        "total_14d_windows": len(counts),
        "max_entry_gap_days": round(max_entry_gap_days(trades, start_ts, end_ts), 1),
        "skips": {k: v for k, v in counters.items() if k.startswith("skip_")},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--cache-dir", type=Path, default=Path("data"))
    parser.add_argument("--report", type=Path, default=None, help="optional concise text report path")
    args = parser.parse_args()

    end_ms = get_server_time()
    start_ms = end_ms - args.days * 24 * 60 * 60 * 1000
    btc = load_or_fetch("BTCUSDT", start_ms, end_ms, args.cache_dir)
    eth = load_or_fetch("ETHUSDT", start_ms, end_ms, args.cache_dir)
    rows = align(btc, eth)
    if len(rows) < 3000:
        raise SystemExit(f"Not enough aligned candles: {len(rows)}")

    scenarios = []
    for beta_days in [7, 14]:
        for z_days in [2, 3]:
            points = build_points(rows, beta_days=beta_days, z_days=z_days)
            if not points:
                continue
            for entry_z in [2.2, 2.4, 2.6]:
                trades, counters = simulate(
                    points,
                    entry_z=entry_z,
                    exit_z=0.5,
                    hook=0.25,
                    stop_loss=-0.0035,
                    require_filters=True,
                )
                scenarios.append(
                    {
                        "beta_days": beta_days,
                        "z_days": z_days,
                        "entry_z": entry_z,
                        "points_start": points[0].ts,
                        "points_end": points[-1].ts,
                        **summarize(trades, counters, points[0].ts, points[-1].ts),
                    }
                )

    lines = [
        "Trigger Audit",
        "=============",
        "",
        f"Data proxy: Binance USD-M futures 15m BTCUSDT/ETHUSDT",
        f"Requested lookback: {args.days} days",
        f"Raw aligned candles: {len(rows)}",
        f"Raw range UTC: {utc(rows[0][0])} to {utc(rows[-1][0])}",
        "",
        "Rules audited: hook `0.25`, exit `abs(z)<=0.5`, stop `-0.35%`, z-stop `3.4`, time stop `8h`, filters on.",
        "",
        "| beta | z window | entry z | alerts | hooks | entries | median / min entries per 14d | zero 14d windows | max gap days | avg pnl | win rate |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for s in scenarios:
        lines.append(
            "| {beta_days}d | {z_days}d | {entry_z:.1f} | {alerts} | {hook_confirms} | {entries} | {median_entries_per_14d} / {min_entries_per_14d} | {zero_trade_14d_windows}/{total_14d_windows} | {max_entry_gap_days} | {avg_pnl_pct:.3f}% | {win_rate_pct:.1f}% |".format(
                **s
            )
        )
    lines += ["", "Full JSON intentionally omitted. Re-run from the script if needed.", ""]
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text("\n".join(lines))
        print(args.report)
    else:
        print("\n".join(lines))


if __name__ == "__main__":
    main()

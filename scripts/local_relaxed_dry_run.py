#!/usr/bin/env python3
"""
Local relaxed dry-run replay.

This is a plumbing/state sanity check, not performance evidence. It replays
recent BTC/ETH 15m proxy candles with easy thresholds so entries/exits happen
quickly, similar to ProfitView RELAXED dry-run mode with orders disabled.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from pathlib import Path

from backtest_strategy import (
    DAY_MS,
    INTERVAL_MS,
    Params,
    align,
    build_points,
    get_server_time,
    load_or_fetch,
    simulate,
    summarize,
    utc,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--cache-dir", type=Path, default=Path("data"))
    parser.add_argument("--report", type=Path, default=None, help="optional concise text report path")
    args = parser.parse_args()

    end_ts = get_server_time()
    start_ts = end_ts - args.days * DAY_MS
    btc = load_or_fetch("BTCUSDT", start_ts, end_ts, args.cache_dir)
    eth = load_or_fetch("ETHUSDT", start_ts, end_ts, args.cache_dir)
    rows = align(btc, eth)

    params = Params(
        beta_days=7,
        z_days=2,
        entry_z=0.5,
        exit_z=0.2,
        gross=0.01,
        stop_loss=-0.01,
        min_expected_reversion=0.0,
        min_corr=0.0,
        shock_15m=99.0,
        shock_1h=99.0,
    )
    points = build_points(rows, params)
    if not points:
        raise SystemExit("Not enough candles for relaxed replay")
    trades = simulate(points, params, start_ts=points[0].ts, end_ts=points[-1].ts + INTERVAL_MS)
    summary = summarize(trades, points[0].ts, points[-1].ts + INTERVAL_MS)

    lines = [
        "Local Relaxed Dry Run",
        "=====================",
        "",
        "Purpose: mechanical dry-run replay with easy thresholds and no orders.",
        "This is not strategy-performance evidence.",
        "",
        f"Data proxy: Binance USD-M futures 15m BTCUSDT/ETHUSDT",
        f"Range UTC: {utc(rows[0][0])} to {utc(rows[-1][0])}",
        f"Signal-ready range UTC: {utc(points[0].ts)} to {utc(points[-1].ts)}",
        "",
        "Params",
        "------",
        "",
        str(asdict(params)).replace("'", '"'),
        "",
        "Summary",
        "-------",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key}: `{value}`")
    lines += [
        "",
        "First Events",
        "------------",
        "",
        "| # | entry UTC | exit UTC | side | entry z | exit z | reason | fake pnl | hold hours |",
        "| ---: | --- | --- | --- | ---: | ---: | --- | ---: | ---: |",
    ]
    for i, trade in enumerate(trades[:30], start=1):
        side = "short ETH / long BTC" if trade.direction > 0 else "long ETH / short BTC"
        lines.append(
            f"| {i} | {utc(trade.entry_ts)} | {utc(trade.exit_ts)} | {side} | {trade.entry_z:.2f} | {trade.exit_z:.2f} | {trade.reason} | {100 * trade.pnl:.4f}% | {trade.bars * 0.25:.2f} |"
        )
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text("\n".join(lines))
        print(args.report)
    else:
        print("\n".join(lines))


if __name__ == "__main__":
    main()

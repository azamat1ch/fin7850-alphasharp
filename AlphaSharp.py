"""
AlphaSharp ProfitView bot.

Default mode is safe: DRY_RUN=True and TEST_MODE="RELAXED".
Paste into ProfitView as AlphaSharp.py, select PERP_BTC_USDT and
PERP_ETH_USDT market streams, and run only after reading docs/plan.md.
"""

from profitview import Link, http

import math
import time


class Trading(Link):
    VENUE = "WooPaper"
    BTC = "PERP_BTC_USDT"
    ETH = "PERP_ETH_USDT"

    # Safety first. Turn orders on only after forced dry-run and tiny paper tests.
    DRY_RUN = True
    TEST_MODE = "RELAXED"  # RELAXED or REAL

    # Real strategy defaults.
    BETA_DAYS = 7
    Z_DAYS = 3
    ENTRY_Z = 2.4
    EXIT_Z = 0.5
    HOOK_Z = 0.25
    BETA_MIN = 0.8
    BETA_MAX = 1.4
    MIN_EXPECTED_REVERSION = 0.005
    MIN_CORR = 0.70
    SHOCK_15M = 0.015
    SHOCK_1H = 0.030
    GROSS_EXPOSURE = 0.75
    MAX_GROSS_EXPOSURE = 1.0
    PAIR_STOP = -0.0035
    EMERGENCY_Z = 3.4
    TIME_STOP_SECONDS = 8 * 60 * 60
    DAILY_STOP = -0.0075
    DRAWDOWN_REDUCE = -0.02
    DRAWDOWN_HALT = -0.04
    PROFIT_REDUCE = 0.01
    PROFIT_HALT_NEW = 0.015

    # Relaxed dry-run defaults. These are only for plumbing/state testing.
    RELAXED_ENTRY_Z = 0.5
    RELAXED_EXIT_Z = 0.2
    RELAXED_BYPASS_FILTERS = True

    MIN_REFRESH_SECONDS = 60
    STALE_QUOTE_SECONDS = 20
    MIN_ORDER_NOTIONAL = 10.0

    def _ensure_state(self):
        if hasattr(self, "latest_quotes"):
            return
        self.state = "FLAT"
        self.paused = False
        self.halted = False
        self.direction = 0
        self.alert_peak = 0.0
        self.entry = None
        self.last_abs_z = None
        self.locked_until_reset = False
        self.last_refresh = 0
        self.latest_quotes = {}
        self.last_signal = None
        self.start_equity = None
        self.day_start_equity = None
        self.peak_equity = None
        self.fake_realized_pnl = 0.0
        self._log("boot", mode=self.TEST_MODE, dry_run=self.DRY_RUN)

    def quote_update(self, src, sym, data):
        self._ensure_state()
        if sym not in (self.BTC, self.ETH):
            return
        price = self._quote_mid(data)
        if price:
            self.latest_quotes[sym] = {"price": price, "ts": time.time()}
        self._tick("quote")

    def trade_update(self, src, sym, data):
        self._ensure_state()
        if sym not in (self.BTC, self.ETH):
            return
        price = self._trade_price(data)
        if price:
            self.latest_quotes[sym] = {"price": price, "ts": time.time()}
        self._tick("trade")

    def position_update(self, src, sym, data):
        self._ensure_state()
        if sym in (self.BTC, self.ETH) and self._src_ok(src, data):
            self._log("position_update", sym=sym, data=str(data)[:500])

    def order_update(self, src, sym, data):
        self._ensure_state()
        if sym in (self.BTC, self.ETH) and self._src_ok(src, data):
            self._log("order_update", sym=sym, data=str(data)[:500])

    def fill_update(self, src, sym, data):
        self._ensure_state()
        if sym in (self.BTC, self.ETH) and self._src_ok(src, data):
            self._log("fill_update", sym=sym, data=str(data)[:500])

    @http.route
    def get_status(self, data):
        self._ensure_state()
        return {
            "state": self.state,
            "paused": self.paused,
            "halted": self.halted,
            "dry_run": self.DRY_RUN,
            "test_mode": self.TEST_MODE,
            "last_signal": self.last_signal,
            "entry": self.entry,
        }

    @http.route
    def post_pause(self, data):
        self._ensure_state()
        self.paused = True
        self._log("manual_pause")
        return self.get_status(data)

    @http.route
    def post_resume(self, data):
        self._ensure_state()
        self.paused = False
        self._log("manual_resume")
        return self.get_status(data)

    @http.route
    def post_flatten(self, data):
        self._ensure_state()
        self._log("manual_flatten_requested")
        self._exit_pair("manual_flatten")
        self.state = "FLAT"
        return self.get_status(data)

    @http.route
    def post_force_relaxed(self, data):
        self._ensure_state()
        self.TEST_MODE = "RELAXED"
        self.DRY_RUN = True
        self._log("force_relaxed_dry_run")
        return self.get_status(data)

    def _tick(self, event):
        self._ensure_state()
        now = time.time()
        if now - self.last_refresh < self.MIN_REFRESH_SECONDS:
            return
        self.last_refresh = now
        try:
            signal = self._compute_signal()
            if not signal:
                return
            self.last_signal = signal
            self._handle_signal(signal)
        except Exception as exc:
            self._log("error", event=event, error=repr(exc))

    def _handle_signal(self, signal):
        z = signal["z"]
        abs_z = abs(z)
        entry_z = self.RELAXED_ENTRY_Z if self.TEST_MODE == "RELAXED" else self.ENTRY_Z
        exit_z = self.RELAXED_EXIT_Z if self.TEST_MODE == "RELAXED" else self.EXIT_Z

        if self.paused or self.halted:
            self._log("skip_paused_or_halted", paused=self.paused, halted=self.halted)
            return

        equity = self._equity()
        if self.start_equity is None:
            self.start_equity = equity
            self.day_start_equity = equity
            self.peak_equity = equity
        if self._risk_halt(equity):
            return

        if self.locked_until_reset:
            if abs_z < 1.0:
                self.locked_until_reset = False
                self._log("reset_after_time_stop", z=z)
            else:
                self._log("skip_waiting_for_reset", z=z)
                return

        if self.state == "FLAT":
            if abs_z >= entry_z:
                self.direction = 1 if z > 0 else -1
                self.alert_peak = abs_z
                self.state = "ALERT"
                self._log("alert", z=z, direction=self.direction)
            else:
                self._log("skip_no_extreme", z=z)
            return

        if self.state == "ALERT":
            if z * self.direction <= 0 or abs_z < 1.0:
                self._log("alert_cancelled", z=z)
                self._reset_to_flat()
                return
            self.alert_peak = max(self.alert_peak, abs_z)
            if abs_z <= self.alert_peak - self.HOOK_Z and abs_z > exit_z:
                if self._filters_ok(signal):
                    self._enter_pair(signal)
                else:
                    self._reset_to_flat()
            else:
                self._log("wait_hook", z=z, peak=self.alert_peak)
            return

        if self.state == "OPEN":
            self._manage_open(signal)

    def _enter_pair(self, signal):
        self.state = "ENTERING"
        gross = min(self.GROSS_EXPOSURE, self.MAX_GROSS_EXPOSURE)
        equity = self._equity()
        btc_notional, eth_notional = self._leg_notionals(gross * equity, signal["beta"])

        if self.direction > 0:
            orders = [(self.ETH, "sell", eth_notional), (self.BTC, "buy", btc_notional)]
            name = "short_eth_long_btc"
        else:
            orders = [(self.ETH, "buy", eth_notional), (self.BTC, "sell", btc_notional)]
            name = "long_eth_short_btc"

        self.entry = {
            "ts": time.time(),
            "z": signal["z"],
            "beta": signal["beta"],
            "btc": signal["btc"],
            "eth": signal["eth"],
            "direction": self.direction,
            "gross_equity": gross,
            "equity": equity,
        }
        self.last_abs_z = abs(signal["z"])

        if self.DRY_RUN:
            self._log("WOULD_ENTER", name=name, z=signal["z"], gross=gross, btc_notional=btc_notional, eth_notional=eth_notional)
            self.state = "OPEN"
            return

        try:
            for sym, side, notional in orders:
                size = self._size_from_notional(sym, notional)
                if size <= 0:
                    raise ValueError("size <= 0")
                self._log("order_entry", sym=sym, side=side, size=size, notional=notional)
                self.create_market_order(self.VENUE, sym=sym, side=side, size=size)
            self.state = "OPEN"
        except Exception as exc:
            self._log("entry_failed_flattening", error=repr(exc))
            self._flatten_best_effort()
            self._reset_to_flat()

    def _manage_open(self, signal):
        if not self.entry:
            self._log("state_open_missing_entry")
            self._reset_to_flat()
            return
        exit_z = self.RELAXED_EXIT_Z if self.TEST_MODE == "RELAXED" else self.EXIT_Z
        net_pnl = self._pair_pnl(signal)
        abs_z = abs(signal["z"])
        reason = None
        if abs_z <= exit_z:
            reason = "mean_reversion"
        elif net_pnl <= self.PAIR_STOP:
            reason = "pair_stop"
        elif abs_z >= self.EMERGENCY_Z and self.last_abs_z is not None and abs_z > self.last_abs_z:
            reason = "z_stop"
        elif time.time() - self.entry["ts"] >= self.TIME_STOP_SECONDS and net_pnl <= 0 and abs_z > max(exit_z, abs(self.entry["z"]) - 0.25):
            reason = "time_stop"

        self._log("open_check", z=signal["z"], pnl=net_pnl, reason=reason)
        if reason:
            self._exit_pair(reason)
            if reason == "time_stop":
                self.locked_until_reset = True
        else:
            self.last_abs_z = abs_z

    def _exit_pair(self, reason):
        if not self.entry:
            return
        self.state = "EXITING"
        direction = self.entry["direction"]
        gross = self.entry["gross_equity"]
        equity = self._equity()
        btc_notional, eth_notional = self._leg_notionals(gross * equity, self.entry["beta"])

        if direction > 0:
            orders = [(self.ETH, "buy", eth_notional), (self.BTC, "sell", btc_notional)]
        else:
            orders = [(self.ETH, "sell", eth_notional), (self.BTC, "buy", btc_notional)]

        if self.DRY_RUN:
            pnl = self._pair_pnl(self.last_signal) if self.last_signal else 0.0
            self.fake_realized_pnl += pnl
            self._log("WOULD_EXIT", reason=reason, pnl=pnl)
            self._reset_to_flat()
            return

        try:
            for sym, side, notional in orders:
                size = self._size_from_notional(sym, notional)
                self._log("order_exit", sym=sym, side=side, size=size, reason=reason)
                self.create_market_order(self.VENUE, sym=sym, side=side, size=size)
        finally:
            self._reset_to_flat()

    def _filters_ok(self, signal):
        if self.TEST_MODE == "RELAXED" and self.RELAXED_BYPASS_FILTERS:
            self._log("filters_bypassed_relaxed")
            return True
        expected_reversion = max(0.0, (abs(signal["z"]) - self.EXIT_Z) * signal["resid_sigma"])
        if expected_reversion < self.MIN_EXPECTED_REVERSION:
            self._log("SKIP", reason="expected_move_too_small", expected=expected_reversion)
            return False
        if signal["corr"] < self.MIN_CORR:
            self._log("SKIP", reason="corr_low", corr=signal["corr"])
            return False
        if signal["shock"]:
            self._log("SKIP", reason="market_shock")
            return False
        if not self._quotes_fresh():
            self._log("SKIP", reason="stale_quotes")
            return False
        return True

    def _risk_halt(self, equity):
        if not equity:
            return False
        daily = equity / self.day_start_equity - 1 if self.day_start_equity else 0
        total = equity / self.start_equity - 1 if self.start_equity else 0
        self.peak_equity = max(self.peak_equity or equity, equity)
        drawdown = equity / self.peak_equity - 1 if self.peak_equity else 0
        if daily <= self.DAILY_STOP or drawdown <= self.DRAWDOWN_HALT:
            self.halted = True
            self._log("risk_halt", daily=daily, total=total, drawdown=drawdown)
            return True
        if total >= self.PROFIT_HALT_NEW and self.state == "FLAT":
            self._log("profit_lock_no_new_trades", total=total)
            return True
        return False

    def _compute_signal(self):
        btc_rows = self._fetch_candles(self.BTC, "15m")
        eth_rows = self._fetch_candles(self.ETH, "15m")
        rows = self._align_candles(btc_rows, eth_rows)
        min_bars = max(self.BETA_DAYS, self.Z_DAYS, 3) * 24 * 4 + self.Z_DAYS * 24 * 4 + 10
        if len(rows) < min_bars:
            self._log("not_enough_candles", candles=len(rows), needed=min_bars)
            return None
        beta_n = self.BETA_DAYS * 24 * 4
        z_n = self.Z_DAYS * 24 * 4
        corr_n = 3 * 24 * 4
        log_btc = [math.log(r["btc"]) for r in rows]
        log_eth = [math.log(r["eth"]) for r in rows]
        ret_btc = [0.0] + [log_btc[i] - log_btc[i - 1] for i in range(1, len(rows))]
        ret_eth = [0.0] + [log_eth[i] - log_eth[i - 1] for i in range(1, len(rows))]
        i = len(rows) - 1
        beta = self._beta(ret_btc[i - beta_n + 1 : i + 1], ret_eth[i - beta_n + 1 : i + 1])
        residuals = []
        start = i - z_n + 1
        for j in range(start, i + 1):
            residuals.append(log_eth[j] - beta * log_btc[j])
        resid_mean = self._mean(residuals)
        resid_sigma = self._std(residuals)
        if resid_sigma <= 0:
            return None
        z = (residuals[-1] - resid_mean) / resid_sigma
        c = self._corr(ret_btc[i - corr_n + 1 : i + 1], ret_eth[i - corr_n + 1 : i + 1])
        shock = max(abs(ret_btc[i]), abs(ret_eth[i])) > self.SHOCK_15M or max(abs(log_btc[i] - log_btc[i - 4]), abs(log_eth[i] - log_eth[i - 4])) > self.SHOCK_1H
        return {
            "ts": rows[-1]["ts"],
            "btc": rows[-1]["btc"],
            "eth": rows[-1]["eth"],
            "beta": beta,
            "z": z,
            "resid_sigma": resid_sigma,
            "corr": c,
            "shock": shock,
        }

    def _fetch_candles(self, sym, level):
        data = self.fetch_candles(self.VENUE, sym=sym, level=level)
        rows = data.get("data", data) if isinstance(data, dict) else data
        out = []
        for row in rows or []:
            if isinstance(row, dict):
                ts = row.get("timestamp") or row.get("start_timestamp") or row.get("time") or row.get("ts")
                close = row.get("close") or row.get("c")
            else:
                ts = row[0]
                close = row[4]
            if ts is not None and close is not None:
                out.append({"ts": int(float(ts)), "close": float(close)})
        return sorted(out, key=lambda r: r["ts"])

    def _align_candles(self, btc_rows, eth_rows):
        btc = {r["ts"]: r["close"] for r in btc_rows}
        eth = {r["ts"]: r["close"] for r in eth_rows}
        out = []
        for ts in sorted(set(btc) & set(eth)):
            out.append({"ts": ts, "btc": btc[ts], "eth": eth[ts]})
        return out

    def _pair_pnl(self, signal):
        if not self.entry or not signal:
            return 0.0
        gross = self.entry["gross_equity"]
        beta = abs(self.entry["beta"])
        eth_notional = gross / (1 + beta)
        btc_notional = beta * gross / (1 + beta)
        btc_ret = signal["btc"] / self.entry["btc"] - 1
        eth_ret = signal["eth"] / self.entry["eth"] - 1
        if self.entry["direction"] > 0:
            gross_pnl = btc_notional * btc_ret - eth_notional * eth_ret
        else:
            gross_pnl = eth_notional * eth_ret - btc_notional * btc_ret
        return gross_pnl - 0.001 * gross

    def _leg_notionals(self, gross_usdt, beta):
        eth_notional = gross_usdt / (1 + abs(beta))
        btc_notional = abs(beta) * gross_usdt / (1 + abs(beta))
        return btc_notional, eth_notional

    def _size_from_notional(self, sym, notional):
        price = self.latest_quotes.get(sym, {}).get("price")
        if not price or notional < self.MIN_ORDER_NOTIONAL:
            return 0.0
        return notional / price

    def _quotes_fresh(self):
        now = time.time()
        for sym in (self.BTC, self.ETH):
            if sym not in self.latest_quotes:
                return False
            if now - self.latest_quotes[sym]["ts"] > self.STALE_QUOTE_SECONDS:
                return False
        return True

    def _quote_mid(self, data):
        bid = self._as_float(data.get("bid") or data.get("best_bid") or data.get("bid_price"))
        ask = self._as_float(data.get("ask") or data.get("best_ask") or data.get("ask_price"))
        if bid and ask:
            return (bid + ask) / 2
        return self._trade_price(data)

    def _trade_price(self, data):
        return self._as_float(data.get("price") or data.get("last") or data.get("close"))

    def _as_float(self, value):
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        if isinstance(value, dict):
            value = value.get("price") or value.get("p") or value.get("value")
        return float(value) if value is not None else None

    def _src_ok(self, src, data):
        venue = data.get("venue") if isinstance(data, dict) else None
        return src in (self.VENUE, "woo", "WOO", "WOO X", "WooPaper") or venue == self.VENUE

    def _equity(self):
        if self.DRY_RUN:
            return 10000.0 * (1 + self.fake_realized_pnl)
        try:
            balances = self.fetch_balances(self.VENUE)
            data = balances.get("data", balances) if isinstance(balances, dict) else balances
            text = str(data)
            # Fallback is intentionally conservative; exact parsing depends on venue payload.
            return float(data.get("USDT", {}).get("total")) if isinstance(data, dict) and "USDT" in data else 10000.0
        except Exception:
            return 10000.0

    def _flatten_best_effort(self):
        self._log("flatten_best_effort_needed")

    def _reset_to_flat(self):
        self.state = "FLAT"
        self.direction = 0
        self.alert_peak = 0.0
        self.entry = None
        self.last_abs_z = None

    def _beta(self, xs, ys):
        mx = self._mean(xs)
        my = self._mean(ys)
        var = sum((x - mx) ** 2 for x in xs)
        if var <= 0:
            return 1.0
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        return min(self.BETA_MAX, max(self.BETA_MIN, cov / var))

    def _corr(self, xs, ys):
        if len(xs) < 3 or len(xs) != len(ys):
            return 0.0
        mx = self._mean(xs)
        my = self._mean(ys)
        vx = sum((x - mx) ** 2 for x in xs)
        vy = sum((y - my) ** 2 for y in ys)
        if vx <= 0 or vy <= 0:
            return 0.0
        return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(vx * vy)

    def _mean(self, xs):
        return sum(xs) / len(xs)

    def _std(self, xs):
        if len(xs) < 2:
            return 0.0
        m = self._mean(xs)
        return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))

    def _log(self, event, **fields):
        payload = " ".join([event] + [f"{k}={v}" for k, v in sorted(fields.items())])
        try:
            self.log(payload)
        except Exception:
            print(payload)

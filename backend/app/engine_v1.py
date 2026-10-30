"""Deterministic, long-only candle research engine. No arbitrary code or network.

Signal i is calculated after completed candle i. With execution_delay_bars=1,
execution is at open i+2, with a full intervening candle for availability.
Stops use candle envelopes, adverse-first ordering, and explicit limitations.
"""
from __future__ import annotations

from collections import defaultdict, deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import statistics

from .domain_v1 import CATALOG, validate_strategy

ENGINE_VERSION = "kedr-candle-1.0.0"
STEP_SECONDS = 4 * 3600
BARS_PER_YEAR = 365 * 6
UTC = timezone.utc


def _time(value):
    if isinstance(value, datetime):
        d = value
    elif isinstance(value, str):
        d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise ValueError("Timestamps must be ISO date or UTC datetime strings.")
    return d.replace(tzinfo=UTC) if d.tzinfo is None else d.astimezone(UTC)


def _iso(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _finite(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (ValueError, OverflowError):
        return False


def _sma(values, period):
    out, window, total = [], deque(), 0.0
    for value in values:
        if value is None:
            window.clear()
            total = 0.0
            out.append(None)
            continue
        window.append(value)
        total += value
        if len(window) > period:
            total -= window.popleft()
        out.append(total / period if len(window) == period else None)
    return out


def _ema(values, period):
    out, seed, state = [], [], None
    alpha = 2 / (period + 1)
    for value in values:
        if value is None:
            seed, state = [], None
            out.append(None)
            continue
        if state is None:
            seed.append(value)
            if len(seed) == period:
                state = sum(seed) / period
        else:
            state = alpha * value + (1 - alpha) * state
        out.append(state)
    return out


def _rsi(values, period):
    out, prev, gains, losses, avg_gain, avg_loss = [], None, [], [], None, None
    for value in values:
        if value is None:
            prev, gains, losses, avg_gain, avg_loss = None, [], [], None, None
            out.append(None)
            continue
        if prev is None:
            prev = value
            out.append(None)
            continue
        gain, loss = max(value - prev, 0), max(prev - value, 0)
        prev = value
        if avg_gain is None:
            gains.append(gain)
            losses.append(loss)
            if len(gains) == period:
                avg_gain, avg_loss = sum(gains) / period, sum(losses) / period
        else:
            avg_gain = ((period - 1) * avg_gain + gain) / period
            avg_loss = ((period - 1) * avg_loss + loss) / period
        if avg_gain is None:
            out.append(None)
        elif avg_gain == 0 and avg_loss == 0:
            out.append(50.0)
        elif avg_loss == 0:
            out.append(100.0)
        else:
            out.append(100 - 100 / (1 + avg_gain / avg_loss))
    return out


def _indicator(kind, values, params):
    period = params.get("period", 20 if kind in ("sma", "ema", "bollinger") else 14 if kind == "rsi" else 28 if kind == "volatility" else 1)
    if kind == "sma":
        return _sma(values, period)
    if kind == "ema":
        return _ema(values, period)
    if kind == "rsi":
        return _rsi(values, period)
    if kind == "macd":
        fast, slow = _ema(values, params.get("fast", 12)), _ema(values, params.get("slow", 26))
        line = [a - b if a is not None and b is not None else None for a, b in zip(fast, slow)]
        signal = _ema(line, params.get("signal", 9))
        output = params.get("output", "line")
        return line if output == "line" else signal if output == "signal" else [a - b if a is not None and b is not None else None for a, b in zip(line, signal)]
    out, window, log_window = [], deque(), deque()
    total, total_sq, log_sum, log_sq = 0.0, 0.0, 0.0, 0.0
    for value in values:
        if value is None:
            window.clear()
            log_window.clear()
            total, total_sq, log_sum, log_sq = 0.0, 0.0, 0.0, 0.0
            out.append(None)
            continue
        if kind == "volatility" and window and window[-1] > 0 and value > 0:
            ret = math.log(value / window[-1])
            log_window.append(ret)
            log_sum += ret
            log_sq += ret * ret
            if len(log_window) > period:
                removed = log_window.popleft()
                log_sum -= removed
                log_sq -= removed * removed
        window.append(value)
        total += value
        total_sq += value * value
        required = period + 1 if kind in ("returns", "volatility") else period
        if len(window) > required:
            removed = window.popleft()
            total -= removed
            total_sq -= removed * removed
        if len(window) < required:
            out.append(None)
        elif kind == "returns":
            out.append(100 * (window[-1] / window[0] - 1) if window[0] > 0 else None)
        elif kind == "volatility":
            if len(log_window) != period or period < 2:
                out.append(None)
            else:
                variance = max(0.0, (log_sq - log_sum * log_sum / period) / (period - 1))
                out.append(math.sqrt(variance * BARS_PER_YEAR) * 100)
        elif kind == "bollinger":
            avg = total / period
            sd = math.sqrt(max(0.0, total_sq / period - avg * avg))
            output = params.get("output", "upper")
            out.append(avg + (1 if output == "upper" else -1 if output == "lower" else 0) * params.get("stddev", 2) * sd)
        else:
            raise ValueError("Unsupported indicator.")
    return out


def evaluate_graph(spec, bars):
    """Return causal node series; all indicator state is reset at source gaps."""
    validation = validate_strategy(spec)
    if not validation["valid"]:
        raise ValueError("Invalid strategy: " + "; ".join(e["message"] for e in validation["errors"]))
    n = len(bars)
    by_id = {node["id"]: node for node in spec["nodes"]}
    incoming = {nid: {} for nid in by_id}
    for edge in spec["edges"]:
        incoming[edge["target"]][edge.get("targetHandle") or "input"] = edge["source"]
    pending, order = set(by_id), []
    while pending:
        ready = sorted(nid for nid in pending if all(source in order for source in incoming[nid].values()))
        if not ready:
            raise ValueError("Strategy graph is cyclic.")
        order.extend(ready)
        pending.difference_update(ready)
    # Null separators force every rolling/recursive indicator to restart. The
    # first actual bar after a gap is still an observed, usable candle.
    expanded, original = [], []
    last_time = None
    for i, bar in enumerate(bars):
        current = _time(bar["time"])
        if last_time is not None and (current - last_time).total_seconds() != STEP_SECONDS:
            expanded.append(None)
        original.append(len(expanded))
        expanded.append(bar)
        last_time = current
    m, values = len(expanded), {}
    for nid in order:
        node = by_id[nid]
        kind, p = node["type"], node.get("params", {})
        links = incoming[nid]
        if kind in ("price", "volume"):
            field = p.get("field", "close") if kind == "price" else "volume"
            values[nid] = [bar[field] if bar is not None else None for bar in expanded]
        elif kind == "constant":
            values[nid] = [p.get("value", 50) if bar is not None else None for bar in expanded]
        elif kind == "market":
            values[nid] = [spec["symbol"] if bar is not None else None for bar in expanded]
        elif kind in ("sma", "ema", "rsi", "macd", "bollinger", "volatility", "returns"):
            values[nid] = _indicator(kind, values[links["input"]], p)
        elif kind in ("gt", "lt", "cross_above", "cross_below", "and", "or"):
            a, b, out = values[links["a"]], values[links["b"]], []
            for i, (av, bv) in enumerate(zip(a, b)):
                if av is None or bv is None:
                    out.append(None)
                elif kind == "gt":
                    out.append(av > bv)
                elif kind == "lt":
                    out.append(av < bv)
                elif kind == "and":
                    out.append(bool(av and bv))
                elif kind == "or":
                    out.append(bool(av or bv))
                elif i == 0 or a[i - 1] is None or b[i - 1] is None:
                    out.append(None)
                elif kind == "cross_above":
                    out.append(av > bv and a[i - 1] <= b[i - 1])
                else:
                    out.append(av < bv and a[i - 1] >= b[i - 1])
            values[nid] = out
        elif kind in ("enter_long", "exit_long"):
            values[nid] = list(values[links["input"]])
        elif kind == "hold_cash":
            values[nid] = [True if bar is not None else None for bar in expanded]
        else:
            values[nid] = [None] * m  # Static risk configuration has no signal.
    return {nid: [series[i] for i in original] for nid, series in values.items()}


def _risk(spec):
    root = spec.get("risk", {})
    exposure = root.get("max_exposure", 1)
    stop, take = root.get("stop_loss_pct"), root.get("take_profit_pct")
    for node in spec["nodes"]:
        kind, p = node["type"], node.get("params", {})
        if kind in ("position_size", "max_exposure"):
            exposure = min(exposure, p.get("fraction", 1))
        elif kind == "stop_loss":
            stop = p.get("pct", 5)
        elif kind == "take_profit":
            take = p.get("pct", 10)
    return exposure, stop, take


def _configuration(config):
    if not isinstance(config, dict):
        raise ValueError("Backtest configuration must be an object.")
    c = {"start": "2022-01-01", "end": "2025-12-31", "initial_cash": 10000,
         "fee_bps": 10, "slippage_bps": 2, "execution_delay_bars": 1, **config}
    for key, low, high in (("initial_cash", 10, 1e9), ("fee_bps", 0, 100), ("slippage_bps", 0, 100)):
        if not _finite(c[key]) or not low <= c[key] <= high:
            raise ValueError(f"{key} must be finite and between {low} and {high}.")
    delay = c["execution_delay_bars"]
    if not isinstance(delay, int) or isinstance(delay, bool) or not 1 <= delay <= 6:
        raise ValueError("execution_delay_bars must be an integer from 1 to 6. Zero-delay fills are disabled.")
    if not isinstance(c["start"], str) or not isinstance(c["end"], str):
        raise ValueError("Start and end must be ISO date strings.")
    try:
        start, end = _time(c["start"]), _time(c["end"])
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Select valid ISO start/end dates.") from exc
    if len(c["end"]) == 10:
        end += timedelta(days=1)
    if start >= end:
        raise ValueError("The testing end must be after its start.")
    return c, start, end


def _prepared_bars(dataset, end):
    if not isinstance(dataset, dict) or not isinstance(dataset.get("bars"), list) or not isinstance(dataset.get("metadata"), dict):
        raise ValueError("Select a dataset from an available adapter.")
    if len(dataset["bars"]) > 20000:
        raise ValueError("The initial local engine supports at most 20,000 candles per job.")
    bars, rejected, last = [], 0, None
    for raw in dataset["bars"]:
        if not isinstance(raw, dict):
            raise ValueError("Each dataset candle must be an object.")
        try:
            dt = _time(raw["time"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Dataset contains an invalid timestamp.") from exc
        if last is not None and dt <= last:
            raise ValueError("Dataset must be strictly time-ordered with unique timestamps.")
        last = dt
        if dt >= end:
            continue
        if raw.get("valid", True) is False:
            rejected += 1
            continue
        if not all(_finite(raw.get(k)) for k in ("open", "high", "low", "close", "volume")):
            rejected += 1
            continue
        op, hi, lo, cl = (raw[k] for k in ("open", "high", "low", "close"))
        if min(op, hi, lo, cl) <= 0 or raw["volume"] < 0 or not lo <= min(op, cl) <= max(op, cl) <= hi:
            rejected += 1
            continue
        if int(dt.timestamp()) % STEP_SECONDS != 0 or dt.microsecond:
            rejected += 1
            continue
        bars.append({**raw, "time": _iso(dt)})
    return bars, rejected


def _path_metrics(equity, initial, closed, fees, slippage_cost, exposure_mean, elapsed_days):
    final = equity[-1]["equity"]
    # Gross is an explicit same-quantity add-back, not a zero-cost re-investment.
    net = (final / initial - 1) * 100
    gross = ((final + fees + slippage_cost) / initial - 1) * 100
    returns, previous = [], initial
    for point in equity:
        returns.append(point["equity"] / previous - 1 if previous else 0)
        previous = point["equity"]
    # A 4h Sharpe annualizer is only reported on an uninterrupted grid; return
    # intervals spanning gaps are not silently treated as four-hour returns.
    contiguous = all((_time(b["time"]) - _time(a["time"])).total_seconds() == STEP_SECONDS for a, b in zip(equity, equity[1:]))
    sd = statistics.stdev(returns) if len(returns) > 1 else 0
    sharpe = statistics.mean(returns) / sd * math.sqrt(BARS_PER_YEAR) if contiguous and len(returns) >= 30 and sd > 1e-12 else None
    cagr = ((final / initial) ** (365.25 / elapsed_days) - 1) * 100 if elapsed_days >= 365 and final > 0 else None
    high, longest = initial, 0.0
    # Keep the actual prior high-watermark clock. A source gap must not turn
    # several elapsed days underwater into one ordinary candle interval.
    peak_time = _time(equity[0]["time"]) - timedelta(seconds=STEP_SECONDS)
    underwater = False
    for p in equity:
        dt = _time(p["time"])
        if p["equity"] >= high:
            if underwater:
                longest = max(longest, (dt - peak_time).total_seconds() / 86400)
            high, peak_time, underwater = p["equity"], dt, False
        else:
            underwater = True
            longest = max(longest, (dt - peak_time).total_seconds() / 86400)
    winners = [t["net_pnl"] for t in closed if t["net_pnl"] > 0]
    losers = [t["net_pnl"] for t in closed if t["net_pnl"] < 0]
    return {"net_return_pct": net, "gross_return_pct": gross, "cagr_pct": cagr,
            "sharpe": sharpe, "max_drawdown_pct": max((p["drawdown_pct"] for p in equity), default=0),
            "longest_drawdown_days": longest, "win_rate_pct": 100 * len(winners) / len(closed) if closed else None,
            "profit_factor": sum(winners) / -sum(losers) if losers else None,
            "fees": fees, "slippage_cost": slippage_cost, "total_trades": len(closed),
            "closed_trades": len(closed), "exposure_pct": exposure_mean * 100,
            "final_equity": final, "initial_cash": initial, "elapsed_days": elapsed_days}


def _period_returns(equity, initial, annual=False):
    groups, previous = {}, initial
    for point in equity:
        # A candle ending exactly at UTC midnight belongs to the period whose
        # final interval it completed, not to the following month/year.
        closed_period = _iso(_time(point["time"]) - timedelta(microseconds=1))
        period = closed_period[:4] if annual else closed_period[:7]
        if period not in groups:
            groups[period] = {"start": previous, "end": point["equity"]}
        groups[period]["end"] = point["equity"]
        previous = point["equity"]
    return [{"period": period, "return_pct": (v["end"] / v["start"] - 1) * 100} for period, v in groups.items()]


def run_backtest(spec, dataset, config):
    validation = validate_strategy(spec)
    if not validation["valid"]:
        raise ValueError("Invalid strategy: " + "; ".join(e["message"] for e in validation["errors"]))
    c, start, end = _configuration(config)
    if not isinstance(dataset, dict):
        raise ValueError("Select a dataset from an available adapter.")
    if spec["symbol"] != dataset.get("metadata", {}).get("symbol") or spec["timeframe"] != dataset.get("metadata", {}).get("timeframe"):
        raise ValueError("Strategy symbol/timeframe and dataset must match. No automatic market substitution is performed.")
    bars, rejected = _prepared_bars(dataset, end)
    selected = [i for i, b in enumerate(bars) if _time(b["time"]) >= start]
    if len(selected) < 3:
        raise ValueError("Select a period containing at least three valid candles.")
    first, last = selected[0], selected[-1]
    # Only completed bars within the selected end can generate signals or fills.
    bars = bars[:last + 1]
    graph = evaluate_graph(spec, bars)
    actions = {kind: [n["id"] for n in spec["nodes"] if n["type"] == kind] for kind in ("enter_long", "exit_long", "hold_cash")}
    exposure_cap, stop_pct, take_pct = _risk(spec)
    fee, slip = c["fee_bps"] / 10000, c["slippage_bps"] / 10000
    cash, quantity = float(c["initial_cash"]), 0.0
    fees, slip_cost, exposure_sum = 0.0, 0.0, 0.0
    trades, current, equity, pending = [], None, [], {}
    segments, segment = [], 0
    for i, bar in enumerate(bars):
        if i and (_time(bar["time"]) - _time(bars[i - 1]["time"])).total_seconds() != STEP_SECONDS:
            segment += 1
        segments.append(segment)
    canceled, warmup, unfilled_end = 0, 0, 0
    peak = cash
    benchmark_cash, benchmark_qty = cash, 0.0
    benchmark_fees, benchmark_slip = 0.0, 0.0
    benchmark_entry = None
    def enter(i, signal_i):
        nonlocal cash, quantity, fees, slip_cost, current
        if quantity > 1e-14 or cash <= 0 or exposure_cap <= 0:
            return
        ref = bars[i]["open"]
        fill = ref * (1 + slip)
        budget = cash * exposure_cap
        qty = budget / (fill * (1 + fee))
        if qty <= 0:
            return
        cost, tx_fee = qty * fill, qty * fill * fee
        cash -= cost + tx_fee
        if abs(cash) < 1e-9:
            cash = 0.0
        quantity = qty
        fees += tx_fee
        impact = qty * (fill - ref)
        slip_cost += impact
        current = {"entry_time": bars[i]["time"], "signal_time": bars[signal_i]["time"],
                   "signal_completed_at": _iso(_time(bars[signal_i]["time"]) + timedelta(seconds=STEP_SECONDS)),
                   "entry_price": fill, "entry_reference_price": ref, "exit_time": None, "exit_price": None,
                   "quantity": qty, "net_pnl": None, "fees": tx_fee, "slippage_cost": impact,
                   "status": "open", "exit_reason": None, "entry_cost": cost + tx_fee}
        trades.append(current)
    def exit_position(i, ref, reason):
        nonlocal cash, quantity, fees, slip_cost, current
        if quantity <= 1e-14 or current is None:
            return
        fill = ref * (1 - slip)
        revenue, tx_fee = quantity * fill, quantity * fill * fee
        cash += revenue - tx_fee
        fees += tx_fee
        impact = quantity * (ref - fill)
        slip_cost += impact
        current.update({"exit_time": bars[i]["time"], "exit_price": fill, "exit_reference_price": ref,
                        "net_pnl": revenue - tx_fee - current["entry_cost"], "fees": current["fees"] + tx_fee,
                        "slippage_cost": current["slippage_cost"] + impact, "status": "closed", "exit_reason": reason})
        current["exit_time_precision"] = "bar_interval" if reason in ("stop_loss", "take_profit") else "open_reference"
        if reason in ("stop_loss", "take_profit"):
            current["exit_interval_end"] = _iso(_time(bars[i]["time"]) + timedelta(seconds=STEP_SECONDS))
        quantity, current = 0.0, None
    for i in range(first, len(bars)):
        bar = bars[i]
        same_segment = i == 0 or segments[i] == segments[i - 1]
        order = pending.pop(i, None)
        if order is not None:
            if segments[order["signal_i"]] != segments[i]:
                canceled += 1
            elif order["action"] == "exit":
                exit_position(i, bar["open"], "signal")
            else:
                enter(i, order["signal_i"])
        # Passive control uses the identical first available signal and delay,
        # costs and gap-safe clock, with 100% initial exposure and no rebalancing.
        if benchmark_entry is None:
            origin = first
            due = origin + c["execution_delay_bars"] + 1
            if i >= due:
                if segments[origin] == segments[i]:
                    fill = bar["open"] * (1 + slip)
                    benchmark_qty = benchmark_cash / (fill * (1 + fee))
                    benchmark_fees = benchmark_qty * fill * fee
                    benchmark_slip = benchmark_qty * (fill - bar["open"])
                    benchmark_cash = 0.0
                    benchmark_entry = bar["time"]
                else:
                    # A discontinuity cancels this order. Reschedule from the
                    # first actual bar of the current contiguous segment.
                    first_for_segment = i
                    while first_for_segment > first and segments[first_for_segment - 1] == segments[i]:
                        first_for_segment -= 1
                    if i - first_for_segment >= c["execution_delay_bars"] + 1:
                        fill = bar["open"] * (1 + slip)
                        benchmark_qty = benchmark_cash / (fill * (1 + fee))
                        benchmark_fees = benchmark_qty * fill * fee
                        benchmark_slip = benchmark_qty * (fill - bar["open"])
                        benchmark_cash, benchmark_entry = 0.0, bar["time"]
        # OHLC cannot establish intrabar path. If both thresholds are touched,
        # stop-loss takes priority. Gap-open stop fills use the worse open.
        # A source time gap suppresses all threshold fills on its first bar.
        if quantity > 0 and current is not None and same_segment:
            stop = current["entry_price"] * (1 - stop_pct / 100) if stop_pct is not None else None
            take = current["entry_price"] * (1 + take_pct / 100) if take_pct is not None else None
            if stop is not None and bar["low"] <= stop:
                exit_position(i, min(bar["open"], stop), "stop_loss")
            elif take is not None and bar["high"] >= take:
                # No price improvement is invented on a gap above the target.
                exit_position(i, take, "take_profit")
        entry_values = [graph[nid][i] for nid in actions["enter_long"]]
        exit_values = [graph[nid][i] for nid in actions["exit_long"]]
        signal_ready = not entry_values or any(v is not None for v in entry_values)
        if not signal_ready:
            warmup += 1
        act = "exit" if any(v is True for v in exit_values) else "enter" if any(v is True for v in entry_values) else None
        if act:
            due = i + c["execution_delay_bars"] + 1
            if due < len(bars):
                pending[due] = {"action": act, "signal_i": i}
            else:
                unfilled_end += 1
        value = cash + quantity * bar["close"]
        peak = max(peak, value)
        marked_holdings = quantity * bar["close"]
        exposure_sum += marked_holdings / value if value > 0 else 0
        equity.append({"time": _iso(_time(bar["time"]) + timedelta(seconds=STEP_SECONDS)),
                       "equity": value, "cash": cash, "holdings": marked_holdings, "quantity": quantity,
                       "drawdown_pct": max(0, (1 - value / peak) * 100),
                       "benchmark_equity": benchmark_cash + benchmark_qty * bar["close"], "price": bar["close"]})
    if current is not None:
        current["unrealized_pnl"] = quantity * bars[-1]["close"] - current["entry_cost"]
        current["marked_value"] = quantity * bars[-1]["close"]
    closed = [t for t in trades if t["status"] == "closed"]
    elapsed_days = (_time(equity[-1]["time"]) - _time(bars[first]["time"])).total_seconds() / 86400
    metrics = _path_metrics(equity, c["initial_cash"], closed, fees, slip_cost, exposure_sum / len(equity), elapsed_days)
    metrics["open_trades"] = sum(t["status"] == "open" for t in trades)
    metrics["entries"] = len(trades)
    expected = int((_time(bars[-1]["time"]) - _time(bars[first]["time"])).total_seconds() / STEP_SECONDS) + 1
    requested_expected = max(1, math.ceil((end - start).total_seconds() / STEP_SECONDS))
    gap_count = sum(segments[i] != segments[i - 1] for i in range(first + 1, len(bars)))
    warnings = list(validation["warnings"])
    if dataset["metadata"].get("source_type") == "synthetic_demo":
        warnings.append("SYNTHETIC DEMONSTRATION: these generated candles are not historical market evidence.")
    if gap_count or rejected:
        warnings.append("Source gaps/invalid rows reset indicators and cancel orders across gaps. Existing inventory remains marked; unobserved intragap risk cannot be reconstructed.")
    if _time(bars[first]["time"]) > start or _time(equity[-1]["time"]) < end:
        warnings.append("The dataset does not cover the full requested calendar period. Actual start/end and requested-period coverage are reported explicitly.")
    if metrics["open_trades"]:
        warnings.append("Final inventory remains open and marked at the last close. Exit fees/slippage are not charged without an actual simulated exit.")
    if len(closed) < 30:
        warnings.append("Fewer than 30 closed trades: trade-level summaries are unstable and are not independent validation.")
    if elapsed_days < 365:
        warnings.append("CAGR is undefined for periods shorter than one year.")
    if metrics["sharpe"] is None:
        warnings.append("Sharpe is undefined for constant/short paths or irregular observed intervals.")
    assumptions = [
        "Long-only Spot simulation; zero cash interest, no leverage, borrow, funding, market impact or private accounts.",
        f"Signal on completed bar i; execution reference open i+{c['execution_delay_bars'] + 1}. Full-candle publication embargo; no signal-close fills.",
        "Candle OHLC reference prices are not executable bid/ask quotes, historical receipt clocks or depth evidence.",
        "Signals use only earlier/completed candles. Indicator warm-up restarts at each four-hour timestamp discontinuity.",
        "Exit overrides entry if both signals are true. Repeated entries while invested do not pyramid or rebalance.",
        "Exposure is a fraction of available cash at entry including fees. Price drift can change later exposure; this is not continuous risk rebalancing. No exchange-specific lot/minimum-notional filters are certified.",
        "Static risk-node fractions can only reduce root max exposure; explicit stop/take nodes override root percentages.",
        "Stops/takes are approximate OHLC-envelope fills: stop first if both touched, worse open for stop gaps, no favorable take-gap improvement. No intrabar timestamp is known.",
        "Reported stop/take exit time is the candle-open label of the containing bar, not an observed intrabar fill timestamp.",
        "Gross return is net terminal equity plus actual same-quantity fees and slippage add-backs, divided by initial cash. It is not a zero-cost compounding counterfactual.",
        "Terminal inventory is marked, not forcibly liquidated. Closed-trade statistics exclude open positions.",
        "Historical selections and repeated parameter edits are retrospective; no held-out or independent evaluation is registered.",
    ]
    # Match the API's immutable-version canonical JSON, including Unicode IDs.
    spec_hash = hashlib.sha256(json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    config_hash = hashlib.sha256(json.dumps(c, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    source = dataset["metadata"].get("source_type", "unknown")
    provenance = {"engine_version": ENGINE_VERSION, "spec_sha256": spec_hash, "config_sha256": config_hash,
                  "dataset_id": dataset["metadata"].get("id"), "dataset_sha256": dataset["metadata"].get("sha256"),
                  "source_type": source, "requested_start": c["start"], "requested_end": c["end"],
                  "actual_start": bars[first]["time"], "actual_end": equity[-1]["time"],
                  "evaluated_bars": len(equity), "preperiod_context_bars": first,
                  "warmup_bars": warmup, "gaps": gap_count, "invalid_rows_excluded": rejected,
                  "cross_gap_orders_canceled": canceled, "signals_without_future_execution_bar": unfilled_end,
                  "signal_to_open_index_offset": c["execution_delay_bars"] + 1,
                  "seed": dataset.get("provenance", {}).get("seed"),
                  "source": deepcopy(dataset.get("provenance", {}))}
    result = {"metrics": metrics, "equity": equity, "trades": trades,
              "monthly": _period_returns(equity, c["initial_cash"]), "annual": _period_returns(equity, c["initial_cash"], True),
              "returns": [{"time": point["time"], "return_pct": (point["equity"] / (equity[i - 1]["equity"] if i else c["initial_cash"]) - 1) * 100} for i, point in enumerate(equity)],
              "benchmarks": {"cash": {"final_equity": c["initial_cash"], "net_return_pct": 0},
                             "buy_hold": {"final_equity": equity[-1]["benchmark_equity"],
                                          "net_return_pct": (equity[-1]["benchmark_equity"] / c["initial_cash"] - 1) * 100,
                                          "fees": benchmark_fees, "slippage_cost": benchmark_slip,
                                          "entry_time": benchmark_entry, "terminal_inventory_marked": True,
                                          "description": "Same initial cash, fees/slippage, first signal and embargo; passive 100% allocation. No final forced sale."}},
              "quality": {"warnings": warnings, "source_type": source, "data_coverage_pct": min(100, 100 * len(equity) / requested_expected),
                          "observed_span_coverage_pct": min(100, 100 * len(equity) / expected),
                          "independent_evaluation": False, "assumptions": assumptions},
              "provenance": provenance, "config": c, "dataset": deepcopy(dataset["metadata"])}
    # Fail rather than write NaN/Infinity into persisted reports.
    json.dumps(result, allow_nan=False)
    return result


def explain_result(result, locale="ru"):
    """Auditable offline interpretation. This is explicitly not AI generation."""
    m = result["metrics"]
    ru = locale != "en"
    def number(value, digits=2):
        return ("не определено" if ru else "undefined") if value is None else f"{value:,.{digits}f}"
    source = result.get("quality", {}).get("source_type", "unknown")
    passive = result.get("benchmarks", {}).get("buy_hold", {}).get("net_return_pct")
    difference = m["net_return_pct"] - passive if passive is not None else None
    months = result.get("monthly", [])
    best = max(months, key=lambda x: x["return_pct"]) if months else None
    worst = min(months, key=lambda x: x["return_pct"]) if months else None
    if ru:
        summary = f"Симуляция дала {number(m['net_return_pct'])}% после затрат при максимальной просадке {number(m['max_drawdown_pct'])}%. Это ретроспективное описание, а не подтверждённое преимущество."
        sections = [
            {"title": "Что измерено", "body": f"Закрытых сделок: {m['total_trades']}; открытых: {m.get('open_trades', 0)}. Средняя доля в активе: {number(m['exposure_pct'])}%. Источник: {source}."},
            {"title": "Сравнение с простым ориентиром", "body": f"Пассивное владение на том же капитале и задержке: {number(passive)}%. Разница: {number(difference)} п.п. Риск и экспозиция могут различаться; разница не является альфой."},
            {"title": "Риск и издержки", "body": f"Комиссии: {number(m['fees'])} USDT; учтённое проскальзывание: {number(m['slippage_cost'])} USDT. Просадка измеряется по закрытиям свечей и не ограничивает возможный внутрисвечной убыток."},
            {"title": "Сильные и слабые периоды", "body": (f"Лучший месяц: {best['period']} ({number(best['return_pct'])}%); худший: {worst['period']} ({number(worst['return_pct'])}%). " if best else "Нет месячных данных. ") + "Периоды описывают уже известную историю и не задают будущие фильтры."},
            {"title": "Качество доказательств", "body": "Независимого контрольного периода нет. Перебор параметров после просмотра результата повышает риск переобучения. Котировки, глубина и очередь исполнения не измерены. Синтетические данные служат только обучению."},
            {"title": "Следующая проверка", "body": "Сохраните неизменяемую версию, задайте отдельный будущий период и критерий полезного эффекта до его исходов. Сравните с деньгами и пассивным владением при тех же затратах. Не выбирайте вариант по одной красивой кривой."},
        ]
    else:
        summary = f"The simulation returned {number(m['net_return_pct'])}% after costs, with {number(m['max_drawdown_pct'])}% maximum drawdown. This is retrospective description, not an established edge."
        sections = [
            {"title": "What was measured", "body": f"Closed trades: {m['total_trades']}; open: {m.get('open_trades', 0)}. Mean asset exposure: {number(m['exposure_pct'])}%. Source: {source}."},
            {"title": "Simple benchmark", "body": f"Passive holding with identical cash and entry delay returned {number(passive)}%; difference {number(difference)} percentage points. Risk/exposure differ; this is not alpha."},
            {"title": "Risk and costs", "body": f"Fees: {number(m['fees'])} USDT; modeled slippage: {number(m['slippage_cost'])} USDT. Close-mark drawdown is not an intrabar loss bound."},
            {"title": "Stronger and weaker periods", "body": (f"Best month: {best['period']} ({number(best['return_pct'])}%); worst: {worst['period']} ({number(worst['return_pct'])}%). " if best else "No monthly observations. ") + "These known outcomes do not define prospective market filters."},
            {"title": "Evidence quality", "body": "There is no independent evaluation period. Editing after viewing performance increases overfitting risk. Quotes, depth and queue execution were not measured. Synthetic inputs are educational only."},
            {"title": "Next check", "body": "Save an immutable version and define a separate future period and meaningful effect before outcomes. Retain cash/passive controls under identical costs. Do not select a candidate from an attractive equity curve alone."},
        ]
    return {"mode": "offline_rules", "provider_status": "not_configured", "template_version": "offline-analysis-v1",
            "locale": "ru" if ru else "en", "summary": summary, "sections": sections,
            "references": {"engine_version": result.get("provenance", {}).get("engine_version"),
                           "spec_sha256": result.get("provenance", {}).get("spec_sha256"),
                           "dataset_sha256": result.get("provenance", {}).get("dataset_sha256")},
            "warnings": result.get("quality", {}).get("warnings", [])}


"""Causal long/cash research engine v2, with explicit clocks and saved traces.

The frozen v1 engine is independent of this module. Nothing here certifies a
market fill, historical receipt time, or an independently validated strategy.
"""
from bisect import bisect_left, bisect_right, insort
from collections import defaultdict, deque
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
import math
import statistics

from . import domain_v2 as domain
from . import engine_v1 as legacy

ENGINE_VERSION = "kedr-candle-2.0.0"
MAX_BARS = 50000
TRACE_LIMITS = {"decisions": 3000, "orders": 6000, "account": 20000}
_time, _iso, _finite = legacy._time, legacy._iso, legacy._finite


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _rolling(values, period, fn):
    result, window = [], deque()
    for value in values:
        if value is None:
            window.clear()
            result.append(None)
            continue
        window.append(value)
        if len(window) > period:
            window.popleft()
        result.append(fn(window) if len(window) == period else None)
    return result


def _moments(values, period):
    """Rolling Welford mean/M2 with removal; O(n), no price-square subtraction."""
    result, window, mean, m2 = [], deque(), 0.0, 0.0
    for value in values:
        if value is None:
            window.clear()
            mean, m2 = 0.0, 0.0
            result.append(None)
            continue
        if len(window) == period:
            old = window.popleft()
            if period == 1:
                mean, m2 = 0.0, 0.0
            else:
                reduced = (period * mean - old) / (period - 1)
                m2 = max(0.0, m2 - (old - mean) * (old - reduced))
                mean = reduced
        count = len(window) + 1
        delta = value - mean
        mean += delta / count
        m2 += delta * (value - mean)
        window.append(value)
        result.append((mean, max(0.0, m2)) if count == period else None)
    return result


def _extrema(values, period, maximum):
    result, queue, count = [], deque(), 0
    for i, value in enumerate(values):
        if value is None:
            queue.clear()
            count = 0
            result.append(None)
            continue
        count += 1
        while queue and queue[0][0] <= i - period:
            queue.popleft()
        while queue and (queue[-1][1] <= value if maximum else queue[-1][1] >= value):
            queue.pop()
        queue.append((i, value))
        result.append(queue[0][1] if count >= period else None)
    return result


def _correlation(values, period):
    result, window = [], deque()
    mx, my, m2x, m2y, covariance = 0.0, 0.0, 0.0, 0.0, 0.0
    for pair in values:
        if pair is None:
            window.clear()
            mx, my, m2x, m2y, covariance = 0.0, 0.0, 0.0, 0.0, 0.0
            result.append(None)
            continue
        if len(window) == period:
            x, y = window.popleft()
            if period > 1:
                nx, ny = (period * mx - x) / (period - 1), (period * my - y) / (period - 1)
                m2x = max(0.0, m2x - (x - mx) * (x - nx))
                m2y = max(0.0, m2y - (y - my) * (y - ny))
                covariance -= (x - mx) * (y - ny)
                mx, my = nx, ny
            else:
                mx, my, m2x, m2y, covariance = 0.0, 0.0, 0.0, 0.0, 0.0
        x, y = pair
        count = len(window) + 1
        dx, dy = x - mx, y - my
        mx, my = mx + dx / count, my + dy / count
        m2x += dx * (x - mx)
        m2y += dy * (y - my)
        covariance += dx * (y - my)
        window.append(pair)
        result.append(max(-1.0, min(1.0, covariance / math.sqrt(m2x * m2y))) if count == period and min(m2x, m2y) > 1e-30 else None)
    return result


def _wilder(values, period):
    result, seed, state = [], [], None
    for value in values:
        if value is None:
            seed, state = [], None
            result.append(None)
            continue
        if state is None:
            seed.append(value)
            if len(seed) == period:
                state = sum(seed) / period
        else:
            state = ((period - 1) * state + value) / period
        result.append(state)
    return result


def _numeric(kind, values, params, step):
    if kind in ("sma", "ema", "rsi", "macd", "returns"):
        return legacy._indicator(kind, values, params)
    period = params.get("period", 28)
    if kind == "bollinger":
        sign = 1 if params.get("output", "upper") == "upper" else -1 if params.get("output") == "lower" else 0
        return [m[0] + sign * params.get("stddev", 2) * math.sqrt(m[1] / period) if m else None for m in _moments(values, period)]
    if kind == "volatility":
        returns, prior = [], None
        for value in values:
            returns.append(math.log(value / prior) if value is not None and prior is not None and min(value, prior) > 0 else None)
            prior = value
        moments = _moments(returns, period)
        return [math.sqrt(m[1] / (period - 1) * 365 * 86400 / step) * 100 if m is not None and period > 1 else None for m in moments]
    if kind in ("momentum", "log_returns"):
        result, window = [], deque()
        for value in values:
            if value is None or (kind != "momentum" and value <= 0):
                window.clear()
                result.append(None)
                continue
            window.append(value)
            if len(window) > period + 1:
                window.popleft()
            if len(window) != period + 1:
                result.append(None)
            elif kind == "momentum":
                result.append(window[-1] - window[0])
            elif kind == "log_returns":
                result.append(100 * math.log(window[-1] / window[0]))
        return result
    if kind == "wma":
        result, window, total, weighted = [], deque(), 0.0, 0.0
        for value in values:
            if value is None:
                window.clear()
                total, weighted = 0.0, 0.0
                result.append(None)
                continue
            if len(window) == period:
                weighted -= total
                total -= window.popleft()
            window.append(value)
            weighted += len(window) * value
            total += value
            result.append(weighted / (period * (period + 1) / 2) if len(window) == period else None)
        return result
    if kind == "rolling_high":
        return _extrema(values, period, True)
    if kind == "rolling_low":
        return _extrema(values, period, False)
    if kind == "zscore":
        return [None if m is None else (value - m[0]) / math.sqrt(m[1] / period) if m[1] > 1e-30 else 0.0 for value, m in zip(values, _moments(values, period))]
    if kind == "volatility_percentile":
        # Current value against strictly earlier history; ties get midrank.
        result, window, sorted_window = [], deque(), []
        for value in values:
            if value is None:
                window.clear()
                sorted_window.clear()
                result.append(None)
                continue
            result.append(50 * (bisect_left(sorted_window, value) + bisect_right(sorted_window, value)) / period if len(window) == period else None)
            window.append(value)
            insort(sorted_window, value)
            if len(window) > period:
                old = window.popleft()
                sorted_window.pop(bisect_left(sorted_window, old))
        return result
    raise ValueError(f"Unsupported numeric indicator: {kind}")


def _market_indicator(kind, bars, params):
    p = params.get("period", 14)
    highs = [b["high"] if b else None for b in bars]
    lows = [b["low"] if b else None for b in bars]
    closes = [b["close"] if b else None for b in bars]
    if kind == "vwap":
        p = params.get("period", 28)
        for b in bars:
            if b is not None and (not _finite(b.get("quote_volume")) or b["quote_volume"] < 0):
                raise ValueError("VWAP requires genuine quote_volume and base volume. Close-weighted proxies are not substituted.")
        quote = legacy._sma([b["quote_volume"] if b else None for b in bars], p)
        base = legacy._sma([b["volume"] if b else None for b in bars], p)
        return [q / v if q is not None and v is not None and v > 0 else None for q, v in zip(quote, base)]
    if kind in ("stochastic", "donchian"):
        p = params.get("period", 20 if kind == "donchian" else 14)
        if kind == "donchian" and params.get("exclude_current", True):
            highs, lows = [None] + highs[:-1], [None] + lows[:-1]
        hh, ll = _extrema(highs, p, True), _extrema(lows, p, False)
        if kind == "donchian":
            return [None if h is None or l is None else h if params.get("output", "upper") == "upper" else l if params.get("output") == "lower" else (h + l) / 2 for h, l in zip(hh, ll)]
        k = [None if h is None or l is None or c is None else 50.0 if h == l else 100 * (c - l) / (h - l) for h, l, c in zip(hh, ll, closes)]
        return legacy._sma(k, params.get("smooth", 3)) if params.get("output", "k") == "d" else k
    if kind == "obv":
        result, prior, state = [], None, 0.0
        for b in bars:
            if b is None:
                prior, state = None, 0.0
                result.append(None)
                continue
            if prior is not None:
                state += (1 if b["close"] > prior else -1 if b["close"] < prior else 0) * b["volume"]
            prior = b["close"]
            result.append(state)
        return result
    if kind == "mfi":
        flow, prior = [], None
        for b in bars:
            if b is None:
                prior = None
                flow.append(None)
                continue
            typical = (b["high"] + b["low"] + b["close"]) / 3
            flow.append(None if prior is None else (typical * b["volume"] if typical > prior else 0, typical * b["volume"] if typical < prior else 0))
            prior = typical
        positive = legacy._sma([v[0] if v else None for v in flow], p)
        negative = legacy._sma([v[1] if v else None for v in flow], p)
        return [None if pos is None or neg is None else 50.0 if pos == neg == 0 else 100.0 if neg == 0 else 100 - 100 / (1 + pos / neg) for pos, neg in zip(positive, negative)]
    if kind in ("atr", "adx"):
        tr, plus, minus, prior = [], [], [], None
        for b in bars:
            if b is None:
                tr.append(None)
                plus.append(None)
                minus.append(None)
                prior = None
                continue
            tr.append(b["high"] - b["low"] if prior is None else max(b["high"] - b["low"], abs(b["high"] - prior["close"]), abs(b["low"] - prior["close"])))
            up = b["high"] - prior["high"] if prior else 0
            down = prior["low"] - b["low"] if prior else 0
            plus.append(up if up > down and up > 0 else 0.0)
            minus.append(down if down > up and down > 0 else 0.0)
            prior = b
        atr = _wilder(tr, p)
        if kind == "atr":
            return atr
        smp, smm = _wilder(plus, p), _wilder(minus, p)
        pd = [100 * a / t if t and a is not None else 0.0 if t == 0 else None for a, t in zip(smp, atr)]
        md = [100 * a / t if t and a is not None else 0.0 if t == 0 else None for a, t in zip(smm, atr)]
        if params.get("output", "adx") == "plus_di":
            return pd
        if params.get("output") == "minus_di":
            return md
        dx = [None if a is None or b is None else 100 * abs(a - b) / (a + b) if a + b else 0.0 for a, b in zip(pd, md)]
        return _wilder(dx, p)
    raise ValueError("Unsupported market indicator.")


def _source(bars, timeframe, availability_seconds=5):
    step = domain.TIMEFRAMES[timeframe]
    if len(bars) > MAX_BARS:
        raise ValueError(f"At most {MAX_BARS} candles per source.")
    expanded, originals, available, previous = [], [], [], None
    times = []
    for b in bars:
        dt = _time(b["time"])
        if previous is not None and dt <= previous:
            raise ValueError("Source must be strictly time-ordered.")
        if int(dt.timestamp()) % step or dt.microsecond:
            raise ValueError("Source has an off-grid timestamp; no rounding allowed.")
        if previous is not None and (dt - previous).total_seconds() != step:
            expanded.append(None)
        originals.append(len(expanded))
        expanded.append(b)
        completed = dt + timedelta(seconds=step)
        at = _time(b["available_at"]) if b.get("available_at") else completed + timedelta(seconds=availability_seconds)
        if at < completed:
            raise ValueError("Source availability precedes candle completion.")
        if available and at <= available[-1]:
            raise ValueError("Source availability clocks must be ordered.")
        available.append(at)
        times.append(dt)
        previous = dt
    return {"bars": bars, "expanded": expanded, "originals": originals, "times": times, "available": available, "step": step, "timeframe": timeframe}


def _series(source, values):
    return {"source": source, "values": values}


def _asof(series, decisions):
    source = series["source"]
    compact = [series["values"][i] for i in source["originals"]]
    out = []
    for at in decisions:
        i = bisect_right(source["available"], at) - 1
        # A missing expected candle must not keep its predecessor fresh forever.
        if i < 0 or at >= source["available"][i] + timedelta(seconds=source["step"]):
            out.append(None)
        else:
            out.append(compact[i])
    return out


def _expanded_values(source, compact):
    output = [None] * len(source["expanded"])
    for i, value in zip(source["originals"], compact):
        output[i] = value
    return output


def evaluate_graph(spec, bars, *, auxiliary=None, availability_seconds=5):
    """Native-timeframe indicators are calculated before causal as-of alignment."""
    validation = domain.validate_strategy(spec)
    if not validation["valid"]:
        raise ValueError("Invalid strategy: " + "; ".join(e["message"] for e in validation["errors"]))
    base = _source(bars, spec["timeframe"], availability_seconds)
    decisions = [t + timedelta(seconds=base["step"] + availability_seconds) for t in base["times"]]
    sources = {f"{spec['symbol']}:{spec['timeframe']}": base}
    for key, value in (auxiliary or {}).items():
        tf = value.get("metadata", {}).get("timeframe", key.split(":")[-1])
        sources[key] = _source(value["bars"], tf, value.get("metadata", {}).get("availability_seconds", 5))
    nodes = {n["id"]: n for n in spec["nodes"]}
    incoming = {nid: {} for nid in nodes}
    for edge in spec["edges"]:
        incoming[edge["target"]][edge.get("targetHandle") or "input"] = edge["source"]
    remaining, order = set(nodes), []
    while remaining:
        ready = sorted(nid for nid in remaining if all(s in order for s in incoming[nid].values()))
        if not ready:
            raise ValueError("Cyclic strategy.")
        order.extend(ready)
        remaining.difference_update(ready)
    series, aligned = {}, {}
    market_kinds = {"atr", "adx", "stochastic", "donchian", "vwap", "obv", "mfi"}
    numeric_kinds = {"sma", "ema", "wma", "rsi", "macd", "bollinger", "volatility", "returns", "log_returns", "momentum", "rolling_high", "rolling_low", "zscore", "volatility_percentile"}
    for nid in order:
        node, links = nodes[nid], incoming[nid]
        kind = node["type"]
        p = {**domain.CATALOG[kind]["params"], **node.get("params", {})}
        if kind == "market":
            key = f"{p['symbol']}:{p['timeframe']}"
            if key not in sources:
                raise ValueError(f"Missing genuine source {key}; no market/timeframe substitution.")
            series[nid] = sources[key]
            aligned[nid] = [key] * len(bars)
            continue
        if kind in ("price", "volume", "trade_count") or kind in market_kinds:
            source = series[links["input"]] if "input" in links else base
            if kind in market_kinds:
                vals = _market_indicator(kind, source["expanded"], p)
            else:
                field = p["field"] if kind == "price" else "volume" if kind == "volume" else "number_of_trades"
                if any(b is not None and (not _finite(b.get(field))) for b in source["expanded"]):
                    raise ValueError(f"Source does not provide valid {field}; no fabricated values.")
                vals = [b[field] if b else None for b in source["expanded"]]
            series[nid] = _series(source, vals)
        elif kind in numeric_kinds:
            parent = series[links["input"]]
            series[nid] = _series(parent["source"], _numeric(kind, parent["values"], p, parent["source"]["step"]))
        else:
            vals = []
            if kind == "constant":
                vals = [p["value"]] * len(bars)
            elif kind in ("calendar", "time_window"):
                for at in decisions:
                    if kind == "calendar":
                        vals.append(at.hour if p["field"] == "hour" else at.weekday() if p["field"] == "weekday" else int(at.weekday() >= 5) if p["field"] == "weekend" else at.month)
                    else:
                        low, high = p["start_hour"], p["end_hour"]
                        vals.append(low <= at.hour < high if low <= high else at.hour >= low or at.hour < high)
            elif kind in ("enter_long", "exit_long", "not", "availability", "consecutive", "rolling_confirmation", "cooldown"):
                v = aligned[links["input"]]
                if kind in ("enter_long", "exit_long"):
                    vals = list(v)
                elif kind == "not":
                    vals = [not x if x is not None else None for x in v]
                elif kind == "availability":
                    vals = [x is not None for x in v]
                elif kind == "cooldown":
                    last = -p["bars"] - 1
                    for i, x in enumerate(v):
                        if i and (base["times"][i] - base["times"][i - 1]).total_seconds() != base["step"]:
                            last = -p["bars"] - 1
                        fire = x is True and i - last > p["bars"]
                        vals.append(fire if x is not None else None)
                        if fire:
                            last = i
                else:
                    expanded = _expanded_values(base, v)
                    count = p["period"] if kind == "consecutive" else p["minimum"]
                    average = legacy._sma(expanded, p["period"])
                    output = [value >= count / p["period"] if value is not None else None for value in average]
                    vals = [output[i] for i in base["originals"]]
            elif kind == "hold_cash":
                vals = [True] * len(bars)
            elif domain.CATALOG[kind]["category"] == "risk":
                vals = [None] * len(bars)
            elif kind == "conditional":
                vals = [None if c is None else a if c else b for c, a, b in zip(aligned[links["condition"]], aligned[links["a"]], aligned[links["b"]])]
            else:
                a, b = aligned[links["a"]], aligned[links["b"]]
                if kind == "correlation":
                    pairs = [(x, y) if x is not None and y is not None else None for x, y in zip(a, b)]
                    out = _correlation(_expanded_values(base, pairs), p["period"])
                    vals = [out[i] for i in base["originals"]]
                else:
                    for i, (x, y) in enumerate(zip(a, b)):
                        if x is None or y is None:
                            vals.append(None)
                        elif kind == "spread":
                            vals.append(x - y)
                        elif kind == "relative_strength":
                            vals.append(x / y if y != 0 else None)
                        elif kind in ("and", "or"):
                            vals.append(bool(x and y) if kind == "and" else bool(x or y))
                        elif kind in ("cross_above", "cross_below"):
                            if not i or a[i - 1] is None or b[i - 1] is None or (base["times"][i] - base["times"][i - 1]).total_seconds() != base["step"]:
                                vals.append(None)
                            else:
                                vals.append(x > y and a[i - 1] <= b[i - 1] if kind == "cross_above" else x < y and a[i - 1] >= b[i - 1])
                        else:
                            vals.append(x > y if kind == "gt" else x < y if kind == "lt" else x >= y if kind == "gte" else x <= y if kind == "lte" else x == y if kind == "eq" else abs(x - y) <= p["tolerance"])
            series[nid] = _series(base, _expanded_values(base, vals))
        aligned[nid] = _asof(series[nid], decisions)
    return aligned


def indicator_series(kind, bars, params=None, *, timeframe="4h"):
    """Chart adapter: list of {time,value}; null warm-up/gaps are preserved.

    The time is the input candle OPEN chart label. Its value is only available
    after that candle completes; it is not an intrabar signal timestamp.
    """
    if kind not in domain.CATALOG or domain.CATALOG[kind]["category"] != "indicator" or domain.CATALOG[kind]["status"] != "executable":
        raise ValueError("Select an executable indicator.")
    p = {**domain.CATALOG[kind]["params"], **(params or {})}
    s = domain.blank_strategy(timeframe=timeframe)
    n = {"id": "indicator", "type": kind, "params": p}
    s["nodes"] = [{"id": "price", "type": "price", "params": {"field": "close"}}, n, {"id": "cash", "type": "hold_cash", "params": {}}]
    if domain.CATALOG[kind]["inputs"].get("input") == "number":
        s["edges"] = [{"id": "input", "source": "price", "target": "indicator", "targetHandle": "input"}]
    elif "a" in domain.CATALOG[kind]["inputs"]:
        raise ValueError("Pair indicators require an explicit strategy/source pair.")
    out = evaluate_graph(s, bars)["indicator"]
    return [{"time": b["time"], "value": value} for b, value in zip(bars, out)]


def _configuration(config):
    if not isinstance(config, dict):
        raise ValueError("Backtest configuration must be an object.")
    mode = config.get("execution_mode", "full_bar_embargo")
    if mode not in ("full_bar_embargo", "next_bar_open_optimistic"):
        raise ValueError("Unsupported execution mode; finer-reference event execution is not connected.")
    c, start, end = legacy._configuration(config)
    c["execution_mode"] = mode
    c["availability_seconds"] = config.get("availability_seconds", 0 if mode == "next_bar_open_optimistic" else 5)
    if not _finite(c["availability_seconds"]) or not 0 <= c["availability_seconds"] <= 60:
        raise ValueError("availability_seconds must be in [0,60].")
    if mode == "next_bar_open_optimistic" and (c["availability_seconds"] != 0 or c["execution_delay_bars"] != 1):
        raise ValueError("Optimistic next-open mode requires zero assumed availability lag and delay=1.")
    return c, start, end


def _prepared_bars(dataset, end, step):
    if not isinstance(dataset, dict) or not isinstance(dataset.get("bars"), list) or not isinstance(dataset.get("metadata"), dict):
        raise ValueError("Select a genuine connected dataset or explicit demo dataset.")
    if len(dataset["bars"]) > MAX_BARS:
        raise ValueError(f"At most {MAX_BARS} source candles per local job.")
    result, rejected, prior = [], 0, None
    for raw in dataset["bars"]:
        if not isinstance(raw, dict):
            raise ValueError("Each candle must be an object.")
        try:
            dt = _time(raw["time"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Invalid candle timestamp.") from exc
        if prior is not None and dt <= prior:
            raise ValueError("Source must be strictly time-ordered with unique timestamps.")
        prior = dt
        if dt >= end:
            continue
        if raw.get("valid", True) is False or not all(_finite(raw.get(k)) for k in ("open", "high", "low", "close", "volume")):
            rejected += 1
            continue
        op, hi, lo, cl = (raw[k] for k in ("open", "high", "low", "close"))
        if min(op, hi, lo, cl) <= 0 or raw["volume"] < 0 or not lo <= min(op, cl) <= max(op, cl) <= hi or int(dt.timestamp()) % step or dt.microsecond:
            rejected += 1
            continue
        # Only fully completed candles enter signals/marking by the end cutoff.
        if dt + timedelta(seconds=step) > end:
            continue
        result.append({**raw, "time": _iso(dt)})
    return result, rejected


def _risk(spec):
    risk = {**domain.RISK_DEFAULTS, **spec.get("risk", {})}
    mapping = {"stop_loss": ("stop_loss_pct", "pct"), "take_profit": ("take_profit_pct", "pct"),
               "trailing_stop": ("trailing_stop_pct", "pct"), "max_holding_period": ("max_holding_bars", "bars"),
               "cooldown_after_loss": ("cooldown_after_loss_bars", "bars"), "max_trades_per_day": ("max_trades_per_day", "count"),
               "daily_loss_limit": ("daily_loss_limit_pct", "pct"), "risk_position_size": ("risk_per_trade_pct", "pct")}
    for node in spec["nodes"]:
        kind = node["type"]
        p = {**domain.CATALOG[kind]["params"], **node.get("params", {})}
        if kind in ("position_size", "max_exposure"):
            risk["max_exposure"] = min(risk["max_exposure"], p["fraction"])
        elif kind in mapping:
            name, key = mapping[kind]
            risk[name] = p[key]
        elif kind == "drawdown_pause":
            risk["drawdown_pause_pct"], risk["drawdown_pause_bars"] = p["pct"], p["bars"]
    return risk


def _metrics(equity, initial, closed, fees, slippage, exposure, elapsed, step):
    result = legacy._path_metrics(equity, initial, closed, fees, slippage, exposure, elapsed)
    rets, previous = [], initial
    peak, peak_time = initial, _time(equity[0]["time"]) - timedelta(seconds=step)
    longest, underwater = 0.0, False
    for point in equity:
        rets.append(point["equity"] / previous - 1 if previous else 0)
        previous = point["equity"]
        dt = _time(point["time"])
        if point["equity"] >= peak:
            if underwater:
                longest = max(longest, (dt - peak_time).total_seconds() / 86400)
            peak, peak_time = point["equity"], dt
            underwater = False
        else:
            underwater = True
            longest = max(longest, (dt - peak_time).total_seconds() / 86400)
    sd = statistics.stdev(rets) if len(rets) > 1 else 0
    contiguous = all((_time(b["time"]) - _time(a["time"])).total_seconds() == step for a, b in zip(equity, equity[1:]))
    result["sharpe"] = statistics.fmean(rets) / sd * math.sqrt(365 * 86400 / step) if contiguous and len(rets) >= 30 and sd > 1e-12 else None
    result["longest_drawdown_days"] = longest
    return result


def run_backtest(spec, dataset, config):
    validation = domain.validate_strategy(spec)
    if not validation["valid"]:
        raise ValueError("Invalid strategy: " + "; ".join(e["message"] for e in validation["errors"]))
    c, start, end = _configuration(config)
    meta = dataset.get("metadata", {}) if isinstance(dataset, dict) else {}
    if spec["symbol"] != meta.get("symbol") or spec["timeframe"] != meta.get("timeframe"):
        raise ValueError("Strategy and dataset symbol/timeframe must match exactly.")
    step = domain.TIMEFRAMES[spec["timeframe"]]
    bars, rejected = _prepared_bars(dataset, end, step)
    selected = [i for i, b in enumerate(bars) if _time(b["time"]) >= start]
    if len(selected) < 3:
        raise ValueError("Select at least three complete supported candles.")
    first = selected[0]
    bars = bars[:selected[-1] + 1]
    # Auxiliary sources also respect the end cutoff and their native validity.
    auxiliary = {}
    for key, source in dataset.get("auxiliary", {}).items():
        tf = source.get("metadata", {}).get("timeframe", key.split(":")[-1])
        if tf not in domain.TIMEFRAMES:
            raise ValueError("Unsupported auxiliary timeframe.")
        aux_bars, _ = _prepared_bars(source, end, domain.TIMEFRAMES[tf])
        auxiliary[key] = {**source, "bars": aux_bars}
    graph = evaluate_graph(spec, bars, auxiliary=auxiliary, availability_seconds=c["availability_seconds"])
    risk = _risk(spec)
    offset = c["execution_delay_bars"] + 1 if c["execution_mode"] == "full_bar_embargo" else 1
    trail_offset = 2 if c["execution_mode"] == "full_bar_embargo" else 1
    fee, slip = c["fee_bps"] / 10000, c["slippage_bps"] / 10000
    actions = {kind: [n["id"] for n in spec["nodes"] if n["type"] == kind] for kind in ("enter_long", "exit_long")}
    boolean_nodes = [n["id"] for n in spec["nodes"] if domain.CATALOG[n["type"]]["output"] == "boolean"]
    cash, quantity, peak = float(c["initial_cash"]), 0.0, float(c["initial_cash"])
    fees, slip_cost, exposure_sum = 0.0, 0.0, 0.0
    trades, current, equity, pending = [], None, [], {}
    segments, segment = [], 0
    for i, b in enumerate(bars):
        if i and (_time(b["time"]) - _time(bars[i - 1]["time"])).total_seconds() != step:
            segment += 1
        segments.append(segment)
    traces = {"schema_version": 1, "decisions": [], "orders": [], "account": [], "limits": deepcopy(TRACE_LIMITS),
              "truncated": False, "dropped": dict.fromkeys(TRACE_LIMITS, 0)}
    order_count, event_count = 0, 0
    canceled, warmup, unfilled_end = 0, 0, 0
    day, day_initial, day_entries, day_paused = None, cash, 0, False
    loss_pause_until, drawdown_pause_until = -1, -1
    trail_updates = {}
    benchmark_cash, benchmark_qty, benchmark_fees, benchmark_slip, benchmark_entry = cash, 0.0, 0.0, 0.0, None
    benchmark_origin = first

    def append_trace(kind, record):
        if len(traces[kind]) < TRACE_LIMITS[kind]:
            traces[kind].append(record)
        else:
            traces["truncated"] = True
            traces["dropped"][kind] += 1

    def state(mark=None):
        entry = current["entry_price"] if current else None
        return {"cash": cash, "quantity": quantity, "position": "long" if quantity > 0 else "cash",
                "stop_price": entry * (1 - risk["stop_loss_pct"] / 100) if entry and risk["stop_loss_pct"] else None,
                "take_profit_price": entry * (1 + risk["take_profit_pct"] / 100) if entry and risk["take_profit_pct"] else None,
                "trailing_stop_price": current.get("trailing_stop_price") if current else None,
                "unrealized_pnl": quantity * mark - current["entry_cost"] if current and mark else None}

    def order_event(order, status, **details):
        nonlocal event_count
        event_count += 1
        append_trace("orders", {**order, "event_id": f"e_{event_count}", "status": status, **details})

    def new_order(i, action, decision_id, reason):
        nonlocal order_count
        order_count += 1
        completed = _time(bars[i]["time"]) + timedelta(seconds=step)
        return {"id": f"o_{order_count}", "decision_id": decision_id, "trade_id": current["id"] if current else None,
                "action": action, "reason": reason, "signal_time": bars[i]["time"],
                "signal_completed_at": _iso(completed), "assumed_available_at": _iso(completed + timedelta(seconds=c["availability_seconds"])),
                "decision_time": _iso(completed + timedelta(seconds=c["availability_seconds"])),
                "eligible_at": _iso(_time(bars[i]["time"]) + timedelta(seconds=step * offset)), "signal_i": i,
                "execution_time": None, "reference_price": None, "fill_price": None, "quantity": None,
                "fee": None, "slippage_cost": None, "account_after": None, "time_precision": "open_reference"}

    def reject(order, reason, i):
        order_event(order, "rejected", reason=reason, observed_at=bars[i]["time"], account_after={"cash": cash, "quantity": quantity})

    def enter(i, order):
        nonlocal cash, quantity, current, fees, slip_cost, day_entries
        if quantity > 1e-14:
            reject(order, "already_invested_no_pyramiding", i)
            return
        if i <= loss_pause_until or i <= drawdown_pause_until or day_paused:
            reject(order, "risk_entry_pause", i)
            return
        if risk["max_trades_per_day"] is not None and day_entries >= risk["max_trades_per_day"]:
            reject(order, "maximum_entries_per_utc_day", i)
            return
        fraction = risk["max_exposure"]
        if risk["risk_per_trade_pct"] is not None:
            fraction = min(fraction, risk["risk_per_trade_pct"] / risk["stop_loss_pct"])
        if cash <= 0 or fraction <= 0:
            reject(order, "no_allocatable_cash", i)
            return
        ref, budget = bars[i]["open"], cash * fraction
        fill = ref * (1 + slip)
        quantity = budget / (fill * (1 + fee))
        cost, tx_fee = quantity * fill, quantity * fill * fee
        cash = max(0.0, cash - cost - tx_fee)
        impact = quantity * (fill - ref)
        fees += tx_fee
        slip_cost += impact
        current = {"id": f"t_{len(trades) + 1}", "entry_time": bars[i]["time"], "entry_i": i,
                   "signal_time": order["signal_time"], "signal_completed_at": order["signal_completed_at"],
                   "entry_decision_id": order["decision_id"], "entry_order_id": order["id"],
                   "entry_price": fill, "entry_reference_price": ref, "exit_time": None, "exit_price": None,
                   "quantity": quantity, "net_pnl": None, "fees": tx_fee, "slippage_cost": impact,
                   "status": "open", "exit_reason": None, "entry_cost": cost + tx_fee,
                   "observed_high": fill, "trailing_stop_price": fill * (1 - risk["trailing_stop_pct"] / 100) if risk["trailing_stop_pct"] else None}
        trades.append(current)
        day_entries += 1
        order_event(order, "executed", trade_id=current["id"], execution_time=bars[i]["time"], reference_price=ref,
                    fill_price=fill, quantity=quantity, fee=tx_fee, slippage_cost=impact, account_after={"cash": cash, "quantity": quantity})

    def exit_position(i, ref, reason, order=None, interval=False):
        nonlocal cash, quantity, current, fees, slip_cost, loss_pause_until, order_count
        if quantity <= 1e-14 or current is None:
            if order:
                reject(order, "no_position_to_exit", i)
            return
        if order is None:
            order_count += 1
            order = {"id": f"o_{order_count}", "decision_id": current["entry_decision_id"], "trade_id": current["id"],
                     "action": "exit", "reason": reason, "signal_time": current["signal_time"],
                     "decision_time": current["entry_time"], "eligible_at": current["entry_time"],
                     "risk_level_committed_before_interval": True}
        fill, qty = ref * (1 - slip), quantity
        revenue, tx_fee = qty * fill, qty * fill * fee
        cash += revenue - tx_fee
        impact = qty * (ref - fill)
        fees += tx_fee
        slip_cost += impact
        pnl = revenue - tx_fee - current["entry_cost"]
        current.update(exit_time=bars[i]["time"], exit_price=fill, exit_reference_price=ref, net_pnl=pnl,
                       fees=current["fees"] + tx_fee, slippage_cost=current["slippage_cost"] + impact,
                       status="closed", exit_reason=reason, exit_order_id=order["id"],
                       exit_decision_id=order.get("decision_id"),
                       exit_time_precision="bar_interval" if interval else "open_reference")
        interval_end = _iso(_time(bars[i]["time"]) + timedelta(seconds=step)) if interval else None
        if interval:
            current["exit_interval_end"] = interval_end
        order_event(order, "executed", trade_id=current["id"], execution_time=bars[i]["time"], reference_price=ref,
                    fill_price=fill, quantity=qty, fee=tx_fee, slippage_cost=impact, account_after={"cash": cash, "quantity": 0.0},
                    time_precision="bar_interval" if interval else "open_reference", interval_end=interval_end)
        if pnl < 0 and risk["cooldown_after_loss_bars"]:
            loss_pause_until = i + risk["cooldown_after_loss_bars"]
        quantity, current = 0.0, None

    for i in range(first, len(bars)):
        bar = bars[i]
        dt = _time(bar["time"])
        same_segment = i == 0 or segments[i] == segments[i - 1]
        if day != dt.date():
            day, day_initial, day_entries, day_paused = dt.date(), cash + quantity * bar["open"], 0, False
        update = trail_updates.pop(i, None)
        if update and current and update["trade_id"] == current["id"] and segments[update["signal_i"]] == segments[i]:
            current["trailing_stop_price"] = max(current["trailing_stop_price"] or 0, update["price"])
        order = pending.pop(i, None)
        if order:
            if segments[order["signal_i"]] != segments[i]:
                canceled += 1
                order_event(order, "cancelled", reason="source_gap_between_signal_and_execution", observed_at=bar["time"])
            elif order["action"] == "exit":
                exit_position(i, bar["open"], order["reason"], order)
            else:
                enter(i, order)
        if benchmark_entry is None:
            if i > first and not same_segment:
                benchmark_origin = i
            if i >= benchmark_origin + offset and segments[benchmark_origin] == segments[i]:
                fill = bar["open"] * (1 + slip)
                benchmark_qty = benchmark_cash / (fill * (1 + fee))
                benchmark_fees = benchmark_qty * fill * fee
                benchmark_slip = benchmark_qty * (fill - bar["open"])
                benchmark_cash, benchmark_entry = 0.0, bar["time"]
        # A threshold was committed before this interval. OHLC cannot establish
        # the actual intrabar time/path: adverse-first is an assumption.
        if current and same_segment:
            levels = state()
            stop = max(x for x in (levels["stop_price"], levels["trailing_stop_price"]) if x is not None) if any(x is not None for x in (levels["stop_price"], levels["trailing_stop_price"])) else None
            take = levels["take_profit_price"]
            if stop is not None and bar["low"] <= stop:
                reason = "trailing_stop" if levels["trailing_stop_price"] is not None and stop == levels["trailing_stop_price"] and (levels["stop_price"] is None or stop > levels["stop_price"]) else "stop_loss"
                exit_position(i, min(bar["open"], stop), reason, interval=True)
            elif take is not None and bar["high"] >= take:
                exit_position(i, take, "take_profit", interval=True)
        value = cash + quantity * bar["close"]
        peak = max(peak, value)
        drawdown = max(0.0, (1 - value / peak) * 100)
        if risk["daily_loss_limit_pct"] and value <= day_initial * (1 - risk["daily_loss_limit_pct"] / 100):
            day_paused = True
        if risk["drawdown_pause_pct"] and drawdown >= risk["drawdown_pause_pct"] and i > drawdown_pause_until:
            drawdown_pause_until = i + risk["drawdown_pause_bars"]
        entries, exits = [graph[k][i] for k in actions["enter_long"]], [graph[k][i] for k in actions["exit_long"]]
        if entries and all(x is None for x in entries):
            warmup += 1
        holding_exit = current is not None and risk["max_holding_bars"] is not None and i - current["entry_i"] + 1 >= risk["max_holding_bars"]
        action = "exit" if any(x is True for x in exits) or holding_exit else "enter" if any(x is True for x in entries) else None
        completed = dt + timedelta(seconds=step)
        decision_id = f"d_{i}"
        append_trace("decisions", {"id": decision_id, "bar_index": i, "bar_time": bar["time"],
                                  "signal_completed_at": _iso(completed), "assumed_available_at": _iso(completed + timedelta(seconds=c["availability_seconds"])),
                                  "decision_time": _iso(completed + timedelta(seconds=c["availability_seconds"])),
                                  "knowledge_cutoff": _iso(completed), "node_values": {k: graph[k][i] for k in graph},
                                  "true_conditions": [k for k in boolean_nodes if graph[k][i] is True],
                                  "false_conditions": [k for k in boolean_nodes if graph[k][i] is False], "action": action,
                                  "state": {**state(bar["close"]), "daily_entry_pause": day_paused, "loss_pause_until_bar": loss_pause_until,
                                            "drawdown_pause_until_bar": drawdown_pause_until}})
        # Do not invent a new order for repeated hold signals or pyramid.
        applicable = action == "exit" and quantity > 0 or action == "enter" and quantity == 0
        if applicable and not any(o["action"] == action for o in pending.values()):
            reason = "maximum_holding_period" if holding_exit else "signal"
            order = new_order(i, action, decision_id, reason)
            order_event(order, "submitted")
            due = i + offset
            if due < len(bars):
                pending[due] = order
            else:
                unfilled_end += 1
                order_event(order, "cancelled", reason="no_future_execution_reference")
        if current and risk["trailing_stop_pct"]:
            current["observed_high"] = max(current["observed_high"], bar["high"])
            trail_updates[i + trail_offset] = {"trade_id": current["id"], "signal_i": i,
                                                "price": current["observed_high"] * (1 - risk["trailing_stop_pct"] / 100)}
        marked = quantity * bar["close"]
        exposure_sum += marked / value if value else 0
        point = {"time": _iso(completed), "equity": value, "cash": cash, "holdings": marked, "quantity": quantity,
                 "drawdown_pct": drawdown, "benchmark_equity": benchmark_cash + benchmark_qty * bar["close"], "price": bar["close"]}
        point["fixed_half_equity"] = .5 * c["initial_cash"] + .5 * point["benchmark_equity"]
        equity.append(point)
        append_trace("account", {**point, **state(bar["close"])})
    if current:
        current["unrealized_pnl"] = quantity * bars[-1]["close"] - current["entry_cost"]
        current["marked_value"] = quantity * bars[-1]["close"]
    closed = [t for t in trades if t["status"] == "closed"]
    elapsed = (_time(equity[-1]["time"]) - _time(bars[first]["time"])).total_seconds() / 86400
    metrics = _metrics(equity, c["initial_cash"], closed, fees, slip_cost, exposure_sum / len(equity), elapsed, step)
    metrics.update(open_trades=sum(t["status"] == "open" for t in trades), entries=len(trades))
    expected = int((_time(bars[-1]["time"]) - _time(bars[first]["time"])).total_seconds() / step) + 1
    requested = max(1, math.ceil((end - start).total_seconds() / step))
    gaps = sum(segments[i] != segments[i - 1] for i in range(first + 1, len(bars)))
    warnings = list(validation["warnings"])
    if meta.get("source_type") == "synthetic_demo":
        warnings.append("SYNTHETIC DEMONSTRATION: generated candles are not historical market evidence.")
    if c["execution_mode"] == "next_bar_open_optimistic":
        warnings.append("OPTIMISTIC ZERO-LATENCY MODE: same-boundary next-open price assumes instantaneous candle availability; not an executable fill.")
    if gaps or rejected:
        warnings.append("Gaps/invalid rows reset indicators and cancel cross-gap orders. First post-gap candle cannot certify missing intragap stops or risk.")
    if metrics["open_trades"]:
        warnings.append("Final inventory remains open and marked; no fabricated liquidation or exit fees.")
    if len(closed) < 30:
        warnings.append("Fewer than 30 closed trades; summaries are unstable and not independent evidence.")
    if traces["truncated"]:
        warnings.append("Trace storage cap reached. Dropped records are counted; decisions outside retained trace coverage cannot be reconstructed from future information.")
    if len(equity) < requested:
        warnings.append("Requested-calendar coverage is incomplete; actual source support is reported separately.")
    assumptions = [
        "Long-only Spot, zero cash interest; no shorts, leverage, derivatives funding, borrow, order-book depth or certified executable quotes.",
        f"Mode {c['execution_mode']}: signal completes at bar i end; assumed availability +{c['availability_seconds']}s; reference open i+{offset}. Open reference is not a fill certification.",
        "Indicators on auxiliary markets/timeframes are calculated on native completed bars, then mapped as-of decision time. Unavailable/partial higher candles never enter signals.",
        "Risk allocation is a cash fraction at entry, not continuous exposure targeting. Risk-to-stop sizing ignores gap-loss protection; gaps can exceed the stated risk budget.",
        "Stops/takes use OHLC envelopes under adverse-first intrabar ordering and worse gap-open stop prices. Actual intrabar execution time/order is unknown.",
        f"Trailing levels use only completed observed highs and activate {trail_offset} candle opens later; they never use the current candle high to tighten a stop within that same candle.",
        "Daily-loss/drawdown limits pause future entries; they do not force exits or promise a maximum portfolio loss. Holding-period exits obey the selected execution delay.",
        "Source gaps reset indicator state and cancel pending cross-gap orders. Existing inventory remains marked; intragap behavior is unknown.",
        "Gross return adds actual same-quantity modeled fees/slippage back to net equity; it is not a reinvested zero-cost counterfactual.",
        "Terminal inventory is marked, not forced into an unsupported sale. Historical selections, edits, comparisons and sensitivity remain retrospective.",
    ]
    result = {"metrics": metrics, "equity": equity, "trades": trades, "traces": traces,
              "monthly": legacy._period_returns(equity, c["initial_cash"]), "annual": legacy._period_returns(equity, c["initial_cash"], True),
              "returns": [{"time": p["time"], "return_pct": (p["equity"] / (equity[i - 1]["equity"] if i else c["initial_cash"]) - 1) * 100} for i, p in enumerate(equity)],
              "benchmarks": {"cash": {"final_equity": c["initial_cash"], "net_return_pct": 0},
                             "fixed_initial_half": {"final_equity": equity[-1]["fixed_half_equity"],
                                                    "net_return_pct": (equity[-1]["fixed_half_equity"] / c["initial_cash"] - 1) * 100,
                                                    "fees": .5 * benchmark_fees, "slippage_cost": .5 * benchmark_slip,
                                                    "entry_time": benchmark_entry, "initial_fraction": .5, "terminal_inventory_marked": True,
                                                    "description": "Fixed initial 50% asset / 50% zero-interest cash, no rebalance; identical reference clock and linear fees/slippage. Not an ex-post risk match; no exchange quantity filters certified."},
                             "buy_hold": {"final_equity": equity[-1]["benchmark_equity"], "net_return_pct": (equity[-1]["benchmark_equity"] / c["initial_cash"] - 1) * 100,
                                          "fees": benchmark_fees, "slippage_cost": benchmark_slip, "entry_time": benchmark_entry, "terminal_inventory_marked": True,
                                          "description": "Same initial capital, cost assumptions and explicit execution clock; passive 100% allocation. Risk/exposure may differ."}},
              "quality": {"warnings": warnings, "source_type": meta.get("source_type", "unknown"), "data_coverage_pct": min(100, 100 * len(equity) / requested),
                          "observed_span_coverage_pct": min(100, 100 * len(equity) / expected), "independent_evaluation": False, "assumptions": assumptions},
              "provenance": {"engine_version": ENGINE_VERSION, "schema_version": 2, "trace_schema_version": 1, "spec_sha256": _hash(spec), "config_sha256": _hash(c),
                             "dataset_id": meta.get("id"), "dataset_sha256": meta.get("sha256"), "source_type": meta.get("source_type", "unknown"),
                             "requested_start": c["start"], "requested_end": c["end"], "actual_start": bars[first]["time"], "actual_end": equity[-1]["time"],
                             "evaluated_bars": len(equity), "preperiod_context_bars": first, "warmup_bars": warmup, "gaps": gaps,
                             "invalid_rows_excluded": rejected, "cross_gap_orders_canceled": canceled, "signals_without_future_execution_bar": unfilled_end,
                             "signal_to_open_index_offset": offset, "assumed_availability_seconds": c["availability_seconds"],
                             "auxiliary_sources": {k: {"metadata": v.get("metadata", {}), "provenance": v.get("provenance", {})} for k, v in auxiliary.items()},
                             "source": deepcopy(dataset.get("provenance", {}))}, "config": c, "dataset": deepcopy(meta)}
    json.dumps(result, allow_nan=False)
    return result

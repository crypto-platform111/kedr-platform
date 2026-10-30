"""Bounded, typed v2 strategy data. No expressions or user code are evaluated."""
from copy import deepcopy
import json
import math

from . import domain_v1

TIMEFRAMES = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def _node(kind, category, output, inputs, ru, en, params=None, status="executable", requirements=None):
    return {"type": kind, "category": category, "output": output, "inputs": inputs,
            "name": {"ru": ru, "en": en}, "params": params or {}, "available": status == "executable",
            "status": status, "schema_versions": [2], "requirements": requirements or [],
            "availability_message": {"ru": "Нужен подлинный подключённый источник; исполнение недоступно.",
                                     "en": "A genuine connected source is required; execution unavailable."} if status != "executable" else None}


_CATALOG = deepcopy(domain_v1.node_catalog())
for item in _CATALOG:
    item.update(status="executable" if item["available"] else "provider_required", schema_versions=[1, 2], requirements=[])
    if not item["available"]:
        item["availability_message"] = {"ru": "Провайдер не подключён; ценовой прокси не подставляется.", "en": "Provider disconnected; no price proxy substituted."}

_CATALOG += [
    _node("trade_count", "market", "number", {"input": "market?"}, "Число сделок", "Trade count", requirements=["number_of_trades"]),
    _node("calendar", "market", "number", {}, "Календарь UTC", "UTC calendar", {"field": "hour"}),
    *[_node(k, "indicator", "number", {"input": "number"}, ru, en, {"period": p}) for k, ru, en, p in [
        ("wma", "Взвешенная средняя", "Weighted moving average", 20),
        ("log_returns", "Логарифмическая доходность, %", "Log return, %", 1),
        ("momentum", "Изменение цены", "Price momentum", 28),
        ("rolling_high", "Скользящий максимум", "Rolling maximum", 20),
        ("rolling_low", "Скользящий минимум", "Rolling minimum", 20),
        ("zscore", "Скользящий Z-score", "Rolling z-score", 28),
        ("volatility_percentile", "Исторический перцентиль", "Historical percentile", 100)]],
    _node("atr", "indicator", "number", {"input": "market?"}, "ATR", "ATR", {"period": 14}),
    _node("adx", "indicator", "number", {"input": "market?"}, "ADX / направленное движение", "ADX / directional movement", {"period": 14, "output": "adx"}),
    _node("stochastic", "indicator", "number", {"input": "market?"}, "Стохастический осциллятор", "Stochastic oscillator", {"period": 14, "smooth": 3, "output": "k"}),
    _node("donchian", "indicator", "number", {"input": "market?"}, "Канал Дончиана", "Donchian channel", {"period": 20, "output": "upper", "exclude_current": True}),
    _node("vwap", "indicator", "number", {"input": "market?"}, "VWAP по quote/base объёму", "Quote/base volume VWAP", {"period": 28}, requirements=["quote_volume", "volume"]),
    _node("obv", "indicator", "number", {"input": "market?"}, "Балансовый объём OBV", "On-balance volume"),
    _node("mfi", "indicator", "number", {"input": "market?"}, "Индекс денежного потока", "Money Flow Index", {"period": 14}),
    _node("correlation", "indicator", "number", {"a": "number", "b": "number"}, "Корреляция наблюдаемых рядов", "Observed-series correlation", {"period": 28}),
    _node("relative_strength", "indicator", "number", {"a": "number", "b": "number"}, "Относительная цена A/B", "Relative price A/B"),
    _node("spread", "market", "number", {"a": "number", "b": "number"}, "Разность A−B", "Difference A−B"),
    *[_node(k, "logic", "boolean", {"a": "number", "b": "number"}, ru, en) for k, ru, en in [
        ("gte", "Больше или равно", "Greater or equal"), ("lte", "Меньше или равно", "Less or equal"), ("eq", "Точное равенство", "Exact equality")]],
    _node("approximately_equal", "logic", "boolean", {"a": "number", "b": "number"}, "Приблизительное равенство", "Approximately equal", {"tolerance": 0.001}),
    _node("not", "logic", "boolean", {"input": "boolean"}, "НЕ", "NOT"),
    _node("consecutive", "logic", "boolean", {"input": "boolean"}, "Последовательные подтверждения", "Consecutive confirmations", {"period": 3}),
    _node("rolling_confirmation", "logic", "boolean", {"input": "boolean"}, "Подтверждения в окне", "Rolling confirmation", {"period": 5, "minimum": 3}),
    _node("cooldown", "logic", "boolean", {"input": "boolean"}, "Интервал между сигналами", "Signal cooldown", {"bars": 6}),
    _node("time_window", "logic", "boolean", {}, "Окно решений UTC", "UTC decision window", {"start_hour": 0, "end_hour": 24}),
    _node("availability", "logic", "boolean", {"input": "number"}, "Данные доступны", "Data available"),
    _node("conditional", "logic", "number", {"condition": "boolean", "a": "number", "b": "number"}, "Условный выбор A/B", "Conditional A/B"),
    *[_node(k, "risk", "risk", {}, ru, en, p) for k, ru, en, p in [
        ("trailing_stop", "Трейлинг-стоп, %", "Trailing stop, %", {"pct": 5}),
        ("max_holding_period", "Максимум свечей в позиции", "Maximum holding bars", {"bars": 30}),
        ("cooldown_after_loss", "Пауза после убытка", "Cooldown after loss", {"bars": 6}),
        ("max_trades_per_day", "Максимум входов за день UTC", "Maximum entries per UTC day", {"count": 3}),
        ("daily_loss_limit", "Лимит дневного убытка, %", "Daily loss entry pause, %", {"pct": 3}),
        ("drawdown_pause", "Пауза входов при просадке", "Drawdown entry pause", {"pct": 10, "bars": 30}),
        ("risk_position_size", "Бюджет риска до стопа, %", "Risk-to-stop budget, %", {"pct": 1})]],
]

_EXTERNAL = [
    ("bid_ask_spread", "microstructure", "Спред bid/ask", "Bid/ask spread"),
    ("top_book_imbalance", "microstructure", "Дисбаланс лучших котировок", "Top-of-book imbalance"),
    ("depth_imbalance", "microstructure", "Дисбаланс глубины N", "Top-N depth imbalance"),
    ("order_flow_imbalance", "microstructure", "Дисбаланс потока заявок", "Order-flow imbalance"),
    ("aggressive_volume", "microstructure", "Агрессивный объём", "Aggressive buy/sell volume"),
    ("cumulative_volume_delta", "microstructure", "Кумулятивная дельта", "Cumulative volume delta"),
    ("microprice_deviation", "microstructure", "Отклонение микроцены", "Microprice deviation"),
    ("book_depth", "microstructure", "Глубина стакана", "Order-book depth"),
    ("liquidity_replenishment", "microstructure", "Восполнение ликвидности", "Liquidity replenishment"),
    ("trade_intensity", "microstructure", "Интенсивность сделок", "Trade intensity"),
    ("order_flow_acceleration", "microstructure", "Ускорение потока", "Order-flow acceleration"),
    ("basis", "derivatives", "Spot/perpetual базис", "Spot/perpetual basis"),
    ("mark_index_deviation", "derivatives", "Отклонение mark/index", "Mark/index deviation"),
    ("open_interest", "derivatives", "Открытый интерес", "Open interest"),
    ("oi_change", "derivatives", "Изменение OI", "OI change"),
    ("positioning_ratio", "derivatives", "Коэффициенты позиций", "Positioning ratios"),
    ("liquidation_events", "derivatives", "Биржевые ликвидации", "Exchange-labelled liquidations"),
    ("liquidation_intensity", "derivatives", "Интенсивность ликвидаций", "Liquidation intensity"),
    ("futures_premium", "derivatives", "Фьючерсная премия", "Futures premium"),
    ("news_event_frequency", "intelligence", "Частота новостных событий", "News event frequency"),
    ("ai_event_classification", "intelligence", "AI-классификация событий", "AI event classification"),
    ("event_risk", "intelligence", "Риск событий монеты", "Coin event risk"),
    ("ml_volatility", "intelligence", "Прогноз ML волатильности", "ML volatility forecast"),
    ("ml_adverse_movement", "intelligence", "Прогноз ML неблагоприятного движения", "ML adverse movement forecast"),
]
_CATALOG += [_node(k, c, "number", {}, ru, en, {"source_id": "", "field": k}, "provider_required", [k]) for k, c, ru, en in _EXTERNAL]
_CATALOG += [_node(k, "action", "action", {"input": "boolean"}, ru, en, status="unsupported") for k, ru, en in [
    ("enter_short", "Короткая позиция", "Enter short"), ("leverage", "Плечо", "Leverage"), ("portfolio_action", "Портфельное действие", "Portfolio action")]]
_CATALOG += [_node("state_flag", "logic", "boolean", {"input": "boolean"}, "Флаг состояния", "Stateful flag", {"name": "flag"}, "preview"),
             _node("freshness", "logic", "boolean", {}, "Свежесть источника", "Source freshness", {"max_age_seconds": 60}, "provider_required")]
CATALOG = {n["type"]: n for n in _CATALOG}
RISK_DEFAULTS = {"max_exposure": 1, "stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": None,
                 "max_holding_bars": None, "cooldown_after_loss_bars": 0, "max_trades_per_day": None,
                 "daily_loss_limit_pct": None, "drawdown_pause_pct": None, "drawdown_pause_bars": 30, "risk_per_trade_pct": None}


def node_catalog():
    return deepcopy(_CATALOG)


def blank_strategy(symbol="BTCUSDT", timeframe="4h"):
    return {"schema_version": 2, "symbol": symbol, "timeframe": timeframe, "nodes": [], "edges": [], "risk": deepcopy(RISK_DEFAULTS)}


def _finite(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def validate_strategy(spec, *, for_execution=True):
    errors, warnings = [], []
    def error(code, message, node_id=None, incomplete=False):
        if incomplete and not for_execution:
            return
        errors.append({"code": code, "message": message, **({"node_id": node_id} if node_id else {})})
    def result():
        structural = {"NO_ACTION", "MISSING_INPUT", "UNAVAILABLE"}
        return {"valid": not errors, "structural_valid": not any(e["code"] not in structural for e in errors), "errors": errors, "warnings": warnings, "schema_version": 2}
    if not isinstance(spec, dict):
        error("SPEC", "Strategy must be an object.")
        return result()
    if spec.get("schema_version") != 2:
        error("VERSION", "Select strategy schema version 2.")
    if spec.get("symbol") not in SYMBOLS:
        error("SYMBOL", "Select an allow-listed symbol.")
    if spec.get("timeframe") not in TIMEFRAMES:
        error("TIMEFRAME", "Select 1m, 5m, 15m, 1h, 4h or 1d; actual dataset support is checked separately.")
    nodes, edges = spec.get("nodes"), spec.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        error("GRAPH", "nodes and edges must be arrays.")
        return result()
    try:
        if len(json.dumps(spec, allow_nan=False)) > 150000:
            error("LIMIT", "Strategy exceeds 150,000 characters.")
    except (TypeError, ValueError, OverflowError):
        error("JSON", "Strategy must contain finite JSON values only.")
    if len(nodes) > 80 or len(edges) > 150:
        error("LIMIT", "Use at most 80 nodes and 150 connections.")
    by_id = {}
    for node in nodes:
        if not isinstance(node, dict):
            error("NODE", "Every node must be an object.")
            continue
        nid, kind = node.get("id"), node.get("type")
        if not isinstance(nid, str) or not nid or len(nid) > 80:
            error("NODE_ID", "Node ids must be strings of at most 80 characters.")
            continue
        if nid in by_id:
            error("DUPLICATE_ID", "Node ids must be unique.", nid)
        by_id[nid] = node
        if not isinstance(kind, str) or kind not in CATALOG:
            error("NODE_TYPE", "Unknown node type.", nid)
            continue
        definition = CATALOG[kind]
        if definition["status"] != "executable":
            error("UNAVAILABLE", f"{kind} is {definition['status']}; its source/accounting is disconnected.", nid, True)
        p = node.get("params", {})
        if not isinstance(p, dict):
            error("PARAMS", "Parameters must be an object.", nid)
            continue
        if set(p) - set(definition["params"]):
            error("PARAMS", "Unknown node parameter.", nid)
        for key in ("period", "fast", "slow", "signal", "smooth", "minimum", "bars", "count"):
            if key in p and (not isinstance(p[key], int) or isinstance(p[key], bool) or not 1 <= p[key] <= (10000 if key == "bars" else 500)):
                error("PERIOD", f"{key} must be a bounded positive integer.", nid)
        if kind == "macd" and _finite(p.get("fast", 12)) and _finite(p.get("slow", 26)) and p.get("fast", 12) >= p.get("slow", 26):
            error("MACD", "Fast period must be smaller than slow period.", nid)
        if kind == "constant" and (not _finite(p.get("value", 50)) or abs(p.get("value", 50)) > 1e12):
            error("NUMBER", "Constant must be finite and bounded by 1e12.", nid)
        if kind == "market" and (p.get("symbol", spec.get("symbol")) not in SYMBOLS or p.get("timeframe", spec.get("timeframe")) not in TIMEFRAMES):
            error("MARKET", "Use an allow-listed symbol and timeframe.", nid)
        choices = {"price": ("field", ("open", "high", "low", "close"), "close"), "calendar": ("field", ("hour", "weekday", "weekend", "month"), "hour"),
                   "macd": ("output", ("line", "signal", "histogram"), "line"), "bollinger": ("output", ("upper", "middle", "lower"), "upper"),
                   "donchian": ("output", ("upper", "middle", "lower"), "upper"), "stochastic": ("output", ("k", "d"), "k"), "adx": ("output", ("adx", "plus_di", "minus_di"), "adx")}
        if kind in choices:
            key, allowed, default = choices[kind]
            if p.get(key, default) not in allowed:
                error("OUTPUT", f"{key} must be one of {allowed}.", nid)
        for key, low, high, exclusive in (("fraction", 0, 1, False), ("pct", 0, 100, True), ("stddev", 0, 10, True), ("tolerance", 0, 1e6, False)):
            if key in p and (not _finite(p[key]) or not (low < p[key] <= high if exclusive else low <= p[key] <= high)):
                error("NUMBER", f"{key} is outside numeric bounds.", nid)
        if kind == "rolling_confirmation" and isinstance(p.get("minimum", 3), int) and isinstance(p.get("period", 5), int) and p.get("minimum", 3) > p.get("period", 5):
            error("CONFIRMATION", "minimum cannot exceed period.", nid)
        if kind == "donchian" and not isinstance(p.get("exclude_current", True), bool):
            error("PARAMS", "exclude_current must be Boolean.", nid)
        if kind == "time_window":
            for key, default, high in (("start_hour", 0, 23), ("end_hour", 24, 24)):
                if not isinstance(p.get(key, default), int) or isinstance(p.get(key, default), bool) or not 0 <= p.get(key, default) <= high:
                    error("TIME_WINDOW", "UTC hours must be bounded integers.", nid)
    incoming, outgoing = {k: {} for k in by_id}, {k: [] for k in by_id}
    indegree, edge_ids = dict.fromkeys(by_id, 0), set()
    for edge in edges:
        if not isinstance(edge, dict):
            error("EDGE", "Every edge must be an object.")
            continue
        eid, source, target = edge.get("id"), edge.get("source"), edge.get("target")
        if not isinstance(eid, str) or not eid or eid in edge_ids:
            error("EDGE_ID", "Edges need unique nonempty string ids.")
        edge_ids.add(str(eid))
        if not isinstance(source, str) or not isinstance(target, str) or source not in by_id or target not in by_id:
            error("EDGE_NODE", "Connection refers to a missing node.")
            continue
        sk, tk = by_id[source].get("type"), by_id[target].get("type")
        if not isinstance(sk, str) or not isinstance(tk, str) or sk not in CATALOG or tk not in CATALOG:
            continue
        port = edge.get("targetHandle") or "input"
        if not isinstance(port, str):
            error("TARGET_PORT", "Input port must be a string.", target)
            continue
        expected = CATALOG[tk]["inputs"].get(port)
        if edge.get("sourceHandle") not in (None, "out"):
            error("SOURCE_PORT", "Only out is supported.", source)
        if expected is None:
            error("TARGET_PORT", "Unknown target port.", target)
        elif CATALOG[sk]["output"] != expected.rstrip("?"):
            error("PORT_TYPE", f"{port} requires {expected.rstrip('?')}.", target)
        if port in incoming[target]:
            error("MULTIPLE_INPUT", "Each input accepts only one connection.", target)
        incoming[target][port] = source
        outgoing[source].append(target)
        indegree[target] += 1
    for nid, node in by_id.items():
        kind = node.get("type")
        if isinstance(kind, str) and kind in CATALOG:
            for port, typ in CATALOG[kind]["inputs"].items():
                if not typ.endswith("?") and port not in incoming[nid]:
                    error("MISSING_INPUT", f"Connect {port}.", nid, True)
    queue, visited = [k for k, v in indegree.items() if v == 0], []
    while queue:
        nid = queue.pop(0)
        visited.append(nid)
        for target in outgoing[nid]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(visited) != len(by_id):
        error("CYCLE", "The graph must be acyclic.")
    kinds = [n.get("type") for n in by_id.values()]
    if not any(k in kinds for k in ("enter_long", "exit_long", "hold_cash")):
        error("NO_ACTION", "Add an entry, exit or cash action before running.", incomplete=True)
    if "hold_cash" in kinds and "enter_long" in kinds:
        error("CASH_CONFLICT", "Cash-only and entry actions cannot be combined.")
    for kind, definition in CATALOG.items():
        if definition["category"] == "risk" and kinds.count(kind) > 1:
            error("RISK_DUPLICATE", f"Use only one {kind} node.")
    risk = spec.get("risk", {})
    if not isinstance(risk, dict):
        error("RISK", "risk must be an object.")
    else:
        if set(risk) - set(RISK_DEFAULTS):
            error("RISK", "Unknown root risk field.")
        for key, value in risk.items():
            if value is None and key != "max_exposure":
                continue
            if key == "max_exposure":
                valid = _finite(value) and 0 <= value <= 1
            elif key.endswith("bars") or key == "max_trades_per_day":
                valid = isinstance(value, int) and not isinstance(value, bool) and (0 if key == "cooldown_after_loss_bars" else 1) <= value <= 10000
            else:
                valid = _finite(value) and 0 < value <= 100
            if not valid:
                error("RISK", f"Invalid {key}.")
        if (risk.get("risk_per_trade_pct") or "risk_position_size" in kinds) and not (risk.get("stop_loss_pct") or "stop_loss" in kinds):
            error("RISK_STOP", "Risk-to-stop sizing requires a positive stop-loss percentage.")
    if any(k in kinds for k in ("trailing_stop", "daily_loss_limit", "drawdown_pause")):
        warnings.append("Trailing levels use completed prior candles. Daily-loss/drawdown rules pause future entries; they never guarantee an intrabar loss cap.")
    return result()


def summarize_strategy(spec, locale="ru"):
    ru = locale != "en"
    by_id = {n["id"]: n for n in spec.get("nodes", []) if isinstance(n, dict) and isinstance(n.get("id"), str)}
    incoming = {nid: {} for nid in by_id}
    for e in spec.get("edges", []):
        if isinstance(e, dict) and e.get("target") in incoming:
            incoming[e["target"]][e.get("targetHandle") or "input"] = e.get("source")
    def describe(nid, depth=0):
        if depth > 12 or nid not in by_id:
            return "…" if depth > 12 else ("не подключено" if ru else "not connected")
        n = by_id[nid]
        name = CATALOG.get(n.get("type"), {}).get("name", {}).get("ru" if ru else "en", str(n.get("type")))
        params = ", ".join(f"{k}={v}" for k, v in n.get("params", {}).items())
        children = ", ".join(f"{p}: {describe(s, depth + 1)}" for p, s in incoming[nid].items())
        return f"{name}({'; '.join(x for x in (params, children) if x)})"
    return {"schema_version": spec.get("schema_version"), "locale": "ru" if ru else "en",
            "rules": [{"node_id": nid, "text": describe(nid)} for nid, n in by_id.items() if n.get("type") in ("enter_long", "exit_long", "hold_cash")],
            "risk": deepcopy(spec.get("risk", {})), "independent_validation": False}

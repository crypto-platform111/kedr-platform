"""The bounded, typed KEDR strategy language. No user code is evaluated."""
from __future__ import annotations

from copy import deepcopy
import math


def _definition(kind, category, output, inputs, ru, en, params=None, available=True):
    return {"type": kind, "category": category, "output": output, "inputs": inputs,
            "name": {"ru": ru, "en": en}, "params": params or {}, "available": available}


_CATALOG = [
    _definition("market", "market", "market", {}, "Рынок", "Market", {"symbol": "BTCUSDT", "timeframe": "4h"}),
    _definition("price", "market", "number", {"input": "market?"}, "Цена", "Price", {"field": "close"}),
    _definition("volume", "market", "number", {"input": "market?"}, "Объём", "Volume"),
    _definition("constant", "market", "number", {}, "Число", "Constant", {"value": 50}),
    _definition("sma", "indicator", "number", {"input": "number"}, "Скользящая средняя", "Simple moving average", {"period": 20}),
    _definition("ema", "indicator", "number", {"input": "number"}, "Экспоненциальная средняя", "Exponential moving average", {"period": 20}),
    _definition("rsi", "indicator", "number", {"input": "number"}, "RSI", "RSI", {"period": 14}),
    _definition("macd", "indicator", "number", {"input": "number"}, "MACD", "MACD", {"fast": 12, "slow": 26, "signal": 9, "output": "line"}),
    _definition("bollinger", "indicator", "number", {"input": "number"}, "Полосы Боллинджера", "Bollinger Bands", {"period": 20, "stddev": 2, "output": "upper"}),
    _definition("volatility", "indicator", "number", {"input": "number"}, "Историческая волатильность", "Historical volatility", {"period": 28}),
    _definition("returns", "indicator", "number", {"input": "number"}, "Изменение цены, %", "Price return, %", {"period": 1}),
    *[_definition(t, "logic", "boolean", {"a": "number", "b": "number"}, ru, en) for t, ru, en in [
        ("gt", "Больше", "Greater than"), ("lt", "Меньше", "Less than"),
        ("cross_above", "Пересекает вверх", "Crosses above"), ("cross_below", "Пересекает вниз", "Crosses below")]],
    _definition("and", "logic", "boolean", {"a": "boolean", "b": "boolean"}, "И", "AND"),
    _definition("or", "logic", "boolean", {"a": "boolean", "b": "boolean"}, "ИЛИ", "OR"),
    _definition("enter_long", "action", "action", {"input": "boolean"}, "Купить", "Enter long"),
    _definition("exit_long", "action", "action", {"input": "boolean"}, "Выйти в деньги", "Exit long"),
    _definition("hold_cash", "action", "action", {}, "Остаться в деньгах", "Hold cash"),
    _definition("position_size", "risk", "risk", {}, "Размер позиции", "Position size", {"fraction": 1}),
    _definition("max_exposure", "risk", "risk", {}, "Максимальная доля", "Maximum exposure", {"fraction": 1}),
    _definition("stop_loss", "risk", "risk", {}, "Стоп-лосс, %", "Stop loss, %", {"pct": 5}),
    _definition("take_profit", "risk", "risk", {}, "Тейк-профит, %", "Take profit, %", {"pct": 10}),
    *[_definition(t, "future", "number", {}, ru, en, available=False) for t, ru, en in [
        ("news_sentiment", "Тональность новостей", "News sentiment"),
        ("ml_prediction", "Прогноз ML", "ML prediction"),
        ("funding", "Фандинг / базис", "Funding / basis"),
        ("external_api", "Внешний API", "External API")]],
]
CATALOG = {item["type"]: item for item in _CATALOG}


def node_catalog():
    return deepcopy(_CATALOG)


def _finite(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except (ValueError, OverflowError):
        return False


def validate_strategy(spec):
    """Validate structure, parameter bounds, a DAG and every required typed port."""
    errors, warnings = [], []
    def error(code, message, node_id=None):
        e = {"code": code, "message": message}
        if node_id is not None:
            e["node_id"] = node_id
        errors.append(e)
    if not isinstance(spec, dict):
        return {"valid": False, "errors": [{"code": "SPEC", "message": "Strategy must be a JSON object."}], "warnings": []}
    if spec.get("schema_version") != 1:
        error("VERSION", "Only schema_version 1 is supported.")
    if spec.get("symbol") not in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        error("SYMBOL", "Select BTCUSDT, ETHUSDT or SOLUSDT.")
    if spec.get("timeframe") != "4h":
        error("TIMEFRAME", "The initial engine supports completed 4h candles.")
    nodes, edges = spec.get("nodes"), spec.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        error("GRAPH", "nodes and edges must be arrays.")
        return {"valid": False, "errors": errors, "warnings": warnings}
    if not 1 <= len(nodes) <= 100 or len(edges) > 200:
        error("LIMIT", "Use 1–100 nodes and no more than 200 connections.")
    by_id = {}
    for node in nodes:
        if not isinstance(node, dict):
            error("NODE", "Every node must be an object.")
            continue
        nid = node.get("id")
        if not isinstance(nid, str) or not nid or len(nid) > 80:
            error("NODE_ID", "Every node needs a short nonempty string id.")
            continue
        if nid in by_id:
            error("DUPLICATE_ID", "Node ids must be unique.", nid)
        by_id[nid] = node
        kind = node.get("type")
        if not isinstance(kind, str) or kind not in CATALOG:
            error("NODE_TYPE", "Unknown node type.", nid)
            continue
        if not CATALOG[kind]["available"]:
            error("UNAVAILABLE", "This provider node is not connected and cannot be backtested.", nid)
        p = node.get("params", {})
        if not isinstance(p, dict):
            error("PARAMS", "Node parameters must be an object.", nid)
            continue
        for key in ("period", "fast", "slow", "signal"):
            if key in p and (not isinstance(p[key], int) or isinstance(p[key], bool) or not 1 <= p[key] <= 500):
                error("PERIOD", f"{key} must be an integer from 1 to 500.", nid)
        if kind == "macd" and _finite(p.get("fast", 12)) and _finite(p.get("slow", 26)) and p.get("fast", 12) >= p.get("slow", 26):
            error("MACD", "The fast period must be smaller than the slow period.", nid)
        if kind == "constant" and (not _finite(p.get("value", 50)) or abs(p.get("value", 50)) > 1e12):
            error("NUMBER", "The constant must be a finite number with absolute value ≤ 1e12.", nid)
        if kind == "price" and p.get("field", "close") not in ("open", "high", "low", "close"):
            error("PRICE_FIELD", "Price field must be open, high, low or close.", nid)
        if kind == "bollinger":
            if not _finite(p.get("stddev", 2)) or not 0 < p.get("stddev", 2) <= 10:
                error("STDDEV", "Bollinger standard deviations must be in (0, 10].", nid)
            if p.get("output", "upper") not in ("upper", "middle", "lower"):
                error("OUTPUT", "Bollinger output must be upper, middle or lower.", nid)
        if kind == "macd" and p.get("output", "line") not in ("line", "signal", "histogram"):
            error("OUTPUT", "MACD output must be line, signal or histogram.", nid)
        if kind in ("position_size", "max_exposure") and (not _finite(p.get("fraction", 1)) or not 0 <= p.get("fraction", 1) <= 1):
            error("EXPOSURE", "Exposure fraction must be between 0 and 1; leverage is unavailable.", nid)
        if kind in ("stop_loss", "take_profit") and (not _finite(p.get("pct", 5 if kind == "stop_loss" else 10)) or not 0 < p.get("pct", 5 if kind == "stop_loss" else 10) <= 100):
            error("RISK", "Risk percentage must be in (0, 100].", nid)
        if kind == "market" and (p.get("symbol", spec.get("symbol")) != spec.get("symbol") or p.get("timeframe", "4h") != "4h"):
            error("MARKET", "Market node must match the strategy symbol and 4h timeframe.", nid)
    incoming = {nid: {} for nid in by_id}
    outgoing = {nid: [] for nid in by_id}
    indegree = {nid: 0 for nid in by_id}
    edge_ids = set()
    for edge in edges:
        if not isinstance(edge, dict):
            error("EDGE", "Every connection must be an object.")
            continue
        eid = edge.get("id")
        if not isinstance(eid, str) or not eid or eid in edge_ids:
            error("EDGE_ID", "Connections need unique nonempty ids.")
        edge_ids.add(str(eid))
        source, target = edge.get("source"), edge.get("target")
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
            error("SOURCE_PORT", "Only the out source port is supported.", source)
        if expected is None:
            error("TARGET_PORT", f"Node has no {port} input port.", target)
        elif CATALOG[sk]["output"] != expected.rstrip("?"):
            error("PORT_TYPE", f"{port} requires {expected.rstrip('?')}, received {CATALOG[sk]['output']}.", target)
        if port in incoming[target]:
            error("MULTIPLE_INPUT", "Each input port accepts only one connection.", target)
        incoming[target][port] = source
        outgoing[source].append(target)
        indegree[target] += 1
    for nid, node in by_id.items():
        if isinstance(node.get("type"), str) and node.get("type") in CATALOG:
            for port, typ in CATALOG[node["type"]]["inputs"].items():
                if not typ.endswith("?") and port not in incoming[nid]:
                    error("MISSING_INPUT", f"Connect the {port} input.", nid)
    queue = [nid for nid in by_id if indegree[nid] == 0]
    visited = []
    while queue:
        nid = queue.pop(0)
        visited.append(nid)
        for target in outgoing[nid]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    if len(visited) != len(by_id):
        error("CYCLE", "Feedback loops are not allowed. The strategy graph must be acyclic.")
    actions = [n for n in by_id.values() if n.get("type") in ("enter_long", "exit_long", "hold_cash")]
    if not actions:
        error("NO_ACTION", "Add an entry, exit or cash action.")
    kinds = [n.get("type") for n in by_id.values()]
    if "hold_cash" in kinds and "enter_long" in kinds:
        error("CASH_CONFLICT", "A cash-only strategy cannot also enter a position.")
    for risk_type in ("position_size", "max_exposure", "stop_loss", "take_profit"):
        if kinds.count(risk_type) > 1:
            error("RISK_DUPLICATE", f"Use at most one {risk_type} node.")
    risk = spec.get("risk", {})
    if not isinstance(risk, dict):
        error("RISK", "risk must be an object.")
    else:
        exposure = risk.get("max_exposure", 1)
        if not _finite(exposure) or not 0 <= exposure <= 1:
            error("EXPOSURE", "Maximum exposure must be between 0 and 1.")
        for key in ("stop_loss_pct", "take_profit_pct"):
            val = risk.get(key)
            if val is not None and (not _finite(val) or not 0 < val <= 100):
                error("RISK", f"{key} must be null or a percentage in (0, 100].")
    if any(k in kinds for k in ("position_size", "max_exposure", "stop_loss", "take_profit")):
        warnings.append("Risk nodes are static: exposure uses the minimum of root risk and risk-node fractions; explicit stop/take nodes override the root percentages.")
    if "enter_long" in kinds and "exit_long" not in kinds and not any(k in kinds for k in ("stop_loss", "take_profit")) and not any(spec.get("risk", {}).get(k) for k in ("stop_loss_pct", "take_profit_pct") if isinstance(spec.get("risk", {}), dict)):
        warnings.append("There is no exit signal; any final position will remain marked at the last close.")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def _node(nid, kind, x, y, **params):
    return {"id": nid, "type": kind, "params": params, "position": {"x": x, "y": y}}


def _edge(source, target, port="input"):
    return {"id": source + "_" + target + "_" + port, "source": source, "target": target, "sourceHandle": "out", "targetHandle": port}


def templates():
    risk = {"max_exposure": 1, "stop_loss_pct": None, "take_profit_pct": None}
    def item(tid, ru, en, dru, den, nodes, edges):
        return {"id": tid, "name": {"ru": ru, "en": en}, "description": {"ru": dru, "en": den},
                "spec": {"schema_version": 1, "symbol": "BTCUSDT", "timeframe": "4h", "nodes": nodes, "edges": edges, "risk": deepcopy(risk)}}
    price = _node("price", "price", 40, 180, field="close")
    ma_nodes = [price, _node("fast", "sma", 280, 70, period=20), _node("slow", "sma", 280, 290, period=60),
                _node("up", "cross_above", 520, 70), _node("down", "cross_below", 520, 290),
                _node("entry", "enter_long", 760, 70), _node("exit", "exit_long", 760, 290)]
    ma_edges = [_edge("price", "fast"), _edge("price", "slow"), _edge("fast", "up", "a"), _edge("slow", "up", "b"),
                _edge("fast", "down", "a"), _edge("slow", "down", "b"), _edge("up", "entry"), _edge("down", "exit")]
    rsi_nodes = [price, _node("rsi", "rsi", 260, 170, period=14), _node("low", "constant", 260, 10, value=30),
                 _node("high", "constant", 260, 340, value=70), _node("oversold", "lt", 500, 70),
                 _node("overbought", "gt", 500, 280), _node("entry", "enter_long", 740, 70), _node("exit", "exit_long", 740, 280)]
    rsi_edges = [_edge("price", "rsi"), _edge("rsi", "oversold", "a"), _edge("low", "oversold", "b"),
                 _edge("rsi", "overbought", "a"), _edge("high", "overbought", "b"), _edge("oversold", "entry"), _edge("overbought", "exit")]
    trend_nodes = [price, _node("trend", "sma", 270, 270, period=200), _node("above", "gt", 510, 70),
                   _node("below", "lt", 510, 280), _node("entry", "enter_long", 750, 70), _node("exit", "exit_long", 750, 280)]
    trend_edges = [_edge("price", "trend"), _edge("price", "above", "a"), _edge("trend", "above", "b"),
                   _edge("price", "below", "a"), _edge("trend", "below", "b"), _edge("above", "entry"), _edge("below", "exit")]
    bh_nodes = [_node("one", "constant", 80, 60, value=1), _node("zero", "constant", 80, 240, value=0),
                _node("always", "gt", 350, 130), _node("entry", "enter_long", 620, 130)]
    bh_edges = [_edge("one", "always", "a"), _edge("zero", "always", "b"), _edge("always", "entry")]
    return [
        item("ma_crossover", "Пересечение средних", "MA crossover", "Учебное пересечение SMA20 и SMA60; параметры не оптимизированы.", "Educational SMA20/SMA60 crossover; parameters are not optimized.", ma_nodes, ma_edges),
        item("rsi_threshold", "Возврат RSI", "RSI threshold", "Вход при RSI14 ниже 30, выход выше 70. Учебный пример.", "Enter below RSI14 30 and exit above 70. Educational example.", rsi_nodes, rsi_edges),
        item("simple_trend", "Следование тренду", "Simple trend", "Цена относительно SMA200 четырёхчасовых свечей. Это не 200-дневное правило.", "Price relative to a 200-bar 4h SMA. This is not a 200-day rule.", trend_nodes, trend_edges),
        item("buy_hold", "Купить и держать", "Buy and hold", "Один вход после задержки исполнения; конечная позиция оценивается по цене закрытия.", "One delayed entry; final inventory is marked at the closing reference.", bh_nodes, bh_edges),
        item("cash", "Денежный ориентир", "Cash benchmark", "Средства остаются в USDT с нулевой доходностью.", "Stay in USDT with zero cash interest.", [_node("cash", "hold_cash", 250, 150)], []),
    ]

"""Numerical and causal v2 checks; no network or protected reservations."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math

import pytest

from backend.app import domain, engine, engine_v1
from backend.app.domain_v2 import CATALOG


def dataset(prices, timeframe="4h", gap_at=None):
    step = domain.TIMEFRAMES[timeframe]
    origin = datetime(2023, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i, p in enumerate(prices):
        time = origin + timedelta(seconds=step * (i + (1 if gap_at is not None and i >= gap_at else 0)))
        bars.append({"time": time.isoformat().replace("+00:00", "Z"), "open": p, "high": p + 1,
                     "low": p - 1, "close": p, "volume": 2.0, "quote_volume": 2 * p,
                     "number_of_trades": 7, "valid": True})
    return {"metadata": {"id": "unit", "symbol": "BTCUSDT", "timeframe": timeframe,
                         "source_type": "synthetic_demo", "sha256": "unit"}, "bars": bars, "provenance": {}}


def spec():
    s = deepcopy(next(t["spec"] for t in domain.templates() if t["id"] == "buy_hold"))
    s["schema_version"] = 2
    return s


def config(**kwargs):
    return {"start": "2023-01-01", "end": "2023-12-31", "initial_cash": 1000,
            "fee_bps": 0, "slippage_bps": 0, "execution_delay_bars": 1, **kwargs}


def edge(a, b, port="input"):
    return {"id": f"{a}_{b}_{port}", "source": a, "target": b, "targetHandle": port}


def indicator(kind, bars, **params):
    return [p["value"] for p in engine.indicator_series(kind, bars, params)]


def test_empty_v2_is_safe_draft_but_not_runnable_and_original_templates_stay_v1():
    empty = domain.blank_strategy()
    assert not empty["nodes"] and not empty["edges"]
    assert domain.validate_strategy(empty, for_execution=False)["valid"]
    assert not domain.validate_strategy(empty)["valid"]
    assert all(t["spec"]["schema_version"] == 1 for t in domain.templates())
    with pytest.raises(ValueError, match="Add an entry"):
        engine.run_backtest(empty, dataset([100] * 5), config())


def test_expanded_catalog_has_truthful_availability_and_does_not_execute_missing_data():
    assert len(domain.node_catalog()) > 75
    assert all(n["status"] in ("executable", "provider_required", "preview", "unsupported") for n in domain.node_catalog())
    for kind in ("liquidation_events", "funding", "order_flow_imbalance", "ml_prediction", "enter_short"):
        s = spec()
        s["nodes"].append({"id": "missing", "type": kind, "params": {}})
        assert any(e["code"] == "UNAVAILABLE" for e in domain.validate_strategy(s)["errors"])
        with pytest.raises(ValueError):
            engine.run_backtest(s, dataset([100] * 5), config())


@pytest.mark.parametrize("kind,params", [("sma", {"period": 1000000000}), ("wma", {"period": True}),
                                        ("atr", {"period": -1}), ("rsi", {"unknown": 3}),
                                        ("donchian", {"exclude_current": "yes"})])
def test_bad_indicator_params_fail_before_computation(kind, params):
    with pytest.raises(ValueError, match="Invalid strategy"):
        engine.indicator_series(kind, dataset([100] * 10)["bars"], params)


def test_legacy_dispatch_is_unchanged_and_new_modes_do_not_reinterpret_v1():
    old = deepcopy(next(t["spec"] for t in domain.templates() if t["id"] == "buy_hold"))
    d = dataset([100, 100, 120, 80, 90])
    assert engine.run_backtest(old, d, config()) == engine_v1.run_backtest(old, d, config())
    assert engine.run_backtest(old, d, config())["provenance"]["engine_version"] == "kedr-candle-1.0.0"
    assert "traces" not in engine.run_backtest(old, d, config())


def test_wma_and_prior_channel_exact_numeric_values():
    bars = dataset([10, 20, 30, 100])["bars"]
    assert indicator("wma", bars, period=3) == [None, None, 140 / 6, 380 / 6]
    # Previous three highs: 11,21,31; current 101 cannot raise its own break.
    assert indicator("donchian", bars, period=3, output="upper", exclude_current=True) == [None, None, None, 31]
    assert indicator("donchian", bars, period=3, output="lower", exclude_current=True)[-1] == 9
    assert indicator("rolling_high", bars, period=2)[-1] == 100


def test_atr_includes_overnight_gap_and_wilder_smoothing():
    bars = dataset([10, 20, 22, 23])["bars"]
    # TR:2,11,3,2. Wilder period2 gives6.5,4.75,3.375.
    assert indicator("atr", bars, period=2) == [None, 6.5, 4.75, 3.375]


def test_directional_movement_mfi_obv_and_stochastic():
    bars = dataset([10, 12, 14, 16, 18, 20])["bars"]
    assert indicator("adx", bars, period=2, output="adx")[-1] == 100
    assert indicator("adx", bars, period=2, output="minus_di")[-1] == 0
    assert indicator("mfi", bars, period=2)[-1] == 100
    assert indicator("obv", bars) == [0, 2, 4, 6, 8, 10]
    assert indicator("stochastic", bars, period=2)[-1] == 75


def test_vwap_requires_quote_base_and_uses_actual_quote_not_close_proxy():
    bars = dataset([10, 20, 30])["bars"]
    bars[0].update(quote_volume=100, volume=10)
    bars[1].update(quote_volume=500, volume=20)
    assert indicator("vwap", bars, period=2)[1] == 20
    # Close-weighted proxy would give(10*10+20*20)/30=16.67, not20.
    del bars[2]["quote_volume"]
    with pytest.raises(ValueError, match="genuine quote_volume"):
        indicator("vwap", bars, period=2)


def test_log_returns_percentile_and_timeframe_specific_volatility():
    bars = dataset([100, 110, 121, 100])["bars"]
    assert indicator("log_returns", bars, period=2)[2] == pytest.approx(100 * math.log(1.21))
    assert indicator("volatility_percentile", bars, period=2)[2] == 100
    assert indicator("volatility_percentile", bars, period=2)[3] == 0
    daily = dataset([100, 110, 121, 100], "1d")["bars"]
    a = indicator("volatility", bars, period=3)[-1]
    b = engine.indicator_series("volatility", daily, {"period": 3}, timeframe="1d")[-1]["value"]
    assert a / b == pytest.approx(math.sqrt(6))


def test_higher_timeframe_indicators_use_native_windows_and_only_completed_bars():
    base = dataset([100] * 20)
    daily = dataset([10, 20, 1000], "1d")
    s = domain.blank_strategy()
    s["nodes"] = [{"id": "daily", "type": "market", "params": {"symbol": "BTCUSDT", "timeframe": "1d"}},
                  {"id": "price", "type": "price", "params": {"field": "close"}},
                  {"id": "avg", "type": "sma", "params": {"period": 2}}, {"id": "cash", "type": "hold_cash", "params": {}}]
    s["edges"] = [edge("daily", "price"), edge("price", "avg")]
    out = engine.evaluate_graph(s, base["bars"], auxiliary={"BTCUSDT:1d": daily})
    assert all(x is None for x in out["avg"][:11])
    assert out["avg"][11:17] == [15] * 6
    assert out["avg"][17] == 510
    changed = deepcopy(daily)
    changed["bars"][2]["close"] = 1000000
    after = engine.evaluate_graph(s, base["bars"], auxiliary={"BTCUSDT:1d": changed})
    assert after["avg"][:17] == out["avg"][:17]
    with pytest.raises(ValueError, match="Missing genuine source"):
        engine.evaluate_graph(s, base["bars"])


def test_unknown_higher_source_receipt_before_completion_is_rejected():
    s = spec()
    daily = dataset([10, 20, 30], "1d")
    daily["bars"][0]["available_at"] = daily["bars"][0]["time"]
    with pytest.raises(ValueError, match="availability precedes"):
        engine.evaluate_graph(s, dataset([100] * 20)["bars"], auxiliary={"BTCUSDT:1d": daily})


def test_gap_resets_native_indicator_state_and_cancels_orders():
    d = dataset([100] * 8, gap_at=2)
    assert indicator("wma", d["bars"], period=3)[2:5] == [None, None, 100]
    result = engine.run_backtest(spec(), d, config())
    assert result["provenance"]["cross_gap_orders_canceled"] >= 1
    assert any(o["status"] == "cancelled" and o["reason"] == "source_gap_between_signal_and_execution" for o in result["traces"]["orders"])


def test_explicit_execution_modes_and_saved_signal_order_account_trace():
    d = dataset([100, 110, 120, 130, 140])
    r = engine.run_backtest(spec(), d, config())
    assert r["trades"][0]["entry_reference_price"] == 120
    dec = r["traces"]["decisions"][0]
    assert dec["signal_completed_at"] == "2023-01-01T04:00:00Z"
    assert dec["assumed_available_at"] == "2023-01-01T04:00:05Z"
    order = next(x for x in r["traces"]["orders"] if x["status"] == "executed")
    assert order["decision_id"] == dec["id"]
    assert order["eligible_at"] == "2023-01-01T08:00:00Z"
    assert order["execution_time"] == r["trades"][0]["entry_time"]
    assert order["quantity"] == r["trades"][0]["quantity"]
    assert order["account_after"]["cash"] == 0
    assert dec["node_values"]["always"] is True
    opt = engine.run_backtest(spec(), d, config(execution_mode="next_bar_open_optimistic", availability_seconds=0))
    assert opt["trades"][0]["entry_reference_price"] == 110
    assert any("ZERO-LATENCY" in w for w in opt["quality"]["warnings"])
    with pytest.raises(ValueError, match="zero assumed availability"):
        engine.run_backtest(spec(), d, config(execution_mode="next_bar_open_optimistic", availability_seconds=5))


def test_stop_take_adverse_first_and_account_cost_reconciliation():
    s = spec()
    s["risk"].update(stop_loss_pct=5, take_profit_pct=5)
    d = dataset([100] * 6)
    d["bars"][2].update(high=110, low=90)
    r = engine.run_backtest(s, d, config(fee_bps=10, slippage_bps=2))
    trade = r["trades"][0]
    assert trade["exit_reason"] == "stop_loss"
    assert trade["exit_time_precision"] == "bar_interval"
    events = [o for o in r["traces"]["orders"] if o["status"] == "executed"]
    assert sum(o["fee"] for o in events) == pytest.approx(r["metrics"]["fees"])
    assert sum(o["slippage_cost"] for o in events) == pytest.approx(r["metrics"]["slippage_cost"])
    assert all(p["equity"] == pytest.approx(p["cash"] + p["quantity"] * p["price"]) for p in r["equity"])


def test_trailing_stop_never_uses_same_bar_high_to_tighten():
    s = spec()
    s["nodes"].append({"id": "trail", "type": "trailing_stop", "params": {"pct": 10}})
    d = dataset([100] * 7)
    # Enterbar2 at100, committedstop90. high150 andlow99 must NOT
    # invent a same-bar trail135 stop, because intrabar path is unknown.
    d["bars"][2].update(high=150, low=99)
    d["bars"][3].update(open=140, high=141, low=139, close=140)
    d["bars"][4].update(open=140, high=141, low=130, close=140)
    r = engine.run_backtest(s, d, config())
    trade = r["trades"][0]
    assert trade["exit_time"] == d["bars"][4]["time"]
    assert trade["exit_reason"] == "trailing_stop"
    assert trade["exit_reference_price"] == 135


def test_risk_to_stop_allocation_and_holding_period_delayed_exit():
    s = spec()
    s["risk"].update(stop_loss_pct=10, risk_per_trade_pct=1, max_holding_bars=2)
    r = engine.run_backtest(s, dataset([100] * 9), config())
    t = r["trades"][0]
    assert t["quantity"] == 1
    assert t["exit_time"] == "2023-01-01T20:00:00Z"
    assert t["exit_reason"] == "maximum_holding_period"
    assert t["entry_time"] == "2023-01-01T08:00:00Z"


def test_loss_cooldown_and_entry_frequency_are_enforced_not_only_visual():
    s = spec()
    s["risk"].update(stop_loss_pct=5, cooldown_after_loss_bars=3, max_trades_per_day=1)
    d = dataset([100] * 15)
    d["bars"][2]["low"] = 90
    r = engine.run_backtest(s, d, config())
    assert r["trades"][0]["status"] == "closed"
    assert r["trades"][1]["entry_time"] >= "2023-01-02T00:00:00Z"
    assert any(o["status"] == "rejected" and o["reason"] in ("risk_entry_pause", "maximum_entries_per_utc_day") for o in r["traces"]["orders"])


def test_future_changes_cannot_change_saved_earlier_decisions_accounts_or_orders():
    s = deepcopy(next(t["spec"] for t in domain.templates() if t["id"] == "rsi_threshold"))
    s["schema_version"] = 2
    d = dataset([100 + math.sin(i / 4) * 10 for i in range(150)])
    before = engine.run_backtest(s, d, config())
    changed = deepcopy(d)
    for bar in changed["bars"][100:]:
        for field in ("open", "high", "low", "close"):
            bar[field] *= 2
    after = engine.run_backtest(s, changed, config())
    assert before["traces"]["decisions"][:100] == after["traces"]["decisions"][:100]
    assert before["traces"]["account"][:100] == after["traces"]["account"][:100]
    assert before["equity"][:100] == after["equity"][:100]


def test_daily_and_minute_engine_clocks_do_not_inherit_four_hour_metrics():
    for tf, expected in (("1m", "2023-01-01T00:02:00Z"), ("1d", "2023-01-03T00:00:00Z")):
        s = spec()
        s["timeframe"] = tf
        r = engine.run_backtest(s, dataset([100, 100, 100, 90, 90], tf), config())
        assert r["trades"][0]["entry_time"] == expected
        step = domain.TIMEFRAMES[tf]
        assert r["metrics"]["longest_drawdown_days"] == pytest.approx(2 * step / 86400)


def test_trace_caps_are_explicit_and_deterministic():
    s = spec()
    d = dataset([100] * 3010, "1m")
    s["timeframe"] = "1m"
    r = engine.run_backtest(s, d, config())
    assert len(r["traces"]["decisions"]) == 3000
    assert r["traces"]["dropped"]["decisions"] == 10
    assert r["traces"]["truncated"] is True
    assert any("Trace storage cap" in w for w in r["quality"]["warnings"])
    assert engine.run_backtest(s, d, config()) == r


def test_market_calendar_and_trade_count_are_real_and_time_explicit():
    s = domain.blank_strategy()
    s["nodes"] = [{"id": "trades", "type": "trade_count", "params": {}},
                  {"id": "hour", "type": "calendar", "params": {"field": "hour"}},
                  {"id": "window", "type": "time_window", "params": {"start_hour": 20, "end_hour": 8}},
                  {"id": "cash", "type": "hold_cash", "params": {}}]
    graph = engine.evaluate_graph(s, dataset([100] * 4)["bars"])
    assert graph["trades"] == [7] * 4
    assert graph["hour"] == [4, 8, 12, 16]
    assert graph["window"] == [True, False, False, False]


def test_fixed_initial_half_benchmark_has_actual_linear_costs_and_no_rebalance():
    r = engine.run_backtest(spec(), dataset([100, 100, 100, 120, 150]), config(fee_bps=10, slippage_bps=2))
    full, half = r["benchmarks"]["buy_hold"], r["benchmarks"]["fixed_initial_half"]
    assert half["fees"] == full["fees"] / 2
    assert half["slippage_cost"] == full["slippage_cost"] / 2
    assert half["final_equity"] == pytest.approx(500 + .5 * full["final_equity"])
    assert half["entry_time"] == full["entry_time"]
    assert all(p["fixed_half_equity"] == 500 + p["benchmark_equity"] / 2 for p in r["equity"])


def test_longest_drawdown_includes_recovery_interval_with_actual_timeframe():
    s = spec()
    s["timeframe"] = "1d"
    r = engine.run_backtest(s, dataset([100, 100, 100, 80, 100], "1d"), config())
    assert r["metrics"]["longest_drawdown_days"] == 2


def test_boolean_confirmations_not_availability_conditional_and_cooldowns():
    s = spec()
    s["nodes"] += [{"id": "seq", "type": "consecutive", "params": {"period": 3}},
                   {"id": "roll", "type": "rolling_confirmation", "params": {"period": 3, "minimum": 2}},
                   {"id": "no", "type": "not", "params": {}},
                   {"id": "cool", "type": "cooldown", "params": {"bars": 2}},
                   {"id": "choose", "type": "conditional", "params": {}},
                   {"id": "price", "type": "price", "params": {"field": "close"}},
                   {"id": "avg", "type": "sma", "params": {"period": 3}},
                   {"id": "avail", "type": "availability", "params": {}}]
    s["edges"] += [edge("always", n) for n in ("seq", "roll", "no", "cool")]
    s["edges"] += [edge("always", "choose", "condition"), edge("one", "choose", "a"), edge("zero", "choose", "b"),
                   edge("price", "avg"), edge("avg", "avail")]
    out = engine.evaluate_graph(s, dataset([100] * 8, gap_at=4)["bars"])
    assert out["seq"] == [None, None, True, True, None, None, True, True]
    assert out["roll"] == out["seq"]
    assert out["no"] == [False] * 8
    assert out["cool"] == [True, False, False, True, True, False, False, True]
    assert out["choose"] == [1] * 8
    assert out["avail"] == [False, False, True, True, False, False, True, True]


def test_realized_daily_loss_and_drawdown_pauses_reject_following_entries():
    for risk in ({"daily_loss_limit_pct": 4}, {"drawdown_pause_pct": 4, "drawdown_pause_bars": 3}):
        s = spec()
        s["risk"].update(stop_loss_pct=5, **risk)
        d = dataset([100] * 9)
        d["bars"][2]["low"] = 90
        r = engine.run_backtest(s, d, config())
        assert r["trades"][0]["exit_reason"] == "stop_loss"
        assert any(o["status"] == "rejected" and o["reason"] == "risk_entry_pause" for o in r["traces"]["orders"])
        assert any(x["state"]["daily_entry_pause"] or x["state"]["drawdown_pause_until_bar"] >= x["bar_index"] for x in r["traces"]["decisions"])


def test_correlation_matches_known_affine_series_and_relative_strength_uses_actual_values():
    s = domain.blank_strategy()
    s["nodes"] = [{"id": "close", "type": "price", "params": {"field": "close"}},
                  {"id": "high", "type": "price", "params": {"field": "high"}},
                  {"id": "corr", "type": "correlation", "params": {"period": 3}},
                  {"id": "relative", "type": "relative_strength", "params": {}},
                  {"id": "cash", "type": "hold_cash", "params": {}}]
    s["edges"] = [edge(a, n, p) for n in ("corr", "relative") for a, p in (("high", "a"), ("close", "b"))]
    d = dataset([100, 101, 103, 107, 104, 110])
    for b in d["bars"]:
        b["high"] = b["close"] * 2
    out = engine.evaluate_graph(s, d["bars"])
    assert out["corr"][:2] == [None, None]
    assert all(v == pytest.approx(1) for v in out["corr"][2:])
    assert out["relative"] == [2] * 6


def test_signal_exit_trade_links_to_the_saved_exit_decision_and_order():
    s = spec()
    s["nodes"] += [{"id": "hour", "type": "calendar", "params": {"field": "hour"}},
                   {"id": "threshold", "type": "constant", "params": {"value": 12}},
                   {"id": "exit_condition", "type": "gte", "params": {}},
                   {"id": "exit_action", "type": "exit_long", "params": {}}]
    s["edges"] += [edge("hour", "exit_condition", "a"), edge("threshold", "exit_condition", "b"),
                   edge("exit_condition", "exit_action")]
    r = engine.run_backtest(s, dataset([100] * 9), config())
    trade = next(t for t in r["trades"] if t["status"] == "closed")
    decision = next(d for d in r["traces"]["decisions"] if d["id"] == trade["exit_decision_id"])
    execution = next(o for o in r["traces"]["orders"] if o["id"] == trade["exit_order_id"] and o["status"] == "executed")
    assert decision["action"] == "exit" and decision["node_values"]["exit_condition"] is True
    assert execution["decision_id"] == trade["exit_decision_id"]
    assert execution["signal_time"] == decision["bar_time"]

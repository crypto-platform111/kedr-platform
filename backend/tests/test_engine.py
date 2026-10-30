from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math

import pytest

from backend.app.data import load_dataset, datasets
from backend.app.domain import templates, validate_strategy, node_catalog
from backend.app.engine import run_backtest, evaluate_graph, _sma, _ema, _rsi, _indicator, explain_result


def spec(template="buy_hold"):
    return deepcopy(next(t["spec"] for t in templates() if t["id"] == template))


def dataset(prices, gaps=None):
    start = datetime(2023, 1, 1, tzinfo=timezone.utc)
    bars = []
    for i, price in enumerate(prices):
        dt = start + timedelta(hours=4 * i + (4 if gaps and i >= gaps else 0))
        bars.append({"time": dt.isoformat(), "open": price, "close": price,
                     "high": price, "low": price, "volume": 100, "valid": True})
    return {"metadata": {"id": "test", "symbol": "BTCUSDT", "timeframe": "4h", "source_type": "synthetic_demo", "sha256": "test"},
            "bars": bars, "provenance": {"seed": 0}}


def config(**kwargs):
    return {"start": "2023-01-01", "end": "2023-12-31", "initial_cash": 1000,
            "fee_bps": 0, "slippage_bps": 0, "execution_delay_bars": 1, **kwargs}


def test_all_templates_are_valid_typed_graphs():
    assert len(templates()) == 5
    assert all(validate_strategy(t["spec"])["valid"] for t in templates())
    assert all("name" in n and "inputs" in n and "available" in n for n in node_catalog())


def test_graph_rejects_wrong_port_types_and_missing_inputs():
    s = spec()
    s["edges"][0]["target"] = "entry"
    s["edges"][0]["targetHandle"] = "input"
    errors = validate_strategy(s)["errors"]
    assert any(e["code"] == "PORT_TYPE" for e in errors)
    assert any(e["code"] == "MISSING_INPUT" for e in errors)


def test_graph_rejects_cycles_and_duplicate_nodes():
    s = spec("ma_crossover")
    s["edges"].append({"id": "cycle", "source": "fast", "target": "fast", "targetHandle": "input"})
    assert any(e["code"] == "CYCLE" for e in validate_strategy(s)["errors"])
    s = spec()
    s["nodes"].append(deepcopy(s["nodes"][0]))
    assert not validate_strategy(s)["valid"]


def test_unavailable_nodes_do_not_generate_fake_data():
    s = spec()
    s["nodes"].append({"id": "future", "type": "funding", "params": {}})
    assert any(e["code"] == "UNAVAILABLE" for e in validate_strategy(s)["errors"])
    with pytest.raises(ValueError):
        run_backtest(s, dataset([100] * 8), config())


@pytest.mark.parametrize("mutation", [
    lambda s: s["nodes"][0].update(type={"bad": 1}),
    lambda s: s["edges"][0].update(source=[]),
    lambda s: s["edges"][0].update(targetHandle={"bad": 1}),
    lambda s: s.update(risk=[]),
])
def test_malformed_graphs_return_validation_errors(mutation):
    s = spec()
    mutation(s)
    assert not validate_strategy(s)["valid"]


def test_bad_period_does_not_crash_validator():
    s = spec()
    s["nodes"].append({"id": "bad_macd", "type": "macd", "params": {"fast": "12", "slow": 26}})
    assert not validate_strategy(s)["valid"]


def test_indicator_numerical_definitions_and_warmup():
    assert _sma([1, 2, 3, 4], 3) == [None, None, 2, 3]
    assert _ema([1, 2, 3, 4], 3) == [None, None, 2, 3]
    assert _rsi([1, 2, 3, 4], 3) == [None, None, None, 100]
    assert _rsi([4, 3, 2, 1], 3)[-1] == 0
    assert _rsi([4, 4, 4, 4], 3)[-1] == 50
    assert _indicator("returns", [100, 110, 121], {"period": 2})[-1] == pytest.approx(21)
    assert _indicator("bollinger", [1, 2, 3], {"period": 3, "stddev": 2, "output": "upper"})[-1] == pytest.approx(2 + 2 * math.sqrt(2 / 3))


def test_completed_signal_is_filled_at_open_i_plus_two():
    r = run_backtest(spec(), dataset([100, 110, 120, 130, 140]), config())
    trade = r["trades"][0]
    assert trade["entry_time"] == "2023-01-01T08:00:00Z"
    assert trade["entry_reference_price"] == 120
    assert trade["signal_completed_at"] == "2023-01-01T04:00:00Z"
    assert r["equity"][0]["equity"] == 1000
    assert r["equity"][1]["equity"] == 1000
    assert r["metrics"]["final_equity"] == pytest.approx(1000 / 120 * 140)


def test_zero_delay_execution_is_disabled():
    with pytest.raises(ValueError, match="Zero-delay"):
        run_backtest(spec(), dataset([100] * 10), config(execution_delay_bars=0))


def test_cash_and_open_position_metrics_are_honest():
    cash = run_backtest(spec("cash"), dataset([100, 120, 80, 130, 150]), config())
    assert cash["metrics"]["net_return_pct"] == 0
    assert cash["metrics"]["sharpe"] is None
    assert cash["metrics"]["profit_factor"] is None
    assert cash["metrics"]["win_rate_pct"] is None
    invested = run_backtest(spec(), dataset([100] * 8), config(fee_bps=10, slippage_bps=2))
    assert invested["metrics"]["open_trades"] == 1
    assert invested["metrics"]["total_trades"] == 0
    assert invested["metrics"]["fees"] == pytest.approx(1000 * .001 / 1.001)
    assert invested["trades"][0]["exit_time"] is None
    assert any("Final inventory" in x for x in invested["quality"]["warnings"])


def test_fee_slippage_exposure_and_gross_addback_accounting():
    s = spec()
    s["risk"]["max_exposure"] = .4
    r = run_backtest(s, dataset([100] * 8), config(fee_bps=10, slippage_bps=2))
    trade = r["trades"][0]
    assert trade["quantity"] == pytest.approx(400 / (100 * 1.0002 * 1.001))
    assert r["equity"][-1]["cash"] == pytest.approx(600)
    assert r["metrics"]["gross_return_pct"] == pytest.approx(0, abs=1e-12)
    assert r["metrics"]["final_equity"] + r["metrics"]["fees"] + r["metrics"]["slippage_cost"] == pytest.approx(1000)


def test_closed_trade_costs_reconstruct_cash_exactly():
    s = spec()
    s["risk"]["stop_loss_pct"] = 10
    d = dataset([100, 100, 100, 80])
    r = run_backtest(s, d, config(fee_bps=10, slippage_bps=2))
    trade = r["trades"][0]
    q = 1000 / (100 * 1.0002 * 1.001)
    expected = q * 80 * .9998 * .999
    assert r["metrics"]["final_equity"] == pytest.approx(expected)
    assert trade["net_pnl"] == pytest.approx(expected - 1000)
    assert r["equity"][-1]["cash"] == pytest.approx(expected)
    assert r["equity"][-1]["quantity"] == 0


def test_stop_first_if_stop_and_take_both_touched():
    s = spec()
    s["risk"].update(stop_loss_pct=5, take_profit_pct=10)
    d = dataset([100] * 5)
    d["bars"][2].update(high=120, low=80)
    r = run_backtest(s, d, config())
    assert r["trades"][0]["exit_reason"] == "stop_loss"
    assert r["trades"][0]["exit_price"] == pytest.approx(95)
    assert r["trades"][0]["net_pnl"] == pytest.approx(-50)


def test_stop_gap_down_gets_worse_open_and_take_gets_no_improvement():
    s = spec()
    s["risk"]["stop_loss_pct"] = 5
    d = dataset([100, 100, 100, 80, 80])
    r = run_backtest(s, d, config())
    assert r["trades"][0]["exit_price"] == 80
    s["risk"] = {"max_exposure": 1, "take_profit_pct": 10}
    d = dataset([100, 100, 100, 120, 120])
    r = run_backtest(s, d, config())
    assert r["trades"][0]["exit_price"] == pytest.approx(110)


def test_static_risk_node_precedence_is_conservative():
    s = spec()
    s["risk"].update(max_exposure=.7, stop_loss_pct=20)
    s["nodes"].extend([{"id": "size", "type": "position_size", "params": {"fraction": .3}},
                        {"id": "stop", "type": "stop_loss", "params": {"pct": 5}}])
    d = dataset([100] * 5)
    d["bars"][2].update(low=90)
    r = run_backtest(s, d, config())
    assert r["trades"][0]["quantity"] == 3
    assert r["trades"][0]["exit_price"] == 95


def test_gap_cancels_pending_order_and_resets_rolling_context():
    d = dataset([100] * 8, gaps=2)
    r = run_backtest(spec(), d, config())
    assert r["provenance"]["cross_gap_orders_canceled"] == 2
    assert r["trades"][0]["entry_time"] == "2023-01-01T20:00:00Z"
    assert r["quality"]["data_coverage_pct"] < 100
    assert r["metrics"]["sharpe"] is None
    s = spec("ma_crossover")
    next(n for n in s["nodes"] if n["id"] == "fast")["params"]["period"] = 3
    graph = evaluate_graph(s, d["bars"])
    assert graph["fast"][2] is None
    assert graph["fast"][3] is None
    assert graph["fast"][4] == 100


def test_buy_hold_template_matches_passive_control_with_costs_and_gap():
    d = dataset([100, 101, 99, 102, 104, 103, 105, 107], gaps=2)
    r = run_backtest(spec(), d, config(fee_bps=10, slippage_bps=2))
    assert all(p["equity"] == pytest.approx(p["benchmark_equity"]) for p in r["equity"])


def test_source_gap_does_not_manufacture_stop_fill():
    s = spec()
    s["risk"]["stop_loss_pct"] = 5
    d = dataset([100, 100, 100, 80], gaps=3)
    r = run_backtest(s, d, config())
    assert r["trades"][0]["status"] == "open"
    assert r["equity"][-1]["equity"] == 800


def test_drawdown_duration_preserves_elapsed_calendar_time_across_gap():
    d = dataset([100, 100, 100, 80, 80], gaps=3)
    r = run_backtest(spec(), d, config())
    # Last high is marked at 12:00; final marked boundary is 24:00. The
    # unobserved 12:00–16:00 gap must not be discarded from elapsed duration.
    assert r["metrics"]["longest_drawdown_days"] == pytest.approx(.5)
    assert r["metrics"]["sharpe"] is None


def test_future_candle_changes_do_not_change_earlier_indicators_or_equity():
    d = dataset([100 + math.sin(i / 3) * 10 for i in range(150)])
    s = spec("rsi_threshold")
    before = evaluate_graph(s, d["bars"])
    r1 = run_backtest(s, d, config())
    changed = deepcopy(d)
    for b in changed["bars"][100:]:
        for k in ("open", "high", "low", "close"):
            b[k] *= 2
    after = evaluate_graph(s, changed["bars"])
    r2 = run_backtest(s, changed, config())
    assert all(before[nid][:100] == after[nid][:100] for nid in before)
    assert r1["equity"][:100] == r2["equity"][:100]


def test_drawdown_and_monthly_returns_reconstruct_equity():
    d = dataset([100, 100, 100, 120, 90, 100])
    r = run_backtest(spec(), d, config())
    assert r["metrics"]["max_drawdown_pct"] == pytest.approx(25)
    multiplier = math.prod(1 + row["return_pct"] / 100 for row in r["monthly"])
    assert multiplier * 1000 == pytest.approx(r["metrics"]["final_equity"])
    assert sum(t.get("net_pnl") or 0 for t in r["trades"]) == 0


def test_calendar_periods_assign_midnight_close_to_preceding_month():
    d = dataset([100] * 190)
    r = run_backtest(spec("cash"), d, config())
    assert r["monthly"][0]["period"] == "2023-01"
    assert r["annual"][0]["period"] == "2023"
    assert r["quality"]["data_coverage_pct"] < r["quality"]["observed_span_coverage_pct"]


def test_final_cash_plus_inventory_matches_equity_for_all_templates():
    d = load_dataset("demo_btc_4h")
    for template in templates():
        r = run_backtest(template["spec"], d, config(fee_bps=10, slippage_bps=2))
        assert all(p["cash"] >= -1e-8 and p["quantity"] >= 0 for p in r["equity"])
        assert all(p["equity"] == pytest.approx(p["cash"] + p["holdings"]) for p in r["equity"])
        assert sum(t["fees"] for t in r["trades"]) == pytest.approx(r["metrics"]["fees"])
        assert sum(t["slippage_cost"] for t in r["trades"]) == pytest.approx(r["metrics"]["slippage_cost"])
        if all(t["status"] == "closed" for t in r["trades"]):
            assert sum(t["net_pnl"] for t in r["trades"]) == pytest.approx(r["metrics"]["final_equity"] - 1000)


def test_determinism_serialization_and_offline_analyst():
    d = load_dataset("demo_btc_4h")
    r1 = run_backtest(spec("ma_crossover"), d, config())
    r2 = run_backtest(spec("ma_crossover"), d, config())
    assert r1 == r2
    json.dumps(r1, allow_nan=False)
    assert explain_result(r1, "ru")["mode"] == "offline_rules"
    assert explain_result(r1, "en")["provider_status"] == "not_configured"
    assert not r1["quality"]["independent_evaluation"]


def test_unicode_strategy_hash_matches_immutable_version_canonical_encoding():
    s = spec()
    for node in s["nodes"]:
        node["id"] = "узел_" + node["id"]
    for edge in s["edges"]:
        edge["source"] = "узел_" + edge["source"]
        edge["target"] = "узел_" + edge["target"]
    r = run_backtest(s, dataset([100] * 8), config())
    canonical = json.dumps(s, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    expected = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert r["provenance"]["spec_sha256"] == expected


def test_symbol_mismatch_unknown_source_and_bad_order_fail_closed():
    with pytest.raises(ValueError, match="Unknown dataset"):
        load_dataset("nonexistent")
    d = dataset([100] * 8)
    d["metadata"]["symbol"] = "ETHUSDT"
    with pytest.raises(ValueError, match="match"):
        run_backtest(spec(), d, config())
    d = dataset([100] * 8)
    d["bars"][2], d["bars"][3] = d["bars"][3], d["bars"][2]
    with pytest.raises(ValueError, match="time-ordered"):
        run_backtest(spec(), d, config())


@pytest.mark.local_archives
def test_historical_allowlist_is_verified_and_excludes_2026():
    all_meta = datasets()
    historical = [m for m in all_meta if m["id"] in {"verified_btc_4h", "verified_eth_4h", "verified_sol_4h"}]
    assert len(historical) == 3
    for meta in historical:
        assert meta["verified"] and meta["status"] == "available"
        d = load_dataset(meta["id"])
        assert len(d["provenance"]["source_files"]) == 48
        assert d["bars"][0]["time"].startswith("2022-")
        assert all(b["time"] < "2026" for b in d["bars"])
        assert all("-2026-" not in f["name"] for f in d["provenance"]["source_files"])
        digest = hashlib.sha256(json.dumps(d["bars"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        assert digest == meta["sha256"]

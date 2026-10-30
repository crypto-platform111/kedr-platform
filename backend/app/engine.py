"""Version-dispatched deterministic engines; v1 saved runs retain exact semantics."""
from . import engine_v1, engine_v2
from .engine_v1 import _sma, _ema, _rsi, _indicator, _time, _iso, _configuration

ENGINE_VERSION = engine_v1.ENGINE_VERSION
ENGINE_VERSIONS = {1: engine_v1.ENGINE_VERSION, 2: engine_v2.ENGINE_VERSION}
indicator_series = engine_v2.indicator_series


def evaluate_graph(spec, bars, *, auxiliary=None, availability_seconds=5):
    if isinstance(spec, dict) and spec.get("schema_version") == 2:
        return engine_v2.evaluate_graph(spec, bars, auxiliary=auxiliary, availability_seconds=availability_seconds)
    return engine_v1.evaluate_graph(spec, bars)


def run_backtest(spec, dataset, config):
    if isinstance(spec, dict) and spec.get("schema_version") == 2:
        return engine_v2.run_backtest(spec, dataset, config)
    return engine_v1.run_backtest(spec, dataset, config)


def explain_result(result, locale="ru"):
    return engine_v1.explain_result(result, locale)

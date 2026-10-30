"""Small real historical ML experiment, executed only in a bounded child process.

All features and algorithms are fixed code. Input is data, never Python, shell,
an uploaded estimator or pickle. There is no trading or network adapter here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import statistics
import sys

VERSION = "kedr-ml-tabular-1.0.0"
GROUPS = {"momentum", "volatility", "calendar", "volume"}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def features_at(bars, index, groups, step):
    """Completed-bar-only inputs with a complete 42-return context."""
    if index < 42:
        return None
    window = bars[index - 42:index + 1]
    if any(not b.get("valid", True) for b in window):
        return None
    if any(b["timestamp"] - a["timestamp"] != step for a, b in zip(window, window[1:])):
        return None
    prices = [b["close"] for b in window]
    increments = [math.log(b / a) for a, b in zip(prices, prices[1:])]
    names, values = [], []
    if "momentum" in groups:
        for lookback in (1, 6, 42):
            names.append(f"close_log_momentum_{lookback}")
            values.append(math.log(prices[-1] / prices[-1 - lookback]))
    if "volatility" in groups:
        for lookback in (6, 42):
            names.append(f"log_past_variance_{lookback}")
            values.append(math.log(max(1e-12, sum(v * v for v in increments[-lookback:]) / lookback)))
    if "calendar" in groups:
        clock = datetime.fromtimestamp((bars[index]["timestamp"] + step) / 1000, timezone.utc)
        for name, value in (("hour_sin", math.sin(2 * math.pi * clock.hour / 24)),
                            ("hour_cos", math.cos(2 * math.pi * clock.hour / 24)),
                            ("weekday_sin", math.sin(2 * math.pi * clock.weekday() / 7)),
                            ("weekday_cos", math.cos(2 * math.pi * clock.weekday() / 7))):
            names.append(name)
            values.append(value)
    if "volume" in groups:
        average = statistics.mean(b["volume"] for b in window[:-1])
        names.append("completed_volume_to_prior_mean")
        values.append(math.log(max(1e-12, bars[index]["volume"] / max(average, 1e-12))))
    return names, values


def observations(bars, config):
    if not 100 <= len(bars) <= 20000:
        raise ValueError("ML requires 100–20,000 candles in the fixed historical scope.")
    groups = config["feature_groups"]
    if not groups or not set(groups) <= GROUPS:
        raise ValueError("Unsupported feature group.")
    horizon = config["horizon_bars"]
    if type(horizon) is not int or not 1 <= horizon <= 42:
        raise ValueError("Horizon must be 1–42 bars.")
    step = config["step_ms"]
    origins = []
    excluded = {"past_context_or_gap": 0, "future_gap": 0, "outside_dates": 0}
    feature_names = None
    # Commit a fixed stride before checking support. Reference starts i+2, so
    # a full completed-bar availability embargo separates the signal and fill reference.
    for i in range(42, len(bars) - horizon - 2, horizon):
        end = i + 2 + horizon
        decision_ms = bars[i]["timestamp"] + step + 5000
        decision = datetime.fromtimestamp(decision_ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z")
        origin = decision[:10]
        if origin < config["start"] or bars[end]["time"][:10] > config["end"]:
            excluded["outside_dates"] += 1
            continue
        item = features_at(bars, i, groups, step)
        if item is None:
            excluded["past_context_or_gap"] += 1
            continue
        path = bars[i:end + 1]
        if any(not b.get("valid", True) for b in path) or any(b["timestamp"] - a["timestamp"] != step for a, b in zip(path, path[1:])):
            excluded["future_gap"] += 1
            continue
        feature_names, x = item
        signed = math.log(bars[end]["open"] / bars[i + 2]["open"])
        origins.append({"bar_index": i, "label_end_index": end, "origin": decision, "signal_candle_open": bars[i]["time"],
                        "reference": bars[i + 2]["time"], "label_end": bars[end]["time"],
                        "features": x, "y": int(signed > 0) if config["target"] == "direction" else signed * 10000})
    if len(origins) < 120:
        raise ValueError("Insufficient complete nonoverlapping outcomes: at least 120 are required before splitting.")
    # Splits are committed from chronological origins, then crossing outcomes
    # and one full embargo bar are removed; boundaries never depend on classes.
    v, t = int(len(origins) * .60), int(len(origins) * .80)
    validation_start = origins[v]["bar_index"]
    test_start = origins[t]["bar_index"]
    train = [r for r in origins[:v] if r["label_end_index"] < validation_start - 1]
    validation = [r for r in origins[v:t] if r["label_end_index"] < test_start - 1]
    test = origins[t:]
    if len(train) < 60 or min(len(validation), len(test)) < 20:
        raise ValueError("Chronological training/validation/test capacity fails 60/20/20 floors after purging.")
    if config["target"] == "direction":
        for name, rows, floor in (("train", train, 10), ("validation", validation, 2), ("test", test, 2)):
            up = sum(r["y"] for r in rows)
            if min(up, len(rows) - up) < floor:
                raise ValueError(f"Insufficient classes in {name}; the split or class gate is not relaxed.")
    manifest = {"method": "fixed chronological 60/20/20 origins then label purge plus one-bar embargo",
                "origin_stride_bars": horizon, "reference_offset_bars": 2, "assumed_availability_seconds": 5, "horizon_bars": horizon,
                "exclusions": excluded, "committed_complete_origins": len(origins),
                "purged_origins": len(origins) - len(train) - len(validation) - len(test)}
    for key, rows in (("train", train), ("validation", validation), ("test", test)):
        manifest[key] = {"count": len(rows), "first_origin": rows[0]["origin"], "last_origin": rows[-1]["origin"],
                         "maximum_label_end": rows[-1]["label_end"], "up_count": sum(r["y"] for r in rows) if config["target"] == "direction" else None,
                         "origin_indices": [r["bar_index"] for r in rows], "maximum_label_end_index": rows[-1]["label_end_index"]}
    return feature_names, train, validation, test, manifest


def sigmoid(value):
    return 1 / (1 + math.exp(-max(-35, min(35, value))))


def auc(y, p):
    positives = sum(y)
    negatives = len(y) - positives
    if not positives or not negatives:
        return None
    ordered = sorted(zip(p, y))
    total, index = 0., 0
    while index < len(ordered):
        stop = index + 1
        while stop < len(ordered) and ordered[stop][0] == ordered[index][0]:
            stop += 1
        average_rank = (index + 1 + stop) / 2
        total += average_rank * sum(value for _, value in ordered[index:stop])
        index = stop
    return (total - positives * (positives + 1) / 2) / (positives * negatives)


def metrics(y, p, classification):
    n = len(y)
    if not classification:
        mse = statistics.mean((a - b) ** 2 for a, b in zip(y, p))
        denominator = sum(a * a for a in y)
        return {"n": n, "mae_bps": statistics.mean(abs(a - b) for a, b in zip(y, p)), "rmse_bps": math.sqrt(mse),
                "r2_vs_zero": 1 - n * mse / denominator if denominator else None,
                "mean_prediction_bps": statistics.mean(p), "mean_observed_bps": statistics.mean(y)}
    positive, negative = sum(y), n - sum(y)
    correct = sum(int(b >= .5) == a for a, b in zip(y, p))
    up_recall = sum(a == 1 and b >= .5 for a, b in zip(y, p)) / positive if positive else None
    down_recall = sum(a == 0 and b < .5 for a, b in zip(y, p)) / negative if negative else None
    bins = calibration(y, p)
    return {"n": n, "brier": statistics.mean((a - b) ** 2 for a, b in zip(y, p)),
            "log_loss": statistics.mean(-a * math.log(max(1e-12, b)) - (1 - a) * math.log(max(1e-12, 1 - b)) for a, b in zip(y, p)),
            "accuracy": correct / n, "balanced_accuracy": (up_recall + down_recall) / 2 if up_recall is not None and down_recall is not None else None,
            "auc": auc(y, p), "observed_up": positive / n, "predicted_up": statistics.mean(p),
            "ece": sum(item["count"] * abs(item["predicted"] - item["observed"]) for item in bins) / n}


def calibration(y, p):
    result = []
    for k in range(10):
        pairs = [(a, b) for a, b in zip(y, p) if min(9, int(b * 10)) == k]
        if pairs:
            result.append({"bin": k, "lower": k / 10, "upper": (k + 1) / 10, "count": len(pairs),
                           "predicted": statistics.mean(b for _, b in pairs), "observed": statistics.mean(a for a, _ in pairs)})
    return result


def solve(matrix, vector):
    """Pivoted Gaussian elimination for a tiny positive ridge system."""
    n = len(vector)
    a = [list(row) + [value] for row, value in zip(matrix, vector)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        a[col], a[pivot] = a[pivot], a[col]
        if abs(a[col][col]) < 1e-12:
            raise ValueError("Singular fixed ridge system.")
        divisor = a[col][col]
        a[col] = [value / divisor for value in a[col]]
        for row in range(n):
            if row != col:
                factor = a[row][col]
                a[row] = [x - factor * y for x, y in zip(a[row], a[col])]
    return [row[-1] for row in a]


def run_experiment(payload):
    bars, config = payload["bars"], payload["config"]
    if config["target"] not in ("direction", "return") or config["model_family"] != ("logistic" if config["target"] == "direction" else "ridge"):
        raise ValueError("Direction requires logistic; return requires ridge.")
    names, train, validation, test, splits = observations(bars, config)
    means = [statistics.mean(r["features"][i] for r in train) for i in range(len(names))]
    scales = [max(1e-8, statistics.pstdev(r["features"][i] for r in train)) for i in range(len(names))]
    def transform(row):
        return [max(-5., min(5., (v - m) / s)) for v, m, s in zip(row["features"], means, scales)]
    x = [transform(row) for row in train]
    y = [row["y"] for row in train]
    classification = config["target"] == "direction"
    baseline = statistics.mean(y)
    if classification:
        weights = [0.] * len(names)
        intercept = math.log((sum(y) + .5) / (len(y) - sum(y) + .5))
        for _ in range(400):
            errors = [sigmoid(intercept + sum(a * b for a, b in zip(weights, row))) - actual for row, actual in zip(x, y)]
            intercept -= .15 * statistics.mean(errors)
            for j in range(len(weights)):
                gradient = sum(error * row[j] for error, row in zip(errors, x)) / len(x) + weights[j] / len(x)
                weights[j] -= .15 * gradient
    else:
        augmented = [[1.] + row for row in x]
        n = len(names) + 1
        matrix = [[sum(row[i] * row[j] for row in augmented) + (1. if i == j and i else 0.) for j in range(n)] for i in range(n)]
        vector = [sum(row[i] * actual for row, actual in zip(augmented, y)) for i in range(n)]
        fitted = solve(matrix, vector)
        intercept, weights = fitted[0], fitted[1:]
    result = {"metrics": {}, "baseline_metrics": {}, "features": names, "splits": splits,
              "feature_contributions": [{"feature": name, "coefficient": weight} for name, weight in zip(names, weights)],
              "limitations": ["Retrospective chronological evaluation; not independent future validation.",
                              "A single fixed family and specification; validation is reported without model or threshold selection.",
                              "Nonoverlapping target paths still share regimes and feature contexts; small calendar support limits precision.",
                              "Signed returns and probability metrics are forecasts, not a trading strategy or profit estimate.",
                              "Training coefficients are associations, not causal importance.",
                              "Artifact cannot execute as a strategy node until an explicit compatible as-of prediction adapter exists."]}
    predictions = []
    for name, rows in (("train", train), ("validation", validation), ("test", test)):
        actuals = [row["y"] for row in rows]
        estimates = [intercept + sum(a * b for a, b in zip(weights, transform(row))) for row in rows]
        estimates = [sigmoid(value) for value in estimates] if classification else estimates
        result["metrics"][name] = metrics(actuals, estimates, classification)
        result["baseline_metrics"][name] = metrics(actuals, [baseline] * len(rows), classification)
        if name == "test":
            result["calibration"] = calibration(actuals, estimates) if classification else []
        predictions.extend({"split": name, "origin": row["origin"], "reference": row["reference"], "label_end": row["label_end"],
                            "actual": row["y"], "prediction": prediction} for row, prediction in zip(rows, estimates))
    score = "brier" if classification else "mae_bps"
    result["summary"] = {"score_name": score, "test_score": result["metrics"]["test"][score],
                         "baseline_score": result["baseline_metrics"]["test"][score],
                         "improvement": result["baseline_metrics"]["test"][score] - result["metrics"]["test"][score]}
    artifact = {"schema_version": 1, "worker_version": VERSION, "model_family": config["model_family"], "target": config["target"],
                "feature_names": names, "feature_groups": config["feature_groups"], "weights": weights, "intercept": intercept,
                "mean": means, "scale": scales, "clip": 5, "horizon_bars": config["horizon_bars"],
                "training_label_end": splits["train"]["maximum_label_end"], "dataset_sha256": payload["dataset"]["sha256"],
                "dataset_id": payload["dataset"]["id"], "symbol": payload["dataset"]["symbol"], "timeframe": payload["dataset"]["timeframe"],
                "hyperparameters": {"ridge_alpha": 1, "iterations": 400 if classification else None, "learning_rate": .15 if classification else None},
                "strategy_node_executable": False}
    result.update(artifact=artifact, predictions=predictions, dataset=payload["dataset"], source=payload.get("provenance", {}),
                  configuration=config, configuration_sha256=hashlib.sha256(canonical(config).encode()).hexdigest())
    # Native reload equality with no opaque estimator serialization.
    reload_artifact = json.loads(canonical(artifact))
    for row in test:
        z = [max(-reload_artifact["clip"], min(reload_artifact["clip"], (a - b) / c)) for a, b, c in zip(row["features"], reload_artifact["mean"], reload_artifact["scale"])]
        value = reload_artifact["intercept"] + sum(a * b for a, b in zip(reload_artifact["weights"], z))
        value = sigmoid(value) if classification else value
        saved = next(item["prediction"] for item in predictions if item["split"] == "test" and item["origin"] == row["origin"])
        if value != saved:
            raise ValueError("Native model artifact did not reproduce saved predictions.")
    result["reload_max_error"] = 0.
    canonical(result)
    return result


def main():
    # Parent uses a pipe and fixed code path; no user file/path/import accepted.
    raw = sys.stdin.buffer.read(16_000_001)
    if len(raw) > 16_000_000:
        raise ValueError("Training input exceeds the 16 MB cap.")
    result = run_experiment(json.loads(raw))
    output = canonical(result)
    if len(output.encode()) > 2_000_000:
        raise ValueError("Training artifact exceeds the 2 MB output cap.")
    sys.stdout.buffer.write(output.encode("utf-8"))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.stdout.buffer.write(canonical({"error": str(exc)[:400] if isinstance(exc, (ValueError, KeyError)) else "Bounded training failed."}).encode("utf-8"))
        sys.exit(1)

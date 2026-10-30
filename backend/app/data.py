"""Read-only adapters for a fixed, allow-listed historical slice and demo data.

No network, credentials, legacy imports, or source writers. The manifest and ZIP
checksums are rechecked once per process before exposing historical prices.
"""
from __future__ import annotations

from copy import deepcopy
import csv
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import zipfile

UTC = timezone.utc
STEP_MS = 4 * 60 * 60 * 1000
# Historical files are an optional external input, never part of a source clone.
# In particular, Path("") must not accidentally make the working directory a
# configured research root. The installed developer may opt in via environment.
_legacy_setting = os.environ.get("KEDR_LEGACY_ROOT", "").strip()
LEGACY_ROOT = Path(_legacy_setting).expanduser().resolve() if _legacy_setting else None
MANIFEST = LEGACY_ROOT / "research/cross_asset_200day_robustness/source_provenance.json" if LEGACY_ROOT else None


def historical_source_status():
    """Cheap configuration status; loading still verifies all source hashes."""
    configured = LEGACY_ROOT is not None
    installed = configured and MANIFEST.is_file()
    return {
        "configured": configured,
        "manifest_installed": installed,
        "status": "local_configured" if installed else "not_installed" if configured else "unconfigured",
        "message": (
            "Optional local historical manifest found; each selected dataset still requires SHA256 and schema validation."
            if installed else
            "Optional historical archives are not installed. Select an explicitly labelled synthetic demo dataset."
        ),
    }


def _iso(ms):
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat().replace("+00:00", "Z")


def _hash(content):
    return hashlib.sha256(content).hexdigest()


def _description(symbol, source_type):
    if source_type == "synthetic_demo":
        return {"ru": f"Синтетические учебные свечи {symbol}. Не являются историей рынка и не подтверждают доходность.",
                "en": f"Synthetic educational {symbol} candles. Not market history and not evidence of returns."}
    return {"ru": f"{symbol}: проверенные SHA256 архивы Binance Spot, 2022–2025. Ретроспективные цены; без заявок и подтверждённой задержки получения.",
            "en": f"{symbol}: SHA256-verified Binance Spot archives, 2022–2025. Retrospective prices without quotes or verified receipt latency."}


def _assemble(dataset_id, symbol, bars, source_type, provenance):
    if not bars:
        raise ValueError("The allow-listed dataset contains no valid candles.")
    gaps = []
    for a, b in zip(bars, bars[1:]):
        delta = b["timestamp"] - a["timestamp"]
        if delta != STEP_MS:
            gaps.append({"after": a["time"], "before": b["time"], "seconds": delta / 1000,
                         "missing_bars": max(0, delta // STEP_MS - 1)})
    digest = _hash(json.dumps(bars, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
    metadata = {"id": dataset_id, "name": f"{symbol} · 4h · " + ("DEMO" if source_type == "synthetic_demo" else "2022–2025"),
                "symbol": symbol, "timeframe": "4h", "start": bars[0]["time"], "end": bars[-1]["time"],
                "bars": len(bars), "source_type": source_type, "sha256": digest,
                "description": _description(symbol, source_type), "gaps": len(gaps),
                "verified": source_type == "verified_historical", "status": "available"}
    provenance = {**provenance, "dataset_sha256": digest, "gaps": gaps,
                  "availability": "Completed candles are assumed available after one full candle embargo. Historical receipt timestamps are unavailable.",
                  "independent_evaluation": False, "network_downloads": 0}
    return {"metadata": metadata, "bars": bars, "provenance": provenance}


@lru_cache(maxsize=4)
def _synthetic(symbol="BTCUSDT"):
    """Stable PRNG seed and a separate market label; never silently replaces real data."""
    rng = random.Random(73041 + ("BTCUSDT", "ETHUSDT", "SOLUSDT").index(symbol))
    price = {"BTCUSDT": 30000.0, "ETHUSDT": 1800.0, "SOLUSDT": 35.0}[symbol]
    start = datetime(2023, 1, 1, tzinfo=UTC)
    bars = []
    for i in range(2190):
        drift = 0.0001 + 0.0011 * math.sin(i / 110) + 0.00035 * math.sin(i / 23)
        ret = drift + rng.gauss(0, 0.009)
        op = price
        price = op * math.exp(ret)
        spread = abs(rng.gauss(0.006, 0.003))
        ms = int((start + timedelta(hours=4 * i)).timestamp() * 1000)
        bars.append({"time": _iso(ms), "timestamp": ms, "open": round(op, 8),
                     "high": round(max(op, price) * (1 + spread), 8),
                     "low": round(min(op, price) / (1 + spread), 8), "close": round(price, 8),
                     "volume": round(1000 + rng.random() * 2000, 6), "valid": True})
    return _assemble("demo_" + symbol[:3].lower() + "_4h", symbol, bars, "synthetic_demo",
                     {"adapter": "seeded_synthetic_v1", "seed": 73041 + ("BTCUSDT", "ETHUSDT", "SOLUSDT").index(symbol),
                      "source_files": [], "warning": "Generated illustrative OHLCV; not real prices, news or account performance."})


@lru_cache(maxsize=3)
def _historical(symbol):
    if symbol not in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        raise ValueError("Unknown symbol.")
    if MANIFEST is None:
        raise ValueError("Optional historical source is unconfigured. Set KEDR_LEGACY_ROOT only if the verified archives are installed; select a labelled demo dataset otherwise.")
    manifest_bytes = MANIFEST.read_bytes()
    manifest = json.loads(manifest_bytes)
    allow_list = manifest["verified_pre2026_archives"]
    expected_names = {f"{symbol}-4h-{y}-{m:02d}.zip" for y in range(2022, 2026) for m in range(1, 13)}
    sources = sorted((Path(path), sha) for path, sha in allow_list.items() if Path(path).name in expected_names)
    if len(sources) != 48 or {path.name for path, _ in sources} != expected_names:
        raise ValueError("The protected source manifest does not contain all 48 allowed monthly archives.")
    bars, file_receipts, rejected = [], [], []
    seen = set()
    minimum = int(datetime(2022, 1, 1, tzinfo=UTC).timestamp() * 1000)
    maximum = int(datetime(2026, 1, 1, tzinfo=UTC).timestamp() * 1000)
    for path, expected_sha in sources:
        # The path must remain within the documented legacy raw directory.
        safe_root = (LEGACY_ROOT / "research/multiasset_trend/raw").resolve()
        if not path.resolve().is_relative_to(safe_root):
            raise ValueError("A source path escaped the allow-listed raw archive directory.")
        raw = path.read_bytes()
        digest = _hash(raw)
        if digest != expected_sha:
            raise ValueError(f"Source checksum mismatch: {path.name}. Historical data is disabled.")
        file_receipts.append({"name": path.name, "sha256": digest, "bytes": len(raw)})
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if archive.testzip() is not None:
                raise ValueError(f"ZIP integrity failure: {path.name}")
            csv_names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise ValueError("Each allow-listed archive must contain exactly one CSV.")
            with archive.open(csv_names[0]) as handle:
                reader = csv.reader(io.TextIOWrapper(handle, encoding="utf-8-sig"))
                for row_number, row in enumerate(reader, 1):
                    if not row or row[0] in ("open_time", "Open time"):
                        continue
                    if len(row) != 12:
                        raise ValueError(f"Unexpected source schema in {path.name}:{row_number}")
                    raw_open, raw_close = int(row[0]), int(row[6])
                    unit = 1000 if raw_open >= 100_000_000_000_000 else 1
                    # Integer source clocks preserve the microsecond inclusive quantum.
                    if raw_open % unit:
                        rejected.append({"file": path.name, "row": row_number, "reason": "unaligned_source_clock"})
                        continue
                    ms = raw_open // unit
                    # Explicitly reject out-of-scope data before decoding OHLC values.
                    if not minimum <= ms < maximum:
                        raise ValueError("An allow-listed archive contains an out-of-scope timestamp; no prices decoded.")
                    if ms in seen:
                        raise ValueError("Duplicate historical candle timestamp.")
                    seen.add(ms)
                    vals = [float(row[x]) for x in (1, 2, 3, 4, 5, 7)]
                    op, hi, lo, cl, volume, quote = vals
                    if (not all(math.isfinite(x) for x in vals) or min(op, hi, lo, cl) <= 0 or
                            not lo <= min(op, cl) <= max(op, cl) <= hi or min(volume, quote) < 0 or
                            ms % STEP_MS or raw_close + 1 - raw_open != STEP_MS * unit):
                        rejected.append({"file": path.name, "row": row_number, "time": _iso(ms), "reason": "invalid_ohlcv_clock_or_duration"})
                        continue
                    bars.append({"time": _iso(ms), "timestamp": ms, "open": op, "high": hi, "low": lo,
                                 "close": cl, "volume": volume, "quote_volume": quote,
                                 "number_of_trades": int(row[8]), "valid": True})
    bars.sort(key=lambda b: b["timestamp"])
    return _assemble("verified_" + symbol[:3].lower() + "_4h", symbol, bars, "verified_historical",
                     {"adapter": "binance_protected_zip_readonly_v1", "manifest_sha256": _hash(manifest_bytes),
                      "source_files": file_receipts, "rejected_rows": rejected,
                      "scope": "Only 2022-01 through 2025-12 monthly Spot 4h ZIPs. No 2026 archive opened.",
                      "historical_revision_warning": "Hashes verify retrieved archive versions, not original publication time or an unrevised historical feed."})


def datasets():
    result = [deepcopy(_synthetic(symbol)["metadata"]) for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT")]
    for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
        try:
            result.append(deepcopy(_historical(symbol)["metadata"]))
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            # A failed real adapter is explicit and never replaced by generated prices.
            result.append({"id": "verified_" + symbol[:3].lower() + "_4h", "name": symbol + " · historical unavailable",
                           "symbol": symbol, "timeframe": "4h", "source_type": "verified_historical", "verified": False,
                           "status": "unavailable", "description": {"ru": "Проверенный источник недоступен. Выберите учебный набор явно.", "en": "Verified source unavailable. Select demonstration data explicitly."},
                           "error": str(exc), "start": "", "end": "", "bars": 0, "gaps": 0, "sha256": ""})
    return result


def load_dataset(dataset_id):
    mapping = {"demo_" + s[:3].lower() + "_4h": ("demo", s) for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")}
    mapping.update({"verified_" + s[:3].lower() + "_4h": ("verified", s) for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")})
    if dataset_id not in mapping:
        raise ValueError("Unknown dataset. No implicit source fallback is allowed.")
    source, symbol = mapping[dataset_id]
    try:
        data = _synthetic(symbol) if source == "demo" else _historical(symbol)
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise ValueError("Verified historical source unavailable; select a labelled demo dataset explicitly.") from exc
    return deepcopy(data)


# Preserve original dataset identity, bars, provenance and hashes for schema 1.
_legacy_load_dataset = load_dataset
_legacy_datasets = datasets

def load_dataset(dataset_id):
    from . import data_v2
    if dataset_id in data_v2.INTRADAY_IDS or dataset_id in data_v2.DAILY_IDS:
        return data_v2.load(dataset_id)
    return _legacy_load_dataset(dataset_id)

def datasets():
    from . import data_v2
    return _legacy_datasets() + data_v2.datasets()

def load_dataset_for_strategy(spec, dataset_id):
    from . import data_v2
    return data_v2.for_strategy(spec, dataset_id)

"""Versioned local-only datasets and strict UTC coarsening; no market downloads.

The original six dataset IDs remain owned by data.py's unchanged v1 adapters.
A single predeclared, already verified BTC minute month powers the new intraday
examples. Incomplete aggregate intervals are excluded rather than synthesized.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import csv
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

TIMEFRAME_MS = {"1m":60_000,"5m":300_000,"15m":900_000,"1h":3_600_000,"4h":14_400_000,"1d":86_400_000}
SYMBOLS = ("BTCUSDT","ETHUSDT","SOLUSDT")
INTRADAY_IDS = {f"verified_btc_{tf}_2025_01": tf for tf in ("1m","5m","15m","1h")}
DAILY_IDS = {f"{source}_{s[:3].lower()}_1d": (source,s) for source in ("verified","demo") for s in SYMBOLS}


def _iso(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat().replace("+00:00","Z")


def strict_resample(bars, source_timeframe, target_timeframe):
    source, target = TIMEFRAME_MS[source_timeframe], TIMEFRAME_MS[target_timeframe]
    if target < source or target % source:
        raise ValueError("Only exact UTC coarsening is supported; smaller candles cannot be reconstructed.")
    groups = defaultdict(list)
    for bar in bars:
        groups[(bar["timestamp"]//target)*target].append(bar)
    result, excluded = [], []
    for start, rows in sorted(groups.items()):
        expected = target//source
        if len(rows)!=expected or any(r["timestamp"]!=start+i*source or not r.get("valid",True) for i,r in enumerate(rows)):
            excluded.append({"time":_iso(start),"observed":len(rows),"expected":expected,"reason":"incomplete_or_invalid_source_bucket"})
            continue
        first, last = rows[0],rows[-1]
        bar={"time":_iso(start),"timestamp":start,"open":first["open"],"high":max(r["high"] for r in rows),
             "low":min(r["low"] for r in rows),"close":last["close"],"volume":sum(r["volume"] for r in rows),"valid":True}
        for field in ("quote_volume","number_of_trades","taker_buy_base_volume","taker_buy_quote_volume"):
            if all(field in r for r in rows):
                bar[field]=sum(r[field] for r in rows)
        result.append(bar)
    return result,excluded


def _assemble(dataset_id, symbol, timeframe, bars, source, provenance):
    if not bars:
        raise ValueError("No complete source-supported candles remain.")
    step=TIMEFRAME_MS[timeframe]
    gaps=[{"after":a["time"],"before":b["time"],"seconds":(b["timestamp"]-a["timestamp"])/1000,
           "missing_bars":max(0,(b["timestamp"]-a["timestamp"])//step-1)} for a,b in zip(bars,bars[1:]) if b["timestamp"]-a["timestamp"]!=step]
    digest=hashlib.sha256(json.dumps(bars,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    label="DEMO" if source=="synthetic_demo" else ("2025-01" if "2025_01" in dataset_id else "2022–2025")
    fields=sorted(set.intersection(*(set(b) for b in bars)))
    metadata={"id":dataset_id,"name":f"{symbol} ? {timeframe} ? {label}","symbol":symbol,"timeframe":timeframe,
              "start":bars[0]["time"],"end":bars[-1]["time"],"bars":len(bars),"source_type":source,
              "sha256":digest,"gaps":len(gaps),"verified":source=="verified_historical","status":"available",
              "fields":fields,"availability_seconds":5,"dataset_schema":"kedr-market-data/2",
              "description":{"en":"Verified local, retrospective candles. Receipt timing is unknown; completed-candle availability assumes 5 seconds." if source=="verified_historical" else "Clearly labelled synthetic candles, strictly aggregated from the demo series.",
                             "ru":"Локальные ретроспективные свечи. Время получения неизвестно; доступность через 5 секунд — допущение." if source=="verified_historical" else "Учебные синтетические свечи, агрегированные из демонстрационного ряда."}}
    return {"metadata":metadata,"bars":bars,"provenance":{**provenance,"dataset_sha256":digest,"gaps":gaps,
            "availability":"Completion + 5 seconds assumed; historical first publication and receipt clocks unavailable.",
            "availability_seconds":5,"independent_evaluation":False,"network_downloads":0}}


@lru_cache(maxsize=1)
def _minute_month():
    from . import data
    if data.LEGACY_ROOT is None:
        raise ValueError("Optional historical minute source is unconfigured. Install the separately verified source before setting KEDR_LEGACY_ROOT; demo datasets remain available.")
    audit_path=data.LEGACY_ROOT/"research/btc_long_horizon_direction/data_audit.json"
    audit_bytes=audit_path.read_bytes(); audit=json.loads(audit_bytes)
    name="BTCUSDT-1m-2025-01.zip"
    entries=[r for r in audit["BTC_source_archives"] if Path(r["path"]).name==name]
    if len(entries)!=1:
        raise ValueError("The protected audit must identify exactly one authorized January 2025 source.")
    receipt=entries[0]; path=(data.LEGACY_ROOT/receipt["path"]).resolve()
    safe=(data.LEGACY_ROOT/"research/btc_volatility_trading_value/raw").resolve()
    if not path.is_relative_to(safe):
        raise ValueError("Source escaped the fixed verified archive root.")
    payload=path.read_bytes(); sha=hashlib.sha256(payload).hexdigest()
    if sha!=receipt["sha256"]:
        raise ValueError("BTC minute archive checksum mismatch; no fallback.")
    bars=[]; rejected=[]; seen=set(); start=1735689600000; end=1738368000000
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if archive.testzip() is not None:
            raise ValueError("BTC minute archive failed ZIP CRC.")
        names=[n for n in archive.namelist() if n.lower().endswith(".csv")]
        if len(names)!=1 or archive.getinfo(names[0]).file_size>32*1024*1024:
            raise ValueError("Unexpected archive members or inflated size.")
        with archive.open(names[0]) as handle:
            for number,row in enumerate(csv.reader(io.TextIOWrapper(handle,encoding="utf-8-sig")),1):
                if not row or row[0]=="open_time": continue
                if len(row)!=12: raise ValueError("Unexpected minute CSV schema.")
                op_raw,cl_raw=int(row[0]),int(row[6]); quantum=1000 if op_raw>=100_000_000_000_000 else 1
                ms=op_raw//quantum
                # Validate scope before decoding market values; this source is pre-2026 only.
                if not start<=ms<end: raise ValueError("Minute source contains an unauthorized date.")
                if ms in seen: raise ValueError("Duplicate source minute.")
                seen.add(ms)
                values=[float(row[k]) for k in (1,2,3,4,5,7,9,10)]
                op,hi,lo,cl,volume,quote,tbase,tquote=values
                trades=int(row[8])
                if (op_raw%quantum or ms%60_000 or cl_raw+1-op_raw!=60_000*quantum or
                    not all(math.isfinite(x) for x in values) or min(op,hi,lo,cl)<=0 or not lo<=min(op,cl)<=max(op,cl)<=hi or
                    min(volume,quote,tbase,tquote,trades)<0 or tbase>volume+1e-6 or tquote>quote+1e-3):
                    rejected.append({"row":number,"time":_iso(ms),"reason":"source_schema_clock_or_ohlcv_invalid"});continue
                bars.append({"time":_iso(ms),"timestamp":ms,"open":op,"high":hi,"low":lo,"close":cl,"volume":volume,
                             "quote_volume":quote,"number_of_trades":trades,"taker_buy_base_volume":tbase,
                             "taker_buy_quote_volume":tquote,"valid":True})
    bars.sort(key=lambda r:r["timestamp"])
    return bars,{"adapter":"binance_verified_minute_month/2","source_files":[{"name":name,"sha256":sha,"bytes":len(payload)}],
                 "source_manifest_sha256":hashlib.sha256(audit_bytes).hexdigest(),"source_time_units":"original integer microseconds in January 2025, normalized UTC milliseconds",
                 "scope":"Only the fixed existing January 2025 Spot minute archive is opened; no reserved or 2026 values.",
                 "rejected_rows":rejected,"historical_revision_warning":"SHA256 verifies the current archived version, not original receipt or absence of revisions.",
                 "source_permission":{"access":"previously acquired official free archive","license":"Exchange data terms; not a grant of redistribution rights","read_only":True}}


@lru_cache(maxsize=10)
def _load(dataset_id):
    from . import data
    if dataset_id in INTRADAY_IDS:
        timeframe=INTRADAY_IDS[dataset_id]; source,provenance=_minute_month()
        bars,excluded=strict_resample(source,"1m",timeframe)
        return _assemble(dataset_id,"BTCUSDT",timeframe,bars,"verified_historical",{**provenance,"resampling":{"source":"1m","target":timeframe,"utc_aligned":True,"excluded_buckets":excluded}})
    if dataset_id in DAILY_IDS:
        source,symbol=DAILY_IDS[dataset_id]
        base=data._legacy_load_dataset(f"{source}_{symbol[:3].lower()}_4h")
        bars,excluded=strict_resample(base["bars"],"4h","1d")
        return _assemble(dataset_id,symbol,"1d",bars,base["metadata"]["source_type"],{**base["provenance"],"parent_dataset_sha256":base["metadata"]["sha256"],
                        "adapter":"strict_utc_resample/2","resampling":{"source":"4h","target":"1d","utc_aligned":True,"excluded_buckets":excluded}})
    raise ValueError("Unknown v2 dataset; no implicit source or timeframe fallback.")


def load(dataset_id):
    return deepcopy(_load(dataset_id))


def datasets():
    result=[]
    for dataset_id in [*INTRADAY_IDS,*DAILY_IDS]:
        try: result.append(deepcopy(_load(dataset_id)["metadata"]))
        except (OSError,ValueError,KeyError,zipfile.BadZipFile) as exc:
            tf=INTRADAY_IDS.get(dataset_id,"1d"); symbol="BTCUSDT" if dataset_id in INTRADAY_IDS else DAILY_IDS[dataset_id][1]
            result.append({"id":dataset_id,"name":dataset_id,"symbol":symbol,"timeframe":tf,"status":"unavailable","verified":False,
                           "source_type":"verified_historical" if dataset_id.startswith("verified") else "synthetic_demo","error":str(exc),"bars":0,
                           "start":"","end":"","gaps":0,"sha256":"",
                           "description":{"ru":"Источник недоступен; подмена отключена.","en":"Source unavailable; fallback disabled."}})
    return result


def for_strategy(spec,dataset_id):
    from . import data
    result=data.load_dataset(dataset_id)
    if spec.get("schema_version",1)==1: return result
    base_meta=result["metadata"]; auxiliary={}
    for node in spec.get("nodes",[]):
        if node.get("type")!="market": continue
        params=node.get("params",{}); symbol=params.get("symbol",spec.get("symbol")); timeframe=params.get("timeframe",spec.get("timeframe"))
        if symbol==base_meta["symbol"] and timeframe==base_meta["timeframe"]: continue
        if timeframe not in TIMEFRAME_MS or symbol not in SYMBOLS: raise ValueError("Unknown auxiliary market or timeframe.")
        if TIMEFRAME_MS[timeframe]<TIMEFRAME_MS[base_meta["timeframe"]]: raise ValueError("Auxiliary smaller-timeframe candles require a separately supported execution design.")
        if dataset_id in INTRADAY_IDS:
            if symbol!="BTCUSDT": raise ValueError("Cross-asset intraday data is not connected.")
            bars,excluded=strict_resample(result["bars"],base_meta["timeframe"],timeframe)
            native=_assemble(f"aux_{symbol}_{timeframe}",symbol,timeframe,bars,base_meta["source_type"],{**result["provenance"],"resampling":{"source":base_meta["timeframe"],"target":timeframe,"excluded_buckets":excluded}})
        else:
            prefix="demo" if base_meta["source_type"]=="synthetic_demo" else "verified"
            native=data.load_dataset(f"{prefix}_{symbol[:3].lower()}_{timeframe}")
        auxiliary[f"{symbol}:{timeframe}"]={"bars":native["bars"],"metadata":{**native["metadata"],"availability_seconds":5},"provenance":native["provenance"]}
    result["auxiliary"]=auxiliary
    return result

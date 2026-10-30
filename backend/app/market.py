"""Bounded market-chart API, calculated from the same causal engine indicators."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from fastapi import APIRouter,Depends,HTTPException,Query
from . import data,engine
from .auth import current_user
from .market_providers import capabilities

router=APIRouter(prefix="/api/market",tags=["market"])
CHART_INDICATORS={"sma","ema","wma","bollinger","vwap","rsi","macd","atr","volatility","donchian","obv","mfi","adx","stochastic","zscore"}


def _clock(text,end=False):
    if text is None:return None
    try:
        if len(text)==10:
            ms=int(datetime.fromisoformat(text).replace(tzinfo=timezone.utc).timestamp()*1000)
            if end:ms+=86400000-1
        else:
            parsed=datetime.fromisoformat(text.replace("Z","+00:00"))
            if parsed.tzinfo is None:raise ValueError()
            ms=int(parsed.timestamp()*1000)
        if ms>=1767225600000 or ms<0:raise ValueError()
        return ms
    except (ValueError,OverflowError):raise HTTPException(422,"Use an explicit UTC historical date/time before 2026.")


@router.get("/capabilities")
def market_capabilities(user=Depends(current_user)):
    return {"provider_schema":"kedr-observation/2","capabilities":capabilities(),
            "timeframes":{"BTCUSDT":["1m","5m","15m","1h","4h","1d"],"ETHUSDT":["4h","1d"],"SOLUSDT":["4h","1d"]},
            "intraday_scope":"BTC January 2025 only; no market downloads", "receipt_verified":False}


@router.get("/chart")
def chart(dataset_id:str=Query(max_length=80),start:str|None=Query(default=None,max_length=40),
          end:str|None=Query(default=None,max_length=40),limit:int=Query(default=1200,ge=10,le=5000),
          indicators:str="[]",user=Depends(current_user)):
    if len(indicators)>4000:raise HTTPException(413,"Indicator request exceeds 4000 characters.")
    try:
        selections=json.loads(indicators)
        if not isinstance(selections,list) or len(selections)>8:raise ValueError("At most eight indicators are allowed.")
        for item in selections:
            if not isinstance(item,dict) or set(item)-{"id","kind","params"}:raise ValueError("Invalid chart indicator schema.")
            if item.get("kind") not in CHART_INDICATORS:raise ValueError("Unsupported chart indicator.")
            if not isinstance(item.get("params",{}),dict) or len(str(item.get("id","")))>80:raise ValueError("Invalid chart parameters.")
        native=data.load_dataset(dataset_id)
    except (ValueError,TypeError,KeyError) as exc:raise HTTPException(422,str(exc))
    begin,finish=_clock(start),_clock(end,True)
    if begin is not None and finish is not None and begin>finish:raise HTTPException(422,"Start must precede end.")
    all_bars=native["bars"]
    eligible=[i for i,b in enumerate(all_bars) if (begin is None or b["timestamp"]>=begin) and (finish is None or b["timestamp"]<=finish)]
    indices=eligible[-limit:]
    bars=[all_bars[i] for i in indices]
    # Native history before the visible interval supplies warm-up. No future bar
    # enters any returned indicator value, even if history continues past end.
    prefix=all_bars[:indices[-1]+1] if indices else []
    series=[]
    for item in selections:
        try:
            values=engine.indicator_series(item["kind"],prefix,item.get("params",{}),timeframe=native["metadata"]["timeframe"]) if prefix else []
            if isinstance(values,dict):
                values=values.get("values",values.get("series"))
            if not isinstance(values,list) or len(values)!=len(prefix):raise ValueError("Indicator output has incompatible alignment.")
            if values and isinstance(values[0],dict):
                if any(v.get("time")!=b["time"] for v,b in zip(values,prefix)):raise ValueError("Indicator clocks do not match source candles.")
                values=[v["value"] for v in values]
            series.append({"id":item.get("id",item["kind"]),"kind":item["kind"],"params":item.get("params",{}),"values":[values[i] for i in indices],"status":"available"})
        except (ValueError,KeyError,TypeError) as exc:
            series.append({"id":item.get("id",item["kind"]),"kind":item["kind"],"values":[],"status":"unavailable","message":str(exc)})
    gaps=[g for g in native["provenance"].get("gaps",[]) if bars and g["before"]>=bars[0]["time"] and g["after"]<=bars[-1]["time"]]
    return {"schema_version":"kedr-chart/2","dataset":native["metadata"],"bars":bars,"gaps":gaps,"provenance":native["provenance"],
            "indicators":series,"truncated":len(eligible)>limit,"eligible_bars":len(eligible),"returned_bars":len(bars),
            "warmup_bars":indices[0] if indices else 0,"sampling":"Actual consecutive supported candles; no random downsampling", "empty":not bars}

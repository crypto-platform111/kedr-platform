"""Causal data and provider-boundary tests independent of model performance."""
from copy import deepcopy
import json
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.app import data
from backend.app.data_v2 import strict_resample,for_strategy
from backend.app.market_providers import MarketObservation
from backend.app.main import create_app


def fixture_bars(n=12,step=14400000):
    return [{"time":data._iso(i*step),"timestamp":i*step,"open":100+i,"high":102+i,"low":99+i,"close":101+i,"volume":10,
             "quote_volume":1000+i,"number_of_trades":3,"valid":True} for i in range(n)]


def test_resampling_uses_real_complete_native_intervals():
    bars=fixture_bars(); daily,excluded=strict_resample(bars,"4h","1d")
    assert not excluded and len(daily)==2
    assert daily[0]["open"]==100 and daily[0]["close"]==106
    assert daily[0]["high"]==107 and daily[0]["low"]==99
    assert daily[0]["volume"]==60 and daily[0]["quote_volume"]==6015 and daily[0]["number_of_trades"]==18
    bars.pop(2); daily,excluded=strict_resample(bars,"4h","1d")
    assert len(daily)==1 and daily[0]["timestamp"]==86400000
    assert excluded[0]["observed"]==5


def test_invalid_buckets_not_padded_and_no_downsampling_to_smaller_candles():
    bars=fixture_bars(); bars[2]["valid"]=False
    daily,excluded=strict_resample(bars,"4h","1d")
    assert len(daily)==1 and len(excluded)==1
    with pytest.raises(ValueError,match="smaller"):
        strict_resample(bars,"4h","1h")
    with pytest.raises(ValueError):strict_resample(bars,"4h","5m")


def test_resampling_does_not_use_future_buckets():
    bars=fixture_bars(18); prior=strict_resample(bars[:12],"4h","1d")[0]
    changed=deepcopy(bars);changed[12]["close"]=1e9
    assert strict_resample(changed,"4h","1d")[0][:2]==prior


def observation(**change):
    args={"source_id":"public-capture","family":"funding_settled","venue":"Binance","symbol":"BTCUSDT", "native_timestamp":"1000",
          "native_unit":"milliseconds","event_timestamp_ms":1000,"receipt_ms":1100,"available_at_ms":1100,
          "availability_basis":"archived_receipt","source_version":"v1","acquired_at":"2025-01-01T00:00:00Z","valid":True,
          "values":{"settled_rate":.0001},"permission":{"access":"local_authorized","scope":"Local research only"}}
    return MarketObservation(**{**args,**change})


def test_receipt_availability_and_freshness_are_explicit():
    row=observation()
    assert not row.usable_at(1099) and row.usable_at(1100)
    assert not row.usable_at(5000,max_age_ms=1000)
    with pytest.raises(ValidationError):observation(available_at_ms=1000)
    with pytest.raises(ValidationError):observation(availability_basis="unknown")
    unknown=observation(availability_basis="unknown",available_at_ms=None)
    assert not unknown.usable_at(1_000_000)


def test_assumed_lag_never_claims_receipt_and_liquidations_need_labels():
    lag=observation(availability_basis="assumed_lag",receipt_ms=None,assumed_lag_ms=86400000,available_at_ms=86401000)
    assert lag.usable_at(86401000)
    with pytest.raises(ValidationError):observation(availability_basis="assumed_lag",assumed_lag_ms=86400000)
    with pytest.raises(ValidationError):observation(family="liquidation_event",values={"price_drop":.05})
    with pytest.raises(ValidationError):observation(quality_flags=["indicative"])
    assert observation(family="liquidation_event",values={"exchange_labelled":True,"quantity":10}).valid


@pytest.mark.parametrize("dataset_id", ["demo_btc_4h", pytest.param("verified_btc_4h", marks=pytest.mark.local_archives)])
def test_legacy_dataset_objects_remain_exact(dataset_id):
    assert data.load_dataset(dataset_id)==data._legacy_load_dataset(dataset_id)
    assert for_strategy({"schema_version":1},dataset_id)==data._legacy_load_dataset(dataset_id)


@pytest.mark.local_archives
def test_verified_intraday_clocks_and_true_volume_fields():
    minute=data.load_dataset("verified_btc_1m_2025_01")
    assert minute["metadata"]["bars"]==44640
    assert minute["bars"][0]["time"]=="2025-01-01T00:00:00Z"
    assert all(b["timestamp"]%60000==0 for b in minute["bars"])
    assert all("quote_volume" in b and "number_of_trades" in b for b in minute["bars"])
    hourly=data.load_dataset("verified_btc_1h_2025_01")
    assert len(hourly["bars"])==744
    assert hourly["bars"][0]["close"]==minute["bars"][59]["close"]
    assert hourly["bars"][0]["quote_volume"]==sum(b["quote_volume"] for b in minute["bars"][:60])
    assert minute["provenance"]["network_downloads"]==0
    assert minute["provenance"]["independent_evaluation"] is False


@pytest.mark.local_archives
def test_auxiliary_native_daily_source_and_missing_intraday_asset():
    spec={"schema_version":2,"symbol":"BTCUSDT","timeframe":"4h", "nodes":[{"type":"market","params":{"symbol":"ETHUSDT","timeframe":"1d"}}]}
    assembled=for_strategy(spec,"verified_btc_4h")
    assert len(assembled["auxiliary"]["ETHUSDT:1d"]["bars"])==1461
    assert assembled["auxiliary"]["ETHUSDT:1d"]["metadata"]["availability_seconds"]==5
    with pytest.raises(ValueError,match="Cross-asset intraday"):
        for_strategy(spec,"verified_btc_1h_2025_01")


def test_chart_auth_bounds_alignment_and_nonexistent_provider(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/market/chart",params={"dataset_id":"demo_btc_4h"}).status_code==401
        client.post("/api/auth/demo",json={})
        query={"dataset_id":"demo_btc_4h","limit":10,"start":"2023-02-01","end":"2023-02-03","indicators":json.dumps([{"id":"sma3","kind":"sma","params":{"period":3}}])}
        response=client.get("/api/market/chart",params=query)
        assert response.status_code==200,response.text
        chart=response.json();assert chart["returned_bars"]==10 and chart["truncated"] and chart["warmup_bars"]>0
        assert len(chart["indicators"][0]["values"])==10 and chart["indicators"][0]["values"][0] is not None
        prior=chart["bars"][0]["timestamp"]
        full=data.load_dataset("demo_btc_4h")["bars"];i=next(i for i,b in enumerate(full) if b["timestamp"]==prior)
        assert chart["indicators"][0]["values"][0]==pytest.approx(sum(b["close"] for b in full[i-2:i+1])/3)
        assert client.get("/api/market/chart",params={"dataset_id":"demo_btc_4h","limit":5001}).status_code==422
        assert client.get("/api/market/chart",params={"dataset_id":"demo_btc_4h","end":"2026-01-01"}).status_code==422
        assert client.get("/api/market/chart",params={"dataset_id":"nonexistent"}).status_code==422
        assert client.get("/api/market/chart",params={"dataset_id":"demo_btc_4h","indicators":json.dumps([{"kind":"funding"}])}).status_code==422

"""Strict data-provider contracts for future independently authorized adapters.

These definitions do not connect a feed, open a database, or reinterpret event
clocks as publication clocks. A connected feed must supply its own permission,
quality, version and availability evidence before a node can execute.
"""
from __future__ import annotations
from typing import Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field, model_validator

FAMILIES=("spot_ohlcv","futures_ohlcv","funding_settled","funding_indicative","open_interest","mark_index", "book_snapshot","book_update","aggregate_trade","liquidation_event","news","sentiment","cross_asset")

class SourcePermission(BaseModel):
    model_config=ConfigDict(extra="forbid")
    access:Literal["local_authorized","official_public","licensed","unverified"]
    terms_url:str|None=None
    redistribution:Literal["unknown","prohibited","allowed"]="unknown"
    scope:str=Field(max_length=2000)

class MarketObservation(BaseModel):
    model_config=ConfigDict(extra="forbid",allow_inf_nan=False)
    schema_version:Literal["kedr-observation/2"]="kedr-observation/2"
    source_id:str=Field(min_length=1,max_length=100)
    family:Literal["spot_ohlcv","futures_ohlcv","funding_settled","funding_indicative","open_interest","mark_index","book_snapshot","book_update","aggregate_trade","liquidation_event","news","sentiment","cross_asset"]
    venue:str=Field(min_length=1,max_length=100)
    symbol:str=Field(min_length=1,max_length=30)
    native_timestamp:str=Field(min_length=1,max_length=100)
    native_unit:Literal["seconds","milliseconds","microseconds","nanoseconds","iso8601"]
    event_timestamp_ms:int=Field(ge=0)
    period_end_ms:int|None=Field(default=None,ge=0)
    first_seen_ms:int|None=Field(default=None,ge=0)
    receipt_ms:int|None=Field(default=None,ge=0)
    available_at_ms:int|None=Field(default=None,ge=0)
    availability_basis:Literal["archived_receipt","archived_first_seen","assumed_lag","unknown"]="unknown"
    assumed_lag_ms:int|None=Field(default=None,ge=0,le=7*86400000)
    timezone:Literal["UTC"]="UTC"
    sampling_interval_ms:int|None=Field(default=None,ge=1)
    source_version:str=Field(min_length=1,max_length=200)
    acquired_at:str=Field(min_length=1,max_length=100)
    valid:bool
    gap_before:bool=False
    quality_flags:list[str]=Field(default_factory=list,max_length=30)
    values:dict[str,float|int|str|bool|None]=Field(max_length=80)
    permission:SourcePermission

    @model_validator(mode="after")
    def causal_clock(self):
        if self.family=="funding_settled" and "indicative" in self.quality_flags:
            raise ValueError("Indicative funding must use funding_indicative, not a settled observation.")
        if self.family=="liquidation_event" and self.values.get("exchange_labelled") is not True:
            raise ValueError("A liquidation observation requires an exchange label; a price proxy is not a liquidation.")
        base=self.period_end_ms if self.period_end_ms is not None else self.event_timestamp_ms
        if self.availability_basis=="unknown":
            if self.available_at_ms is not None: raise ValueError("Unknown availability cannot declare an available_at clock.")
        elif self.availability_basis=="archived_receipt":
            if self.receipt_ms is None or self.available_at_ms is None or self.available_at_ms<max(base,self.receipt_ms):
                raise ValueError("Receipt eligibility must be no earlier than the archived receipt and completed observation.")
        elif self.availability_basis=="archived_first_seen":
            if self.first_seen_ms is None or self.available_at_ms is None or self.available_at_ms<max(base,self.first_seen_ms):
                raise ValueError("First-seen eligibility must follow the archived first observation.")
        elif self.assumed_lag_ms is None or self.available_at_ms is None or self.available_at_ms<base+self.assumed_lag_ms:
            raise ValueError("Assumed-lag availability needs a disclosed lag and cannot precede it.")
        return self

    def usable_at(self,decision_ms:int,max_age_ms:int|None=None)->bool:
        return bool(self.valid and self.permission.access!="unverified" and self.available_at_ms is not None and
                    self.available_at_ms<=decision_ms and (max_age_ms is None or 0<=decision_ms-self.available_at_ms<=max_age_ms))

class DatasetCoverage(BaseModel):
    model_config=ConfigDict(extra="forbid")
    source_id:str
    family:str
    symbol:str
    start_ms:int|None
    end_ms:int|None
    sampling_interval_ms:int|None
    observations:int=Field(ge=0)
    invalid:int=Field(ge=0)
    gaps:int=Field(ge=0)
    source_version:str
    permission:SourcePermission
    verified_receipt_timestamps:bool=False
    historical_revision_warning:str

class ObservationProvider(Protocol):
    def coverage(self)->DatasetCoverage: ...
    def observations(self,*,start_ms:int,end_ms:int,limit:int)->list[MarketObservation]: ...


def capabilities():
    return [{"family":family,"status":"local_verified" if family in {"spot_ohlcv","cross_asset"} else "not_connected",
             "execution_enabled":family in {"spot_ohlcv","cross_asset"},
             "receipt_verified":False,"source":"verified local archives" if family in {"spot_ohlcv","cross_asset"} else None,
             "message":"Read-only retrospective OHLCV with disclosed availability assumption" if family in {"spot_ohlcv","cross_asset"} else "Contract validated; no executable historical adapter is connected"} for family in FAMILIES]

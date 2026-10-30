"""Provider-neutral boundaries. No secrets, network calls or arbitrary code execution.

Adapters must explicitly identify their capabilities. Adding an environment key
alone never changes a service to connected. Production adapters must implement
bounded timeouts, per-user quotas, health checks and structured validation.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field

@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    status: Literal['connected','unhealthy','demo','not_configured','coming_soon']
    checked_at: str
    capabilities: tuple[str,...] = ()
    message: str = ''

class AnalysisSection(BaseModel):
    title: str
    body: str
    metric_references: list[str] = Field(default_factory=list)

class AnalysisEnvelope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    mode: Literal['offline_rules','external_ai']
    template_version: str = 'kedr-research-explanation/1'
    summary: str
    sections: list[AnalysisSection]
    limitations: list[str] = Field(default_factory=list)

class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    prompt: str = Field(min_length=10,max_length=2000)
    locale: Literal['ru','en'] = 'ru'
    schema_version: Literal[1] = 1
    supported_node_types: list[str] = Field(default_factory=list,max_length=40)

class GenerationResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    spec: dict[str,Any]
    explanations: list[str]
    template_version: str
    # A response must additionally pass domain.validate_strategy before saving.

@dataclass(frozen=True)
class Article:
    id: str
    source_url: str
    title: str
    published_at: str
    first_seen_at: str
    content_hash: str
    symbols: tuple[str,...]
    is_fixture: bool = False

@dataclass(frozen=True)
class SentimentObservation:
    article_id: str
    observed_at: str
    model_version: str
    label: Literal['positive','negative','neutral']
    score: float | None = None
    # This label is text sentiment, never a future-return probability.

class MarketDataProvider(Protocol):
    def health(self) -> ProviderHealth: ...
    def list_datasets(self) -> list[dict[str,Any]]: ...
    def load(self,dataset_id:str) -> dict[str,Any]: ...

class ResearchAnalysisProvider(Protocol):
    def health(self) -> ProviderHealth: ...
    def analyze(self,run:dict[str,Any],locale:str,*,timeout_seconds:float=20,max_output_tokens:int=1500) -> AnalysisEnvelope: ...

class StrategyGenerationProvider(Protocol):
    def generate(self,request:GenerationRequest) -> GenerationResponse: ...

class NewsProvider(Protocol):
    def health(self) -> ProviderHealth: ...
    def articles(self,symbol:str,*,limit:int=20) -> list[Article]: ...

class SentimentProvider(Protocol):
    def health(self) -> ProviderHealth: ...
    def classify(self,article:Article) -> SentimentObservation: ...

class TrainingWorker(Protocol):
    def health(self) -> ProviderHealth: ...
    def submit(self,*,owner_id:str,immutable_dataset_hash:str,feature_schema:dict[str,Any],chronological_split:dict[str,str],budget:dict[str,int]) -> str: ...
    def status(self,job_id:str,owner_id:str) -> dict[str,Any]: ...

@dataclass(frozen=True)
class RegionPolicy:
    country_code: str
    available_features: tuple[str,...] = ('research','backtesting')
    exchange_access_verified: bool = False
    payment_methods: tuple[str,...] = ()
    notes: str = 'Research only; country-specific access and regulatory terms are not asserted.'

@dataclass(frozen=True)
class DisabledExecutionGateway:
    """No execution implementation is included in the foundation."""
    enabled: bool = field(default=False,init=False)
    def submit_order(self,*args:Any,**kwargs:Any) -> None:
        raise RuntimeError('Live trading is disabled; no exchange credentials or order adapter is supported.')

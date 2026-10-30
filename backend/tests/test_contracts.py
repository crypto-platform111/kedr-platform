import pytest
from pydantic import ValidationError
from backend.app.contracts import DisabledExecutionGateway, GenerationRequest, RegionPolicy
from backend.app.providers import provider_statuses

def test_live_gateway_cannot_send_orders():
    gateway=DisabledExecutionGateway()
    assert gateway.enabled is False
    with pytest.raises(RuntimeError,match='disabled'):
        gateway.submit_order(symbol='BTCUSDT',quantity=1)

def test_future_generation_input_is_bounded_data():
    request=GenerationRequest(prompt='Describe a simple MA crossover',locale='ru')
    assert request.schema_version==1
    with pytest.raises(ValidationError):
        GenerationRequest(prompt='x'*2001)
    with pytest.raises(ValidationError):
        GenerationRequest(prompt='A bounded strategy request',executable_code='print(1)')

def test_configured_key_does_not_claim_connected(monkeypatch):
    monkeypatch.setenv('KEDR_AI_API_KEY','test-only-not-a-real-key')
    providers=provider_statuses()
    ai=next(item for item in providers if item['id']=='ai')
    assert ai['configured'] and ai['status']=='not_connected' and not ai['capabilities']
    assert 'test-only-not-a-real-key' not in str(providers)

def test_region_extension_has_no_exchange_access_claim():
    policy=RegionPolicy(country_code='KZ')
    assert not policy.exchange_access_verified
    assert 'execution' not in policy.available_features

"""A source clone must work without private historical files or D: paths."""
import json
import os
from pathlib import Path
import subprocess
import sys

from backend.app import data, data_v2


def test_empty_historical_configuration_is_explicit_and_demo_is_deterministic(tmp_path):
    project = Path(__file__).resolve().parents[2]
    env = {**os.environ, "KEDR_LEGACY_ROOT": "", "KEDR_DATA_DIR": str(tmp_path / "app")}
    code = """
from fastapi.testclient import TestClient
from backend.app import data
from backend.app.providers import provider_statuses
from backend.app.main import create_app
import json, os
assert data.LEGACY_ROOT is None and data.MANIFEST is None
catalog = data.datasets()
available = [r for r in catalog if r['status'] == 'available']
assert len(available) == 6 and all(r['source_type'] == 'synthetic_demo' for r in available)
real = [r for r in catalog if r['source_type'] == 'verified_historical']
assert len(real) == 10 and all(r['status'] == 'unavailable' and not r['verified'] for r in real)
for row in real:
    try: data.load_dataset(row['id'])
    except ValueError as exc: assert 'unconfigured' in str(exc)
    else: raise AssertionError('Historical source was silently replaced')
demo = data.load_dataset('demo_btc_4h')
assert demo['metadata']['sha256'] == '9d0a8601c0d15e0dd1acb6fac6e25ad568f39fc851bd2328c50355e496351063'
assert demo['provenance']['network_downloads'] == 0
provider = next(p for p in provider_statuses() if p['id'] == 'historical_data')
assert provider['status'] == 'unconfigured' and not provider['configured']
assert not provider['manifest_installed'] and provider['capabilities'] == ['synthetic_demo', 'strict_utc_coarsening']
with TestClient(create_app(os.environ['KEDR_DATA_DIR'])) as client:
    assert client.get('/api/health').status_code == 200
    assert client.post('/api/auth/demo', json={}).status_code == 200
    chart = client.get('/api/market/chart', params={'dataset_id':'demo_btc_4h','limit':10})
    assert chart.status_code == 200 and len(chart.json()['bars']) == 10
    missing = client.get('/api/market/chart', params={'dataset_id':'verified_btc_4h','limit':10})
    assert missing.status_code == 422 and 'unconfigured' in missing.json()['detail']
print(json.dumps({'available_demo_datasets':len(available),'unavailable_optional_datasets':len(real)}))
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=project, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.splitlines()[-1])["available_demo_datasets"] == 6


def test_all_demo_series_retain_frozen_identity_and_true_coarsening():
    expected = {
        "BTCUSDT": "9d0a8601c0d15e0dd1acb6fac6e25ad568f39fc851bd2328c50355e496351063",
        "ETHUSDT": "8fcefd99160c019ca49d562eb9948efd554550ea7cc16e8369d8deff25abee96",
        "SOLUSDT": "d3e358797ab16f56bd2915c12776bfab58a42e4a89135470d741db4e438433e3",
    }
    for symbol, digest in expected.items():
        prefix = symbol[:3].lower()
        native = data.load_dataset(f"demo_{prefix}_4h")
        assert native["metadata"]["sha256"] == digest
        assert native["provenance"]["adapter"] == "seeded_synthetic_v1"
        daily = data.load_dataset(f"demo_{prefix}_1d")
        actual, _ = data_v2.strict_resample(native["bars"], "4h", "1d")
        assert daily["bars"] == actual and len(actual) == 365
        assert daily["metadata"]["source_type"] == "synthetic_demo"
        assert daily["metadata"]["verified"] is False


def test_demo_multitimeframe_alignment_without_external_files():
    spec = {"schema_version": 2, "symbol": "BTCUSDT", "timeframe": "4h", "nodes": [
        {"type": "market", "params": {"symbol": "ETHUSDT", "timeframe": "1d"}}
    ]}
    assembled = data.load_dataset_for_strategy(spec, "demo_btc_4h")
    auxiliary = assembled["auxiliary"]["ETHUSDT:1d"]
    assert len(auxiliary["bars"]) == 365
    assert auxiliary["metadata"]["source_type"] == "synthetic_demo"
    assert all(row["timestamp"] % 86_400_000 == 0 for row in auxiliary["bars"])

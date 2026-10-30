"""Exercise the deployed host/origin boundary without a cloud DB or network."""
import pytest
from fastapi.testclient import TestClient

from backend.app.hosting import allowed_hosts, allowed_origins, secure_cookies
from backend.app.main import create_app


@pytest.fixture(autouse=True)
def isolated_host_configuration(monkeypatch):
    for name in ("VERCEL", "VERCEL_ENV", "VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL",
                 "KEDR_ALLOWED_HOSTS", "KEDR_ALLOWED_ORIGINS", "KEDR_SECURE_COOKIES"):
        monkeypatch.delenv(name, raising=False)


def test_preview_accepts_its_exact_host_and_origin_with_secure_session(tmp_path, monkeypatch):
    monkeypatch.setenv("KEDR_ALLOWED_HOSTS", "kedr-preview-example.vercel.app")
    monkeypatch.setenv("KEDR_ALLOWED_ORIGINS", "https://kedr-preview-example.vercel.app")
    monkeypatch.setenv("KEDR_SECURE_COOKIES", "1")
    with TestClient(create_app(tmp_path), base_url="https://kedr-preview-example.vercel.app") as client:
        assert client.get("/api/health").status_code == 200
        response = client.post("/api/auth/demo", headers={"Origin": "https://kedr-preview-example.vercel.app"})
        assert response.status_code == 200
        assert "Secure" in response.headers["set-cookie"]
        csrf = response.json()["csrf_token"]
        assert client.patch("/api/profile", json={"locale": "en"}, headers={
            "Origin": "https://kedr-preview-example.vercel.app", "X-CSRF-Token": csrf,
        }).status_code == 200
        assert client.post("/api/auth/demo", headers={"Origin": "https://attacker.example"}).status_code == 403
        assert client.get("/api/health", headers={"Host": "kedr-preview-example.vercel.app.attacker.example"}).status_code == 400


def test_custom_origin_allows_reverse_proxy_scheme_without_trusting_forwarded_origin(tmp_path, monkeypatch):
    monkeypatch.setenv("KEDR_ALLOWED_HOSTS", "studio.example.com")
    monkeypatch.setenv("KEDR_ALLOWED_ORIGINS", "https://studio.example.com")
    with TestClient(create_app(tmp_path), base_url="http://studio.example.com") as client:
        assert client.post("/api/auth/demo", headers={"Origin": "https://studio.example.com"}).status_code == 200
        assert client.post("/api/auth/demo", headers={
            "Origin": "https://attacker.example", "X-Forwarded-Host": "attacker.example",
        }).status_code == 403


def test_local_vercel_dev_origin_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "development")
    monkeypatch.setenv("VERCEL_URL", "127.0.0.1:3000")
    monkeypatch.setenv("KEDR_ALLOWED_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000")
    with TestClient(create_app(tmp_path), base_url="http://127.0.0.1:8715") as client:
        response = client.post("/api/auth/demo", headers={"Origin": "http://127.0.0.1:3000"})
        assert response.status_code == 200
        assert "; Secure" not in response.headers["set-cookie"]
        assert client.post("/api/auth/demo", headers={"Origin": "http://127.0.0.1:3001"}).status_code == 403


@pytest.mark.parametrize("value", ["*", "https://*.example.com", "https://example.com/path", "https://example.com?x=1", "https://example.com#x", "https://name:x@example.com", "ftp://example.com", "https://example.com:bad"])
def test_ambiguous_origins_are_rejected(monkeypatch, value):
    monkeypatch.setenv("KEDR_ALLOWED_ORIGINS", value)
    with pytest.raises(ValueError):
        allowed_origins()


def test_generated_domain_is_used_only_in_vercel_environment(monkeypatch):
    monkeypatch.setenv("VERCEL_URL", "unrelated.example.com")
    assert "unrelated.example.com" not in allowed_hosts()
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_URL", "*.vercel.app")
    with pytest.raises(ValueError):
        allowed_hosts()


def test_cloud_storage_fails_closed_and_cookies_default_secure(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_ENV", "preview")
    monkeypatch.setenv("KEDR_DATABASE_URL", "")
    assert secure_cookies() is True
    with pytest.raises(RuntimeError, match="shared PostgreSQL"):
        create_app(tmp_path)

"""Exact host/origin configuration for local and Vercel request routing.

This module configures HTTP only. It does not turn SQLite or local workers
into distributed persistence or durable cloud jobs.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlsplit


LOCAL_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
_HOST = re.compile(r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


def vercel_cloud() -> bool:
    return os.environ.get("VERCEL") == "1" and os.environ.get("VERCEL_ENV") != "development"


def configured_database_url() -> str:
    explicit = os.environ.get("KEDR_DATABASE_URL", "").strip()
    # Marketplace Neon injects DATABASE_URL. Do not consume a generic URL from
    # an unrelated local shell; the fallback belongs only to this cloud project.
    return explicit or (os.environ.get("DATABASE_URL", "").strip() if vercel_cloud() else "")


def _vercel_hosts() -> list[str]:
    # `vercel dev` injects a local URL containing its port, not a cloud hostname.
    # Local origins stay explicit; never turn that value into an HTTPS origin.
    if not vercel_cloud():
        return []
    result = []
    for name in ("VERCEL_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
        value = os.environ.get(name, "").strip().lower()
        if value:
            if not _HOST.fullmatch(value):
                raise ValueError(f"{name} must contain an exact hostname without a scheme or path")
            result.append(value)
    return result


def allowed_hosts() -> list[str]:
    hosts = ["127.0.0.1", "localhost", "testserver", *_vercel_hosts()]
    hosts.extend(value.strip() for value in os.environ.get("KEDR_ALLOWED_HOSTS", "").split(",") if value.strip())
    return list(dict.fromkeys(hosts))


def allowed_origins() -> list[str]:
    origins = [*LOCAL_ORIGINS, *(f"https://{host}" for host in _vercel_hosts())]
    for value in os.environ.get("KEDR_ALLOWED_ORIGINS", "").split(","):
        value = value.strip()
        if not value:
            continue
        parsed = urlsplit(value)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or "*" in parsed.netloc):
            raise ValueError("KEDR_ALLOWED_ORIGINS must contain exact HTTP(S) origins, without credentials or paths")
        # Evaluating port rejects malformed authorities such as ':not-a-port'.
        parsed.port
        origins.append(f"{parsed.scheme}://{parsed.netloc}".lower())
    return list(dict.fromkeys(origins))


def secure_cookies() -> bool:
    value = os.environ.get("KEDR_SECURE_COOKIES")
    if value is not None:
        return value == "1"
    return os.environ.get("VERCEL") == "1" and os.environ.get("VERCEL_ENV") != "development"

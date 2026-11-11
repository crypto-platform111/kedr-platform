from types import SimpleNamespace

import psycopg

from backend.app import postgres


class Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def capture(monkeypatch, *, windows=True):
    calls = []
    monkeypatch.setattr(postgres, "os", SimpleNamespace(name="nt" if windows else "posix"))
    monkeypatch.setattr(psycopg, "connect", lambda url, **options: calls.append((url, options)) or Connection())
    return calls


def test_windows_neon_keeps_tls_hostname_and_resolves_a_fresh_address(monkeypatch):
    calls = capture(monkeypatch)
    addresses = iter(["203.0.113.1", "203.0.113.2"])
    monkeypatch.setattr(postgres.socket, "gethostbyname", lambda host: next(addresses))
    url = "postgresql://u:x@fixture.neon.tech/neondb?sslmode=verify-full&channel_binding=require"
    for _ in range(2):
        with postgres.connect_postgres(url):
            pass
    assert [options["hostaddr"] for _, options in calls] == ["203.0.113.1", "203.0.113.2"]
    assert all(original == url for original, _ in calls)


def test_linux_and_non_neon_connections_keep_driver_defaults(monkeypatch):
    calls = capture(monkeypatch, windows=False)
    monkeypatch.setattr(postgres.socket, "gethostbyname", lambda host: (_ for _ in ()).throw(AssertionError("Unexpected DNS lookup")))
    with postgres.connect_postgres("postgresql://u:x@fixture.neon.tech/db?sslmode=require"):
        pass
    monkeypatch.setattr(postgres, "os", SimpleNamespace(name="nt"))
    with postgres.connect_postgres("postgresql://u:x@other.example.invalid/db?sslmode=require"):
        pass
    assert all("hostaddr" not in options for _, options in calls)


def test_explicit_addresses_and_ipv6_only_endpoints_are_preserved(monkeypatch):
    calls = capture(monkeypatch)
    def no_ipv4(host):
        raise postgres.socket.gaierror("No IPv4 record")
    monkeypatch.setattr(postgres.socket, "gethostbyname", no_ipv4)
    with postgres.connect_postgres("postgresql://u:x@fixture.neon.tech/db?hostaddr=203.0.113.5&sslmode=require"):
        pass
    with postgres.connect_postgres("postgresql://u:x@fixture.neon.tech/db?sslmode=require"):
        pass
    assert all("hostaddr" not in options for _, options in calls)

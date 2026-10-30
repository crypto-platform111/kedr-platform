import asyncio
import json

from backend.app.hosted_response import HostedJSONResponse


def test_large_json_is_chunked_without_changing_content_or_cookie_headers():
    value = {"trace": "a" * 4_800_000}
    response = HostedJSONResponse(value, headers={"Cache-Control": "no-store"})
    response.set_cookie("fixture", "test-only", httponly=True, secure=True)
    messages = []

    async def send(message):
        messages.append(message)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    asyncio.run(response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send))
    headers = dict(messages[0]["headers"])
    assert b"content-length" not in headers
    assert headers[b"content-type"] == b"application/json"
    assert headers[b"cache-control"] == b"no-store"
    assert b"HttpOnly" in headers[b"set-cookie"]
    parts = [message for message in messages if message["type"] == "http.response.body"]
    assert len(parts) > 2 and parts[0]["more_body"] is True
    assert max(len(part["body"]) for part in parts) <= 64 * 1024
    assert json.loads(b"".join(part["body"] for part in parts)) == value


def test_small_json_retains_normal_response_semantics():
    response = HostedJSONResponse({"status": "ok"})
    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(response({"type": "http"}, None, send))
    assert b"content-length" in dict(messages[0]["headers"])
    assert len(messages) == 2

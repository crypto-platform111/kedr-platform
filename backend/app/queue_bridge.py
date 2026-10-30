"""Private Vercel-generated queue subscriber, not a public HTTP callback.

The Vercel build reads the subscriber declared in pyproject.toml. The SDK
authenticates the private delivery, renews its queue lease and acknowledges only
after this function returns. Application-row leases additionally fence writes.
Importing this module at build time never opens a database or loads user data.
"""
from __future__ import annotations

import re

from vercel.queue import Message, RetryAfter, subscribe

from .durable_jobs import DurableJobs, TOPIC, WorkBusy
from .hosting import configured_database_url


@subscribe(topic=TOPIC, consumer_group="kedr-work-v1", retry_after=60, max_concurrency=2, max_attempts=20)
async def process_work(message: Message[dict[str, str]]) -> None:
    payload = message.payload
    if not isinstance(payload, dict) or set(payload) != {"work_key"}:
        raise ValueError("Invalid durable work reference")
    key = payload["work_key"]
    if not isinstance(key, str) or not re.fullmatch(r"(?:backtest|research):[a-f0-9]{32}", key):
        raise ValueError("Invalid durable work reference")
    # Lazy construction prevents migrations and connections during discovery.
    from .db import Database

    database_url = configured_database_url()
    if not database_url:
        raise RuntimeError("Hosted queue worker requires the configured shared database")
    db = Database("/tmp/kedr", database_url=database_url)
    service = DurableJobs(db)
    try:
        await service.handle(key)
    except WorkBusy:
        raise RetryAfter(60) from None

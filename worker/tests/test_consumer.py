"""Worker-loop resilience: transient Redis failures must not kill the worker.

Regression tests for the Colima crash where an idle BLPOP raised
``redis.exceptions.TimeoutError`` and took the whole worker down.
"""

from __future__ import annotations

import types

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from worker import consumer


class FlakyRedis:
    """Fake client that raises on the first N pops, then answers normally."""

    def __init__(self, failures: int, exc: Exception) -> None:
        self.failures = failures
        self.exc = exc
        self.calls = 0

    def blpop(self, key: str, timeout: int = 5):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc
        return None


def test_blpop_retries_transient_socket_timeout() -> None:
    client = FlakyRedis(2, RedisTimeoutError("Timeout reading from socket"))
    assert consumer.blpop_with_retry(client, "tabforge:queue", timeout=5) is None
    assert client.calls == 3


def test_blpop_retries_connection_error() -> None:
    client = FlakyRedis(1, RedisConnectionError("Connection reset by peer"))
    assert consumer.blpop_with_retry(client, "tabforge:queue", timeout=5) is None
    assert client.calls == 2


def test_blpop_raises_after_sustained_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    """After max_wait of continuous failures the helper gives up (restart policy's job)."""
    clock = [0.0]
    monkeypatch.setattr(
        consumer,
        "time",
        types.SimpleNamespace(
            monotonic=lambda: clock[0],
            sleep=lambda s: clock.__setitem__(0, clock[0] + s),
        ),
    )

    class Down:
        def __init__(self) -> None:
            self.calls = 0

        def blpop(self, key: str, timeout: int = 5):
            self.calls += 1
            raise RedisConnectionError("down")

    client = Down()
    with pytest.raises(RedisConnectionError):
        consumer.blpop_with_retry(client, "tabforge:queue", timeout=5, max_wait=3.0)
    assert client.calls == 4

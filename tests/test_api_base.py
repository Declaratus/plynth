from __future__ import annotations

from unittest.mock import patch

import responses

from plynth.engine.api_base import GHESClient


def test_auth_header_set() -> None:
    client = GHESClient("https://ghes.example.com", "tok123", write_delay_ms=0)
    assert client.session.headers["Authorization"] == "Bearer tok123"
    assert client.session.headers["Accept"] == "application/json"


def test_write_delay_enforced() -> None:
    client = GHESClient("https://ghes.example.com", "tok", write_delay_ms=500)
    client._record_write()

    with patch("plynth.engine.api_base.time") as mock_time:
        # 100ms after the recorded write — 400ms remaining.
        mock_time.time.return_value = client._last_write_time + 0.1
        client._wait_for_write_delay()

    # sleep called with positive remaining time
    mock_time.sleep.assert_called_once()
    slept_for = mock_time.sleep.call_args[0][0]
    assert 0.39 <= slept_for <= 0.41


def test_write_delay_not_enforced_when_elapsed() -> None:
    client = GHESClient("https://ghes.example.com", "tok", write_delay_ms=500)
    client._record_write()

    with patch("plynth.engine.api_base.time") as mock_time:
        # 1s after the recorded write — already past the delay.
        mock_time.time.return_value = client._last_write_time + 1.0
        client._wait_for_write_delay()

    mock_time.sleep.assert_not_called()


def test_handle_retry_with_retry_after_header() -> None:
    client = GHESClient("https://ghes.example.com", "tok", write_delay_ms=0)

    @responses.activate
    def _do() -> bool:
        responses.add(
            responses.GET,
            "https://ghes.example.com/api/test",
            status=429,
            headers={"Retry-After": "0"},
        )
        r = client.session.get("https://ghes.example.com/api/test")
        with patch("plynth.engine.api_base.time.sleep") as mock_sleep:
            should_retry = client._handle_retry(r, attempt=0)
            mock_sleep.assert_called_once_with(0.0)
        return should_retry

    assert _do() is True


def test_handle_retry_503_uses_exponential_backoff() -> None:
    client = GHESClient("https://ghes.example.com", "tok", write_delay_ms=0)

    @responses.activate
    def _do() -> None:
        responses.add(responses.GET, "https://ghes.example.com/api/test", status=503)
        r = client.session.get("https://ghes.example.com/api/test")
        with patch("plynth.engine.api_base.time.sleep") as mock_sleep:
            assert client._handle_retry(r, attempt=2) is True
            # 2 ** 2 = 4
            mock_sleep.assert_called_once_with(4)

    _do()


def test_handle_retry_returns_false_on_200() -> None:
    client = GHESClient("https://ghes.example.com", "tok", write_delay_ms=0)

    @responses.activate
    def _do() -> bool:
        responses.add(responses.GET, "https://ghes.example.com/api/test", status=200)
        r = client.session.get("https://ghes.example.com/api/test")
        return client._handle_retry(r, attempt=0)

    assert _do() is False

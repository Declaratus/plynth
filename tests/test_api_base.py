from __future__ import annotations

from unittest.mock import patch

import pytest
import responses

from plynth.engine.api_base import GHESClient, GitHubClient, is_rate_limited_403


def test_auth_header_set() -> None:
    client = GitHubClient("https://ghes.example.com", "tok123", write_delay_ms=0)
    assert client.session.headers["Authorization"] == "Bearer tok123"
    assert client.session.headers["Accept"] == "application/json"


def test_default_headers_include_user_agent_and_api_version() -> None:
    """github.com 403s missing User-Agent on some paths; pin REST API version too."""
    client = GitHubClient("github.com", "tok", write_delay_ms=0)
    assert client.session.headers["User-Agent"].startswith("plynth/")
    assert client.session.headers["X-GitHub-Api-Version"] == "2022-11-28"


def test_endpoints_for_github_com() -> None:
    client = GitHubClient("github.com", "tok", write_delay_ms=0)
    assert client.graphql_endpoint == "https://api.github.com/graphql"
    assert client.rest_base == "https://api.github.com"
    assert client.display_target == "github.com"


def test_endpoints_for_empty_target_default_to_github_com() -> None:
    client = GitHubClient("", "tok", write_delay_ms=0)
    assert client.graphql_endpoint == "https://api.github.com/graphql"
    assert client.rest_base == "https://api.github.com"
    # display_target falls back to "github.com" for diagnostics.
    assert client.display_target == "github.com"


def test_endpoints_for_ghes() -> None:
    client = GitHubClient("https://ghes.example.com", "tok", write_delay_ms=0)
    assert client.graphql_endpoint == "https://ghes.example.com/api/graphql"
    assert client.rest_base == "https://ghes.example.com/api/v3"
    assert client.display_target == "https://ghes.example.com"


@pytest.mark.parametrize(
    "target,expected_is_ghes",
    [
        ("", False),
        ("github.com", False),
        ("github.com/", False),  # trailing slash tolerated by derive_api_roots
        ("https://api.github.com", False),
        ("https://api.github.com/", False),  # same
        ("https://ghes.example.com", True),
        ("https://ghes.example.com/", True),
        ("https://github.acme.internal", True),
    ],
)
def test_is_ghes(target: str, expected_is_ghes: bool) -> None:
    assert GitHubClient(target, "tok", write_delay_ms=0).is_ghes is expected_is_ghes


def test_installed_version_starts_none() -> None:
    client = GitHubClient("https://ghes.example.com", "tok", write_delay_ms=0)
    assert client.installed_version is None


def test_warn_if_below_warns_when_below(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    client = GitHubClient("https://ghes.example.com", "tok", write_delay_ms=0)
    client.installed_version = (3, 19)
    log = logging.getLogger("plynth.test.warn_if_below_below")
    with caplog.at_level(logging.WARNING, logger=log.name):
        client.warn_if_below((3, 20), "views API", log)
    msgs = [r.message for r in caplog.records if r.name == log.name]
    assert any("requires GHES 3.20+" in m and "detected 3.19" in m for m in msgs)


def test_warn_if_below_silent_when_at_or_above(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    client = GitHubClient("https://ghes.example.com", "tok", write_delay_ms=0)
    log = logging.getLogger("plynth.test.warn_if_below_above")

    for version in [(3, 20), (3, 21), (4, 0)]:
        client.installed_version = version
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger=log.name):
            client.warn_if_below((3, 20), "views API", log)
        assert [r for r in caplog.records if r.name == log.name] == []


def test_warn_if_below_silent_when_version_unknown(caplog: pytest.LogCaptureFixture) -> None:
    """github.com (None) and detection failures (also None) must not warn."""
    import logging

    client = GitHubClient("github.com", "tok", write_delay_ms=0)
    assert client.installed_version is None
    log = logging.getLogger("plynth.test.warn_if_below_unknown")
    with caplog.at_level(logging.WARNING, logger=log.name):
        client.warn_if_below((3, 20), "views API", log)
    assert [r for r in caplog.records if r.name == log.name] == []


def test_ghesclient_alias_emits_deprecation_warning() -> None:
    with pytest.warns(DeprecationWarning, match="GHESClient is deprecated"):
        client = GHESClient("https://ghes.example.com", "tok", write_delay_ms=0)
    # Functionally identical to GitHubClient.
    assert isinstance(client, GitHubClient)
    assert client.graphql_endpoint == "https://ghes.example.com/api/graphql"


def test_write_delay_enforced() -> None:
    client = GitHubClient("https://ghes.example.com", "tok", write_delay_ms=500)
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
    client = GitHubClient("https://ghes.example.com", "tok", write_delay_ms=500)
    client._record_write()

    with patch("plynth.engine.api_base.time") as mock_time:
        # 1s after the recorded write — already past the delay.
        mock_time.time.return_value = client._last_write_time + 1.0
        client._wait_for_write_delay()

    mock_time.sleep.assert_not_called()


def test_handle_retry_with_retry_after_header() -> None:
    client = GitHubClient("https://ghes.example.com", "tok", write_delay_ms=0)

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
    client = GitHubClient("https://ghes.example.com", "tok", write_delay_ms=0)

    @responses.activate
    def _do() -> None:
        responses.add(responses.GET, "https://ghes.example.com/api/test", status=503)
        r = client.session.get("https://ghes.example.com/api/test")
        with patch("plynth.engine.api_base.time.sleep") as mock_sleep:
            assert client._handle_retry(r, attempt=2) is True
            # 2 ** 2 = 4
            mock_sleep.assert_called_once_with(4)

    _do()


def test_handle_retry_clamps_large_retry_after_to_60s() -> None:
    client = GitHubClient("https://ghes.example.com", "tok", write_delay_ms=0)

    @responses.activate
    def _do() -> bool:
        responses.add(
            responses.GET,
            "https://ghes.example.com/api/test",
            status=429,
            headers={"Retry-After": "999999"},
        )
        r = client.session.get("https://ghes.example.com/api/test")
        with patch("plynth.engine.api_base.time.sleep") as mock_sleep:
            should_retry = client._handle_retry(r, attempt=0)
            mock_sleep.assert_called_once_with(60.0)
        return should_retry

    assert _do() is True


def test_handle_retry_returns_false_on_200() -> None:
    client = GitHubClient("https://ghes.example.com", "tok", write_delay_ms=0)

    @responses.activate
    def _do() -> bool:
        responses.add(responses.GET, "https://ghes.example.com/api/test", status=200)
        r = client.session.get("https://ghes.example.com/api/test")
        return client._handle_retry(r, attempt=0)

    assert _do() is False


# ── 403 retry policy (#41) ─────────────────────────────────────
#
# GitHub uses 403 for both rate-limit / abuse detection (retryable) and
# permission denial (not retryable). The retry helper only retries 403s that
# carry one of the canonical rate-limit signals; everything else falls
# through so the caller can raise AuthError.


def test_handle_retry_403_with_retry_after_retries() -> None:
    client = GitHubClient("https://ghes.example.com", "tok", write_delay_ms=0)

    @responses.activate
    def _do() -> bool:
        responses.add(
            responses.GET,
            "https://ghes.example.com/api/test",
            status=403,
            headers={"Retry-After": "0"},
        )
        r = client.session.get("https://ghes.example.com/api/test")
        with patch("plynth.engine.api_base.time.sleep"):
            return client._handle_retry(r, attempt=0)

    assert _do() is True


def test_handle_retry_403_with_zero_rate_limit_remaining_retries() -> None:
    client = GitHubClient("https://ghes.example.com", "tok", write_delay_ms=0)

    @responses.activate
    def _do() -> bool:
        responses.add(
            responses.GET,
            "https://ghes.example.com/api/test",
            status=403,
            headers={"X-RateLimit-Remaining": "0"},
        )
        r = client.session.get("https://ghes.example.com/api/test")
        with patch("plynth.engine.api_base.time.sleep"):
            return client._handle_retry(r, attempt=0)

    assert _do() is True


# Real GitHub phrasing trimmed to fit the line-length cap; the case-insensitive
# substring match in is_rate_limited_403 keys on the canonical phrases here.
_SECONDARY_RATE_LIMIT_BODIES = [
    "You have exceeded a secondary rate limit.",
    "You have triggered an abuse detection mechanism.",
]


@pytest.mark.parametrize("message", _SECONDARY_RATE_LIMIT_BODIES)
def test_handle_retry_403_with_rate_limit_body_message_retries(message: str) -> None:
    client = GitHubClient("https://ghes.example.com", "tok", write_delay_ms=0)

    @responses.activate
    def _do() -> bool:
        responses.add(
            responses.GET,
            "https://ghes.example.com/api/test",
            status=403,
            json={"message": message},
        )
        r = client.session.get("https://ghes.example.com/api/test")
        with patch("plynth.engine.api_base.time.sleep"):
            return client._handle_retry(r, attempt=0)

    assert _do() is True


def test_handle_retry_403_permission_denied_returns_false() -> None:
    """No rate-limit signals → permission denial. Don't sleep, don't retry."""
    client = GitHubClient("https://ghes.example.com", "tok", write_delay_ms=0)

    @responses.activate
    def _do() -> bool:
        responses.add(
            responses.GET,
            "https://ghes.example.com/api/test",
            status=403,
            json={"message": "Resource not accessible by integration"},
        )
        r = client.session.get("https://ghes.example.com/api/test")
        with patch("plynth.engine.api_base.time.sleep") as mock_sleep:
            should_retry = client._handle_retry(r, attempt=0)
            mock_sleep.assert_not_called()
        return should_retry

    assert _do() is False


@pytest.mark.parametrize(
    "headers,body,expected",
    [
        ({"Retry-After": "5"}, None, True),
        ({"X-RateLimit-Remaining": "0"}, None, True),
        ({"X-RateLimit-Remaining": "42"}, None, False),
        ({}, {"message": "You have exceeded a secondary rate limit."}, True),
        ({}, {"message": "abuse detection mechanism triggered"}, True),
        ({}, {"message": "Resource not accessible by integration"}, False),
        ({}, None, False),
    ],
)
def test_is_rate_limited_403_signal_matrix(
    headers: dict[str, str], body: dict | None, expected: bool
) -> None:
    """Single source of truth for the retry-vs-deny decision rule."""

    @responses.activate
    def _do() -> bool:
        kwargs: dict = {"status": 403, "headers": headers}
        if body is not None:
            kwargs["json"] = body
        responses.add(responses.GET, "https://ghes.example.com/api/test", **kwargs)
        client = GitHubClient("https://ghes.example.com", "tok", write_delay_ms=0)
        r = client.session.get("https://ghes.example.com/api/test")
        return is_rate_limited_403(r)

    assert _do() is expected

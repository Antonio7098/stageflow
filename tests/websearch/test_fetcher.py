"""Tests for websearch fetcher module."""

import asyncio

import pytest

from stageflow.websearch.fetcher import (
    FetchConfig,
    FetchResult,
    MockFetcher,
)


class TestFetchConfig:
    """Tests for FetchConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = FetchConfig()
        assert config.timeout == 30.0
        assert config.max_retries == 3
        assert config.retry_delay == 1.0
        assert config.follow_redirects is True
        assert config.max_redirects == 10
        assert config.verify_ssl is True
        assert config.max_content_length == 10_000_000

    def test_custom_values(self) -> None:
        """Test custom configuration."""
        config = FetchConfig(
            timeout=10.0,
            max_retries=5,
            user_agent="CustomBot/1.0",
        )
        assert config.timeout == 10.0
        assert config.max_retries == 5
        assert config.user_agent == "CustomBot/1.0"


class TestFetchResult:
    """Tests for FetchResult dataclass."""

    def test_default_values(self) -> None:
        """Test default result values."""
        result = FetchResult(url="https://example.com")
        assert result.url == "https://example.com"
        assert result.status_code == 0
        assert result.content == b""
        assert result.error is None

    def test_success_property(self) -> None:
        """Test success property."""
        result_ok = FetchResult(url="https://example.com", status_code=200)
        assert result_ok.success is True

        result_redirect = FetchResult(url="https://example.com", status_code=301)
        assert result_redirect.success is True

        result_404 = FetchResult(url="https://example.com", status_code=404)
        assert result_404.success is False

        result_500 = FetchResult(url="https://example.com", status_code=500)
        assert result_500.success is False

        result_error = FetchResult(
            url="https://example.com", status_code=200, error="Failed"
        )
        assert result_error.success is False

    def test_text_property_utf8(self) -> None:
        """Test text property with UTF-8 content."""
        result = FetchResult(
            url="https://example.com",
            content=b"Hello World",
            content_type="text/html; charset=utf-8",
        )
        assert result.text == "Hello World"

    def test_text_property_other_encoding(self) -> None:
        """Test text property with different encoding."""
        content = "Héllo Wörld".encode("iso-8859-1")
        result = FetchResult(
            url="https://example.com",
            content=content,
            content_type="text/html; charset=iso-8859-1",
        )
        assert "llo W" in result.text

    def test_text_property_fallback(self) -> None:
        """Test text property fallback for invalid encoding."""
        result = FetchResult(
            url="https://example.com",
            content=b"Hello\xff\xfeWorld",
            content_type="text/html",
        )
        text = result.text
        assert "Hello" in text

    def test_is_html_property(self) -> None:
        """Test is_html property."""
        html_result = FetchResult(
            url="https://example.com",
            content_type="text/html; charset=utf-8",
        )
        assert html_result.is_html is True

        xhtml_result = FetchResult(
            url="https://example.com",
            content_type="application/xhtml+xml",
        )
        assert xhtml_result.is_html is True

        json_result = FetchResult(
            url="https://example.com",
            content_type="application/json",
        )
        assert json_result.is_html is False

    def test_to_dict(self) -> None:
        """Test serialization."""
        result = FetchResult(
            url="https://example.com",
            final_url="https://www.example.com",
            status_code=200,
            content=b"Hello",
            content_type="text/html",
            duration_ms=150.5,
        )
        d = result.to_dict()
        assert d["url"] == "https://example.com"
        assert d["final_url"] == "https://www.example.com"
        assert d["status_code"] == 200
        assert d["content_length"] == 5
        assert d["duration_ms"] == 150.5


class TestMockFetcher:
    """Tests for MockFetcher."""

    @pytest.mark.asyncio
    async def test_mock_response(self) -> None:
        """Test mock fetcher returns configured responses."""
        responses = {
            "https://example.com": (
                200,
                "<html><body>Hello</body></html>",
                {"content-type": "text/html"},
            ),
        }
        fetcher = MockFetcher(responses)

        result = await fetcher.fetch("https://example.com")
        assert result.status_code == 200
        assert b"Hello" in result.content
        assert result.is_html is True

    @pytest.mark.asyncio
    async def test_mock_default_response(self) -> None:
        """Test mock fetcher returns default for unknown URLs."""
        fetcher = MockFetcher()

        result = await fetcher.fetch("https://unknown.com")
        assert result.status_code == 404
        assert result.text == "Not Found"

    @pytest.mark.asyncio
    async def test_mock_custom_default(self) -> None:
        """Test mock fetcher with custom default response."""
        fetcher = MockFetcher(
            default_response=(500, "Server Error", {"content-type": "text/plain"})
        )

        result = await fetcher.fetch("https://unknown.com")
        assert result.status_code == 500
        assert result.text == "Server Error"

    @pytest.mark.asyncio
    async def test_fetch_history(self) -> None:
        """Test mock fetcher records fetch history."""
        fetcher = MockFetcher()

        await fetcher.fetch("https://example.com")
        await fetcher.fetch("https://other.com")

        assert fetcher.fetch_history == [
            "https://example.com",
            "https://other.com",
        ]

    @pytest.mark.asyncio
    async def test_fetch_many(self) -> None:
        """Test batch fetching with mock."""
        responses = {
            "https://a.com": (200, "A", {"content-type": "text/html"}),
            "https://b.com": (200, "B", {"content-type": "text/html"}),
            "https://c.com": (200, "C", {"content-type": "text/html"}),
        }
        fetcher = MockFetcher(responses)

        results = await fetcher.fetch_many(
            ["https://a.com", "https://b.com", "https://c.com"],
            concurrency=2,
        )

        assert len(results) == 3
        assert results[0].text == "A"
        assert results[1].text == "B"
        assert results[2].text == "C"

    @pytest.mark.asyncio
    async def test_fetch_many_preserves_order(self) -> None:
        """Test batch fetching preserves URL order."""
        responses = {
            f"https://example.com/{i}": (200, f"Page {i}", {"content-type": "text/html"})
            for i in range(5)
        }
        fetcher = MockFetcher(responses)

        urls = [f"https://example.com/{i}" for i in range(5)]
        results = await fetcher.fetch_many(urls)

        for i, result in enumerate(results):
            assert result.text == f"Page {i}"

    @pytest.mark.asyncio
    async def test_fetch_many_empty_list(self) -> None:
        """Test batch fetching with empty list."""
        fetcher = MockFetcher()
        results = await fetcher.fetch_many([])
        assert results == []


class TestFetcherObservability:
    """Tests for fetcher observability hooks."""

    @pytest.mark.asyncio
    async def test_on_fetch_start_called(self) -> None:
        """Test on_fetch_start callback is called."""
        calls: list[tuple[str, str]] = []

        def on_start(url: str, request_id: str) -> None:
            calls.append((url, request_id))

        fetcher = MockFetcher(on_fetch_start=on_start)
        await fetcher.fetch("https://example.com")

        assert len(calls) == 1
        assert calls[0][0] == "https://example.com"
        assert calls[0][1]  # request_id should be non-empty

    @pytest.mark.asyncio
    async def test_on_fetch_complete_called(self) -> None:
        """Test on_fetch_complete callback is called on success."""
        calls: list[tuple] = []

        def on_complete(
            url: str,
            request_id: str,
            status: int,
            duration_ms: float,
            size: int,
            from_cache: bool,
        ) -> None:
            calls.append((url, request_id, status, duration_ms, size, from_cache))

        responses = {
            "https://example.com": (200, "Hello", {"content-type": "text/html"}),
        }
        fetcher = MockFetcher(responses, on_fetch_complete=on_complete)
        await fetcher.fetch("https://example.com")

        assert len(calls) == 1
        assert calls[0][0] == "https://example.com"
        assert calls[0][2] == 200  # status
        assert calls[0][4] == 5  # size of "Hello"

    @pytest.mark.asyncio
    async def test_on_fetch_error_called(self) -> None:
        """Test on_fetch_error callback is called on failure."""
        calls: list[tuple] = []

        def on_error(
            url: str,
            request_id: str,
            error: str,
            duration_ms: float,
            retryable: bool,
        ) -> None:
            calls.append((url, request_id, error, duration_ms, retryable))

        responses = {
            "https://example.com": (500, "Error", {"content-type": "text/html"}),
        }
        fetcher = MockFetcher(responses, on_fetch_error=on_error)
        await fetcher.fetch("https://example.com")

        assert len(calls) == 1
        assert calls[0][0] == "https://example.com"
        assert "500" in calls[0][2]  # error message
        assert calls[0][4] is True  # retryable (5xx)


class TestFetcherRetry:
    """Tests for fetcher retry logic."""

    @pytest.mark.asyncio
    async def test_retry_count_tracked(self) -> None:
        """Test retry count is tracked in result."""
        fetcher = MockFetcher()
        result = await fetcher.fetch("https://example.com")
        assert result.retry_count == 0

    @pytest.mark.asyncio
    async def test_config_affects_behavior(self) -> None:
        """Test FetchConfig affects fetcher behavior."""
        config = FetchConfig(timeout=5.0, max_retries=1)
        fetcher = MockFetcher(config=config)

        assert fetcher.config.timeout == 5.0
        assert fetcher.config.max_retries == 1

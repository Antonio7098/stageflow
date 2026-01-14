"""Async HTTP fetcher with retries, timeouts, and observability.

Implements FetcherProtocol for reliable web page fetching with:
- Configurable timeouts and retries
- Concurrent batch fetching with semaphore control
- Observability hooks for logging/tracing
- User-agent rotation and rate limiting support
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


@dataclass(frozen=True, slots=True)
class FetchConfig:
    """Configuration for HTTP fetching.

    Attributes:
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
        retry_delay: Base delay between retries (exponential backoff)
        follow_redirects: Whether to follow HTTP redirects
        max_redirects: Maximum number of redirects to follow
        user_agent: User-Agent header value
        default_headers: Default headers for all requests
        verify_ssl: Whether to verify SSL certificates
        max_content_length: Maximum response size in bytes (0 = unlimited)
    """

    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    follow_redirects: bool = True
    max_redirects: int = 10
    user_agent: str = (
        "Mozilla/5.0 (compatible; StageflowBot/1.0; +https://stageflow.dev/bot)"
    )
    default_headers: dict[str, str] = field(default_factory=dict)
    verify_ssl: bool = True
    max_content_length: int = 10_000_000  # 10MB default


@dataclass(slots=True)
class FetchResult:
    """Result of a fetch operation.

    Attributes:
        url: Original requested URL
        final_url: Final URL after redirects
        status_code: HTTP status code
        content: Response body as bytes
        content_type: Content-Type header value
        headers: Response headers
        duration_ms: Request duration in milliseconds
        retry_count: Number of retries performed
        error: Error message if failed
        request_id: Unique ID for this request (for tracing)
    """

    url: str
    final_url: str | None = None
    status_code: int = 0
    content: bytes = b""
    content_type: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    duration_ms: float = 0.0
    retry_count: int = 0
    error: str | None = None
    request_id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def success(self) -> bool:
        """Check if request was successful."""
        return self.error is None and 200 <= self.status_code < 400

    @property
    def text(self) -> str:
        """Decode content as text."""
        if not self.content:
            return ""
        encoding = "utf-8"
        if "charset=" in self.content_type.lower():
            try:
                charset_part = self.content_type.lower().split("charset=")[1]
                encoding = charset_part.split(";")[0].strip()
            except (IndexError, ValueError):
                pass
        try:
            return self.content.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            return self.content.decode("utf-8", errors="replace")

    @property
    def is_html(self) -> bool:
        """Check if response is HTML."""
        ct = self.content_type.lower()
        return "text/html" in ct or "application/xhtml" in ct

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "url": self.url,
            "final_url": self.final_url,
            "status_code": self.status_code,
            "content_type": self.content_type,
            "content_length": len(self.content),
            "headers": self.headers,
            "duration_ms": self.duration_ms,
            "retry_count": self.retry_count,
            "error": self.error,
            "request_id": self.request_id,
        }


class Fetcher:
    """Base fetcher class with retry logic and observability.

    Subclass and override _do_fetch for custom HTTP implementations.
    """

    def __init__(
        self,
        config: FetchConfig | None = None,
        *,
        on_fetch_start: Callable[[str, str], None] | None = None,
        on_fetch_complete: Callable[[str, str, int, float, int, bool], None]
        | None = None,
        on_fetch_error: Callable[[str, str, str, float, bool], None] | None = None,
    ) -> None:
        """Initialize fetcher.

        Args:
            config: Fetch configuration
            on_fetch_start: Callback(url, request_id) when fetch starts
            on_fetch_complete: Callback(url, request_id, status, duration_ms, size, from_cache)
            on_fetch_error: Callback(url, request_id, error, duration_ms, retryable)
        """
        self.config = config or FetchConfig()
        self._on_fetch_start = on_fetch_start
        self._on_fetch_complete = on_fetch_complete
        self._on_fetch_error = on_fetch_error

    def _emit_start(self, url: str, request_id: str) -> None:
        """Emit fetch start event."""
        if self._on_fetch_start:
            with suppress(Exception):
                self._on_fetch_start(url, request_id)

    def _emit_complete(
        self,
        url: str,
        request_id: str,
        status: int,
        duration_ms: float,
        size: int,
        from_cache: bool = False,
    ) -> None:
        """Emit fetch complete event."""
        if self._on_fetch_complete:
            with suppress(Exception):
                self._on_fetch_complete(
                    url, request_id, status, duration_ms, size, from_cache
                )

    def _emit_error(
        self,
        url: str,
        request_id: str,
        error: str,
        duration_ms: float,
        retryable: bool = False,
    ) -> None:
        """Emit fetch error event."""
        if self._on_fetch_error:
            with suppress(Exception):
                self._on_fetch_error(url, request_id, error, duration_ms, retryable)

    async def _do_fetch(
        self,
        url: str,
        *,
        timeout: float,
        headers: dict[str, str],
        follow_redirects: bool,
    ) -> FetchResult:
        """Perform actual HTTP request. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement _do_fetch")

    async def fetch(
        self,
        url: str,
        *,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
        follow_redirects: bool | None = None,
    ) -> FetchResult:
        """Fetch a URL with retries and observability.

        Args:
            url: The URL to fetch
            timeout: Request timeout (uses config default if None)
            headers: Additional headers (merged with config defaults)
            follow_redirects: Whether to follow redirects (uses config if None)

        Returns:
            FetchResult with response data or error
        """
        request_id = str(uuid4())
        effective_timeout = timeout if timeout is not None else self.config.timeout
        effective_follow = (
            follow_redirects
            if follow_redirects is not None
            else self.config.follow_redirects
        )

        merged_headers = {
            "User-Agent": self.config.user_agent,
            **self.config.default_headers,
            **(headers or {}),
        }

        self._emit_start(url, request_id)
        start_time = time.perf_counter()
        last_error: str | None = None
        retry_count = 0

        for attempt in range(self.config.max_retries + 1):
            try:
                result = await self._do_fetch(
                    url,
                    timeout=effective_timeout,
                    headers=merged_headers,
                    follow_redirects=effective_follow,
                )
                result.request_id = request_id
                result.retry_count = retry_count

                duration_ms = (time.perf_counter() - start_time) * 1000
                result.duration_ms = duration_ms

                if result.success:
                    self._emit_complete(
                        url,
                        request_id,
                        result.status_code,
                        duration_ms,
                        len(result.content),
                    )
                else:
                    self._emit_error(
                        url,
                        request_id,
                        result.error or f"HTTP {result.status_code}",
                        duration_ms,
                        retryable=result.status_code >= 500,
                    )

                return result

            except Exception as e:
                last_error = str(e)
                retry_count = attempt + 1
                is_retryable = self._is_retryable_error(e)

                if attempt < self.config.max_retries and is_retryable:
                    delay = self.config.retry_delay * (2**attempt)
                    await asyncio.sleep(delay)
                else:
                    break

        duration_ms = (time.perf_counter() - start_time) * 1000
        self._emit_error(
            url, request_id, last_error or "Unknown error", duration_ms, retryable=False
        )

        return FetchResult(
            url=url,
            error=last_error or "Unknown error",
            duration_ms=duration_ms,
            retry_count=retry_count,
            request_id=request_id,
        )

    def _is_retryable_error(self, error: Exception) -> bool:
        """Check if an error is retryable."""
        error_str = str(error).lower()
        retryable_patterns = [
            "timeout",
            "connection",
            "reset",
            "refused",
            "temporary",
            "503",
            "502",
            "504",
            "429",
        ]
        return any(pattern in error_str for pattern in retryable_patterns)

    async def fetch_many(
        self,
        urls: list[str],
        *,
        concurrency: int = 5,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
    ) -> list[FetchResult]:
        """Fetch multiple URLs concurrently.

        Args:
            urls: List of URLs to fetch
            concurrency: Maximum concurrent requests
            timeout: Per-request timeout
            headers: Additional headers for all requests

        Returns:
            List of FetchResults in same order as input URLs
        """
        if not urls:
            return []

        semaphore = asyncio.Semaphore(concurrency)

        async def fetch_with_semaphore(url: str) -> FetchResult:
            async with semaphore:
                return await self.fetch(url, timeout=timeout, headers=headers)

        tasks = [fetch_with_semaphore(url) for url in urls]
        return await asyncio.gather(*tasks)


class HttpFetcher(Fetcher):
    """HTTP fetcher using httpx for async requests.

    Requires httpx to be installed: pip install httpx
    """

    def __init__(
        self,
        config: FetchConfig | None = None,
        *,
        client: Any | None = None,
        on_fetch_start: Callable[[str, str], None] | None = None,
        on_fetch_complete: Callable[[str, str, int, float, int, bool], None]
        | None = None,
        on_fetch_error: Callable[[str, str, str, float, bool], None] | None = None,
    ) -> None:
        """Initialize HTTP fetcher.

        Args:
            config: Fetch configuration
            client: Optional pre-configured httpx.AsyncClient
            on_fetch_start: Callback when fetch starts
            on_fetch_complete: Callback when fetch completes
            on_fetch_error: Callback when fetch errors
        """
        if not HTTPX_AVAILABLE:
            raise ImportError(
                "httpx is required for HttpFetcher. Install with: pip install httpx"
            )

        super().__init__(
            config,
            on_fetch_start=on_fetch_start,
            on_fetch_complete=on_fetch_complete,
            on_fetch_error=on_fetch_error,
        )
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout),
                follow_redirects=self.config.follow_redirects,
                max_redirects=self.config.max_redirects,
                verify=self.config.verify_ssl,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client if we own it."""
        if self._client and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> HttpFetcher:
        """Async context manager entry."""
        await self._get_client()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def _do_fetch(
        self,
        url: str,
        *,
        timeout: float,
        headers: dict[str, str],
        follow_redirects: bool,
    ) -> FetchResult:
        """Perform HTTP request using httpx."""
        client = await self._get_client()

        response = await client.get(
            url,
            headers=headers,
            timeout=timeout,
            follow_redirects=follow_redirects,
        )

        content = response.content
        if (
            self.config.max_content_length > 0
            and len(content) > self.config.max_content_length
        ):
            content = content[: self.config.max_content_length]

        return FetchResult(
            url=url,
            final_url=str(response.url),
            status_code=response.status_code,
            content=content,
            content_type=response.headers.get("content-type", ""),
            headers=dict(response.headers),
        )


class MockFetcher(Fetcher):
    """Mock fetcher for testing.

    Provide responses dict mapping URLs to (status_code, content, headers).
    """

    def __init__(
        self,
        responses: dict[str, tuple[int, str | bytes, dict[str, str]]] | None = None,
        *,
        default_response: tuple[int, str | bytes, dict[str, str]] | None = None,
        config: FetchConfig | None = None,
        on_fetch_start: Callable[[str, str], None] | None = None,
        on_fetch_complete: Callable[[str, str, int, float, int, bool], None]
        | None = None,
        on_fetch_error: Callable[[str, str, str, float, bool], None] | None = None,
    ) -> None:
        """Initialize mock fetcher.

        Args:
            responses: Dict mapping URL to (status, content, headers)
            default_response: Default response for unmapped URLs
            config: Fetch configuration
            on_fetch_start: Callback when fetch starts
            on_fetch_complete: Callback when fetch completes
            on_fetch_error: Callback when fetch errors
        """
        super().__init__(
            config,
            on_fetch_start=on_fetch_start,
            on_fetch_complete=on_fetch_complete,
            on_fetch_error=on_fetch_error,
        )
        self.responses = responses or {}
        self.default_response = default_response or (
            404,
            "Not Found",
            {"content-type": "text/plain"},
        )
        self.fetch_history: list[str] = []

    async def _do_fetch(
        self,
        url: str,
        *,
        timeout: float,
        headers: dict[str, str],
        follow_redirects: bool,
    ) -> FetchResult:
        """Return mock response."""
        del timeout, headers, follow_redirects
        self.fetch_history.append(url)

        status, content, resp_headers = self.responses.get(url, self.default_response)

        if isinstance(content, str):
            content = content.encode("utf-8")

        return FetchResult(
            url=url,
            final_url=url,
            status_code=status,
            content=content,
            content_type=resp_headers.get("content-type", "text/html"),
            headers=resp_headers,
        )


__all__ = [
    "FetchConfig",
    "FetchResult",
    "Fetcher",
    "HttpFetcher",
    "MockFetcher",
    "HTTPX_AVAILABLE",
]

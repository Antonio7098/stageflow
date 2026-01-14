"""High-level web search client.

Combines fetcher, extractor, and navigator into a unified API
for fetching and processing web pages.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from stageflow.websearch.extractor import (
    ContentExtractor,
    DefaultContentExtractor,
    ExtractionConfig,
    FallbackContentExtractor,
    SELECTOLAX_AVAILABLE,
)
from stageflow.websearch.fetcher import (
    FetchConfig,
    FetchResult,
    Fetcher,
    HttpFetcher,
    HTTPX_AVAILABLE,
    MockFetcher,
)
from stageflow.websearch.models import (
    ExtractedLink,
    NavigationAction,
    PaginationInfo,
    WebPage,
)
from stageflow.websearch.navigator import (
    FallbackNavigator,
    NavigationConfig,
    Navigator,
    PageNavigator,
)


@dataclass(frozen=True, slots=True)
class WebSearchConfig:
    """Configuration for WebSearchClient.

    Attributes:
        fetch: Fetch configuration
        extraction: Extraction configuration
        navigation: Navigation configuration
        max_concurrent: Max concurrent fetches
        auto_extract: Auto-extract content after fetch
        auto_navigate: Auto-analyze navigation after fetch
    """

    fetch: FetchConfig = field(default_factory=FetchConfig)
    extraction: ExtractionConfig = field(default_factory=ExtractionConfig)
    navigation: NavigationConfig = field(default_factory=NavigationConfig)
    max_concurrent: int = 5
    auto_extract: bool = True
    auto_navigate: bool = True


class WebSearchClient:
    """High-level client for web searching and content extraction.

    Combines fetching, extraction, and navigation into a simple API.
    Supports both single and batch operations with full observability.

    Example:
        ```python
        async with WebSearchClient() as client:
            # Single page
            page = await client.fetch("https://example.com")
            print(page.markdown)
            print(page.links)

            # Batch fetch
            pages = await client.fetch_many([
                "https://a.com",
                "https://b.com",
            ])

            # Navigate - follow a link
            if page.pagination and page.pagination.next_url:
                next_page = await client.fetch(page.pagination.next_url)
        ```
    """

    def __init__(
        self,
        config: WebSearchConfig | None = None,
        *,
        fetcher: Fetcher | None = None,
        extractor: ContentExtractor | None = None,
        navigator: Navigator | None = None,
        on_fetch_start: Callable[[str, str], None] | None = None,
        on_fetch_complete: Callable[[str, str, int, float, int, bool], None]
        | None = None,
        on_fetch_error: Callable[[str, str, str, float, bool], None] | None = None,
        on_extract_complete: Callable[[str, str, float, int, int], None] | None = None,
    ) -> None:
        """Initialize web search client.

        Args:
            config: Client configuration
            fetcher: Custom fetcher (uses HttpFetcher by default)
            extractor: Custom extractor (uses DefaultContentExtractor by default)
            navigator: Custom navigator (uses PageNavigator by default)
            on_fetch_start: Callback(url, request_id) when fetch starts
            on_fetch_complete: Callback(url, request_id, status, duration_ms, size, cached)
            on_fetch_error: Callback(url, request_id, error, duration_ms, retryable)
            on_extract_complete: Callback(url, request_id, duration_ms, chars, links)
        """
        self.config = config or WebSearchConfig()
        self._on_extract_complete = on_extract_complete

        if fetcher is not None:
            self._fetcher = fetcher
            self._owns_fetcher = False
        elif HTTPX_AVAILABLE:
            self._fetcher = HttpFetcher(
                self.config.fetch,
                on_fetch_start=on_fetch_start,
                on_fetch_complete=on_fetch_complete,
                on_fetch_error=on_fetch_error,
            )
            self._owns_fetcher = True
        else:
            raise ImportError(
                "httpx is required for WebSearchClient. "
                "Install with: pip install httpx"
            )

        if extractor is not None:
            self._extractor = extractor
        elif SELECTOLAX_AVAILABLE:
            self._extractor = DefaultContentExtractor(self.config.extraction)
        else:
            self._extractor = FallbackContentExtractor(self.config.extraction)

        if navigator is not None:
            self._navigator = navigator
        elif SELECTOLAX_AVAILABLE:
            self._navigator = PageNavigator(self.config.navigation)
        else:
            self._navigator = FallbackNavigator(self.config.navigation)

    async def __aenter__(self) -> "WebSearchClient":
        """Async context manager entry."""
        if hasattr(self._fetcher, "__aenter__"):
            await self._fetcher.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the client and release resources."""
        if self._owns_fetcher and hasattr(self._fetcher, "close"):
            await self._fetcher.close()

    async def fetch(
        self,
        url: str,
        *,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
        selector: str | None = None,
        extract: bool | None = None,
        navigate: bool | None = None,
    ) -> WebPage:
        """Fetch and process a single URL.

        Args:
            url: URL to fetch
            timeout: Request timeout in seconds
            headers: Additional HTTP headers
            selector: CSS selector for content extraction
            extract: Whether to extract content (default: config.auto_extract)
            navigate: Whether to analyze navigation (default: config.auto_navigate)

        Returns:
            WebPage with fetched and processed content
        """
        request_id = str(uuid4())
        should_extract = extract if extract is not None else self.config.auto_extract
        should_navigate = navigate if navigate is not None else self.config.auto_navigate

        fetch_result = await self._fetcher.fetch(
            url, timeout=timeout, headers=headers
        )

        if not fetch_result.success:
            return WebPage.error_result(
                url,
                fetch_result.error or f"HTTP {fetch_result.status_code}",
                fetch_result.duration_ms,
            )

        if not fetch_result.is_html:
            return WebPage(
                url=url,
                final_url=fetch_result.final_url,
                status_code=fetch_result.status_code,
                markdown=fetch_result.text[:10000],
                plain_text=fetch_result.text[:10000],
                fetch_duration_ms=fetch_result.duration_ms,
                fetched_at=datetime.now(timezone.utc).isoformat(),
                word_count=len(fetch_result.text.split()),
            )

        html = fetch_result.text
        extract_start = time.perf_counter()

        if should_extract:
            extraction = self._extractor.extract(
                html,
                base_url=fetch_result.final_url or url,
                selector=selector,
            )
            markdown = extraction.markdown
            plain_text = extraction.plain_text
            metadata = extraction.metadata
            links = extraction.links
            word_count = extraction.word_count
        else:
            markdown = ""
            plain_text = ""
            metadata = self._extractor.extract_metadata(html)
            links = []
            word_count = 0

        navigation_actions: list[NavigationAction] = []
        pagination: PaginationInfo | None = None

        if should_navigate:
            nav_result = self._navigator.analyze(
                html, base_url=fetch_result.final_url or url
            )
            navigation_actions = nav_result.actions
            pagination = nav_result.pagination

        extract_duration_ms = (time.perf_counter() - extract_start) * 1000

        if self._on_extract_complete:
            try:
                self._on_extract_complete(
                    url,
                    request_id,
                    extract_duration_ms,
                    len(markdown),
                    len(links),
                )
            except Exception:
                pass

        return WebPage(
            url=url,
            final_url=fetch_result.final_url,
            status_code=fetch_result.status_code,
            markdown=markdown,
            plain_text=plain_text,
            metadata=metadata,
            links=links,
            navigation_actions=navigation_actions,
            pagination=pagination,
            fetch_duration_ms=fetch_result.duration_ms,
            extract_duration_ms=extract_duration_ms,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            word_count=word_count,
        )

    async def fetch_many(
        self,
        urls: list[str],
        *,
        concurrency: int | None = None,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
        selector: str | None = None,
        extract: bool | None = None,
        navigate: bool | None = None,
    ) -> list[WebPage]:
        """Fetch and process multiple URLs concurrently.

        Args:
            urls: List of URLs to fetch
            concurrency: Max concurrent requests (default: config.max_concurrent)
            timeout: Per-request timeout
            headers: Additional HTTP headers for all requests
            selector: CSS selector for content extraction
            extract: Whether to extract content
            navigate: Whether to analyze navigation

        Returns:
            List of WebPage results in same order as input URLs
        """
        if not urls:
            return []

        max_concurrent = concurrency or self.config.max_concurrent
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_with_semaphore(url: str) -> WebPage:
            async with semaphore:
                return await self.fetch(
                    url,
                    timeout=timeout,
                    headers=headers,
                    selector=selector,
                    extract=extract,
                    navigate=navigate,
                )

        tasks = [fetch_with_semaphore(url) for url in urls]
        return await asyncio.gather(*tasks)

    async def fetch_with_navigation(
        self,
        url: str,
        *,
        max_pages: int = 10,
        follow_pagination: bool = True,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
        selector: str | None = None,
    ) -> list[WebPage]:
        """Fetch a page and follow pagination links.

        Args:
            url: Starting URL
            max_pages: Maximum pages to fetch
            follow_pagination: Whether to follow pagination links
            timeout: Per-request timeout
            headers: Additional HTTP headers
            selector: CSS selector for content extraction

        Returns:
            List of WebPage results for all fetched pages
        """
        pages: list[WebPage] = []
        seen_urls: set[str] = set()
        current_url: str | None = url

        while current_url and len(pages) < max_pages:
            if current_url in seen_urls:
                break
            seen_urls.add(current_url)

            page = await self.fetch(
                current_url,
                timeout=timeout,
                headers=headers,
                selector=selector,
            )
            pages.append(page)

            if not follow_pagination or not page.pagination:
                break

            current_url = page.pagination.next_url

        return pages

    async def crawl(
        self,
        start_url: str,
        *,
        max_pages: int = 10,
        max_depth: int = 2,
        same_domain_only: bool = True,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
        selector: str | None = None,
        link_filter: Callable[[ExtractedLink], bool] | None = None,
    ) -> list[WebPage]:
        """Crawl pages starting from a URL.

        Args:
            start_url: Starting URL
            max_pages: Maximum total pages to fetch
            max_depth: Maximum link depth to follow
            same_domain_only: Only follow links to same domain
            timeout: Per-request timeout
            headers: Additional HTTP headers
            selector: CSS selector for content extraction
            link_filter: Optional function to filter which links to follow

        Returns:
            List of WebPage results for all crawled pages
        """
        from urllib.parse import urlparse

        pages: list[WebPage] = []
        seen_urls: set[str] = set()
        start_domain = urlparse(start_url).netloc

        queue: list[tuple[str, int]] = [(start_url, 0)]

        while queue and len(pages) < max_pages:
            current_url, depth = queue.pop(0)

            if current_url in seen_urls:
                continue
            seen_urls.add(current_url)

            page = await self.fetch(
                current_url,
                timeout=timeout,
                headers=headers,
                selector=selector,
            )
            pages.append(page)

            if depth >= max_depth:
                continue

            for link in page.links:
                if link.url in seen_urls:
                    continue

                if same_domain_only:
                    link_domain = urlparse(link.url).netloc
                    if link_domain != start_domain:
                        continue

                if link_filter and not link_filter(link):
                    continue

                queue.append((link.url, depth + 1))

        return pages

    def extract_content(
        self,
        html: str,
        *,
        base_url: str | None = None,
        selector: str | None = None,
    ) -> WebPage:
        """Extract content from HTML without fetching.

        Useful when you already have the HTML content.

        Args:
            html: Raw HTML string
            base_url: Base URL for resolving relative links
            selector: CSS selector for content extraction

        Returns:
            WebPage with extracted content (no fetch timing)
        """
        extract_start = time.perf_counter()

        extraction = self._extractor.extract(
            html, base_url=base_url, selector=selector
        )

        nav_result = self._navigator.analyze(html, base_url=base_url)

        extract_duration_ms = (time.perf_counter() - extract_start) * 1000

        return WebPage(
            url=base_url or "",
            status_code=200,
            markdown=extraction.markdown,
            plain_text=extraction.plain_text,
            metadata=extraction.metadata,
            links=extraction.links,
            navigation_actions=nav_result.actions,
            pagination=nav_result.pagination,
            extract_duration_ms=extract_duration_ms,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            word_count=extraction.word_count,
        )


def create_mock_client(
    responses: dict[str, tuple[int, str, dict[str, str]]] | None = None,
    *,
    config: WebSearchConfig | None = None,
) -> WebSearchClient:
    """Create a WebSearchClient with mock responses for testing.

    Args:
        responses: Dict mapping URL to (status_code, html_content, headers)
        config: Client configuration

    Returns:
        WebSearchClient configured with MockFetcher
    """
    mock_fetcher = MockFetcher(responses, config=config.fetch if config else None)
    return WebSearchClient(config, fetcher=mock_fetcher)


__all__ = [
    "WebSearchConfig",
    "WebSearchClient",
    "create_mock_client",
]

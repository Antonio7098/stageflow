"""Websearch run utilities for common search workflows.

Provides high-level functions for common websearch patterns:
- Single page fetch with minimal boilerplate
- Batch fetching with progress callbacks
- Search result aggregation
- Site mapping and crawling utilities

Example:
    ```python
    from stageflow.websearch.run_utils import (
        fetch_page,
        fetch_pages,
        search_and_extract,
        map_site,
    )

    # Single page
    page = await fetch_page("https://example.com")

    # Batch with progress
    pages = await fetch_pages(
        urls,
        concurrency=10,
        on_progress=lambda done, total: print(f"{done}/{total}"),
    )

    # Search and extract relevant content
    results = await search_and_extract(
        start_url="https://docs.example.com",
        query="installation guide",
        max_pages=20,
    )
    ```
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Any
from uuid import uuid4

from stageflow.websearch.client import WebSearchClient, WebSearchConfig
from stageflow.websearch.extractor import ExtractionResult
from stageflow.websearch.fetcher import FetchConfig, FetchResult
from stageflow.websearch.models import ExtractedLink, WebPage


@dataclass
class FetchProgress:
    """Progress information for batch fetches.

    Attributes:
        completed: Number of completed fetches
        total: Total number of URLs
        current_url: URL currently being fetched
        success_count: Number of successful fetches
        error_count: Number of failed fetches
        elapsed_ms: Elapsed time in milliseconds
    """

    completed: int = 0
    total: int = 0
    current_url: str | None = None
    success_count: int = 0
    error_count: int = 0
    elapsed_ms: float = 0.0

    @property
    def percent(self) -> float:
        """Get completion percentage."""
        return (self.completed / self.total * 100) if self.total > 0 else 0.0


@dataclass
class SearchResult:
    """Result from search_and_extract.

    Attributes:
        query: Original search query
        pages: All fetched pages
        relevant_pages: Pages matching the query
        total_words: Total word count across relevant pages
        duration_ms: Total operation time
    """

    query: str
    pages: list[WebPage] = field(default_factory=list)
    relevant_pages: list[WebPage] = field(default_factory=list)
    total_words: int = 0
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "query": self.query,
            "pages_fetched": len(self.pages),
            "relevant_pages": len(self.relevant_pages),
            "total_words": self.total_words,
            "duration_ms": self.duration_ms,
        }


@dataclass
class SiteMap:
    """Result from map_site.

    Attributes:
        start_url: Starting URL
        pages: All crawled pages
        internal_links: All internal links found
        external_links: All external links found
        depth_reached: Maximum depth reached
        duration_ms: Total crawl time
    """

    start_url: str
    pages: list[WebPage] = field(default_factory=list)
    internal_links: list[ExtractedLink] = field(default_factory=list)
    external_links: list[ExtractedLink] = field(default_factory=list)
    depth_reached: int = 0
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "start_url": self.start_url,
            "pages_crawled": len(self.pages),
            "internal_links": len(self.internal_links),
            "external_links": len(self.external_links),
            "depth_reached": self.depth_reached,
            "duration_ms": self.duration_ms,
        }


# Thread pool for CPU-bound extraction work
_extraction_executor: ThreadPoolExecutor | None = None


def _get_extraction_executor() -> ThreadPoolExecutor:
    """Get or create the extraction thread pool."""
    global _extraction_executor
    if _extraction_executor is None:
        _extraction_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="extract")
    return _extraction_executor


async def _run_in_thread(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a synchronous function in a thread pool."""
    loop = asyncio.get_running_loop()
    executor = _get_extraction_executor()
    return await loop.run_in_executor(executor, partial(func, *args, **kwargs))


async def fetch_page(
    url: str,
    *,
    timeout: float | None = None,
    headers: dict[str, str] | None = None,
    selector: str | None = None,
    config: WebSearchConfig | None = None,
) -> WebPage:
    """Fetch and extract a single page with minimal boilerplate.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        headers: Additional HTTP headers
        selector: CSS selector for content extraction
        config: WebSearch configuration

    Returns:
        WebPage with extracted content

    Example:
        ```python
        page = await fetch_page("https://example.com")
        print(page.title)
        print(page.markdown)
        ```
    """
    async with WebSearchClient(config) as client:
        return await client.fetch(
            url,
            timeout=timeout,
            headers=headers,
            selector=selector,
        )


async def fetch_pages(
    urls: list[str],
    *,
    concurrency: int = 5,
    timeout: float | None = None,
    headers: dict[str, str] | None = None,
    selector: str | None = None,
    config: WebSearchConfig | None = None,
    on_progress: Callable[[FetchProgress], None] | None = None,
    parallel_extraction: bool = True,
) -> list[WebPage]:
    """Fetch multiple pages with progress tracking and parallel extraction.

    Args:
        urls: List of URLs to fetch
        concurrency: Maximum concurrent requests
        timeout: Per-request timeout in seconds
        headers: Additional HTTP headers
        selector: CSS selector for content extraction
        config: WebSearch configuration
        on_progress: Callback for progress updates
        parallel_extraction: Use thread pool for CPU-bound extraction

    Returns:
        List of WebPage results in same order as input URLs

    Example:
        ```python
        def show_progress(p: FetchProgress):
            print(f"[{p.percent:.0f}%] {p.completed}/{p.total}")

        pages = await fetch_pages(
            urls,
            concurrency=10,
            on_progress=show_progress,
        )
        ```
    """
    if not urls:
        return []

    start_time = datetime.now(UTC)
    results: list[WebPage | None] = [None] * len(urls)
    url_to_index = {url: i for i, url in enumerate(urls)}

    progress = FetchProgress(total=len(urls))

    async with WebSearchClient(config) as client:
        semaphore = asyncio.Semaphore(concurrency)

        async def fetch_one(url: str, index: int) -> None:
            async with semaphore:
                progress.current_url = url

                if parallel_extraction:
                    # Fetch raw HTML first
                    fetch_result = await client._fetcher.fetch(
                        url, timeout=timeout, headers=headers
                    )

                    if fetch_result.success and fetch_result.is_html:
                        # Run extraction in thread pool
                        page = await _extract_page_async(
                            client,
                            url,
                            fetch_result,
                            selector,
                        )
                    elif fetch_result.success:
                        # Non-HTML content
                        page = WebPage(
                            url=url,
                            final_url=fetch_result.final_url,
                            status_code=fetch_result.status_code,
                            markdown=fetch_result.text[:10000],
                            plain_text=fetch_result.text[:10000],
                            fetch_duration_ms=fetch_result.duration_ms,
                            fetched_at=datetime.now(UTC).isoformat(),
                            word_count=len(fetch_result.text.split()),
                        )
                    else:
                        page = WebPage.error_result(
                            url,
                            fetch_result.error or f"HTTP {fetch_result.status_code}",
                            fetch_result.duration_ms,
                        )
                else:
                    page = await client.fetch(
                        url,
                        timeout=timeout,
                        headers=headers,
                        selector=selector,
                    )

                results[index] = page

                progress.completed += 1
                if page.success:
                    progress.success_count += 1
                else:
                    progress.error_count += 1
                progress.elapsed_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

                if on_progress:
                    on_progress(progress)

        tasks = [fetch_one(url, i) for i, url in enumerate(urls)]
        await asyncio.gather(*tasks)

    return [r for r in results if r is not None]


async def _extract_page_async(
    client: WebSearchClient,
    url: str,
    fetch_result: FetchResult,
    selector: str | None,
) -> WebPage:
    """Extract page content using thread pool for CPU-bound work."""
    import time

    html = fetch_result.text
    base_url = fetch_result.final_url or url

    extract_start = time.perf_counter()

    # Run extraction in thread pool
    extraction = await _run_in_thread(
        client._extractor.extract,
        html,
        base_url=base_url,
        selector=selector,
    )

    # Run navigation analysis in thread pool
    nav_result = await _run_in_thread(
        client._navigator.analyze,
        html,
        base_url=base_url,
    )

    extract_duration_ms = (time.perf_counter() - extract_start) * 1000

    return WebPage(
        url=url,
        final_url=fetch_result.final_url,
        status_code=fetch_result.status_code,
        markdown=extraction.markdown,
        plain_text=extraction.plain_text,
        metadata=extraction.metadata,
        links=extraction.links,
        navigation_actions=nav_result.actions,
        pagination=nav_result.pagination,
        fetch_duration_ms=fetch_result.duration_ms,
        extract_duration_ms=extract_duration_ms,
        fetched_at=datetime.now(UTC).isoformat(),
        word_count=extraction.word_count,
    )


async def search_and_extract(
    start_url: str,
    query: str,
    *,
    max_pages: int = 20,
    max_depth: int = 2,
    same_domain_only: bool = True,
    concurrency: int = 5,
    config: WebSearchConfig | None = None,
    relevance_threshold: float = 0.1,
    on_progress: Callable[[FetchProgress], None] | None = None,
) -> SearchResult:
    """Crawl a site and extract pages relevant to a query.

    Uses keyword matching to identify relevant pages. For more sophisticated
    relevance scoring, use an LLM-based approach with the raw pages.

    Args:
        start_url: URL to start crawling from
        query: Search query for relevance filtering
        max_pages: Maximum pages to fetch
        max_depth: Maximum link depth to follow
        same_domain_only: Only follow links to same domain
        concurrency: Maximum concurrent requests
        config: WebSearch configuration
        relevance_threshold: Minimum relevance score (0-1) to include
        on_progress: Progress callback

    Returns:
        SearchResult with all pages and relevant subset

    Example:
        ```python
        result = await search_and_extract(
            "https://docs.python.org",
            "asyncio tutorial",
            max_pages=50,
        )

        for page in result.relevant_pages:
            print(f"- {page.title}: {page.url}")
        ```
    """
    start_time = datetime.now(UTC)

    async with WebSearchClient(config) as client:
        pages = await client.crawl(
            start_url,
            max_pages=max_pages,
            max_depth=max_depth,
            same_domain_only=same_domain_only,
        )

    # Score relevance based on query keywords
    query_terms = set(query.lower().split())
    relevant_pages: list[WebPage] = []

    for page in pages:
        if not page.success:
            continue

        # Calculate simple relevance score
        content = f"{page.title or ''} {page.plain_text}".lower()
        matches = sum(1 for term in query_terms if term in content)
        score = matches / len(query_terms) if query_terms else 0

        if score >= relevance_threshold:
            relevant_pages.append(page)

    # Sort by relevance (pages with more keyword matches first)
    relevant_pages.sort(
        key=lambda p: sum(
            1 for term in query_terms
            if term in f"{p.title or ''} {p.plain_text}".lower()
        ),
        reverse=True,
    )

    total_words = sum(p.word_count for p in relevant_pages)
    duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

    return SearchResult(
        query=query,
        pages=pages,
        relevant_pages=relevant_pages,
        total_words=total_words,
        duration_ms=duration_ms,
    )


async def map_site(
    start_url: str,
    *,
    max_pages: int = 100,
    max_depth: int = 3,
    same_domain_only: bool = True,
    include_external: bool = True,
    concurrency: int = 5,
    config: WebSearchConfig | None = None,
    link_filter: Callable[[ExtractedLink], bool] | None = None,
    on_progress: Callable[[FetchProgress], None] | None = None,
) -> SiteMap:
    """Crawl and map a website's structure.

    Args:
        start_url: URL to start mapping from
        max_pages: Maximum pages to crawl
        max_depth: Maximum link depth
        same_domain_only: Only follow internal links
        include_external: Include external links in results
        concurrency: Maximum concurrent requests
        config: WebSearch configuration
        link_filter: Optional function to filter links
        on_progress: Progress callback

    Returns:
        SiteMap with all pages and link inventory

    Example:
        ```python
        sitemap = await map_site(
            "https://example.com",
            max_pages=200,
            max_depth=4,
        )

        print(f"Pages: {len(sitemap.pages)}")
        print(f"Internal links: {len(sitemap.internal_links)}")
        print(f"External links: {len(sitemap.external_links)}")
        ```
    """
    start_time = datetime.now(UTC)

    async with WebSearchClient(config) as client:
        pages = await client.crawl(
            start_url,
            max_pages=max_pages,
            max_depth=max_depth,
            same_domain_only=same_domain_only,
            link_filter=link_filter,
        )

    # Collect all links
    internal_links: list[ExtractedLink] = []
    external_links: list[ExtractedLink] = []
    seen_urls: set[str] = set()

    max_depth_reached = 0

    for page in pages:
        for link in page.links:
            if link.url in seen_urls:
                continue
            seen_urls.add(link.url)

            if link.is_internal:
                internal_links.append(link)
            elif include_external:
                external_links.append(link)

    duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

    return SiteMap(
        start_url=start_url,
        pages=pages,
        internal_links=internal_links,
        external_links=external_links,
        depth_reached=max_depth,  # Approximate - actual depth tracked in crawler
        duration_ms=duration_ms,
    )


async def fetch_with_retry(
    url: str,
    *,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    timeout: float | None = None,
    headers: dict[str, str] | None = None,
    config: WebSearchConfig | None = None,
) -> WebPage:
    """Fetch a page with automatic retry on failure.

    Args:
        url: URL to fetch
        max_retries: Maximum retry attempts
        retry_delay: Delay between retries in seconds
        timeout: Request timeout
        headers: Additional HTTP headers
        config: WebSearch configuration

    Returns:
        WebPage result (may contain error if all retries failed)

    Example:
        ```python
        page = await fetch_with_retry(
            "https://flaky-server.com/api",
            max_retries=5,
            retry_delay=2.0,
        )
        ```
    """
    last_error: str | None = None

    for attempt in range(max_retries + 1):
        page = await fetch_page(
            url,
            timeout=timeout,
            headers=headers,
            config=config,
        )

        if page.success:
            return page

        last_error = page.error

        if attempt < max_retries:
            await asyncio.sleep(retry_delay * (attempt + 1))  # Exponential backoff

    return WebPage.error_result(
        url,
        f"Failed after {max_retries + 1} attempts: {last_error}",
        0.0,
    )


async def extract_all_links(
    urls: list[str],
    *,
    concurrency: int = 10,
    internal_only: bool = False,
    external_only: bool = False,
    config: WebSearchConfig | None = None,
) -> list[ExtractedLink]:
    """Extract all links from multiple pages.

    Args:
        urls: URLs to fetch and extract links from
        concurrency: Maximum concurrent requests
        internal_only: Only return internal links
        external_only: Only return external links
        config: WebSearch configuration

    Returns:
        Deduplicated list of all extracted links

    Example:
        ```python
        links = await extract_all_links(
            seed_urls,
            internal_only=True,
        )

        print(f"Found {len(links)} unique internal links")
        ```
    """
    pages = await fetch_pages(urls, concurrency=concurrency, config=config)

    all_links: list[ExtractedLink] = []
    seen_urls: set[str] = set()

    for page in pages:
        if not page.success:
            continue

        for link in page.links:
            if link.url in seen_urls:
                continue

            if internal_only and not link.is_internal:
                continue
            if external_only and link.is_internal:
                continue

            seen_urls.add(link.url)
            all_links.append(link)

    return all_links


def shutdown_extraction_pool() -> None:
    """Shutdown the extraction thread pool.

    Call this during application shutdown to clean up resources.
    """
    global _extraction_executor
    if _extraction_executor is not None:
        _extraction_executor.shutdown(wait=True)
        _extraction_executor = None


__all__ = [
    "FetchProgress",
    "SearchResult",
    "SiteMap",
    "extract_all_links",
    "fetch_page",
    "fetch_pages",
    "fetch_with_retry",
    "map_site",
    "search_and_extract",
    "shutdown_extraction_pool",
]

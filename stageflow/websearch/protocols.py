"""Protocol definitions for web search components.

Follows Interface Segregation Principle - each protocol defines
a minimal, focused interface that implementations must satisfy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from stageflow.websearch.models import (
        ExtractedLink,
        NavigationAction,
        PageMetadata,
    )


@runtime_checkable
class FetcherProtocol(Protocol):
    """Protocol for HTTP fetching.

    Implementations handle the actual HTTP requests with
    retries, timeouts, and error handling.

    Example:
        class CustomFetcher:
            async def fetch(self, url: str, **kwargs) -> FetchResult:
                # Custom implementation
                ...
    """

    async def fetch(
        self,
        url: str,
        *,
        timeout: float | None = None,
        headers: dict[str, str] | None = None,
        follow_redirects: bool = True,
    ) -> "FetchResult":
        """Fetch a URL and return raw response data.

        Args:
            url: The URL to fetch
            timeout: Request timeout in seconds
            headers: Additional HTTP headers
            follow_redirects: Whether to follow redirects

        Returns:
            FetchResult with status, content, headers, timing
        """
        ...

    async def fetch_many(
        self,
        urls: list[str],
        *,
        concurrency: int = 5,
        timeout: float | None = None,
    ) -> list["FetchResult"]:
        """Fetch multiple URLs concurrently.

        Args:
            urls: List of URLs to fetch
            concurrency: Max concurrent requests
            timeout: Per-request timeout

        Returns:
            List of FetchResults in same order as input URLs
        """
        ...


@runtime_checkable
class ContentExtractorProtocol(Protocol):
    """Protocol for extracting structured content from HTML.

    Implementations parse HTML and produce clean, structured
    output (markdown, plain text, etc.) while preserving
    semantic structure like headings, lists, and links.
    """

    def extract(
        self,
        html: str,
        *,
        base_url: str | None = None,
        selector: str | None = None,
    ) -> "ExtractionResult":
        """Extract structured content from HTML.

        Args:
            html: Raw HTML string
            base_url: Base URL for resolving relative links
            selector: Optional CSS selector to target specific content

        Returns:
            ExtractionResult with markdown, metadata, links
        """
        ...

    def extract_metadata(self, html: str) -> "PageMetadata":
        """Extract page metadata (title, description, etc.).

        Args:
            html: Raw HTML string

        Returns:
            PageMetadata with title, description, language, etc.
        """
        ...

    def extract_links(
        self,
        html: str,
        *,
        base_url: str | None = None,
        selector: str | None = None,
    ) -> list["ExtractedLink"]:
        """Extract links from HTML.

        Args:
            html: Raw HTML string
            base_url: Base URL for resolving relative links
            selector: Optional CSS selector to filter links

        Returns:
            List of ExtractedLink objects
        """
        ...


@runtime_checkable
class NavigatorProtocol(Protocol):
    """Protocol for page navigation capabilities.

    Enables agents to explore web pages by following links,
    paginating through results, and discovering content.
    """

    def get_navigation_actions(
        self,
        html: str,
        *,
        base_url: str | None = None,
    ) -> list["NavigationAction"]:
        """Get available navigation actions from a page.

        Args:
            html: Raw HTML string
            base_url: Base URL for resolving relative links

        Returns:
            List of possible navigation actions
        """
        ...

    def find_pagination(
        self,
        html: str,
        *,
        base_url: str | None = None,
    ) -> "PaginationInfo | None":
        """Find pagination controls on a page.

        Args:
            html: Raw HTML string
            base_url: Base URL for resolving relative links

        Returns:
            PaginationInfo if pagination found, else None
        """
        ...

    def find_main_content_selector(self, html: str) -> str | None:
        """Auto-detect the main content area selector.

        Args:
            html: Raw HTML string

        Returns:
            CSS selector for main content, or None if not detected
        """
        ...


@runtime_checkable
class ObservabilityProtocol(Protocol):
    """Protocol for observability hooks.

    Implementations can log, trace, or emit metrics
    for web search operations.
    """

    def on_fetch_start(
        self,
        url: str,
        *,
        request_id: str | None = None,
    ) -> None:
        """Called when a fetch operation starts."""
        ...

    def on_fetch_complete(
        self,
        url: str,
        *,
        request_id: str | None = None,
        status_code: int,
        duration_ms: float,
        content_length: int,
        from_cache: bool = False,
    ) -> None:
        """Called when a fetch operation completes successfully."""
        ...

    def on_fetch_error(
        self,
        url: str,
        *,
        request_id: str | None = None,
        error: str,
        duration_ms: float,
        retryable: bool = False,
    ) -> None:
        """Called when a fetch operation fails."""
        ...

    def on_extract_complete(
        self,
        url: str,
        *,
        request_id: str | None = None,
        duration_ms: float,
        content_length: int,
        link_count: int,
    ) -> None:
        """Called when content extraction completes."""
        ...


class FetchResult:
    """Result of a fetch operation (forward declaration for protocol)."""

    url: str
    status_code: int
    content: bytes
    headers: dict[str, str]
    duration_ms: float
    error: str | None


class ExtractionResult:
    """Result of content extraction (forward declaration for protocol)."""

    markdown: str
    plain_text: str
    metadata: "PageMetadata"
    links: list["ExtractedLink"]
    word_count: int


class PaginationInfo:
    """Pagination information (forward declaration for protocol)."""

    current_page: int
    total_pages: int | None
    next_url: str | None
    prev_url: str | None
    page_urls: list[str]


__all__ = [
    "FetcherProtocol",
    "ContentExtractorProtocol",
    "NavigatorProtocol",
    "ObservabilityProtocol",
    "FetchResult",
    "ExtractionResult",
    "PaginationInfo",
]

"""Data models for web search results.

Immutable dataclasses representing web pages, metadata, links,
and navigation actions. Designed for serialization to JSON
and integration with Enrichments.web_results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse


@dataclass(frozen=True, slots=True)
class PageMetadata:
    """Metadata extracted from a web page.

    Attributes:
        title: Page title from <title> or og:title
        description: Meta description or og:description
        language: Page language from html[lang] or meta
        author: Author from meta[name=author]
        published_date: Publication date if found
        canonical_url: Canonical URL if specified
        og_image: Open Graph image URL
        keywords: Meta keywords list
        content_type: Detected content type (article, product, etc.)
    """

    title: str | None = None
    description: str | None = None
    language: str | None = None
    author: str | None = None
    published_date: str | None = None
    canonical_url: str | None = None
    og_image: str | None = None
    keywords: list[str] = field(default_factory=list)
    content_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "title": self.title,
            "description": self.description,
            "language": self.language,
            "author": self.author,
            "published_date": self.published_date,
            "canonical_url": self.canonical_url,
            "og_image": self.og_image,
            "keywords": self.keywords,
            "content_type": self.content_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PageMetadata:
        """Create from dictionary."""
        return cls(
            title=data.get("title"),
            description=data.get("description"),
            language=data.get("language"),
            author=data.get("author"),
            published_date=data.get("published_date"),
            canonical_url=data.get("canonical_url"),
            og_image=data.get("og_image"),
            keywords=data.get("keywords", []),
            content_type=data.get("content_type"),
        )


@dataclass(frozen=True, slots=True)
class ExtractedLink:
    """A link extracted from a web page.

    Attributes:
        url: Absolute URL of the link
        text: Link text content
        title: Link title attribute if present
        rel: Link rel attribute (e.g., "nofollow")
        is_internal: Whether link is to same domain
        context: Surrounding text for context
    """

    url: str
    text: str = ""
    title: str | None = None
    rel: str | None = None
    is_internal: bool = False
    context: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "url": self.url,
            "text": self.text,
            "title": self.title,
            "rel": self.rel,
            "is_internal": self.is_internal,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExtractedLink:
        """Create from dictionary."""
        return cls(
            url=data["url"],
            text=data.get("text", ""),
            title=data.get("title"),
            rel=data.get("rel"),
            is_internal=data.get("is_internal", False),
            context=data.get("context"),
        )

    @classmethod
    def from_element(
        cls,
        href: str,
        text: str,
        *,
        base_url: str | None = None,
        title: str | None = None,
        rel: str | None = None,
        context: str | None = None,
    ) -> ExtractedLink:
        """Create from HTML element attributes.

        Args:
            href: Raw href attribute value
            text: Link text content
            base_url: Base URL for resolving relative links
            title: Link title attribute
            rel: Link rel attribute
            context: Surrounding context text

        Returns:
            ExtractedLink with resolved absolute URL
        """
        if base_url and not href.startswith(("http://", "https://", "//")):
            url = urljoin(base_url, href)
        elif href.startswith("//"):
            url = "https:" + href
        else:
            url = href

        is_internal = False
        if base_url:
            base_domain = urlparse(base_url).netloc
            link_domain = urlparse(url).netloc
            is_internal = base_domain == link_domain

        return cls(
            url=url,
            text=text.strip(),
            title=title,
            rel=rel,
            is_internal=is_internal,
            context=context,
        )


@dataclass(frozen=True, slots=True)
class NavigationAction:
    """A navigation action available on a page.

    Represents something an agent can do to navigate:
    - Follow a link
    - Click pagination
    - Expand a section
    - Submit a search form

    Attributes:
        action_type: Type of action. Valid values:
            - ``"pagination"``: Pagination control (next/prev page)
            - ``"nav_link"``: Navigation menu link
            - ``"content_link"``: Link within main content area
            - ``"external"``: External link to different domain
        url: Target URL if applicable
        label: Human-readable label
        selector: CSS selector for the element
        priority: Suggested priority (1=highest, lower is more important)
        metadata: Additional action-specific data. For pagination actions,
            may include ``{"direction": "next"}`` or ``{"direction": "prev"}``
    """

    action_type: str
    label: str
    url: str | None = None
    selector: str | None = None
    priority: int = 5
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "action_type": self.action_type,
            "label": self.label,
            "url": self.url,
            "selector": self.selector,
            "priority": self.priority,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NavigationAction:
        """Create from dictionary."""
        return cls(
            action_type=data["action_type"],
            label=data["label"],
            url=data.get("url"),
            selector=data.get("selector"),
            priority=data.get("priority", 5),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True, slots=True)
class PaginationInfo:
    """Pagination information for a page.

    Attributes:
        current_page: Current page number (1-indexed)
        total_pages: Total pages if known
        next_url: URL of next page
        prev_url: URL of previous page
        page_urls: List of all page URLs if available
    """

    current_page: int = 1
    total_pages: int | None = None
    next_url: str | None = None
    prev_url: str | None = None
    page_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "current_page": self.current_page,
            "total_pages": self.total_pages,
            "next_url": self.next_url,
            "prev_url": self.prev_url,
            "page_urls": self.page_urls,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaginationInfo:
        """Create from dictionary."""
        return cls(
            current_page=data.get("current_page", 1),
            total_pages=data.get("total_pages"),
            next_url=data.get("next_url"),
            prev_url=data.get("prev_url"),
            page_urls=data.get("page_urls", []),
        )

    @property
    def has_next(self) -> bool:
        """Check if there's a next page."""
        return self.next_url is not None

    @property
    def has_prev(self) -> bool:
        """Check if there's a previous page."""
        return self.prev_url is not None


@dataclass(frozen=True, slots=True)
class WebPage:
    """A fetched and processed web page.

    Immutable container for all extracted data from a URL.
    Designed for storage in Enrichments.web_results.

    Attributes:
        url: Original requested URL
        final_url: Final URL after redirects
        status_code: HTTP status code
        markdown: Structured content as markdown
        plain_text: Plain text content (no formatting)
        metadata: Page metadata (title, description, etc.)
        links: Extracted links from the page
        navigation_actions: Available navigation actions
        pagination: Pagination info if detected
        fetch_duration_ms: Time to fetch in milliseconds
        extract_duration_ms: Time to extract in milliseconds
        fetched_at: Timestamp when fetched
        word_count: Number of words in content
        error: Error message if fetch/extract failed
    """

    url: str
    final_url: str | None = None
    status_code: int = 0
    markdown: str = ""
    plain_text: str = ""
    metadata: PageMetadata = field(default_factory=PageMetadata)
    links: list[ExtractedLink] = field(default_factory=list)
    navigation_actions: list[NavigationAction] = field(default_factory=list)
    pagination: PaginationInfo | None = None
    fetch_duration_ms: float = 0.0
    extract_duration_ms: float = 0.0
    fetched_at: str | None = None
    word_count: int = 0
    error: str | None = None

    @property
    def success(self) -> bool:
        """Check if page was fetched successfully."""
        return self.error is None and 200 <= self.status_code < 400

    @property
    def title(self) -> str | None:
        """Convenience accessor for page title."""
        return self.metadata.title

    @property
    def description(self) -> str | None:
        """Convenience accessor for page description."""
        return self.metadata.description

    @property
    def internal_links(self) -> list[ExtractedLink]:
        """Get only internal links."""
        return [link for link in self.links if link.is_internal]

    @property
    def external_links(self) -> list[ExtractedLink]:
        """Get only external links."""
        return [link for link in self.links if not link.is_internal]

    def extract_links(
        self,
        *,
        selector: str | None = None,
        internal_only: bool = False,
        external_only: bool = False,
        limit: int | None = None,
    ) -> list[ExtractedLink]:
        """Filter and return links.

        Args:
            selector: Not used (links already extracted), for API compat
            internal_only: Return only internal links
            external_only: Return only external links
            limit: Maximum number of links to return

        Returns:
            Filtered list of ExtractedLink objects
        """
        del selector  # For API compatibility; selection handled upstream

        links = self.links

        if internal_only:
            links = self.internal_links
        elif external_only:
            links = self.external_links

        if limit is not None:
            links = links[:limit]

        return links

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary.

        Compatible with Enrichments.web_results format.
        """
        return {
            "url": self.url,
            "final_url": self.final_url,
            "status_code": self.status_code,
            "markdown": self.markdown,
            "plain_text": self.plain_text,
            "metadata": self.metadata.to_dict(),
            "links": [link.to_dict() for link in self.links],
            "navigation_actions": [na.to_dict() for na in self.navigation_actions],
            "pagination": self.pagination.to_dict() if self.pagination else None,
            "fetch_duration_ms": self.fetch_duration_ms,
            "extract_duration_ms": self.extract_duration_ms,
            "fetched_at": self.fetched_at,
            "word_count": self.word_count,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WebPage:
        """Create from dictionary."""
        metadata = PageMetadata.from_dict(data.get("metadata", {}))
        links = [ExtractedLink.from_dict(link_data) for link_data in data.get("links", [])]
        navigation_actions = [
            NavigationAction.from_dict(na)
            for na in data.get("navigation_actions", [])
        ]
        pagination = None
        if data.get("pagination"):
            pagination = PaginationInfo.from_dict(data["pagination"])

        return cls(
            url=data["url"],
            final_url=data.get("final_url"),
            status_code=data.get("status_code", 0),
            markdown=data.get("markdown", ""),
            plain_text=data.get("plain_text", ""),
            metadata=metadata,
            links=links,
            navigation_actions=navigation_actions,
            pagination=pagination,
            fetch_duration_ms=data.get("fetch_duration_ms", 0.0),
            extract_duration_ms=data.get("extract_duration_ms", 0.0),
            fetched_at=data.get("fetched_at"),
            word_count=data.get("word_count", 0),
            error=data.get("error"),
        )

    @classmethod
    def error_result(cls, url: str, error: str, duration_ms: float = 0.0) -> WebPage:
        """Create an error result.

        Args:
            url: The URL that failed
            error: Error message
            duration_ms: Time spent before failure

        Returns:
            WebPage with error set
        """
        return cls(
            url=url,
            status_code=0,
            error=error,
            fetch_duration_ms=duration_ms,
            fetched_at=datetime.now(UTC).isoformat(),
        )

    def truncate(self, max_chars: int = 10000) -> WebPage:
        """Return a new WebPage with truncated content.

        Args:
            max_chars: Maximum characters for markdown/plain_text

        Returns:
            New WebPage with truncated content
        """
        if len(self.markdown) <= max_chars:
            return self

        truncated_md = self.markdown[:max_chars]
        last_para = truncated_md.rfind("\n\n")
        if last_para > max_chars // 2:
            truncated_md = truncated_md[:last_para] + "\n\n[Content truncated...]"

        truncated_plain = self.plain_text[:max_chars]
        last_sentence = max(
            truncated_plain.rfind(". "),
            truncated_plain.rfind("! "),
            truncated_plain.rfind("? "),
        )
        if last_sentence > max_chars // 2:
            truncated_plain = truncated_plain[: last_sentence + 1]

        return WebPage(
            url=self.url,
            final_url=self.final_url,
            status_code=self.status_code,
            markdown=truncated_md,
            plain_text=truncated_plain,
            metadata=self.metadata,
            links=self.links,
            navigation_actions=self.navigation_actions,
            pagination=self.pagination,
            fetch_duration_ms=self.fetch_duration_ms,
            extract_duration_ms=self.extract_duration_ms,
            fetched_at=self.fetched_at,
            word_count=self.word_count,
            error=self.error,
        )


__all__ = [
    "PageMetadata",
    "ExtractedLink",
    "NavigationAction",
    "PaginationInfo",
    "WebPage",
]

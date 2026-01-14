"""Page navigation capabilities for agents.

Enables agents to explore web pages by:
- Extracting and categorizing links
- Detecting pagination controls
- Finding main content areas
- Suggesting navigation actions
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

try:
    from selectolax.parser import HTMLParser, Node

    SELECTOLAX_AVAILABLE = True
except ImportError:
    SELECTOLAX_AVAILABLE = False

from stageflow.websearch.models import (
    ExtractedLink,
    NavigationAction,
    PaginationInfo,
)


@dataclass(frozen=True, slots=True)
class NavigationConfig:
    """Configuration for navigation detection.

    Attributes:
        pagination_selectors: CSS selectors for pagination elements
        nav_link_selectors: Selectors for navigation links
        content_selectors: Selectors for main content detection
        min_nav_links: Minimum links to consider as navigation
        max_actions: Maximum navigation actions to return
    """

    pagination_selectors: list[str] = field(
        default_factory=lambda: [
            ".pagination",
            ".pager",
            ".pages",
            '[role="navigation"]',
            "nav.pagination",
            ".page-numbers",
            ".wp-pagenavi",
        ]
    )
    pagination_link_patterns: list[str] = field(
        default_factory=lambda: [
            r"page[=/-]?\d+",
            r"p[=/-]?\d+",
            r"offset[=/-]?\d+",
            r"\?.*page",
        ]
    )
    next_link_texts: list[str] = field(
        default_factory=lambda: [
            "next",
            "→",
            "»",
            "›",
            ">",
            "next page",
            "older",
            "more",
        ]
    )
    prev_link_texts: list[str] = field(
        default_factory=lambda: [
            "prev",
            "previous",
            "←",
            "«",
            "‹",
            "<",
            "newer",
            "back",
        ]
    )
    nav_link_selectors: list[str] = field(
        default_factory=lambda: [
            "nav a",
            ".nav a",
            ".menu a",
            ".navigation a",
            '[role="navigation"] a',
        ]
    )
    content_selectors: list[str] = field(
        default_factory=lambda: [
            "article",
            "main",
            '[role="main"]',
            ".post-content",
            ".article-content",
            ".entry-content",
            "#content",
            ".content",
        ]
    )
    min_nav_links: int = 3
    max_actions: int = 20


@dataclass(slots=True)
class NavigationResult:
    """Result of navigation analysis.

    Attributes:
        actions: Available navigation actions
        pagination: Pagination info if detected
        main_content_selector: Detected main content selector
        nav_links: Navigation menu links
        breadcrumbs: Breadcrumb links if present
    """

    actions: list[NavigationAction] = field(default_factory=list)
    pagination: PaginationInfo | None = None
    main_content_selector: str | None = None
    nav_links: list[ExtractedLink] = field(default_factory=list)
    breadcrumbs: list[ExtractedLink] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "actions": [a.to_dict() for a in self.actions],
            "pagination": self.pagination.to_dict() if self.pagination else None,
            "main_content_selector": self.main_content_selector,
            "nav_links": [l.to_dict() for l in self.nav_links],
            "breadcrumbs": [l.to_dict() for l in self.breadcrumbs],
        }


class Navigator:
    """Base navigator class for page exploration."""

    def __init__(self, config: NavigationConfig | None = None) -> None:
        """Initialize navigator.

        Args:
            config: Navigation configuration
        """
        self.config = config or NavigationConfig()

    def analyze(
        self,
        html: str,
        *,
        base_url: str | None = None,
    ) -> NavigationResult:
        """Analyze page for navigation options.

        Args:
            html: Raw HTML string
            base_url: Base URL for resolving relative links

        Returns:
            NavigationResult with actions, pagination, etc.
        """
        raise NotImplementedError("Subclasses must implement analyze")

    def get_navigation_actions(
        self,
        html: str,
        *,
        base_url: str | None = None,
    ) -> list[NavigationAction]:
        """Get available navigation actions from a page."""
        result = self.analyze(html, base_url=base_url)
        return result.actions

    def find_pagination(
        self,
        html: str,
        *,
        base_url: str | None = None,
    ) -> PaginationInfo | None:
        """Find pagination controls on a page."""
        result = self.analyze(html, base_url=base_url)
        return result.pagination

    def find_main_content_selector(self, html: str) -> str | None:
        """Auto-detect the main content area selector."""
        result = self.analyze(html)
        return result.main_content_selector


class PageNavigator(Navigator):
    """Navigator implementation using selectolax."""

    def __init__(self, config: NavigationConfig | None = None) -> None:
        super().__init__(config)
        if not SELECTOLAX_AVAILABLE:
            raise ImportError(
                "selectolax is required for PageNavigator. "
                "Install with: pip install selectolax"
            )

    def analyze(
        self,
        html: str,
        *,
        base_url: str | None = None,
    ) -> NavigationResult:
        """Analyze page for navigation options."""
        tree = HTMLParser(html)

        actions: list[NavigationAction] = []
        pagination = self._find_pagination(tree, base_url)
        main_selector = self._detect_main_content(tree)
        nav_links = self._extract_nav_links(tree, base_url)
        breadcrumbs = self._extract_breadcrumbs(tree, base_url)

        if pagination:
            if pagination.next_url:
                actions.append(
                    NavigationAction(
                        action_type="pagination",
                        label="Next page",
                        url=pagination.next_url,
                        priority=1,
                        metadata={"direction": "next"},
                    )
                )
            if pagination.prev_url:
                actions.append(
                    NavigationAction(
                        action_type="pagination",
                        label="Previous page",
                        url=pagination.prev_url,
                        priority=2,
                        metadata={"direction": "prev"},
                    )
                )

        for link in nav_links[: self.config.max_actions - len(actions)]:
            actions.append(
                NavigationAction(
                    action_type="nav_link",
                    label=link.text or link.url,
                    url=link.url,
                    priority=3,
                )
            )

        content_links = self._extract_content_links(tree, base_url, main_selector)
        for link in content_links[: self.config.max_actions - len(actions)]:
            if not any(a.url == link.url for a in actions):
                actions.append(
                    NavigationAction(
                        action_type="content_link",
                        label=link.text or link.url,
                        url=link.url,
                        priority=4,
                    )
                )

        return NavigationResult(
            actions=actions[: self.config.max_actions],
            pagination=pagination,
            main_content_selector=main_selector,
            nav_links=nav_links,
            breadcrumbs=breadcrumbs,
        )

    def _find_pagination(
        self, tree: "HTMLParser", base_url: str | None
    ) -> PaginationInfo | None:
        """Find pagination controls in page."""
        for selector in self.config.pagination_selectors:
            pagination_node = tree.css_first(selector)
            if pagination_node:
                return self._parse_pagination_node(pagination_node, base_url)

        all_links = tree.css("a[href]")
        page_links: list[tuple[str, int | None]] = []

        for a in all_links:
            href = a.attributes.get("href", "")
            text = a.text(strip=True) if hasattr(a, "text") else ""

            for pattern in self.config.pagination_link_patterns:
                if re.search(pattern, href, re.I):
                    page_num = self._extract_page_number(href)
                    if base_url:
                        href = urljoin(base_url, href)
                    page_links.append((href, page_num))
                    break

        if len(page_links) >= 2:
            page_links.sort(key=lambda x: x[1] or 0)
            return PaginationInfo(
                current_page=1,
                page_urls=[url for url, _ in page_links],
                next_url=page_links[0][0] if page_links else None,
            )

        return None

    def _parse_pagination_node(
        self, node: "Node", base_url: str | None
    ) -> PaginationInfo | None:
        """Parse pagination from a pagination container node."""
        links = node.css("a[href]")
        if not links:
            return None

        next_url: str | None = None
        prev_url: str | None = None
        page_urls: list[str] = []
        current_page = 1

        for a in links:
            href = a.attributes.get("href", "")
            text = (a.text(strip=True) if hasattr(a, "text") else "").lower()
            classes = a.attributes.get("class", "").lower()

            if base_url and href:
                href = urljoin(base_url, href)

            if any(t in text for t in self.config.next_link_texts) or "next" in classes:
                next_url = href
            elif (
                any(t in text for t in self.config.prev_link_texts) or "prev" in classes
            ):
                prev_url = href
            elif href:
                page_urls.append(href)

        current_node = node.css_first(".current, .active, [aria-current='page']")
        if current_node:
            text = current_node.text(strip=True) if hasattr(current_node, "text") else ""
            if text.isdigit():
                current_page = int(text)

        return PaginationInfo(
            current_page=current_page,
            next_url=next_url,
            prev_url=prev_url,
            page_urls=page_urls,
            total_pages=len(page_urls) + 1 if page_urls else None,
        )

    def _extract_page_number(self, url: str) -> int | None:
        """Extract page number from URL."""
        patterns = [
            r"page[=/-]?(\d+)",
            r"p[=/-]?(\d+)",
            r"/(\d+)/?$",
        ]
        for pattern in patterns:
            match = re.search(pattern, url, re.I)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    pass
        return None

    def _detect_main_content(self, tree: "HTMLParser") -> str | None:
        """Detect the main content area selector."""
        for selector in self.config.content_selectors:
            node = tree.css_first(selector)
            if node:
                text_len = len(node.text(strip=True) if hasattr(node, "text") else "")
                if text_len > 200:
                    return selector

        candidates: list[tuple[str, int]] = []
        for div in tree.css("div[class], div[id]"):
            class_attr = div.attributes.get("class", "")
            id_attr = div.attributes.get("id", "")

            content_keywords = ["content", "article", "post", "main", "body", "entry"]
            is_candidate = any(
                kw in class_attr.lower() or kw in id_attr.lower()
                for kw in content_keywords
            )

            if is_candidate:
                text_len = len(div.text(strip=True) if hasattr(div, "text") else "")
                selector = f".{class_attr.split()[0]}" if class_attr else f"#{id_attr}"
                candidates.append((selector, text_len))

        if candidates:
            candidates.sort(key=lambda x: x[1], reverse=True)
            return candidates[0][0]

        return None

    def _extract_nav_links(
        self, tree: "HTMLParser", base_url: str | None
    ) -> list[ExtractedLink]:
        """Extract navigation menu links."""
        links: list[ExtractedLink] = []
        seen: set[str] = set()

        for selector in self.config.nav_link_selectors:
            for a in tree.css(selector):
                href = a.attributes.get("href", "")
                if not href or href.startswith(("#", "javascript:")):
                    continue

                text = a.text(strip=True) if hasattr(a, "text") else ""
                link = ExtractedLink.from_element(href, text, base_url=base_url)

                if link.url not in seen:
                    seen.add(link.url)
                    links.append(link)

        return links

    def _extract_breadcrumbs(
        self, tree: "HTMLParser", base_url: str | None
    ) -> list[ExtractedLink]:
        """Extract breadcrumb navigation."""
        breadcrumb_selectors = [
            ".breadcrumb a",
            ".breadcrumbs a",
            '[aria-label="breadcrumb"] a',
            "nav.breadcrumb a",
            ".bread-crumbs a",
        ]

        links: list[ExtractedLink] = []
        for selector in breadcrumb_selectors:
            for a in tree.css(selector):
                href = a.attributes.get("href", "")
                if not href or href.startswith("#"):
                    continue

                text = a.text(strip=True) if hasattr(a, "text") else ""
                link = ExtractedLink.from_element(href, text, base_url=base_url)
                links.append(link)

            if links:
                break

        return links

    def _extract_content_links(
        self,
        tree: "HTMLParser",
        base_url: str | None,
        main_selector: str | None,
    ) -> list[ExtractedLink]:
        """Extract links from main content area."""
        links: list[ExtractedLink] = []
        seen: set[str] = set()

        content_node = tree.body if tree.body else tree.root
        if main_selector:
            node = tree.css_first(main_selector)
            if node:
                content_node = node

        for a in content_node.css("a[href]"):
            href = a.attributes.get("href", "")
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            text = a.text(strip=True) if hasattr(a, "text") else ""
            if len(text) < 3:
                continue

            link = ExtractedLink.from_element(href, text, base_url=base_url)

            if link.url not in seen:
                seen.add(link.url)
                links.append(link)

        return links


class FallbackNavigator(Navigator):
    """Fallback navigator using regex when selectolax unavailable."""

    def analyze(
        self,
        html: str,
        *,
        base_url: str | None = None,
    ) -> NavigationResult:
        """Analyze page using regex patterns."""
        actions: list[NavigationAction] = []

        next_patterns = [
            r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>.*?(?:next|→|»|›).*?</a>',
            r'<a[^>]+class=["\'][^"\']*next[^"\']*["\'][^>]*href=["\']([^"\']+)["\']',
        ]
        prev_patterns = [
            r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>.*?(?:prev|←|«|‹).*?</a>',
            r'<a[^>]+class=["\'][^"\']*prev[^"\']*["\'][^>]*href=["\']([^"\']+)["\']',
        ]

        next_url = None
        prev_url = None

        for pattern in next_patterns:
            match = re.search(pattern, html, re.I | re.DOTALL)
            if match:
                next_url = match.group(1)
                if base_url:
                    next_url = urljoin(base_url, next_url)
                break

        for pattern in prev_patterns:
            match = re.search(pattern, html, re.I | re.DOTALL)
            if match:
                prev_url = match.group(1)
                if base_url:
                    prev_url = urljoin(base_url, prev_url)
                break

        pagination = None
        if next_url or prev_url:
            pagination = PaginationInfo(
                current_page=1,
                next_url=next_url,
                prev_url=prev_url,
            )

            if next_url:
                actions.append(
                    NavigationAction(
                        action_type="pagination",
                        label="Next page",
                        url=next_url,
                        priority=1,
                    )
                )
            if prev_url:
                actions.append(
                    NavigationAction(
                        action_type="pagination",
                        label="Previous page",
                        url=prev_url,
                        priority=2,
                    )
                )

        return NavigationResult(
            actions=actions,
            pagination=pagination,
            main_content_selector=None,
            nav_links=[],
            breadcrumbs=[],
        )


def get_default_navigator(config: NavigationConfig | None = None) -> Navigator:
    """Get the best available navigator.

    Returns PageNavigator if selectolax available,
    otherwise FallbackNavigator.
    """
    if SELECTOLAX_AVAILABLE:
        return PageNavigator(config)
    return FallbackNavigator(config)


__all__ = [
    "NavigationConfig",
    "NavigationResult",
    "Navigator",
    "PageNavigator",
    "FallbackNavigator",
    "get_default_navigator",
]

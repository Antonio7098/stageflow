"""HTML content extractor with structure preservation.

Extracts clean, structured content from HTML while preserving
semantic structure like headings, lists, links, and emphasis.
Outputs markdown for readability and downstream processing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import unescape
from typing import Any
from urllib.parse import urljoin

try:
    from selectolax.parser import HTMLParser, Node

    SELECTOLAX_AVAILABLE = True
except ImportError:
    SELECTOLAX_AVAILABLE = False

from stageflow.websearch.models import ExtractedLink, PageMetadata


@dataclass(frozen=True, slots=True)
class ExtractionConfig:
    """Configuration for content extraction.

    Attributes:
        preserve_headings: Keep heading structure (h1-h6 -> #-######)
        preserve_lists: Keep list structure (ul/ol -> -/1.)
        preserve_links: Keep links as [text](url)
        preserve_emphasis: Keep bold/italic as **/_ 
        preserve_code: Keep code blocks and inline code
        preserve_blockquotes: Keep blockquotes as >
        preserve_tables: Convert tables to markdown
        remove_selectors: CSS selectors for elements to remove
        main_content_selectors: Selectors to try for main content
        max_link_text_length: Max chars for link text
        max_heading_length: Max chars for headings
        include_link_urls: Include URLs in markdown links
        min_text_length: Minimum text length to include a block
    """

    preserve_headings: bool = True
    preserve_lists: bool = True
    preserve_links: bool = True
    preserve_emphasis: bool = True
    preserve_code: bool = True
    preserve_blockquotes: bool = True
    preserve_tables: bool = True
    remove_selectors: list[str] = field(
        default_factory=lambda: [
            "script",
            "style",
            "noscript",
            "iframe",
            "svg",
            "nav",
            "footer",
            "header",
            "aside",
            ".sidebar",
            ".advertisement",
            ".ad",
            ".ads",
            ".cookie-banner",
            ".popup",
            ".modal",
            "#comments",
            ".comments",
            ".share-buttons",
            ".social-share",
        ]
    )
    main_content_selectors: list[str] = field(
        default_factory=lambda: [
            "article",
            "main",
            '[role="main"]',
            ".post-content",
            ".article-content",
            ".entry-content",
            ".content",
            "#content",
            ".post",
            ".article",
        ]
    )
    max_link_text_length: int = 100
    max_heading_length: int = 200
    include_link_urls: bool = True
    min_text_length: int = 1


@dataclass(slots=True)
class ExtractionResult:
    """Result of content extraction.

    Attributes:
        markdown: Structured content as markdown
        plain_text: Plain text without formatting
        metadata: Page metadata
        links: Extracted links
        word_count: Number of words
        heading_outline: List of (level, text) tuples
    """

    markdown: str = ""
    plain_text: str = ""
    metadata: PageMetadata = field(default_factory=PageMetadata)
    links: list[ExtractedLink] = field(default_factory=list)
    word_count: int = 0
    heading_outline: list[tuple[int, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "markdown": self.markdown,
            "plain_text": self.plain_text,
            "metadata": self.metadata.to_dict(),
            "links": [link.to_dict() for link in self.links],
            "word_count": self.word_count,
            "heading_outline": self.heading_outline,
        }


class ContentExtractor:
    """Base content extractor class.

    Subclass and override methods for custom extraction logic.
    """

    def __init__(self, config: ExtractionConfig | None = None) -> None:
        """Initialize extractor.

        Args:
            config: Extraction configuration
        """
        self.config = config or ExtractionConfig()

    def extract(
        self,
        html: str,
        *,
        base_url: str | None = None,
        selector: str | None = None,
    ) -> ExtractionResult:
        """Extract structured content from HTML.

        Args:
            html: Raw HTML string
            base_url: Base URL for resolving relative links
            selector: Optional CSS selector to target specific content

        Returns:
            ExtractionResult with markdown, metadata, links
        """
        raise NotImplementedError("Subclasses must implement extract")

    def extract_metadata(self, html: str) -> PageMetadata:
        """Extract page metadata."""
        raise NotImplementedError("Subclasses must implement extract_metadata")

    def extract_links(
        self,
        html: str,
        *,
        base_url: str | None = None,
        selector: str | None = None,
    ) -> list[ExtractedLink]:
        """Extract links from HTML."""
        raise NotImplementedError("Subclasses must implement extract_links")


class DefaultContentExtractor(ContentExtractor):
    """Default content extractor using selectolax.

    Converts HTML to markdown while preserving structure.
    Falls back to regex-based extraction if selectolax unavailable.
    """

    def __init__(self, config: ExtractionConfig | None = None) -> None:
        super().__init__(config)
        if not SELECTOLAX_AVAILABLE:
            raise ImportError(
                "selectolax is required for DefaultContentExtractor. "
                "Install with: pip install selectolax"
            )

    def extract(
        self,
        html: str,
        *,
        base_url: str | None = None,
        selector: str | None = None,
    ) -> ExtractionResult:
        """Extract structured content from HTML."""
        tree = HTMLParser(html)

        for sel in self.config.remove_selectors:
            for node in tree.css(sel):
                node.decompose()

        content_node = None
        if selector:
            nodes = tree.css(selector)
            if nodes:
                content_node = nodes[0]
        else:
            for sel in self.config.main_content_selectors:
                nodes = tree.css(sel)
                if nodes:
                    content_node = nodes[0]
                    break

        if content_node is None:
            content_node = tree.body if tree.body else tree.root

        metadata = self._extract_metadata_from_tree(tree)
        links = self._extract_links_from_node(content_node, base_url)
        heading_outline: list[tuple[int, str]] = []
        markdown_parts: list[str] = []
        plain_parts: list[str] = []

        self._process_node(
            content_node,
            markdown_parts,
            plain_parts,
            heading_outline,
            base_url,
            depth=0,
        )

        markdown = self._clean_markdown("\n".join(markdown_parts))
        plain_text = self._clean_plain_text(" ".join(plain_parts))
        word_count = len(plain_text.split())

        return ExtractionResult(
            markdown=markdown,
            plain_text=plain_text,
            metadata=metadata,
            links=links,
            word_count=word_count,
            heading_outline=heading_outline,
        )

    def _process_node(
        self,
        node: "Node",
        markdown_parts: list[str],
        plain_parts: list[str],
        heading_outline: list[tuple[int, str]],
        base_url: str | None,
        depth: int = 0,
        list_type: str | None = None,
        list_index: int = 0,
    ) -> int:
        """Recursively process a DOM node.

        Returns updated list_index for numbered lists.
        """
        if node is None:
            return list_index

        tag = node.tag.lower() if node.tag else ""

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            text = self._get_text_content(node).strip()
            if text and len(text) <= self.config.max_heading_length:
                if self.config.preserve_headings:
                    prefix = "#" * level
                    markdown_parts.append(f"\n\n{prefix} {text}\n")
                else:
                    markdown_parts.append(f"\n\n{text}\n")
                plain_parts.append(text)
                heading_outline.append((level, text))
            return list_index

        if tag == "p":
            text = self._process_inline_content(node, base_url)
            if text.strip():
                markdown_parts.append(f"\n\n{text}")
                plain_parts.append(self._strip_markdown(text))
            return list_index

        if tag in ("ul", "ol"):
            markdown_parts.append("\n")
            new_list_type = "ol" if tag == "ol" else "ul"
            idx = 0
            # Use css to find direct li children
            for child in node.css("li"):
                # Only process direct children (parent is this node)
                if child.parent == node:
                    idx = self._process_node(
                        child,
                        markdown_parts,
                        plain_parts,
                        heading_outline,
                        base_url,
                        depth + 1,
                        new_list_type,
                        idx,
                    )
            markdown_parts.append("\n")
            return list_index

        if tag == "li":
            text = self._process_inline_content(node, base_url)
            if text.strip():
                indent = "  " * (depth - 1) if depth > 1 else ""
                if list_type == "ol" and self.config.preserve_lists:
                    list_index += 1
                    markdown_parts.append(f"{indent}{list_index}. {text}\n")
                elif self.config.preserve_lists:
                    markdown_parts.append(f"{indent}- {text}\n")
                else:
                    markdown_parts.append(f"{text} ")
                plain_parts.append(self._strip_markdown(text))
            return list_index

        if tag == "blockquote" and self.config.preserve_blockquotes:
            text = self._get_text_content(node).strip()
            if text:
                quoted = "\n".join(f"> {line}" for line in text.split("\n"))
                markdown_parts.append(f"\n\n{quoted}\n")
                plain_parts.append(text)
            return list_index

        if tag == "pre":
            code_node = node.css_first("code")
            code_text = self._get_text_content(code_node if code_node else node)
            if code_text.strip() and self.config.preserve_code:
                lang = ""
                if code_node:
                    class_attr = code_node.attributes.get("class", "")
                    if "language-" in class_attr:
                        lang = class_attr.split("language-")[1].split()[0]
                markdown_parts.append(f"\n\n```{lang}\n{code_text}\n```\n")
            elif code_text.strip():
                markdown_parts.append(f"\n\n{code_text}\n")
            plain_parts.append(code_text)
            return list_index

        if tag == "table" and self.config.preserve_tables:
            table_md = self._process_table(node)
            if table_md:
                markdown_parts.append(f"\n\n{table_md}\n")
            return list_index

        if tag == "br":
            markdown_parts.append("  \n")
            return list_index

        if tag == "hr":
            markdown_parts.append("\n\n---\n")
            return list_index

        # For container elements, process children
        if tag in ("div", "section", "article", "main", "span", "figure", "body", "html", "-undef-", ""):
            # Get direct children using child property
            child = node.child
            while child is not None:
                list_index = self._process_node(
                    child,
                    markdown_parts,
                    plain_parts,
                    heading_outline,
                    base_url,
                    depth,
                    list_type,
                    list_index,
                )
                child = child.next

            return list_index

        # For any other tag, try to get text content
        text = self._get_text_content(node).strip()
        if text:
            plain_parts.append(text)

        return list_index

    def _process_inline_content(self, node: "Node", base_url: str | None) -> str:
        """Process inline content with formatting preserved."""
        parts: list[str] = []
        self._process_inline_recursive(node, parts, base_url)
        return " ".join(parts).strip()

    def _process_inline_recursive(
        self, node: "Node", parts: list[str], base_url: str | None
    ) -> None:
        """Recursively process inline nodes using child/next traversal."""
        if node is None:
            return

        tag = node.tag.lower() if node.tag else ""

        # Handle specific inline elements
        if tag == "a" and self.config.preserve_links:
            href = node.attributes.get("href", "")
            link_text = self._get_text_content(node).strip()
            if link_text and href:
                if base_url and not href.startswith(("http://", "https://", "//")):
                    href = urljoin(base_url, href)
                if len(link_text) > self.config.max_link_text_length:
                    link_text = link_text[: self.config.max_link_text_length] + "…"
                if self.config.include_link_urls:
                    parts.append(f"[{link_text}]({href})")
                else:
                    parts.append(link_text)
            elif link_text:
                parts.append(link_text)
            return

        if tag in ("strong", "b") and self.config.preserve_emphasis:
            inner = self._get_text_content(node).strip()
            if inner:
                parts.append(f"**{inner}**")
            return

        if tag in ("em", "i") and self.config.preserve_emphasis:
            inner = self._get_text_content(node).strip()
            if inner:
                parts.append(f"_{inner}_")
            return

        if tag == "code" and self.config.preserve_code:
            inner = self._get_text_content(node).strip()
            if inner:
                parts.append(f"`{inner}`")
            return

        if tag == "img":
            alt = node.attributes.get("alt", "")
            if alt:
                parts.append(f"[Image: {alt}]")
            return

        if tag == "br":
            parts.append("\n")
            return

        # For text nodes or container elements, process children
        # Check if this is a text node (tag is None or "-text")
        if not tag or tag == "-text":
            text = node.text(strip=False) if hasattr(node, "text") else ""
            if text and text.strip():
                parts.append(text.strip())
            return

        # For other elements (span, font, etc.), recurse into children
        child = node.child
        while child is not None:
            self._process_inline_recursive(child, parts, base_url)
            child = child.next

    def _process_table(self, node: "Node") -> str:
        """Convert HTML table to markdown."""
        rows: list[list[str]] = []
        for tr in node.css("tr"):
            cells: list[str] = []
            for cell in tr.css("th, td"):
                text = self._get_text_content(cell).strip()
                text = text.replace("|", "\\|").replace("\n", " ")
                cells.append(text)
            if cells:
                rows.append(cells)

        if not rows:
            return ""

        max_cols = max(len(row) for row in rows)
        for row in rows:
            while len(row) < max_cols:
                row.append("")

        lines: list[str] = []
        lines.append("| " + " | ".join(rows[0]) + " |")
        lines.append("| " + " | ".join(["---"] * max_cols) + " |")
        for row in rows[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    def _get_text_content(self, node: "Node") -> str:
        """Get all text content from a node."""
        if node is None:
            return ""
        return node.text(strip=False) if hasattr(node, "text") else ""

    def _strip_markdown(self, text: str) -> str:
        """Remove markdown formatting from text."""
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        return text

    def _clean_markdown(self, text: str) -> str:
        """Clean up markdown output."""
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r" {2,}", " ", text)
        text = re.sub(r"\n +", "\n", text)
        text = unescape(text)
        return text.strip()

    def _clean_plain_text(self, text: str) -> str:
        """Clean up plain text output."""
        text = re.sub(r"\s+", " ", text)
        text = unescape(text)
        return text.strip()

    def _extract_metadata_from_tree(self, tree: "HTMLParser") -> PageMetadata:
        """Extract metadata from parsed HTML tree."""
        title = None
        title_node = tree.css_first("title")
        if title_node:
            title = title_node.text(strip=True)

        og_title = self._get_meta_content(tree, "og:title")
        if og_title:
            title = og_title

        description = self._get_meta_content(tree, "description")
        og_desc = self._get_meta_content(tree, "og:description")
        if og_desc:
            description = og_desc

        language = None
        html_node = tree.css_first("html")
        if html_node:
            language = html_node.attributes.get("lang")

        author = self._get_meta_content(tree, "author")
        published_date = self._get_meta_content(tree, "article:published_time")
        canonical = None
        canonical_node = tree.css_first('link[rel="canonical"]')
        if canonical_node:
            canonical = canonical_node.attributes.get("href")

        og_image = self._get_meta_content(tree, "og:image")

        keywords_str = self._get_meta_content(tree, "keywords")
        keywords = []
        if keywords_str:
            keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]

        content_type = self._get_meta_content(tree, "og:type")

        return PageMetadata(
            title=title,
            description=description,
            language=language,
            author=author,
            published_date=published_date,
            canonical_url=canonical,
            og_image=og_image,
            keywords=keywords,
            content_type=content_type,
        )

    def _get_meta_content(self, tree: "HTMLParser", name: str) -> str | None:
        """Get meta tag content by name or property."""
        node = tree.css_first(f'meta[name="{name}"]')
        if node:
            return node.attributes.get("content")
        node = tree.css_first(f'meta[property="{name}"]')
        if node:
            return node.attributes.get("content")
        return None

    def _extract_links_from_node(
        self, node: "Node", base_url: str | None
    ) -> list[ExtractedLink]:
        """Extract all links from a node."""
        links: list[ExtractedLink] = []
        seen_urls: set[str] = set()

        for a in node.css("a[href]"):
            href = a.attributes.get("href", "")
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            text = self._get_text_content(a).strip()
            title = a.attributes.get("title")
            rel = a.attributes.get("rel")

            link = ExtractedLink.from_element(
                href,
                text,
                base_url=base_url,
                title=title,
                rel=rel,
            )

            if link.url not in seen_urls:
                seen_urls.add(link.url)
                links.append(link)

        return links

    def extract_metadata(self, html: str) -> PageMetadata:
        """Extract page metadata."""
        tree = HTMLParser(html)
        return self._extract_metadata_from_tree(tree)

    def extract_links(
        self,
        html: str,
        *,
        base_url: str | None = None,
        selector: str | None = None,
    ) -> list[ExtractedLink]:
        """Extract links from HTML."""
        tree = HTMLParser(html)

        for sel in self.config.remove_selectors:
            for node in tree.css(sel):
                node.decompose()

        target_node = tree.body if tree.body else tree.root
        if selector:
            nodes = tree.css(selector)
            if nodes:
                target_node = nodes[0]

        return self._extract_links_from_node(target_node, base_url)


class FallbackContentExtractor(ContentExtractor):
    """Fallback extractor using regex when selectolax unavailable."""

    def extract(
        self,
        html: str,
        *,
        base_url: str | None = None,
        selector: str | None = None,
    ) -> ExtractionResult:
        """Extract content using regex patterns."""
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.I)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.I)
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)

        markdown_parts: list[str] = []
        heading_outline: list[tuple[int, str]] = []

        for match in re.finditer(r"<h([1-6])[^>]*>(.*?)</h\1>", html, re.DOTALL | re.I):
            level = int(match.group(1))
            text = re.sub(r"<[^>]+>", "", match.group(2)).strip()
            if text and self.config.preserve_headings:
                markdown_parts.append(f"{'#' * level} {text}\n\n")
                heading_outline.append((level, text))

        for match in re.finditer(r"<p[^>]*>(.*?)</p>", html, re.DOTALL | re.I):
            text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            if text:
                markdown_parts.append(f"{text}\n\n")

        plain_text = re.sub(r"<[^>]+>", " ", html)
        plain_text = re.sub(r"\s+", " ", plain_text).strip()
        plain_text = unescape(plain_text)

        markdown = "".join(markdown_parts)
        markdown = unescape(markdown)

        links = self._extract_links_regex(html, base_url)
        metadata = self._extract_metadata_regex(html)

        return ExtractionResult(
            markdown=markdown.strip(),
            plain_text=plain_text,
            metadata=metadata,
            links=links,
            word_count=len(plain_text.split()),
            heading_outline=heading_outline,
        )

    def _extract_links_regex(
        self, html: str, base_url: str | None
    ) -> list[ExtractedLink]:
        """Extract links using regex."""
        links: list[ExtractedLink] = []
        seen: set[str] = set()

        for match in re.finditer(
            r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.DOTALL | re.I
        ):
            href = match.group(1)
            text = re.sub(r"<[^>]+>", "", match.group(2)).strip()

            if href.startswith(("#", "javascript:", "mailto:")):
                continue

            link = ExtractedLink.from_element(href, text, base_url=base_url)
            if link.url not in seen:
                seen.add(link.url)
                links.append(link)

        return links

    def _extract_metadata_regex(self, html: str) -> PageMetadata:
        """Extract metadata using regex."""
        title = None
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.I)
        if title_match:
            title = re.sub(r"<[^>]+>", "", title_match.group(1)).strip()

        description = None
        desc_match = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
            html,
            re.I,
        )
        if desc_match:
            description = desc_match.group(1)

        return PageMetadata(title=title, description=description)

    def extract_metadata(self, html: str) -> PageMetadata:
        """Extract metadata using regex."""
        return self._extract_metadata_regex(html)

    def extract_links(
        self,
        html: str,
        *,
        base_url: str | None = None,
        selector: str | None = None,
    ) -> list[ExtractedLink]:
        """Extract links using regex."""
        return self._extract_links_regex(html, base_url)


def get_default_extractor(config: ExtractionConfig | None = None) -> ContentExtractor:
    """Get the best available extractor.

    Returns DefaultContentExtractor if selectolax available,
    otherwise FallbackContentExtractor.
    """
    if SELECTOLAX_AVAILABLE:
        return DefaultContentExtractor(config)
    return FallbackContentExtractor(config)


__all__ = [
    "ExtractionConfig",
    "ExtractionResult",
    "ContentExtractor",
    "DefaultContentExtractor",
    "FallbackContentExtractor",
    "get_default_extractor",
    "SELECTOLAX_AVAILABLE",
]

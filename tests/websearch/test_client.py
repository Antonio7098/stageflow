"""Tests for websearch client module."""

import pytest

from stageflow.websearch.client import (
    WebSearchClient,
    WebSearchConfig,
    create_mock_client,
)
from stageflow.websearch.extractor import ExtractionConfig
from stageflow.websearch.fetcher import FetchConfig, MockFetcher
from stageflow.websearch.navigator import NavigationConfig


class TestWebSearchConfig:
    """Tests for WebSearchConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = WebSearchConfig()
        assert config.max_concurrent == 5
        assert config.auto_extract is True
        assert config.auto_navigate is True
        assert isinstance(config.fetch, FetchConfig)
        assert isinstance(config.extraction, ExtractionConfig)
        assert isinstance(config.navigation, NavigationConfig)

    def test_custom_values(self) -> None:
        """Test custom configuration."""
        config = WebSearchConfig(
            max_concurrent=10,
            auto_extract=False,
            fetch=FetchConfig(timeout=10.0),
        )
        assert config.max_concurrent == 10
        assert config.auto_extract is False
        assert config.fetch.timeout == 10.0


class TestCreateMockClient:
    """Tests for create_mock_client factory."""

    def test_creates_client(self) -> None:
        """Test factory creates a client."""
        client = create_mock_client()
        assert client is not None
        assert isinstance(client._fetcher, MockFetcher)

    def test_with_responses(self) -> None:
        """Test factory with custom responses."""
        responses = {
            "https://example.com": (
                200,
                "<html><body><h1>Test</h1></body></html>",
                {"content-type": "text/html"},
            ),
        }
        client = create_mock_client(responses)
        assert client is not None


class TestWebSearchClientBasic:
    """Basic tests for WebSearchClient."""

    @pytest.mark.asyncio
    async def test_fetch_success(self) -> None:
        """Test successful page fetch."""
        responses = {
            "https://example.com": (
                200,
                """
                <html>
                    <head><title>Test Page</title></head>
                    <body>
                        <h1>Hello World</h1>
                        <p>This is a test page.</p>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
        }
        client = create_mock_client(responses)

        page = await client.fetch("https://example.com")

        assert page.success is True
        assert page.status_code == 200
        assert page.url == "https://example.com"
        assert "Hello World" in page.markdown
        assert page.metadata.title == "Test Page"

    @pytest.mark.asyncio
    async def test_fetch_error(self) -> None:
        """Test fetch with HTTP error."""
        responses = {
            "https://example.com": (
                404,
                "Not Found",
                {"content-type": "text/plain"},
            ),
        }
        client = create_mock_client(responses)

        page = await client.fetch("https://example.com")

        assert page.success is False
        assert page.error is not None
        assert "404" in page.error

    @pytest.mark.asyncio
    async def test_fetch_extracts_links(self) -> None:
        """Test that links are extracted."""
        responses = {
            "https://example.com": (
                200,
                """
                <html>
                    <body>
                        <a href="https://example.com/page1">Page 1</a>
                        <a href="https://other.com">External</a>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
        }
        client = create_mock_client(responses)

        page = await client.fetch("https://example.com")

        assert len(page.links) >= 2
        internal = page.internal_links
        external = page.external_links
        assert len(internal) >= 1
        assert len(external) >= 1

    @pytest.mark.asyncio
    async def test_fetch_with_selector(self) -> None:
        """Test fetch with custom selector."""
        responses = {
            "https://example.com": (
                200,
                """
                <html>
                    <body>
                        <div id="header">Header content</div>
                        <div id="main"><p>Main content only</p></div>
                        <div id="footer">Footer content</div>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
        }
        client = create_mock_client(responses)

        page = await client.fetch("https://example.com", selector="#main")

        assert "Main content" in page.plain_text or "Main content" in page.markdown

    @pytest.mark.asyncio
    async def test_fetch_without_extraction(self) -> None:
        """Test fetch with extraction disabled."""
        responses = {
            "https://example.com": (
                200,
                "<html><body><h1>Test</h1></body></html>",
                {"content-type": "text/html"},
            ),
        }
        client = create_mock_client(responses)

        page = await client.fetch("https://example.com", extract=False)

        assert page.markdown == ""
        assert page.metadata is not None  # Metadata still extracted

    @pytest.mark.asyncio
    async def test_fetch_without_navigation(self) -> None:
        """Test fetch with navigation disabled."""
        responses = {
            "https://example.com": (
                200,
                """
                <html>
                    <body>
                        <div class="pagination">
                            <a href="/page/2">Next</a>
                        </div>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
        }
        client = create_mock_client(responses)

        page = await client.fetch("https://example.com", navigate=False)

        assert page.navigation_actions == []
        assert page.pagination is None

    @pytest.mark.asyncio
    async def test_fetch_non_html_content(self) -> None:
        """Test fetch of non-HTML content."""
        responses = {
            "https://example.com/data.json": (
                200,
                '{"key": "value"}',
                {"content-type": "application/json"},
            ),
        }
        client = create_mock_client(responses)

        page = await client.fetch("https://example.com/data.json")

        assert page.success is True
        assert '{"key": "value"}' in page.markdown or '{"key": "value"}' in page.plain_text


class TestWebSearchClientBatch:
    """Tests for batch fetching."""

    @pytest.mark.asyncio
    async def test_fetch_many(self) -> None:
        """Test batch fetching multiple URLs."""
        responses = {
            f"https://example.com/{i}": (
                200,
                f"<html><body><h1>Page {i}</h1></body></html>",
                {"content-type": "text/html"},
            )
            for i in range(5)
        }
        client = create_mock_client(responses)

        urls = [f"https://example.com/{i}" for i in range(5)]
        pages = await client.fetch_many(urls)

        assert len(pages) == 5
        for i, page in enumerate(pages):
            assert page.success is True
            assert f"Page {i}" in page.markdown

    @pytest.mark.asyncio
    async def test_fetch_many_preserves_order(self) -> None:
        """Test batch fetching preserves URL order."""
        responses = {
            f"https://example.com/{i}": (
                200,
                f"<html><body>{i}</body></html>",
                {"content-type": "text/html"},
            )
            for i in range(10)
        }
        client = create_mock_client(responses)

        urls = [f"https://example.com/{i}" for i in range(10)]
        pages = await client.fetch_many(urls)

        for i, page in enumerate(pages):
            assert page.url == f"https://example.com/{i}"

    @pytest.mark.asyncio
    async def test_fetch_many_empty_list(self) -> None:
        """Test batch fetching with empty list."""
        client = create_mock_client()
        pages = await client.fetch_many([])
        assert pages == []

    @pytest.mark.asyncio
    async def test_fetch_many_with_concurrency(self) -> None:
        """Test batch fetching respects concurrency limit."""
        responses = {
            f"https://example.com/{i}": (
                200,
                f"<html><body>{i}</body></html>",
                {"content-type": "text/html"},
            )
            for i in range(10)
        }
        client = create_mock_client(responses)

        urls = [f"https://example.com/{i}" for i in range(10)]
        pages = await client.fetch_many(urls, concurrency=2)

        assert len(pages) == 10


class TestWebSearchClientNavigation:
    """Tests for navigation features."""

    @pytest.mark.asyncio
    async def test_fetch_with_navigation_pagination(self) -> None:
        """Test following pagination links."""
        responses = {
            "https://example.com/page/1": (
                200,
                """
                <html>
                    <body>
                        <h1>Page 1</h1>
                        <div class="pagination">
                            <a href="/page/2" class="next">Next</a>
                        </div>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
            "https://example.com/page/2": (
                200,
                """
                <html>
                    <body>
                        <h1>Page 2</h1>
                        <div class="pagination">
                            <a href="/page/1" class="prev">Prev</a>
                            <a href="/page/3" class="next">Next</a>
                        </div>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
            "https://example.com/page/3": (
                200,
                """
                <html>
                    <body>
                        <h1>Page 3</h1>
                        <div class="pagination">
                            <a href="/page/2" class="prev">Prev</a>
                        </div>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
        }
        client = create_mock_client(responses)

        pages = await client.fetch_with_navigation(
            "https://example.com/page/1",
            max_pages=5,
        )

        assert len(pages) == 3
        assert "Page 1" in pages[0].markdown
        assert "Page 2" in pages[1].markdown
        assert "Page 3" in pages[2].markdown

    @pytest.mark.asyncio
    async def test_fetch_with_navigation_max_pages(self) -> None:
        """Test max_pages limit is respected."""
        responses = {
            f"https://example.com/page/{i}": (
                200,
                f"""
                <html>
                    <body>
                        <h1>Page {i}</h1>
                        <div class="pagination">
                            <a href="/page/{i+1}" class="next">Next</a>
                        </div>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            )
            for i in range(1, 20)
        }
        client = create_mock_client(responses)

        pages = await client.fetch_with_navigation(
            "https://example.com/page/1",
            max_pages=3,
        )

        # Should get at least 1 page, and up to 3 if pagination is detected
        assert len(pages) >= 1
        assert len(pages) <= 3

    @pytest.mark.asyncio
    async def test_fetch_with_navigation_no_pagination(self) -> None:
        """Test navigation stops when no pagination."""
        responses = {
            "https://example.com": (
                200,
                "<html><body><h1>Single Page</h1></body></html>",
                {"content-type": "text/html"},
            ),
        }
        client = create_mock_client(responses)

        pages = await client.fetch_with_navigation("https://example.com")

        assert len(pages) == 1


class TestWebSearchClientCrawl:
    """Tests for crawling features."""

    @pytest.mark.asyncio
    async def test_crawl_basic(self) -> None:
        """Test basic crawling."""
        responses = {
            "https://example.com": (
                200,
                """
                <html>
                    <body>
                        <h1>Home</h1>
                        <a href="https://example.com/page1">Page 1</a>
                        <a href="https://example.com/page2">Page 2</a>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
            "https://example.com/page1": (
                200,
                "<html><body><h1>Page 1</h1></body></html>",
                {"content-type": "text/html"},
            ),
            "https://example.com/page2": (
                200,
                "<html><body><h1>Page 2</h1></body></html>",
                {"content-type": "text/html"},
            ),
        }
        client = create_mock_client(responses)

        pages = await client.crawl(
            "https://example.com",
            max_pages=10,
            max_depth=1,
        )

        assert len(pages) == 3
        urls = {p.url for p in pages}
        assert "https://example.com" in urls
        assert "https://example.com/page1" in urls
        assert "https://example.com/page2" in urls

    @pytest.mark.asyncio
    async def test_crawl_max_pages(self) -> None:
        """Test crawl respects max_pages."""
        responses = {
            "https://example.com": (
                200,
                """
                <html>
                    <body>
                        <a href="https://example.com/1">1</a>
                        <a href="https://example.com/2">2</a>
                        <a href="https://example.com/3">3</a>
                        <a href="https://example.com/4">4</a>
                        <a href="https://example.com/5">5</a>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
            **{
                f"https://example.com/{i}": (
                    200,
                    f"<html><body>Page {i}</body></html>",
                    {"content-type": "text/html"},
                )
                for i in range(1, 6)
            },
        }
        client = create_mock_client(responses)

        pages = await client.crawl(
            "https://example.com",
            max_pages=3,
            max_depth=1,
        )

        assert len(pages) == 3

    @pytest.mark.asyncio
    async def test_crawl_max_depth(self) -> None:
        """Test crawl respects max_depth."""
        responses = {
            "https://example.com": (
                200,
                '<html><body><a href="https://example.com/level1">L1</a></body></html>',
                {"content-type": "text/html"},
            ),
            "https://example.com/level1": (
                200,
                '<html><body><a href="https://example.com/level2">L2</a></body></html>',
                {"content-type": "text/html"},
            ),
            "https://example.com/level2": (
                200,
                '<html><body><a href="https://example.com/level3">L3</a></body></html>',
                {"content-type": "text/html"},
            ),
            "https://example.com/level3": (
                200,
                "<html><body>Level 3</body></html>",
                {"content-type": "text/html"},
            ),
        }
        client = create_mock_client(responses)

        pages = await client.crawl(
            "https://example.com",
            max_pages=10,
            max_depth=1,
        )

        urls = {p.url for p in pages}
        assert "https://example.com" in urls
        assert "https://example.com/level1" in urls
        assert "https://example.com/level2" not in urls

    @pytest.mark.asyncio
    async def test_crawl_same_domain_only(self) -> None:
        """Test crawl stays on same domain."""
        responses = {
            "https://example.com": (
                200,
                """
                <html>
                    <body>
                        <a href="https://example.com/internal">Internal</a>
                        <a href="https://other.com/external">External</a>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
            "https://example.com/internal": (
                200,
                "<html><body>Internal</body></html>",
                {"content-type": "text/html"},
            ),
            "https://other.com/external": (
                200,
                "<html><body>External</body></html>",
                {"content-type": "text/html"},
            ),
        }
        client = create_mock_client(responses)

        pages = await client.crawl(
            "https://example.com",
            max_pages=10,
            max_depth=2,
            same_domain_only=True,
        )

        urls = {p.url for p in pages}
        assert "https://example.com" in urls
        assert "https://example.com/internal" in urls
        assert "https://other.com/external" not in urls

    @pytest.mark.asyncio
    async def test_crawl_with_link_filter(self) -> None:
        """Test crawl with custom link filter."""
        responses = {
            "https://example.com": (
                200,
                """
                <html>
                    <body>
                        <a href="https://example.com/article/1">Article 1</a>
                        <a href="https://example.com/page/1">Page 1</a>
                        <a href="https://example.com/article/2">Article 2</a>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
            "https://example.com/article/1": (
                200,
                "<html><body>Article 1</body></html>",
                {"content-type": "text/html"},
            ),
            "https://example.com/article/2": (
                200,
                "<html><body>Article 2</body></html>",
                {"content-type": "text/html"},
            ),
            "https://example.com/page/1": (
                200,
                "<html><body>Page 1</body></html>",
                {"content-type": "text/html"},
            ),
        }
        client = create_mock_client(responses)

        def article_only(link):
            return "/article/" in link.url

        pages = await client.crawl(
            "https://example.com",
            max_pages=10,
            max_depth=1,
            link_filter=article_only,
        )

        urls = {p.url for p in pages}
        assert "https://example.com/article/1" in urls
        assert "https://example.com/article/2" in urls
        assert "https://example.com/page/1" not in urls


class TestWebSearchClientExtractContent:
    """Tests for extract_content method."""

    def test_extract_content_from_html(self) -> None:
        """Test extracting content from HTML string."""
        html = """
        <html>
            <head><title>Test</title></head>
            <body>
                <h1>Hello</h1>
                <p>World</p>
            </body>
        </html>
        """
        client = create_mock_client()

        page = client.extract_content(html, base_url="https://example.com")

        assert page.success is True
        assert "Hello" in page.markdown
        assert page.metadata.title == "Test"
        assert page.extract_duration_ms > 0

    def test_extract_content_with_selector(self) -> None:
        """Test extracting content with selector."""
        html = """
        <html>
            <body>
                <div id="header">Header</div>
                <div id="content"><p>Main content</p></div>
            </body>
        </html>
        """
        client = create_mock_client()

        page = client.extract_content(html, selector="#content")

        assert "Main content" in page.plain_text or "Main content" in page.markdown


class TestWebSearchClientObservability:
    """Tests for client observability hooks."""

    @pytest.mark.asyncio
    async def test_on_extract_complete_called(self) -> None:
        """Test on_extract_complete callback is called."""
        calls: list[tuple] = []

        def on_extract(
            url: str,
            request_id: str,
            duration_ms: float,
            chars: int,
            links: int,
        ) -> None:
            calls.append((url, request_id, duration_ms, chars, links))

        responses = {
            "https://example.com": (
                200,
                "<html><body><h1>Test</h1><a href='/link'>Link</a></body></html>",
                {"content-type": "text/html"},
            ),
        }
        mock_fetcher = MockFetcher(responses)
        client = WebSearchClient(
            fetcher=mock_fetcher,
            on_extract_complete=on_extract,
        )

        await client.fetch("https://example.com")

        assert len(calls) == 1
        assert calls[0][0] == "https://example.com"
        assert calls[0][2] > 0  # duration_ms
        assert calls[0][3] > 0  # chars


class TestWebSearchClientContextManager:
    """Tests for async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        """Test client as async context manager."""
        responses = {
            "https://example.com": (
                200,
                "<html><body>Test</body></html>",
                {"content-type": "text/html"},
            ),
        }
        mock_fetcher = MockFetcher(responses)

        async with WebSearchClient(fetcher=mock_fetcher) as client:
            page = await client.fetch("https://example.com")
            assert page.success is True

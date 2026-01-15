"""Tests for websearch run utilities."""

from collections.abc import Callable

import pytest

from stageflow.websearch.client import WebSearchClient
from stageflow.websearch.fetcher import MockFetcher
from stageflow.websearch.run_utils import (
    FetchProgress,
    SearchResult,
    SiteMap,
    extract_all_links,
    fetch_page,
    fetch_pages,
    map_site,
    search_and_extract,
    shutdown_extraction_pool,
)


def make_client_factory(responses: dict[str, tuple[int, str, dict[str, str]]]) -> Callable[[], WebSearchClient]:
    """Create a factory that returns WebSearchClient instances backed by MockFetcher."""

    def _factory() -> WebSearchClient:
        return WebSearchClient(fetcher=MockFetcher(responses))

    return _factory


class TestFetchProgress:
    """Tests for FetchProgress dataclass."""

    def test_default_values(self) -> None:
        """Test default progress values."""
        progress = FetchProgress()
        assert progress.completed == 0
        assert progress.total == 0
        assert progress.current_url is None
        assert progress.success_count == 0
        assert progress.error_count == 0

    def test_percent_calculation(self) -> None:
        """Test percentage calculation."""
        progress = FetchProgress(completed=5, total=10)
        assert progress.percent == 50.0

    def test_percent_zero_total(self) -> None:
        """Test percentage with zero total."""
        progress = FetchProgress(completed=0, total=0)
        assert progress.percent == 0.0


class TestSearchResult:
    """Tests for SearchResult dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        result = SearchResult(
            query="test query",
            pages=[],
            relevant_pages=[],
            total_words=100,
            duration_ms=500.0,
        )
        data = result.to_dict()

        assert data["query"] == "test query"
        assert data["pages_fetched"] == 0
        assert data["relevant_pages"] == 0
        assert data["total_words"] == 100
        assert data["duration_ms"] == 500.0


class TestSiteMap:
    """Tests for SiteMap dataclass."""

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        sitemap = SiteMap(
            start_url="https://example.com",
            pages=[],
            internal_links=[],
            external_links=[],
            depth_reached=2,
            duration_ms=1000.0,
        )
        data = sitemap.to_dict()

        assert data["start_url"] == "https://example.com"
        assert data["pages_crawled"] == 0
        assert data["internal_links"] == 0
        assert data["external_links"] == 0
        assert data["depth_reached"] == 2


class TestFetchPage:
    """Tests for fetch_page function."""

    @pytest.mark.asyncio
    async def test_fetch_page_basic(self) -> None:
        """Test basic page fetch."""
        # Use the module-level function with mock
        responses = {
            "https://example.com": (
                200,
                "<html><head><title>Test</title></head><body><h1>Hello</h1></body></html>",
                {"content-type": "text/html"},
            ),
        }

        page = await fetch_page(
            "https://example.com",
            client_factory=make_client_factory(responses),
        )

        assert page.success
        assert page.title == "Test"
        assert "Hello" in page.markdown


class TestFetchPages:
    """Tests for fetch_pages function."""

    @pytest.mark.asyncio
    async def test_fetch_pages_with_progress(self) -> None:
        """Test batch fetch with progress tracking."""
        responses = {
            f"https://example.com/{i}": (
                200,
                f"<html><body><h1>Page {i}</h1></body></html>",
                {"content-type": "text/html"},
            )
            for i in range(3)
        }

        progress_updates: list[FetchProgress] = []

        def on_progress(p: FetchProgress) -> None:
            progress_updates.append(
                FetchProgress(
                    completed=p.completed,
                    total=p.total,
                    success_count=p.success_count,
                    error_count=p.error_count,
                )
            )

        urls = [f"https://example.com/{i}" for i in range(3)]
        pages = await fetch_pages(
            urls,
            concurrency=2,
            client_factory=make_client_factory(responses),
            on_progress=on_progress,
        )

        assert len(pages) == 3
        assert all(p.success for p in pages)

    @pytest.mark.asyncio
    async def test_fetch_pages_empty_list(self) -> None:
        """Test batch fetch with empty URL list."""

        pages = await fetch_pages(
            [],
            client_factory=make_client_factory({}),
        )

        assert pages == []


class TestFetchWithRetry:
    """Tests for fetch_with_retry function."""

    @pytest.mark.asyncio
    async def test_retry_on_success(self) -> None:
        """Test that successful fetch doesn't retry."""
        responses = {
            "https://example.com": (
                200,
                "<html><body>Success</body></html>",
                {"content-type": "text/html"},
            ),
        }

        mock_fetcher = MockFetcher(responses)
        async with WebSearchClient(fetcher=mock_fetcher) as client:
            page = await client.fetch("https://example.com")

        assert page.success


class TestSearchAndExtract:
    """Tests for search_and_extract function."""

    @pytest.mark.asyncio
    async def test_search_filters_relevant_pages(self) -> None:
        """Test that search filters pages by query relevance."""
        responses = {
            "https://example.com": (
                200,
                """
                <html>
                    <body>
                        <h1>Python Documentation</h1>
                        <p>Welcome to Python docs about asyncio tutorial.</p>
                        <a href="https://example.com/asyncio">Asyncio Guide</a>
                        <a href="https://example.com/other">Other Stuff</a>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
            "https://example.com/asyncio": (
                200,
                """
                <html>
                    <body>
                        <h1>Asyncio Tutorial</h1>
                        <p>This is the asyncio tutorial for Python.</p>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
            "https://example.com/other": (
                200,
                """
                <html>
                    <body>
                        <h1>Unrelated Content</h1>
                        <p>This page has nothing to do with async.</p>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
        }

        result = await search_and_extract(
            start_url="https://example.com",
            query="asyncio tutorial",
            max_pages=10,
            max_depth=1,
            client_factory=make_client_factory(responses),
        )

        assert len(result.pages) >= 1
        assert len(result.relevant_pages) >= 1


class TestMapSite:
    """Tests for map_site function."""

    @pytest.mark.asyncio
    async def test_map_site_collects_links(self) -> None:
        """Test that map_site collects internal and external links."""

        responses = {
            "https://example.com": (
                200,
                """
                <html>
                    <body>
                        <h1>Home</h1>
                        <a href="https://example.com/page1">Internal</a>
                        <a href="https://external.com/page">External</a>
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
        }

        sitemap = await map_site(
            "https://example.com",
            max_pages=10,
            max_depth=1,
            client_factory=make_client_factory(responses),
        )

        internal_links = sitemap.internal_links
        external_links = sitemap.external_links

        assert len(internal_links) >= 1
        assert len(external_links) >= 1


class TestExtractAllLinks:
    """Tests for extract_all_links function."""

    @pytest.mark.asyncio
    async def test_extract_all_links_deduplicates(self) -> None:
        """Test that extract_all_links deduplicates URLs."""

        responses = {
            "https://example.com/page1": (
                200,
                """
                <html>
                    <body>
                        <a href="https://example.com/shared">Shared Link</a>
                        <a href="https://example.com/unique1">Unique 1</a>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
            "https://example.com/page2": (
                200,
                """
                <html>
                    <body>
                        <a href="https://example.com/shared">Shared Link</a>
                        <a href="https://example.com/unique2">Unique 2</a>
                    </body>
                </html>
                """,
                {"content-type": "text/html"},
            ),
        }

        links = await extract_all_links(
            ["https://example.com/page1", "https://example.com/page2"],
            client_factory=make_client_factory(responses),
        )

        assert len(links) == 3


class TestShutdownExtractionPool:
    """Tests for shutdown_extraction_pool function."""

    def test_shutdown_is_callable(self) -> None:
        """Test that shutdown function exists and is callable."""
        assert callable(shutdown_extraction_pool)

    def test_shutdown_idempotent(self) -> None:
        """Test that shutdown can be called multiple times."""
        shutdown_extraction_pool()
        shutdown_extraction_pool()  # Should not raise


class TestRunUtilsExports:
    """Tests for run_utils module exports."""

    def test_exports_from_websearch(self) -> None:
        """Test that run utilities are exported from stageflow.websearch."""
        import stageflow.websearch as websearch

        expected_callables = [
            "fetch_page",
            "fetch_pages",
            "fetch_with_retry",
            "search_and_extract",
            "map_site",
            "extract_all_links",
            "shutdown_extraction_pool",
        ]

        for name in ["FetchProgress", "SearchResult", "SiteMap"]:
            assert hasattr(websearch, name)

        for name in expected_callables:
            assert callable(getattr(websearch, name))

    def test_all_in_module_all(self) -> None:
        """Test that all utilities are in __all__."""
        import stageflow.websearch as ws

        expected = [
            "FetchProgress",
            "SearchResult",
            "SiteMap",
            "fetch_page",
            "fetch_pages",
            "fetch_with_retry",
            "search_and_extract",
            "map_site",
            "extract_all_links",
            "shutdown_extraction_pool",
        ]

        for name in expected:
            assert name in ws.__all__, f"{name} not in __all__"

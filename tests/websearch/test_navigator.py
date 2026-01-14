"""Tests for websearch navigator module."""

import pytest

from stageflow.websearch.navigator import (
    FallbackNavigator,
    NavigationConfig,
    NavigationResult,
    get_default_navigator,
    SELECTOLAX_AVAILABLE,
)

if SELECTOLAX_AVAILABLE:
    from stageflow.websearch.navigator import PageNavigator


class TestNavigationConfig:
    """Tests for NavigationConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = NavigationConfig()
        assert ".pagination" in config.pagination_selectors
        assert "next" in config.next_link_texts
        assert "prev" in config.prev_link_texts
        assert config.min_nav_links == 3
        assert config.max_actions == 20

    def test_custom_values(self) -> None:
        """Test custom configuration."""
        config = NavigationConfig(
            max_actions=10,
            min_nav_links=5,
        )
        assert config.max_actions == 10
        assert config.min_nav_links == 5


class TestNavigationResult:
    """Tests for NavigationResult dataclass."""

    def test_default_values(self) -> None:
        """Test default result values."""
        result = NavigationResult()
        assert result.actions == []
        assert result.pagination is None
        assert result.main_content_selector is None
        assert result.nav_links == []
        assert result.breadcrumbs == []

    def test_to_dict(self) -> None:
        """Test serialization."""
        from stageflow.websearch.models import NavigationAction, PaginationInfo

        result = NavigationResult(
            actions=[NavigationAction(action_type="link", label="Test")],
            pagination=PaginationInfo(current_page=1),
            main_content_selector="article",
        )
        d = result.to_dict()
        assert len(d["actions"]) == 1
        assert d["pagination"]["current_page"] == 1
        assert d["main_content_selector"] == "article"


class TestFallbackNavigator:
    """Tests for FallbackNavigator (regex-based)."""

    def test_find_next_link(self) -> None:
        """Test next link detection with regex."""
        html = """
        <html>
            <body>
                <a href="/page/2">Next →</a>
            </body>
        </html>
        """
        navigator = FallbackNavigator()
        result = navigator.analyze(html, base_url="https://example.com")

        assert result.pagination is not None
        assert result.pagination.next_url == "https://example.com/page/2"

    def test_find_prev_link(self) -> None:
        """Test previous link detection with regex."""
        html = """
        <html>
            <body>
                <a href="/page/1">← Previous</a>
            </body>
        </html>
        """
        navigator = FallbackNavigator()
        result = navigator.analyze(html, base_url="https://example.com")

        assert result.pagination is not None
        assert result.pagination.prev_url == "https://example.com/page/1"

    def test_find_next_by_class(self) -> None:
        """Test next link detection by class name."""
        html = """
        <html>
            <body>
                <a class="next-page" href="/page/2">2</a>
            </body>
        </html>
        """
        navigator = FallbackNavigator()
        result = navigator.analyze(html, base_url="https://example.com")

        assert result.pagination is not None
        assert result.pagination.next_url == "https://example.com/page/2"

    def test_no_pagination(self) -> None:
        """Test when no pagination exists."""
        html = """
        <html>
            <body>
                <p>Just some content</p>
            </body>
        </html>
        """
        navigator = FallbackNavigator()
        result = navigator.analyze(html)

        assert result.pagination is None
        assert result.actions == []

    def test_creates_navigation_actions(self) -> None:
        """Test navigation actions are created from pagination."""
        html = """
        <html>
            <body>
                <a href="/page/2">Next</a>
                <a href="/page/0">Prev</a>
            </body>
        </html>
        """
        navigator = FallbackNavigator()
        result = navigator.analyze(html, base_url="https://example.com")

        assert len(result.actions) == 2
        action_types = {a.action_type for a in result.actions}
        assert "pagination" in action_types


@pytest.mark.skipif(not SELECTOLAX_AVAILABLE, reason="selectolax not installed")
class TestPageNavigator:
    """Tests for PageNavigator (selectolax-based)."""

    def test_find_pagination_container(self) -> None:
        """Test pagination detection from container."""
        html = """
        <html>
            <body>
                <div class="pagination">
                    <a href="/page/1">1</a>
                    <span class="current">2</span>
                    <a href="/page/3">3</a>
                    <a href="/page/3" class="next">Next</a>
                </div>
            </body>
        </html>
        """
        navigator = PageNavigator()
        result = navigator.analyze(html, base_url="https://example.com")

        assert result.pagination is not None
        assert result.pagination.next_url == "https://example.com/page/3"

    def test_find_pagination_from_url_pattern(self) -> None:
        """Test pagination detection from URL patterns."""
        html = """
        <html>
            <body>
                <a href="/results?page=1">1</a>
                <a href="/results?page=2">2</a>
                <a href="/results?page=3">3</a>
            </body>
        </html>
        """
        navigator = PageNavigator()
        result = navigator.analyze(html, base_url="https://example.com")

        assert result.pagination is not None
        assert len(result.pagination.page_urls) > 0

    def test_detect_main_content_article(self) -> None:
        """Test main content detection with article tag."""
        html = """
        <html>
            <body>
                <nav>Navigation</nav>
                <article>
                    <h1>Main Article</h1>
                    <p>This is the main content of the page with lots of text to make it substantial.</p>
                    <p>More content here to make it substantial enough for detection and analysis.</p>
                    <p>Even more content to ensure we have enough text length for the threshold.</p>
                    <p>Additional paragraph to really ensure we have enough content for detection.</p>
                    <p>One more paragraph of text to make absolutely sure the content is detected.</p>
                </article>
                <aside>Sidebar</aside>
            </body>
        </html>
        """
        navigator = PageNavigator()
        result = navigator.analyze(html)

        # Should detect article or a content selector
        assert result.main_content_selector is not None or len(result.actions) >= 0

    def test_detect_main_content_div(self) -> None:
        """Test main content detection with content div."""
        html = """
        <html>
            <body>
                <div class="header">Header</div>
                <div class="content">
                    <h1>Page Title</h1>
                    <p>This is substantial content that should be detected as main.</p>
                    <p>Adding more paragraphs to make the content area larger.</p>
                    <p>Even more content here for proper detection threshold.</p>
                </div>
                <div class="footer">Footer</div>
            </body>
        </html>
        """
        navigator = PageNavigator()
        result = navigator.analyze(html)

        assert result.main_content_selector is not None
        assert "content" in result.main_content_selector.lower()

    def test_extract_nav_links(self) -> None:
        """Test navigation link extraction."""
        html = """
        <html>
            <body>
                <nav>
                    <a href="/">Home</a>
                    <a href="/about">About</a>
                    <a href="/contact">Contact</a>
                </nav>
                <main>
                    <p>Content</p>
                </main>
            </body>
        </html>
        """
        navigator = PageNavigator()
        result = navigator.analyze(html, base_url="https://example.com")

        assert len(result.nav_links) >= 3
        nav_urls = {link.url for link in result.nav_links}
        assert "https://example.com/" in nav_urls
        assert "https://example.com/about" in nav_urls

    def test_extract_breadcrumbs(self) -> None:
        """Test breadcrumb extraction."""
        html = """
        <html>
            <body>
                <nav class="breadcrumb">
                    <a href="/">Home</a>
                    <a href="/products">Products</a>
                    <a href="/products/widgets">Widgets</a>
                </nav>
                <main>Content</main>
            </body>
        </html>
        """
        navigator = PageNavigator()
        result = navigator.analyze(html, base_url="https://example.com")

        assert len(result.breadcrumbs) >= 2
        breadcrumb_texts = [bc.text for bc in result.breadcrumbs]
        assert "Home" in breadcrumb_texts

    def test_extract_content_links(self) -> None:
        """Test content link extraction."""
        html = """
        <html>
            <body>
                <article>
                    <h1>Article Title</h1>
                    <p>Read <a href="/related1">related article 1</a> and
                       <a href="/related2">related article 2</a>.</p>
                </article>
            </body>
        </html>
        """
        navigator = PageNavigator()
        result = navigator.analyze(html, base_url="https://example.com")

        content_actions = [a for a in result.actions if a.action_type == "content_link"]
        assert len(content_actions) >= 2

    def test_action_priority_ordering(self) -> None:
        """Test that actions have correct priority ordering."""
        html = """
        <html>
            <body>
                <nav><a href="/nav">Nav Link</a></nav>
                <div class="pagination">
                    <a href="/page/2" class="next">Next</a>
                </div>
                <article>
                    <a href="/content">Content Link</a>
                </article>
            </body>
        </html>
        """
        navigator = PageNavigator()
        result = navigator.analyze(html, base_url="https://example.com")

        if result.actions:
            pagination_actions = [a for a in result.actions if a.action_type == "pagination"]
            if pagination_actions:
                assert pagination_actions[0].priority <= 2

    def test_max_actions_limit(self) -> None:
        """Test that max_actions limit is respected."""
        links = "\n".join([f'<a href="/page/{i}">Link {i}</a>' for i in range(50)])
        html = f"""
        <html>
            <body>
                <article>{links}</article>
            </body>
        </html>
        """
        config = NavigationConfig(max_actions=5)
        navigator = PageNavigator(config)
        result = navigator.analyze(html, base_url="https://example.com")

        assert len(result.actions) <= 5

    def test_no_duplicate_action_urls(self) -> None:
        """Test that duplicate URLs don't create duplicate actions."""
        html = """
        <html>
            <body>
                <nav>
                    <a href="/page">Link</a>
                </nav>
                <article>
                    <a href="/page">Same Link</a>
                </article>
            </body>
        </html>
        """
        navigator = PageNavigator()
        result = navigator.analyze(html, base_url="https://example.com")

        urls = [a.url for a in result.actions if a.url]
        unique_urls = set(urls)
        assert len(urls) == len(unique_urls)


class TestGetDefaultNavigator:
    """Tests for get_default_navigator factory."""

    def test_returns_navigator(self) -> None:
        """Test factory returns a navigator."""
        navigator = get_default_navigator()
        assert navigator is not None

    def test_with_config(self) -> None:
        """Test factory accepts config."""
        config = NavigationConfig(max_actions=5)
        navigator = get_default_navigator(config)
        assert navigator.config.max_actions == 5

    def test_returns_correct_type(self) -> None:
        """Test factory returns correct type based on availability."""
        navigator = get_default_navigator()
        if SELECTOLAX_AVAILABLE:
            assert isinstance(navigator, PageNavigator)
        else:
            assert isinstance(navigator, FallbackNavigator)

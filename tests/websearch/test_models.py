"""Tests for websearch data models."""


from stageflow.websearch.models import (
    ExtractedLink,
    NavigationAction,
    PageMetadata,
    PaginationInfo,
    WebPage,
)


class TestPageMetadata:
    """Tests for PageMetadata dataclass."""

    def test_default_values(self) -> None:
        """Test default values are None/empty."""
        meta = PageMetadata()
        assert meta.title is None
        assert meta.description is None
        assert meta.language is None
        assert meta.keywords == []

    def test_with_values(self) -> None:
        """Test creation with values."""
        meta = PageMetadata(
            title="Test Page",
            description="A test description",
            language="en",
            author="Test Author",
            keywords=["test", "page"],
        )
        assert meta.title == "Test Page"
        assert meta.description == "A test description"
        assert meta.language == "en"
        assert meta.author == "Test Author"
        assert meta.keywords == ["test", "page"]

    def test_to_dict(self) -> None:
        """Test serialization to dict."""
        meta = PageMetadata(title="Test", description="Desc")
        d = meta.to_dict()
        assert d["title"] == "Test"
        assert d["description"] == "Desc"
        assert d["language"] is None

    def test_from_dict(self) -> None:
        """Test deserialization from dict."""
        d = {"title": "Test", "keywords": ["a", "b"]}
        meta = PageMetadata.from_dict(d)
        assert meta.title == "Test"
        assert meta.keywords == ["a", "b"]

    def test_roundtrip(self) -> None:
        """Test to_dict -> from_dict roundtrip."""
        original = PageMetadata(
            title="Test",
            description="Desc",
            language="en",
            author="Author",
            keywords=["k1", "k2"],
        )
        restored = PageMetadata.from_dict(original.to_dict())
        assert restored == original


class TestExtractedLink:
    """Tests for ExtractedLink dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        link = ExtractedLink(url="https://example.com")
        assert link.url == "https://example.com"
        assert link.text == ""
        assert link.is_internal is False

    def test_from_element_absolute_url(self) -> None:
        """Test creating from absolute URL."""
        link = ExtractedLink.from_element(
            "https://example.com/page",
            "Click here",
            base_url="https://example.com",
        )
        assert link.url == "https://example.com/page"
        assert link.text == "Click here"
        assert link.is_internal is True

    def test_from_element_relative_url(self) -> None:
        """Test creating from relative URL with base."""
        link = ExtractedLink.from_element(
            "/page",
            "Page",
            base_url="https://example.com",
        )
        assert link.url == "https://example.com/page"
        assert link.is_internal is True

    def test_from_element_external_url(self) -> None:
        """Test external URL detection."""
        link = ExtractedLink.from_element(
            "https://other.com/page",
            "External",
            base_url="https://example.com",
        )
        assert link.url == "https://other.com/page"
        assert link.is_internal is False

    def test_from_element_protocol_relative(self) -> None:
        """Test protocol-relative URL."""
        link = ExtractedLink.from_element(
            "//cdn.example.com/script.js",
            "CDN",
        )
        assert link.url == "https://cdn.example.com/script.js"

    def test_to_dict(self) -> None:
        """Test serialization."""
        link = ExtractedLink(
            url="https://example.com",
            text="Example",
            is_internal=True,
        )
        d = link.to_dict()
        assert d["url"] == "https://example.com"
        assert d["text"] == "Example"
        assert d["is_internal"] is True

    def test_from_dict(self) -> None:
        """Test deserialization."""
        d = {"url": "https://example.com", "text": "Test", "is_internal": True}
        link = ExtractedLink.from_dict(d)
        assert link.url == "https://example.com"
        assert link.text == "Test"
        assert link.is_internal is True


class TestNavigationAction:
    """Tests for NavigationAction dataclass."""

    def test_creation(self) -> None:
        """Test basic creation."""
        action = NavigationAction(
            action_type="pagination",
            label="Next page",
            url="https://example.com/page/2",
            priority=1,
        )
        assert action.action_type == "pagination"
        assert action.label == "Next page"
        assert action.url == "https://example.com/page/2"
        assert action.priority == 1

    def test_default_priority(self) -> None:
        """Test default priority."""
        action = NavigationAction(action_type="link", label="Test")
        assert action.priority == 5

    def test_to_dict(self) -> None:
        """Test serialization."""
        action = NavigationAction(
            action_type="pagination",
            label="Next",
            url="https://example.com/2",
            metadata={"page": 2},
        )
        d = action.to_dict()
        assert d["action_type"] == "pagination"
        assert d["metadata"] == {"page": 2}

    def test_from_dict(self) -> None:
        """Test deserialization."""
        d = {
            "action_type": "link",
            "label": "Home",
            "url": "https://example.com",
            "priority": 3,
        }
        action = NavigationAction.from_dict(d)
        assert action.action_type == "link"
        assert action.label == "Home"
        assert action.priority == 3


class TestPaginationInfo:
    """Tests for PaginationInfo dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        pag = PaginationInfo()
        assert pag.current_page == 1
        assert pag.total_pages is None
        assert pag.next_url is None
        assert pag.prev_url is None
        assert pag.page_urls == []

    def test_has_next(self) -> None:
        """Test has_next property."""
        pag = PaginationInfo(next_url="https://example.com/page/2")
        assert pag.has_next is True

        pag_no_next = PaginationInfo()
        assert pag_no_next.has_next is False

    def test_has_prev(self) -> None:
        """Test has_prev property."""
        pag = PaginationInfo(prev_url="https://example.com/page/1")
        assert pag.has_prev is True

        pag_no_prev = PaginationInfo()
        assert pag_no_prev.has_prev is False

    def test_to_dict(self) -> None:
        """Test serialization."""
        pag = PaginationInfo(
            current_page=2,
            total_pages=10,
            next_url="https://example.com/3",
            prev_url="https://example.com/1",
        )
        d = pag.to_dict()
        assert d["current_page"] == 2
        assert d["total_pages"] == 10
        assert d["next_url"] == "https://example.com/3"

    def test_from_dict(self) -> None:
        """Test deserialization."""
        d = {"current_page": 3, "next_url": "https://example.com/4"}
        pag = PaginationInfo.from_dict(d)
        assert pag.current_page == 3
        assert pag.next_url == "https://example.com/4"


class TestWebPage:
    """Tests for WebPage dataclass."""

    def test_default_values(self) -> None:
        """Test default values."""
        page = WebPage(url="https://example.com")
        assert page.url == "https://example.com"
        assert page.status_code == 0
        assert page.markdown == ""
        assert page.error is None
        assert page.links == []

    def test_success_property(self) -> None:
        """Test success property."""
        page_ok = WebPage(url="https://example.com", status_code=200)
        assert page_ok.success is True

        page_404 = WebPage(url="https://example.com", status_code=404)
        assert page_404.success is False

        page_error = WebPage(url="https://example.com", status_code=200, error="Failed")
        assert page_error.success is False

    def test_title_property(self) -> None:
        """Test title convenience property."""
        meta = PageMetadata(title="Test Page")
        page = WebPage(url="https://example.com", metadata=meta)
        assert page.title == "Test Page"

    def test_internal_external_links(self) -> None:
        """Test internal/external link filtering."""
        links = [
            ExtractedLink(url="https://example.com/a", is_internal=True),
            ExtractedLink(url="https://other.com/b", is_internal=False),
            ExtractedLink(url="https://example.com/c", is_internal=True),
        ]
        page = WebPage(url="https://example.com", links=links)

        assert len(page.internal_links) == 2
        assert len(page.external_links) == 1
        assert page.internal_links[0].url == "https://example.com/a"
        assert page.external_links[0].url == "https://other.com/b"

    def test_extract_links_with_limit(self) -> None:
        """Test extract_links with limit."""
        links = [
            ExtractedLink(url=f"https://example.com/{i}", is_internal=True)
            for i in range(10)
        ]
        page = WebPage(url="https://example.com", links=links)

        filtered = page.extract_links(limit=3)
        assert len(filtered) == 3

        internal = page.extract_links(internal_only=True, limit=2)
        assert len(internal) == 2

    def test_error_result(self) -> None:
        """Test error_result factory."""
        page = WebPage.error_result(
            "https://example.com",
            "Connection timeout",
            duration_ms=1500.0,
        )
        assert page.url == "https://example.com"
        assert page.error == "Connection timeout"
        assert page.fetch_duration_ms == 1500.0
        assert page.success is False
        assert page.fetched_at is not None

    def test_truncate(self) -> None:
        """Test content truncation."""
        long_content = "Hello world. " * 1000
        page = WebPage(
            url="https://example.com",
            markdown=long_content,
            plain_text=long_content,
        )

        truncated = page.truncate(max_chars=500)
        assert len(truncated.markdown) <= 550  # Some buffer for truncation message
        assert "[Content truncated...]" in truncated.markdown or len(truncated.markdown) <= 500

    def test_truncate_no_change_if_short(self) -> None:
        """Test truncate returns same if content already short."""
        page = WebPage(url="https://example.com", markdown="Short content")
        truncated = page.truncate(max_chars=1000)
        assert truncated is page

    def test_to_dict(self) -> None:
        """Test full serialization."""
        page = WebPage(
            url="https://example.com",
            final_url="https://www.example.com",
            status_code=200,
            markdown="# Hello",
            plain_text="Hello",
            word_count=1,
        )
        d = page.to_dict()
        assert d["url"] == "https://example.com"
        assert d["final_url"] == "https://www.example.com"
        assert d["status_code"] == 200
        assert d["markdown"] == "# Hello"
        assert d["word_count"] == 1

    def test_from_dict(self) -> None:
        """Test full deserialization."""
        d = {
            "url": "https://example.com",
            "status_code": 200,
            "markdown": "# Test",
            "plain_text": "Test",
            "metadata": {"title": "Test Page"},
            "links": [{"url": "https://example.com/a", "text": "Link"}],
        }
        page = WebPage.from_dict(d)
        assert page.url == "https://example.com"
        assert page.status_code == 200
        assert page.markdown == "# Test"
        assert page.metadata.title == "Test Page"
        assert len(page.links) == 1

    def test_roundtrip(self) -> None:
        """Test to_dict -> from_dict roundtrip."""
        original = WebPage(
            url="https://example.com",
            status_code=200,
            markdown="# Content",
            plain_text="Content",
            metadata=PageMetadata(title="Test"),
            links=[ExtractedLink(url="https://example.com/a", text="A")],
            pagination=PaginationInfo(current_page=1, next_url="https://example.com/2"),
            word_count=1,
        )
        restored = WebPage.from_dict(original.to_dict())
        assert restored.url == original.url
        assert restored.status_code == original.status_code
        assert restored.markdown == original.markdown
        assert restored.metadata.title == original.metadata.title
        assert len(restored.links) == len(original.links)
        assert restored.pagination is not None
        assert restored.pagination.next_url == original.pagination.next_url

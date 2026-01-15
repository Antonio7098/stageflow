"""Tests for websearch module exports.

Verifies that all config classes and other symbols are properly exported
from the main stageflow.websearch module.
"""


class TestWebsearchExports:
    """Tests for websearch module exports."""

    def test_exports_websearch_config(self) -> None:
        """WebSearchConfig should be importable from stageflow.websearch."""
        from stageflow.websearch import WebSearchConfig

        config = WebSearchConfig()
        assert config.max_concurrent == 5
        assert config.auto_extract is True

    def test_exports_navigation_config(self) -> None:
        """NavigationConfig should be importable from stageflow.websearch."""
        from stageflow.websearch import NavigationConfig

        config = NavigationConfig()
        assert config.max_actions == 20
        assert len(config.pagination_selectors) > 0

    def test_exports_extraction_config(self) -> None:
        """ExtractionConfig should be importable from stageflow.websearch."""
        from stageflow.websearch import ExtractionConfig

        config = ExtractionConfig()
        assert config.preserve_headings is True
        assert config.preserve_links is True

    def test_exports_fetch_config(self) -> None:
        """FetchConfig should be importable from stageflow.websearch."""
        from stageflow.websearch import FetchConfig

        config = FetchConfig()
        assert config.timeout > 0

    def test_all_config_classes_in_all(self) -> None:
        """All config classes should be in __all__."""
        import stageflow.websearch as ws

        assert "WebSearchConfig" in ws.__all__
        assert "NavigationConfig" in ws.__all__
        assert "ExtractionConfig" in ws.__all__
        assert "FetchConfig" in ws.__all__

    def test_exports_main_client(self) -> None:
        """WebSearchClient should be importable from stageflow.websearch."""
        from stageflow.websearch import WebSearchClient

        assert WebSearchClient is not None

    def test_exports_models(self) -> None:
        """Model classes should be importable from stageflow.websearch."""
        from stageflow.websearch import (
            ExtractedLink,
            NavigationAction,
            PageMetadata,
            WebPage,
        )

        assert WebPage is not None
        assert ExtractedLink is not None
        assert NavigationAction is not None
        assert PageMetadata is not None

    def test_exports_protocols(self) -> None:
        """Protocol classes should be importable from stageflow.websearch."""
        from stageflow.websearch import (
            ContentExtractorProtocol,
            FetcherProtocol,
            NavigatorProtocol,
        )

        assert FetcherProtocol is not None
        assert ContentExtractorProtocol is not None
        assert NavigatorProtocol is not None


class TestNavigationActionTypes:
    """Tests for NavigationAction action_type documentation."""

    def test_pagination_action_type(self) -> None:
        """Pagination action type should be documented."""
        from stageflow.websearch import NavigationAction

        action = NavigationAction(
            action_type="pagination",
            label="Next page",
            url="https://example.com/page/2",
            priority=1,
            metadata={"direction": "next"},
        )
        assert action.action_type == "pagination"
        assert action.metadata["direction"] == "next"

    def test_nav_link_action_type(self) -> None:
        """Navigation link action type should work."""
        from stageflow.websearch import NavigationAction

        action = NavigationAction(
            action_type="nav_link",
            label="About",
            url="https://example.com/about",
            priority=3,
        )
        assert action.action_type == "nav_link"

    def test_content_link_action_type(self) -> None:
        """Content link action type should work."""
        from stageflow.websearch import NavigationAction

        action = NavigationAction(
            action_type="content_link",
            label="Read more",
            url="https://example.com/article",
            priority=4,
        )
        assert action.action_type == "content_link"

    def test_action_type_docstring_documents_types(self) -> None:
        """NavigationAction docstring should document valid action types."""
        from stageflow.websearch import NavigationAction

        docstring = NavigationAction.__doc__ or ""

        # Verify all action types are documented
        assert "pagination" in docstring
        assert "nav_link" in docstring
        assert "content_link" in docstring
        assert "external" in docstring

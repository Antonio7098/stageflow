"""Web search and content extraction module.

This module provides async web fetching, HTML cleaning with structure preservation,
and navigation capabilities for agents to explore web pages.

Architecture follows SOLID principles:
- **Single Responsibility**: Each class has one job (fetch, extract, navigate)
- **Open/Closed**: Extend via protocols, not modification
- **Liskov Substitution**: All extractors/fetchers are interchangeable
- **Interface Segregation**: Small, focused protocols
- **Dependency Inversion**: High-level code depends on protocols

Key Components:
    - **Fetcher**: Async HTTP client with retries, timeouts, observability
    - **Extractor**: HTML to structured markdown with headings, lists, links
    - **Navigator**: Link extraction, pagination, page traversal
    - **WebPage**: Immutable result container with metadata

Example:
    ```python
    from stageflow.websearch import WebSearchClient

    client = WebSearchClient()

    # Single page fetch
    page = await client.fetch("https://example.com")
    print(page.markdown)  # Structured content

    # Batch fetch with parallelization
    pages = await client.fetch_many(["https://a.com", "https://b.com"])

    # Navigate and follow links
    links = page.extract_links(selector="article a")
    child_pages = await client.fetch_many([l.url for l in links[:5]])
    ```
"""

from stageflow.websearch.client import WebSearchClient, WebSearchConfig
from stageflow.websearch.extractor import (
    ContentExtractor,
    DefaultContentExtractor,
    ExtractionConfig,
)
from stageflow.websearch.fetcher import (
    FetchConfig,
    Fetcher,
    FetchResult,
    HttpFetcher,
)
from stageflow.websearch.models import (
    ExtractedLink,
    NavigationAction,
    PageMetadata,
    WebPage,
)
from stageflow.websearch.navigator import (
    NavigationConfig,
    NavigationResult,
    Navigator,
    PageNavigator,
)
from stageflow.websearch.protocols import (
    ContentExtractorProtocol,
    FetcherProtocol,
    NavigatorProtocol,
)
from stageflow.websearch.run_utils import (
    FetchProgress,
    SearchResult,
    SiteMap,
    extract_all_links,
    fetch_page,
    fetch_pages,
    fetch_with_retry,
    map_site,
    search_and_extract,
    shutdown_extraction_pool,
)

__all__ = [
    # Main client
    "WebSearchClient",
    "WebSearchConfig",
    # Protocols (for extension)
    "FetcherProtocol",
    "ContentExtractorProtocol",
    "NavigatorProtocol",
    # Fetcher
    "Fetcher",
    "HttpFetcher",
    "FetchConfig",
    "FetchResult",
    # Extractor
    "ContentExtractor",
    "DefaultContentExtractor",
    "ExtractionConfig",
    # Navigator
    "Navigator",
    "PageNavigator",
    "NavigationConfig",
    "NavigationResult",
    # Models
    "WebPage",
    "PageMetadata",
    "ExtractedLink",
    "NavigationAction",
    # Run utilities
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

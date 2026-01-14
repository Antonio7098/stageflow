"""Tests for websearch extractor module."""

import pytest

from stageflow.websearch.extractor import (
    SELECTOLAX_AVAILABLE,
    ExtractionConfig,
    ExtractionResult,
    FallbackContentExtractor,
    get_default_extractor,
)

if SELECTOLAX_AVAILABLE:
    from stageflow.websearch.extractor import DefaultContentExtractor


class TestExtractionConfig:
    """Tests for ExtractionConfig dataclass."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = ExtractionConfig()
        assert config.preserve_headings is True
        assert config.preserve_lists is True
        assert config.preserve_links is True
        assert config.preserve_emphasis is True
        assert config.preserve_code is True
        assert config.max_link_text_length == 100
        assert "script" in config.remove_selectors
        assert "article" in config.main_content_selectors

    def test_custom_values(self) -> None:
        """Test custom configuration."""
        config = ExtractionConfig(
            preserve_headings=False,
            preserve_links=False,
            max_link_text_length=50,
        )
        assert config.preserve_headings is False
        assert config.preserve_links is False
        assert config.max_link_text_length == 50


class TestExtractionResult:
    """Tests for ExtractionResult dataclass."""

    def test_default_values(self) -> None:
        """Test default result values."""
        result = ExtractionResult()
        assert result.markdown == ""
        assert result.plain_text == ""
        assert result.links == []
        assert result.word_count == 0
        assert result.heading_outline == []

    def test_to_dict(self) -> None:
        """Test serialization."""
        result = ExtractionResult(
            markdown="# Test",
            plain_text="Test",
            word_count=1,
            heading_outline=[(1, "Test")],
        )
        d = result.to_dict()
        assert d["markdown"] == "# Test"
        assert d["word_count"] == 1
        assert d["heading_outline"] == [(1, "Test")]


class TestFallbackContentExtractor:
    """Tests for FallbackContentExtractor (regex-based)."""

    def test_extract_headings(self) -> None:
        """Test heading extraction with regex."""
        html = """
        <html>
            <body>
                <h1>Main Title</h1>
                <p>Some text</p>
                <h2>Subtitle</h2>
                <p>More text</p>
            </body>
        </html>
        """
        extractor = FallbackContentExtractor()
        result = extractor.extract(html)

        assert "# Main Title" in result.markdown
        assert "## Subtitle" in result.markdown
        assert (1, "Main Title") in result.heading_outline
        assert (2, "Subtitle") in result.heading_outline

    def test_extract_paragraphs(self) -> None:
        """Test paragraph extraction."""
        html = """
        <html>
            <body>
                <p>First paragraph.</p>
                <p>Second paragraph.</p>
            </body>
        </html>
        """
        extractor = FallbackContentExtractor()
        result = extractor.extract(html)

        assert "First paragraph" in result.markdown
        assert "Second paragraph" in result.markdown

    def test_extract_removes_scripts(self) -> None:
        """Test script tag removal."""
        html = """
        <html>
            <body>
                <p>Visible text</p>
                <script>alert('hidden');</script>
                <p>More text</p>
            </body>
        </html>
        """
        extractor = FallbackContentExtractor()
        result = extractor.extract(html)

        assert "Visible text" in result.plain_text
        assert "alert" not in result.plain_text
        assert "hidden" not in result.plain_text

    def test_extract_removes_styles(self) -> None:
        """Test style tag removal."""
        html = """
        <html>
            <head><style>.hidden { display: none; }</style></head>
            <body>
                <p>Content</p>
            </body>
        </html>
        """
        extractor = FallbackContentExtractor()
        result = extractor.extract(html)

        assert "Content" in result.plain_text
        assert "display" not in result.plain_text
        assert "none" not in result.plain_text

    def test_extract_links_regex(self) -> None:
        """Test link extraction with regex."""
        html = """
        <html>
            <body>
                <a href="https://example.com">Example</a>
                <a href="/page">Page</a>
                <a href="javascript:void(0)">Skip</a>
            </body>
        </html>
        """
        extractor = FallbackContentExtractor()
        links = extractor.extract_links(html, base_url="https://test.com")

        assert len(links) == 2
        assert links[0].url == "https://example.com"
        assert links[0].text == "Example"
        assert links[1].url == "https://test.com/page"

    def test_extract_metadata_regex(self) -> None:
        """Test metadata extraction with regex."""
        html = """
        <html>
            <head>
                <title>Test Page Title</title>
                <meta name="description" content="Test description">
            </head>
            <body></body>
        </html>
        """
        extractor = FallbackContentExtractor()
        metadata = extractor.extract_metadata(html)

        assert metadata.title == "Test Page Title"
        assert metadata.description == "Test description"

    def test_word_count(self) -> None:
        """Test word count calculation."""
        html = """
        <html>
            <body>
                <p>This is a test paragraph with several words.</p>
            </body>
        </html>
        """
        extractor = FallbackContentExtractor()
        result = extractor.extract(html)

        assert result.word_count > 0

    def test_html_entities_decoded(self) -> None:
        """Test HTML entities are decoded."""
        html = """
        <html>
            <body>
                <p>Test &amp; more &lt;text&gt;</p>
            </body>
        </html>
        """
        extractor = FallbackContentExtractor()
        result = extractor.extract(html)

        assert "&" in result.plain_text
        assert "<text>" in result.plain_text


@pytest.mark.skipif(not SELECTOLAX_AVAILABLE, reason="selectolax not installed")
class TestDefaultContentExtractor:
    """Tests for DefaultContentExtractor (selectolax-based)."""

    def test_extract_headings(self) -> None:
        """Test heading extraction preserves structure."""
        html = """
        <html>
            <body>
                <h1>Main Title</h1>
                <p>Introduction</p>
                <h2>Section 1</h2>
                <p>Content 1</p>
                <h3>Subsection 1.1</h3>
                <p>Content 1.1</p>
            </body>
        </html>
        """
        extractor = DefaultContentExtractor()
        result = extractor.extract(html)

        assert "# Main Title" in result.markdown
        assert "## Section 1" in result.markdown
        assert "### Subsection 1.1" in result.markdown
        assert len(result.heading_outline) == 3

    def test_extract_lists_unordered(self) -> None:
        """Test unordered list extraction."""
        html = """
        <html>
            <body>
                <ul>
                    <li>Item 1</li>
                    <li>Item 2</li>
                    <li>Item 3</li>
                </ul>
            </body>
        </html>
        """
        extractor = DefaultContentExtractor()
        result = extractor.extract(html)

        assert "- Item 1" in result.markdown
        assert "- Item 2" in result.markdown
        assert "- Item 3" in result.markdown

    def test_extract_lists_ordered(self) -> None:
        """Test ordered list extraction."""
        html = """
        <html>
            <body>
                <ol>
                    <li>First</li>
                    <li>Second</li>
                    <li>Third</li>
                </ol>
            </body>
        </html>
        """
        extractor = DefaultContentExtractor()
        result = extractor.extract(html)

        assert "1. First" in result.markdown
        assert "2. Second" in result.markdown
        assert "3. Third" in result.markdown

    def test_extract_links_as_markdown(self) -> None:
        """Test links are converted to markdown format."""
        html = """
        <html>
            <body>
                <p>Check out <a href="https://example.com">this link</a> for more.</p>
            </body>
        </html>
        """
        extractor = DefaultContentExtractor()
        result = extractor.extract(html, base_url="https://test.com")

        assert "[this link](https://example.com)" in result.markdown

    def test_extract_emphasis_bold(self) -> None:
        """Test bold text preservation."""
        html = """
        <html>
            <body>
                <p>This is <strong>important</strong> text.</p>
            </body>
        </html>
        """
        extractor = DefaultContentExtractor()
        result = extractor.extract(html)

        assert "**important**" in result.markdown

    def test_extract_emphasis_italic(self) -> None:
        """Test italic text preservation."""
        html = """
        <html>
            <body>
                <p>This is <em>emphasized</em> text.</p>
            </body>
        </html>
        """
        extractor = DefaultContentExtractor()
        result = extractor.extract(html)

        assert "_emphasized_" in result.markdown

    def test_extract_code_inline(self) -> None:
        """Test inline code preservation."""
        html = """
        <html>
            <body>
                <p>Use the <code>print()</code> function.</p>
            </body>
        </html>
        """
        extractor = DefaultContentExtractor()
        result = extractor.extract(html)

        assert "`print()`" in result.markdown

    def test_extract_code_block(self) -> None:
        """Test code block preservation."""
        html = """
        <html>
            <body>
                <pre><code class="language-python">def hello():
    print("Hello")</code></pre>
            </body>
        </html>
        """
        extractor = DefaultContentExtractor()
        result = extractor.extract(html)

        assert "```python" in result.markdown
        assert "def hello():" in result.markdown
        assert "```" in result.markdown

    def test_extract_blockquote(self) -> None:
        """Test blockquote preservation."""
        html = """
        <html>
            <body>
                <blockquote>This is a quote.</blockquote>
            </body>
        </html>
        """
        extractor = DefaultContentExtractor()
        result = extractor.extract(html)

        assert "> This is a quote" in result.markdown

    def test_extract_table(self) -> None:
        """Test table conversion to markdown."""
        html = """
        <html>
            <body>
                <table>
                    <tr><th>Name</th><th>Value</th></tr>
                    <tr><td>A</td><td>1</td></tr>
                    <tr><td>B</td><td>2</td></tr>
                </table>
            </body>
        </html>
        """
        extractor = DefaultContentExtractor()
        result = extractor.extract(html)

        assert "| Name | Value |" in result.markdown
        assert "| --- | --- |" in result.markdown
        assert "| A | 1 |" in result.markdown

    def test_removes_unwanted_elements(self) -> None:
        """Test removal of script, style, nav, etc."""
        html = """
        <html>
            <body>
                <nav><a href="/">Home</a></nav>
                <script>alert('bad');</script>
                <style>.hidden{display:none;}</style>
                <article>
                    <p>Main content here.</p>
                </article>
                <footer>Copyright 2024</footer>
            </body>
        </html>
        """
        extractor = DefaultContentExtractor()
        result = extractor.extract(html)

        assert "Main content" in result.markdown
        assert "alert" not in result.markdown
        assert "display:none" not in result.markdown

    def test_uses_main_content_selector(self) -> None:
        """Test main content selector detection."""
        html = """
        <html>
            <body>
                <div class="sidebar">Sidebar stuff</div>
                <article>
                    <h1>Article Title</h1>
                    <p>Article content.</p>
                </article>
            </body>
        </html>
        """
        extractor = DefaultContentExtractor()
        result = extractor.extract(html)

        assert "Article Title" in result.markdown
        assert "Article content" in result.markdown

    def test_custom_selector(self) -> None:
        """Test extraction with custom selector."""
        html = """
        <html>
            <body>
                <div id="header">Header content</div>
                <div id="main">
                    <p>Main content only.</p>
                </div>
                <div id="footer">Footer content</div>
            </body>
        </html>
        """
        extractor = DefaultContentExtractor()
        result = extractor.extract(html, selector="#main")

        assert "Main content only" in result.markdown

    def test_extract_metadata_full(self) -> None:
        """Test full metadata extraction."""
        html = """
        <html lang="en">
            <head>
                <title>Test Page</title>
                <meta name="description" content="A test page">
                <meta name="author" content="Test Author">
                <meta property="og:title" content="OG Title">
                <meta property="og:description" content="OG Description">
                <meta property="og:image" content="https://example.com/image.jpg">
                <meta property="og:type" content="article">
                <meta property="article:published_time" content="2024-01-01">
                <meta name="keywords" content="test, page, example">
                <link rel="canonical" href="https://example.com/test">
            </head>
            <body></body>
        </html>
        """
        extractor = DefaultContentExtractor()
        metadata = extractor.extract_metadata(html)

        assert metadata.title == "OG Title"  # og:title takes precedence
        assert metadata.description == "OG Description"
        assert metadata.language == "en"
        assert metadata.author == "Test Author"
        assert metadata.og_image == "https://example.com/image.jpg"
        assert metadata.canonical_url == "https://example.com/test"
        assert metadata.content_type == "article"
        assert "test" in metadata.keywords

    def test_relative_link_resolution(self) -> None:
        """Test relative links are resolved to absolute."""
        html = """
        <html>
            <body>
                <a href="/page1">Page 1</a>
                <a href="page2">Page 2</a>
                <a href="../page3">Page 3</a>
            </body>
        </html>
        """
        extractor = DefaultContentExtractor()
        links = extractor.extract_links(html, base_url="https://example.com/dir/")

        assert links[0].url == "https://example.com/page1"
        assert links[1].url == "https://example.com/dir/page2"
        assert links[2].url == "https://example.com/page3"

    def test_link_deduplication(self) -> None:
        """Test duplicate links are removed."""
        html = """
        <html>
            <body>
                <a href="https://example.com">Link 1</a>
                <a href="https://example.com">Link 2</a>
                <a href="https://example.com">Link 3</a>
            </body>
        </html>
        """
        extractor = DefaultContentExtractor()
        links = extractor.extract_links(html)

        assert len(links) == 1

    def test_config_disable_headings(self) -> None:
        """Test disabling heading preservation."""
        html = "<html><body><h1>Title</h1></body></html>"
        config = ExtractionConfig(preserve_headings=False)
        extractor = DefaultContentExtractor(config)
        result = extractor.extract(html)

        assert "# Title" not in result.markdown
        assert "Title" in result.markdown

    def test_config_disable_links(self) -> None:
        """Test disabling link URL inclusion."""
        html = '<html><body><p>Click <a href="https://example.com">Link</a> here</p></body></html>'
        config = ExtractionConfig(include_link_urls=False)
        extractor = DefaultContentExtractor(config)
        result = extractor.extract(html)

        assert "https://example.com" not in result.markdown
        assert "Link" in result.plain_text


class TestGetDefaultExtractor:
    """Tests for get_default_extractor factory."""

    def test_returns_extractor(self) -> None:
        """Test factory returns an extractor."""
        extractor = get_default_extractor()
        assert extractor is not None

    def test_with_config(self) -> None:
        """Test factory accepts config."""
        config = ExtractionConfig(preserve_headings=False)
        extractor = get_default_extractor(config)
        assert extractor.config.preserve_headings is False

    def test_returns_correct_type(self) -> None:
        """Test factory returns correct type based on availability."""
        extractor = get_default_extractor()
        if SELECTOLAX_AVAILABLE:
            assert isinstance(extractor, DefaultContentExtractor)
        else:
            assert isinstance(extractor, FallbackContentExtractor)

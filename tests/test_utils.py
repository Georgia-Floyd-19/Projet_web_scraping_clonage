"""Basic tests for Web Cloner core utilities."""
from __future__ import annotations

from pathlib import Path

import pytest

from core.utils import (
    get_domain,
    is_internal_url,
    is_html_url,
    normalize_url,
    clean_url,
    url_depth,
    human_size,
)


class TestUtils:
    def test_get_domain(self):
        assert get_domain("https://example.com/page") == "example.com"
        assert get_domain("http://www.site.org/path") == "site.org"
        assert get_domain("https://sub.domain.com") == "sub.domain.com"

    def test_is_internal_url(self):
        domain = "example.com"
        assert is_internal_url("https://example.com/page", domain) is True
        assert is_internal_url("https://other.com/page", domain) is False
        assert is_internal_url("/relative/path", domain) is True

    def test_is_html_url(self):
        assert is_html_url("https://example.com") is True
        assert is_html_url("https://example.com/page.html") is True
        assert is_html_url("https://example.com/image.jpg") is False
        assert is_html_url("https://example.com/style.css") is False

    def test_normalize_url(self):
        base = "https://example.com"
        assert normalize_url("/page", base) == "https://example.com/page"
        assert normalize_url("https://other.com", base) == "https://other.com"
        assert normalize_url("https://example.com/page#anchor", base) == "https://example.com/page"

    def test_clean_url(self):
        assert clean_url("https://example.com/page?ref=1") == "https://example.com/page"
        assert clean_url("https://example.com/#fragment") == "https://example.com/"

    def test_url_depth(self):
        assert url_depth("https://example.com") == 0
        assert url_depth("https://example.com/page1") == 1
        assert url_depth("https://example.com/a/b/c") == 3

    def test_human_size(self):
        assert human_size(0) == "0 o"
        assert human_size(500) == "500 o"
        assert human_size(1024) == "1.00 Ko"
        assert human_size(1048576) == "1.00 Mo"
        assert human_size(1073741824) == "1.00 Go"


class TestBrowserConfig:
    def test_default_config(self):
        from core.browser import BrowserConfig
        config = BrowserConfig()
        assert config.headless is True
        assert config.channel == "chromium"
        assert config.viewport_width == 1920
        assert config.viewport_height == 1080
        assert config.locale == "fr-FR"
        assert config.timezone == "Europe/Paris"

    def test_custom_config(self):
        from core.browser import BrowserConfig
        config = BrowserConfig(
            headless=False,
            channel="msedge",
            user_agent="Custom Agent",
            viewport_width=800,
            viewport_height=600,
            stealth=True,
        )
        assert config.headless is False
        assert config.channel == "msedge"
        assert config.user_agent == "Custom Agent"
        assert config.viewport_width == 800
        assert config.viewport_height == 600
        assert config.stealth is True


class TestCrawlResult:
    def test_default_result(self):
        from core.crawler import CrawlResult
        result = CrawlResult()
        assert result.pages_cloned == 0
        assert result.resources_saved == 0
        assert result.api_calls_saved == 0
        assert result.success is False

    def test_success_result(self):
        from core.crawler import CrawlResult
        result = CrawlResult(pages_cloned=5, resources_saved=100, total_size_bytes=2048)
        assert result.pages_cloned == 5
        assert result.resources_saved == 100
        assert result.success is True
        assert result.total_size_bytes == 2048


class TestGroqSummarizer:
    def test_is_available_no_key(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        from utils.groq import GroqSummarizer
        summarizer = GroqSummarizer(api_key=None)
        assert summarizer.is_available() is False

    def test_is_available_with_key(self):
        from utils.groq import GroqSummarizer
        summarizer = GroqSummarizer(api_key="gsk_test_key")
        assert summarizer.is_available() is True

    def test_summarize_no_key(self):
        from utils.groq import GroqSummarizer
        summarizer = GroqSummarizer(api_key=None)
        assert summarizer.summarize("<html><body><p>Hello</p></body></html>") == ""


class TestStorage:
    def test_output_path_resolution(self, tmp_path):
        from core.storage import StorageManager
        output = tmp_path / "_clones" / "test"
        output.mkdir(parents=True)
        storage = StorageManager(str(output), "https://example.com")
        assert storage.output_folder == str(output)
        assert storage.start_url == "https://example.com"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

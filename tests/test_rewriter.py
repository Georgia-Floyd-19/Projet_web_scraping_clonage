"""Tests for the HTML/CSS rewriter module."""
from __future__ import annotations

import pytest

from core.rewriter import HTMLRewriter, CSSRewriter


class TestHTMLRewriter:
    def test_init(self):
        rewriter = HTMLRewriter(base_url="https://example.com")
        assert rewriter.base_url == "https://example.com"

    def test_rewrite_simple_html(self):
        rewriter = HTMLRewriter(base_url="https://example.com")
        html = "<html><head></head><body><p>Hello</p></body></html>"
        result = rewriter.rewrite(html)
        assert "<p>Hello</p>" in result


class TestCSSRewriter:
    def test_init(self):
        rewriter = CSSRewriter()
        assert rewriter is not None

    def test_rewrite_empty(self):
        rewriter = CSSRewriter()
        result = rewriter.rewrite("")
        assert result == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

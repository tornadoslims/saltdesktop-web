"""Tests for web fetch and web search tools."""

from unittest.mock import MagicMock, patch
import io

import pytest

from salt_agent.tools.web_fetch import WebFetchTool
from salt_agent.tools.web_search import WebSearchTool


class TestWebFetchTool:
    def test_definition(self):
        tool = WebFetchTool()
        defn = tool.definition()
        assert defn.name == "web_fetch"
        assert len(defn.params) == 2

    def test_fetch_strips_html(self):
        tool = WebFetchTool()
        html = b"<html><head><title>Test</title></head><body><p>Hello World</p></body></html>"

        mock_resp = MagicMock()
        mock_resp.read.return_value = html
        mock_resp.headers = MagicMock()
        mock_resp.headers.get.return_value = 'text/html; charset=utf-8'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = tool.execute(url="http://example.com")

        assert "Hello World" in result
        assert "<p>" not in result

    def test_fetch_strips_scripts(self):
        tool = WebFetchTool()
        html = b"<html><script>alert('xss')</script><body>Clean</body></html>"

        mock_resp = MagicMock()
        mock_resp.read.return_value = html
        mock_resp.headers = MagicMock()
        mock_resp.headers.get.return_value = 'text/html; charset=utf-8'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = tool.execute(url="http://example.com")

        assert "alert" not in result
        assert "Clean" in result

    def test_fetch_max_chars(self):
        tool = WebFetchTool()
        html = b"<body>" + b"x" * 50000 + b"</body>"

        mock_resp = MagicMock()
        mock_resp.read.return_value = html
        mock_resp.headers = MagicMock()
        mock_resp.headers.get.return_value = 'text/html; charset=utf-8'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = tool.execute(url="http://example.com", max_chars=100)

        # 100 chars + truncation suffix
        assert len(result) <= 150

    def test_fetch_error_handling(self):
        tool = WebFetchTool()

        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            result = tool.execute(url="http://invalid.example.com")

        assert "Error fetching" in result
        assert "Connection refused" in result

    def test_fetch_default_max_chars(self):
        tool = WebFetchTool()
        html = b"<body>" + b"A" * 60000 + b"</body>"

        mock_resp = MagicMock()
        mock_resp.read.return_value = html
        mock_resp.headers = MagicMock()
        mock_resp.headers.get.return_value = 'text/html; charset=utf-8'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = tool.execute(url="http://example.com")

        # Default is 50000 + truncation suffix
        assert len(result) <= 50000 + 50


class TestWebSearchTool:
    def test_definition(self):
        tool = WebSearchTool()
        defn = tool.definition()
        assert defn.name == "web_search"
        assert len(defn.params) == 2

    def test_search_parses_results(self):
        tool = WebSearchTool()
        html = (
            b'<div class="result__a" href="https://example.com">Example Title</a>'
            b'<span class="result__snippet">A snippet about the result</span>'
        )

        mock_resp = MagicMock()
        mock_resp.read.return_value = html
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = tool.execute(query="test query")

        assert "Example Title" in result
        assert "example.com" in result

    def test_search_no_results(self):
        tool = WebSearchTool()
        html = b"<html><body>No results here</body></html>"

        mock_resp = MagicMock()
        mock_resp.read.return_value = html
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = tool.execute(query="obscure query")

        assert "No results found" in result

    def test_search_error_handling(self):
        tool = WebSearchTool()

        with patch("urllib.request.urlopen", side_effect=Exception("Timeout")):
            result = tool.execute(query="test")

        assert "Search error" in result
        assert "Timeout" in result

    def test_search_decodes_uddg_redirect(self):
        tool = WebSearchTool()
        encoded_url = "https%3A%2F%2Freal.example.com%2Fpage"
        html = (
            f'<div class="result__a" href="https://duckduckgo.com/?uddg={encoded_url}&rut=abc">Real Title</a>'
            f'<span class="result__snippet">Real snippet</span>'
        ).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = html
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = tool.execute(query="test")

        assert "real.example.com" in result

    def test_search_max_results(self):
        tool = WebSearchTool()
        # Build HTML with multiple results
        results_html = ""
        for i in range(10):
            results_html += f'<div class="result__a" href="https://example{i}.com">Title {i}</a>'
            results_html += f'<span class="result__snippet">Snippet {i}</span>'

        mock_resp = MagicMock()
        mock_resp.read.return_value = results_html.encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = tool.execute(query="test", max_results=3)

        # Should only have 3 numbered results
        assert "4." not in result

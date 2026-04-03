"""Web fetch tool -- retrieve content from a URL."""

from __future__ import annotations

import logging
import re
import urllib.request

from salt_agent.tools.base import Tool, ToolDefinition, ToolParam

logger = logging.getLogger(__name__)


def _html_to_text(html: str) -> str:
    """Convert HTML to readable text, preserving structure."""

    # Remove scripts, styles, SVGs, and other non-content
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<svg[^>]*>.*?</svg>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<noscript[^>]*>.*?</noscript>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

    # Convert structural elements to text equivalents
    html = re.sub(r'<br\s*/?\s*>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</?p[^>]*>', '\n\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</?div[^>]*>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\n\n## \1\n', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<li[^>]*>(.*?)</li>', r'\n- \1', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'</?[ou]l[^>]*>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</?tr[^>]*>', '\n', html, flags=re.IGNORECASE)
    html = re.sub(r'</?td[^>]*>', ' | ', html, flags=re.IGNORECASE)
    html = re.sub(r'</?th[^>]*>', ' | ', html, flags=re.IGNORECASE)

    # Extract link text with URL
    html = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'\2 (\1)', html, flags=re.DOTALL | re.IGNORECASE)

    # Bold/italic
    html = re.sub(r'</?(?:b|strong)[^>]*>', '**', html, flags=re.IGNORECASE)
    html = re.sub(r'</?(?:i|em)[^>]*>', '*', html, flags=re.IGNORECASE)

    # Remove remaining tags
    html = re.sub(r'<[^>]+>', ' ', html)

    # Decode HTML entities
    html = html.replace('&amp;', '&')
    html = html.replace('&lt;', '<')
    html = html.replace('&gt;', '>')
    html = html.replace('&quot;', '"')
    html = html.replace('&#39;', "'")
    html = html.replace('&nbsp;', ' ')
    html = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), html)
    html = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), html)

    # Clean up whitespace
    text = re.sub(r'[ \t]+', ' ', html)  # collapse horizontal whitespace
    text = re.sub(r'\n[ \t]+', '\n', text)  # strip leading whitespace on lines
    text = re.sub(r'\n{3,}', '\n\n', text)  # max 2 consecutive newlines
    text = text.strip()

    return text


class WebFetchTool(Tool):
    """Fetch content from a URL and return as readable text."""

    EXTRACTORS = ("trafilatura", "readability", "regex")

    def __init__(self, extractor: str = "trafilatura"):
        """
        Args:
            extractor: Content extraction method.
                "trafilatura" (best quality), "readability", or "regex" (fallback).
        """
        if extractor not in self.EXTRACTORS:
            raise ValueError(
                f"Unknown extractor {extractor!r}. Choose from: {', '.join(self.EXTRACTORS)}"
            )
        self.extractor = extractor

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="web_fetch",
            description=(
                "Fetch content from a URL. Returns the page content as text "
                "(HTML converted to readable text)."
            ),
            params=[
                ToolParam("url", "string", "The URL to fetch"),
                ToolParam(
                    "max_chars",
                    "integer",
                    "Maximum characters to return (default 50000)",
                    required=False,
                ),
            ],
        )

    def execute(self, **kwargs) -> str:
        url: str = kwargs["url"]
        max_chars: int = kwargs.get("max_chars", 50000) or 50000

        try:
            html = self._fetch_html(url)
            text = self._extract(html, url)

            if len(text) > max_chars:
                text = text[:max_chars] + "\n\n[...truncated]"

            return text
        except Exception as e:
            return f"Error fetching {url}: {e}"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_html(url: str) -> str:
        """Fetch raw HTML from *url*."""
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
            content_type = resp.headers.get("Content-Type", "")
            encoding = "utf-8"
            if "charset=" in content_type:
                encoding = content_type.split("charset=")[-1].split(";")[0].strip()
            try:
                return raw.decode(encoding, errors="replace")
            except (UnicodeDecodeError, LookupError):
                return raw.decode("utf-8", errors="replace")

    def _extract(self, html: str, url: str) -> str:
        """Extract readable text from HTML using the configured extractor."""
        if self.extractor == "trafilatura":
            return self._extract_trafilatura(html, url)
        elif self.extractor == "readability":
            return self._extract_readability(html, url)
        return self._extract_regex(html)

    @staticmethod
    def _extract_trafilatura(html: str, url: str) -> str:
        """Best quality extraction -- article text, tables, lists."""
        try:
            import trafilatura  # noqa: F811

            result = trafilatura.extract(
                html,
                url=url,
                include_tables=True,
                include_links=True,
                include_comments=False,
                output_format="txt",
                favor_recall=True,
            )
            if result and len(result) > 100:
                return result
        except ImportError:
            logger.debug("trafilatura not installed, falling back to regex")
        except Exception as exc:
            logger.debug("trafilatura extraction failed: %s", exc)
        # Fall back to regex
        return _html_to_text(html)

    @staticmethod
    def _extract_readability(html: str, url: str) -> str:
        """Good quality extraction -- strips boilerplate, keeps article."""
        try:
            from readability import Document  # noqa: F811

            doc = Document(html, url=url)
            summary_html = doc.summary()
            title = doc.title()
            text = _html_to_text(summary_html)
            if title:
                text = f"# {title}\n\n{text}"
            if len(text) > 100:
                return text
        except ImportError:
            logger.debug("readability-lxml not installed, falling back to regex")
        except Exception as exc:
            logger.debug("readability extraction failed: %s", exc)
        return _html_to_text(html)

    @staticmethod
    def _extract_regex(html: str) -> str:
        """Fallback -- regex-based HTML stripping."""
        return _html_to_text(html)

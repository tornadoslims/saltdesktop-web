# Web Tools

## web_fetch

Retrieve and extract content from a URL. Converts HTML to readable text.

### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `url` | string | yes | The URL to fetch |
| `extractor` | string | no | HTML extraction method |

### HTML Extraction

Three extraction backends:

| Extractor | Description |
|-----------|-------------|
| `trafilatura` | ML-based article extraction (default, best quality) |
| `readability` | Mozilla Readability port |
| `regex` | Built-in regex-based extraction (no dependencies) |

The built-in regex extractor:

- Removes scripts, styles, SVGs, nav, footer, header
- Converts headings, lists, tables to text equivalents
- Preserves link text with URLs
- Decodes HTML entities
- Collapses whitespace

### Returns

Extracted text content from the page, truncated to fit the context window.

### Configuration

```python
agent = create_agent(
    include_web_tools=True,   # default
    web_extractor="trafilatura",  # or "readability", "regex"
)
```

To disable web tools entirely:

```python
agent = create_agent(include_web_tools=False)
```

---

## web_search

Search the web using DuckDuckGo (no API key required).

### Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `query` | string | yes | The search query |
| `max_results` | integer | no | Maximum results to return (default 5) |

### Returns

A formatted list of results with titles, URLs, and snippets.

### Notes

- Automatically appends the current year to queries to bias toward recent results
- Uses DuckDuckGo's HTML search endpoint (no API key needed)
- User-Agent is set to `SaltAgent/0.1`
- 10-second timeout on the HTTP request

### Example Result

```
1. Title of First Result
   https://example.com/article
   A brief snippet from the search result...

2. Title of Second Result
   https://example.com/another
   Another snippet...
```

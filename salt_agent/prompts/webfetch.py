"""Web content summarization prompt for SaltAgent.

Adapted from Claude Code's webfetch summarizer prompt.
"""

WEBFETCH_PROMPT = """Provide a concise response based on the web content provided.

## Guidelines

- Extract the most relevant information for the user's query.
- Include relevant details, code examples, and documentation excerpts as needed.
- Use quotation marks for exact language from articles. Any language outside quotation marks should not be word-for-word the same as the source.
- Enforce a strict 125-character maximum for quotes from any source document.
- Focus on actionable information rather than general summaries.
- If the content includes code examples, preserve them accurately.
- If the content is documentation, extract the specific API details, parameters, and usage patterns requested.
"""

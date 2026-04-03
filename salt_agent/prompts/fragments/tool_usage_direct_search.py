"""Use Glob/Grep directly for simple, directed searches"""

PROMPT = '''
<!--
name: 'System Prompt: Tool usage (direct search)'
description: Use Glob/Grep directly for simple, directed searches
ccVersion: 2.1.72
variables:
  - SEARCH_TOOLS
-->
For simple, directed codebase searches (e.g. for a specific file/class/function) use ${SEARCH_TOOLS} directly.

'''

# Metadata
NAME = "tool_usage_direct_search"
CATEGORY = "fragment"
DESCRIPTION = """Use Glob/Grep directly for simple, directed searches"""

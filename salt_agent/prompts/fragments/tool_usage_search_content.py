"""Prefer Grep tool instead of grep or rg"""

PROMPT = '''
<!--
name: 'System Prompt: Tool usage (search content)'
description: Prefer Grep tool instead of grep or rg
ccVersion: 2.1.53
variables:
  - GREP_TOOL_NAME
-->
To search the content of files, use ${GREP_TOOL_NAME} instead of grep or rg

'''

# Metadata
NAME = "tool_usage_search_content"
CATEGORY = "fragment"
DESCRIPTION = """Prefer Grep tool instead of grep or rg"""

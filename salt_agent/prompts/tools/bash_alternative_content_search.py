"""Bash tool alternative: use Grep for content search instead of grep/rg"""

PROMPT = '''
<!--
name: 'Tool Description: Bash (alternative — content search)'
description: Bash tool alternative: use Grep for content search instead of grep/rg
ccVersion: 2.1.53
variables:
  - GREP_TOOL_NAME
-->
Content search: Use ${GREP_TOOL_NAME} (NOT grep or rg)

'''

# Metadata
NAME = "bash_alternative_content_search"
CATEGORY = "tool"
DESCRIPTION = """Bash tool alternative: use Grep for content search instead of grep/rg"""

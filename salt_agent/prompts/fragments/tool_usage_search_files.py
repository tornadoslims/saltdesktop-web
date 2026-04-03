"""Prefer Glob tool instead of find or ls"""

PROMPT = '''
<!--
name: 'System Prompt: Tool usage (search files)'
description: Prefer Glob tool instead of find or ls
ccVersion: 2.1.53
variables:
  - GLOB_TOOL_NAME
-->
To search for files use ${GLOB_TOOL_NAME} instead of find or ls

'''

# Metadata
NAME = "tool_usage_search_files"
CATEGORY = "fragment"
DESCRIPTION = """Prefer Glob tool instead of find or ls"""

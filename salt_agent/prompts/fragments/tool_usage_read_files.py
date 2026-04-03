"""Prefer Read tool instead of cat/head/tail/sed"""

PROMPT = '''
<!--
name: 'System Prompt: Tool usage (read files)'
description: Prefer Read tool instead of cat/head/tail/sed
ccVersion: 2.1.53
variables:
  - READ_TOOL_NAME
-->
To read files use ${READ_TOOL_NAME} instead of cat, head, tail, or sed

'''

# Metadata
NAME = "tool_usage_read_files"
CATEGORY = "fragment"
DESCRIPTION = """Prefer Read tool instead of cat/head/tail/sed"""

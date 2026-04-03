"""Bash tool alternative: use Read for file reading instead of cat/head/tail"""

PROMPT = '''
<!--
name: 'Tool Description: Bash (alternative — read files)'
description: Bash tool alternative: use Read for file reading instead of cat/head/tail
ccVersion: 2.1.53
variables:
  - READ_TOOL_NAME
-->
Read files: Use ${READ_TOOL_NAME} (NOT cat/head/tail)

'''

# Metadata
NAME = "bash_alternative_read_files"
CATEGORY = "tool"
DESCRIPTION = """Bash tool alternative: use Read for file reading instead of cat/head/tail"""

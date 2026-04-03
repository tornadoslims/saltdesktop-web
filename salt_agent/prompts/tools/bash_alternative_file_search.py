"""Bash tool alternative: use Glob for file search instead of find/ls"""

PROMPT = '''
<!--
name: 'Tool Description: Bash (alternative — file search)'
description: Bash tool alternative: use Glob for file search instead of find/ls
ccVersion: 2.1.53
variables:
  - GLOB_TOOL_NAME
-->
File search: Use ${GLOB_TOOL_NAME} (NOT find or ls)

'''

# Metadata
NAME = "bash_alternative_file_search"
CATEGORY = "tool"
DESCRIPTION = """Bash tool alternative: use Glob for file search instead of find/ls"""

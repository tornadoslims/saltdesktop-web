"""Bash tool instruction: use semicolons when sequential order matters but failure does not"""

PROMPT = '''
<!--
name: 'Tool Description: Bash (semicolon usage)'
description: Bash tool instruction: use semicolons when sequential order matters but failure does not
ccVersion: 2.1.53
-->
Use ';' only when you need to run commands sequentially but don't care if earlier commands fail.

'''

# Metadata
NAME = "bash_semicolon_usage"
CATEGORY = "tool"
DESCRIPTION = """Bash tool instruction: use semicolons when sequential order matters but failure does not"""

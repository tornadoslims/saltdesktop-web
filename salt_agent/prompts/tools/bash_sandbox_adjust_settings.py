"""Work with user to adjust sandbox settings on failure"""

PROMPT = '''
<!--
name: 'Tool Description: Bash (sandbox — adjust settings)'
description: Work with user to adjust sandbox settings on failure
ccVersion: 2.1.53
-->
If a command fails due to sandbox restrictions, work with the user to adjust sandbox settings instead.

'''

# Metadata
NAME = "bash_sandbox_adjust_settings"
CATEGORY = "tool"
DESCRIPTION = """Work with user to adjust sandbox settings on failure"""

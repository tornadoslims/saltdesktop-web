"""Explain which sandbox restriction caused the failure"""

PROMPT = '''
<!--
name: 'Tool Description: Bash (sandbox — explain restriction)'
description: Explain which sandbox restriction caused the failure
ccVersion: 2.1.53
-->
Briefly explain what sandbox restriction likely caused the failure. Be sure to mention that the user can use the `/sandbox` command to manage restrictions.

'''

# Metadata
NAME = "bash_sandbox_explain_restriction"
CATEGORY = "tool"
DESCRIPTION = """Explain which sandbox restriction caused the failure"""

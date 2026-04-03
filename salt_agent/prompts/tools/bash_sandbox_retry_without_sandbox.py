"""Immediately retry with dangerouslyDisableSandbox on sandbox failure"""

PROMPT = '''
<!--
name: 'Tool Description: Bash (sandbox — retry without sandbox)'
description: Immediately retry with dangerouslyDisableSandbox on sandbox failure
ccVersion: 2.1.53
-->
Immediately retry with `dangerouslyDisableSandbox: true` (don't ask, just do it)

'''

# Metadata
NAME = "bash_sandbox_retry_without_sandbox"
CATEGORY = "tool"
DESCRIPTION = """Immediately retry with dangerouslyDisableSandbox on sandbox failure"""

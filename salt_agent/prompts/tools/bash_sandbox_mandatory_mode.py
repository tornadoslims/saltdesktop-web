"""Policy: all commands must run in sandbox mode"""

PROMPT = '''
<!--
name: 'Tool Description: Bash (sandbox — mandatory mode)'
description: Policy: all commands must run in sandbox mode
ccVersion: 2.1.53
-->
All commands MUST run in sandbox mode - the `dangerouslyDisableSandbox` parameter is disabled by policy.

'''

# Metadata
NAME = "bash_sandbox_mandatory_mode"
CATEGORY = "tool"
DESCRIPTION = """Policy: all commands must run in sandbox mode"""

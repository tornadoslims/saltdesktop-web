"""Default to sandbox; only bypass when user asks or evidence of sandbox restriction"""

PROMPT = '''
<!--
name: 'Tool Description: Bash (sandbox — default to sandbox)'
description: Default to sandbox; only bypass when user asks or evidence of sandbox restriction
ccVersion: 2.1.53
-->
You should always default to running commands within the sandbox. Do NOT attempt to set `dangerouslyDisableSandbox: true` unless:

'''

# Metadata
NAME = "bash_sandbox_default_to_sandbox"
CATEGORY = "tool"
DESCRIPTION = """Default to sandbox; only bypass when user asks or evidence of sandbox restriction"""

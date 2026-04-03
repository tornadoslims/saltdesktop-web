"""Do not suggest adding sensitive paths to sandbox allowlist"""

PROMPT = '''
<!--
name: 'Tool Description: Bash (sandbox — no sensitive paths)'
description: Do not suggest adding sensitive paths to sandbox allowlist
ccVersion: 2.1.53
-->
Do not suggest adding sensitive paths like ~/.bashrc, ~/.zshrc, ~/.ssh/*, or credential files to the sandbox allowlist.

'''

# Metadata
NAME = "bash_sandbox_no_sensitive_paths"
CATEGORY = "tool"
DESCRIPTION = """Do not suggest adding sensitive paths to sandbox allowlist"""

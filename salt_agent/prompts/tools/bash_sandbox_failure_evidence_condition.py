"""Condition: command failed with evidence of sandbox restrictions"""

PROMPT = '''
<!--
name: 'Tool Description: Bash (sandbox — failure evidence condition)'
description: Condition: command failed with evidence of sandbox restrictions
ccVersion: 2.1.53
-->
A specific command just failed and you see evidence of sandbox restrictions causing the failure. Note that commands can fail for many reasons unrelated to the sandbox (missing files, wrong arguments, network issues, etc.).

'''

# Metadata
NAME = "bash_sandbox_failure_evidence_condition"
CATEGORY = "tool"
DESCRIPTION = """Condition: command failed with evidence of sandbox restrictions"""

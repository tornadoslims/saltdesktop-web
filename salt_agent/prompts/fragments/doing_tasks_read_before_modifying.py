"""Read and understand existing code before suggesting modifications"""

PROMPT = '''
<!--
name: 'System Prompt: Doing tasks (read before modifying)'
description: Read and understand existing code before suggesting modifications
ccVersion: 2.1.53
-->
In general, do not propose changes to code you haven't read. If a user asks about or wants you to modify a file, read it first. Understand existing code before suggesting modifications.

'''

# Metadata
NAME = "doing_tasks_read_before_modifying"
CATEGORY = "fragment"
DESCRIPTION = """Read and understand existing code before suggesting modifications"""

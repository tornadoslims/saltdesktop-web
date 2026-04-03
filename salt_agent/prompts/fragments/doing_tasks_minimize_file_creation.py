"""Prefer editing existing files over creating new ones"""

PROMPT = '''
<!--
name: 'System Prompt: Doing tasks (minimize file creation)'
description: Prefer editing existing files over creating new ones
ccVersion: 2.1.53
-->
Do not create files unless they're absolutely necessary for achieving your goal. Generally prefer editing an existing file to creating a new one, as this prevents file bloat and builds on existing work more effectively.

'''

# Metadata
NAME = "doing_tasks_minimize_file_creation"
CATEGORY = "fragment"
DESCRIPTION = """Prefer editing existing files over creating new ones"""

"""Contents of a nested memory file"""

PROMPT = '''
<!--
name: 'System Reminder: Nested memory contents'
description: Contents of a nested memory file
ccVersion: 2.1.18
variables:
  - ATTACHMENT_OBJECT
-->
Contents of ${ATTACHMENT_OBJECT.content.path}:

${ATTACHMENT_OBJECT.content.content}

'''

# Metadata
NAME = "nested_memory_contents"
CATEGORY = "fragment"
DESCRIPTION = """Contents of a nested memory file"""

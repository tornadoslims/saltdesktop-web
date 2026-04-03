"""Contents of a memory file by path"""

PROMPT = '''
<!--
name: 'System Reminder: Memory file contents'
description: Contents of a memory file by path
ccVersion: 2.1.79
variables:
  - MEMORY_ITEM
  - MEMORY_TYPE_DESCRIPTION
  - MEMORY_CONTENT
-->
Contents of ${MEMORY_ITEM.path}${MEMORY_TYPE_DESCRIPTION}:

${MEMORY_CONTENT}

'''

# Metadata
NAME = "memory_file_contents"
CATEGORY = "fragment"
DESCRIPTION = """Contents of a memory file by path"""

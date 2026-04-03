"""Tool for writing files to the local filesystem"""

PROMPT = '''
<!--
name: 'Tool Description: Write'
description: Tool for writing files to the local filesystem
ccVersion: 2.1.91
variables:
  - GET_NEW_FILE_NOTE_FN
  - WRITE_FILE_NOTE
  - PREFER_EDIT_NOTE
-->
Writes a file to the local filesystem.

Usage:
- This tool will overwrite the existing file if there is one at the provided path.${GET_NEW_FILE_NOTE_FN()}${WRITE_FILE_NOTE}
- Prefer the Edit tool for modifying existing files — it only sends the diff. ${PREFER_EDIT_NOTE}
- NEVER create documentation files (*.md) or README files unless explicitly requested by the User.
- Only use emojis if the user explicitly requests it. Avoid writing emojis to files unless asked.

'''

# Metadata
NAME = "write"
CATEGORY = "tool"
DESCRIPTION = """Tool for writing files to the local filesystem"""

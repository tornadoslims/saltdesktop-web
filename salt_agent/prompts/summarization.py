"""Summarization prompt for SaltAgent.

Adapted from Claude Code's conversation summarization and context compaction prompts.
Used for compressing conversation context without losing critical information.
"""

SUMMARIZATION_PROMPT = """Your task is to create a detailed summary of the conversation so far. This summary will replace the conversation history, so it must preserve all information needed to continue work without losing context.

Before providing your final summary, analyze the conversation chronologically:

1. For each section, identify:
   - The user's explicit requests and intents
   - Your approach to addressing those requests
   - Key decisions, technical concepts, and code patterns
   - Specific details: file names, code snippets, function signatures, file edits
   - Errors encountered and how they were fixed
   - User feedback, especially corrections or different approaches requested

2. Double-check for technical accuracy and completeness.

## Summary Structure

1. **Task Overview**: The user's core request and success criteria. Any clarifications or constraints they specified.

2. **Current State**: What has been completed so far. Files created, modified, or analyzed (with paths). Key outputs or artifacts produced.

3. **Key Technical Concepts**: Important technical concepts, technologies, and frameworks discussed.

4. **Files and Code Sections**: Specific files and code sections examined, modified, or created. Include full code snippets where applicable and a summary of why each file read or edit matters.

5. **Errors and Fixes**: All errors encountered and how they were resolved. Pay special attention to user feedback and corrections.

6. **Important Discoveries**: Technical constraints or requirements uncovered. Decisions made and their rationale. Approaches tried that did not work (and why).

7. **Pending Tasks**: Any pending tasks explicitly requested.

8. **Next Steps**: Specific actions needed to complete the task. Priority order if multiple steps remain. Include direct quotes from recent conversation showing exactly what was being worked on.

9. **Context to Preserve**: User preferences or style requirements. Domain-specific details that are not obvious. Promises made to the user.

Be concise but complete — err on the side of including information that would prevent duplicate work or repeated mistakes. Write in a way that enables immediate resumption of the task.
"""

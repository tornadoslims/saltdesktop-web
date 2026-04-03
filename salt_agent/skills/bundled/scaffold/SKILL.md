---
name: scaffold
description: Generate project structure with boilerplate files
user-invocable: true
---
# Scaffold Project Structure

Generate a complete project structure with boilerplate:

1. Analyze the user's requirements to determine what components are needed
2. Create the directory layout:
   - Source files organized by module/feature
   - Test files mirroring source structure
   - Configuration files (linting, formatting, CI)
   - Documentation stubs
3. Generate boilerplate files:
   - Entry points with argument parsing
   - Base classes and interfaces
   - Test fixtures and conftest
   - CI/CD pipeline config (.github/workflows/ or similar)
4. Add type hints and docstrings to all generated code
5. Ensure all imports are valid and the project can be imported
6. Run any available linters to verify code quality
7. Summarize what was created and suggest next steps

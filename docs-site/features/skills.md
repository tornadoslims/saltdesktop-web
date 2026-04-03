# Skills

Skills are markdown-based prompt injection commands. When invoked, a skill's `SKILL.md` content is injected into the agent's context, teaching it how to perform a specific task.

## Skill Structure

A skill is a directory containing a `SKILL.md` file:

```
my-skill/
  SKILL.md          # Required: skill content
  scripts/          # Optional: helper scripts
  references/       # Optional: reference data
```

### SKILL.md Format

```markdown
---
name: deploy
description: Deploy the application to production
user-invocable: true
---
Follow these steps to deploy:
1. Run tests: `pytest tests/ -v`
2. Build: `docker build -t myapp .`
3. Push: `docker push myapp:latest`
4. Deploy: `kubectl rollout restart deployment/myapp`
```

The YAML frontmatter is optional. The body (after frontmatter) is what gets injected into context.

## Skill Discovery

Skills are loaded from multiple directories in priority order (later overrides earlier):

1. `salt_agent/skills/bundled/` -- bundled skills (lowest priority)
2. `~/.s_code/skills/` -- user-installed skills
3. `./skills/` or `./.skills/` -- workspace skills (highest priority)
4. Custom directories via `skill_dirs` config

## Requirements

Skills can declare requirements in frontmatter that must be met for activation:

```yaml
---
name: docker-deploy
description: Deploy with Docker
metadata:
  requires:
    bins: [docker, kubectl]
    env: [DOCKER_REGISTRY, KUBE_CONFIG]
  os: [linux, darwin]
---
```

| Requirement | Check |
|-------------|-------|
| `bins` | Binaries must be available via `shutil.which()` |
| `env` | Environment variables must be set |
| `os` | `sys.platform` must match one of the values |

Skills with unmet requirements are silently skipped.

## Invoking Skills

### Via the CLI

```
salt> /deploy
salt> /commit
salt> /review
```

### Via the Skill Tool

The LLM can invoke skills programmatically:

```
[tool_use: skill(name="deploy")]
```

### Via Python

```python
content = agent.skill_manager.invoke("deploy")
# Returns the SKILL.md body text, or an error message
```

## Listing Skills

```python
all_skills = agent.skill_manager.list_skills()
user_skills = agent.skill_manager.list_user_invocable()

for skill in user_skills:
    print(f"/{skill.name} -- {skill.description}")
```

CLI:

```
salt> /skills
```

## Skill Data

```python
@dataclass
class Skill:
    name: str                    # Skill name (from frontmatter or directory name)
    description: str             # Brief description
    content: str                 # SKILL.md body (after frontmatter)
    path: Path                   # Directory path
    user_invocable: bool         # Can be invoked via /command
    scripts_dir: Path | None     # scripts/ subdirectory
    references_dir: Path | None  # references/ subdirectory
    metadata: dict | None        # Parsed frontmatter
```

## Creating Custom Skills

1. Create a directory in `~/.s_code/skills/`:
   ```bash
   mkdir -p ~/.s_code/skills/my-skill
   ```

2. Write the SKILL.md:
   ```bash
   cat > ~/.s_code/skills/my-skill/SKILL.md << 'EOF'
   ---
   name: my-skill
   description: Do something useful
   ---
   When the user invokes this skill, follow these steps:
   1. First, check the current state
   2. Then, apply the changes
   3. Finally, verify everything works
   EOF
   ```

3. The skill is immediately available (discovered on next session start or skill manager refresh).

## Workspace Skills

For project-specific skills, create a `skills/` directory in your project:

```
my-project/
  skills/
    format/
      SKILL.md   # Project-specific formatting skill
    test/
      SKILL.md   # Project-specific test runner skill
  src/
  tests/
```

Workspace skills override user and bundled skills with the same name.

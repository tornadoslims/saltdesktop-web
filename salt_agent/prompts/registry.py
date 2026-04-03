"""Registry of all available prompts, searchable by category and name."""

from pathlib import Path
import importlib
import pkgutil


_PACKAGE_MAP = {
    "fragment": "fragments",
    "fragments": "fragments",
    "agent": "agents",
    "agents": "agents",
    "skill": "skills",
    "skills": "skills",
    "tool": "tools",
    "tools": "tools",
    "data": "data",
}

_ALL_PACKAGES = ["fragments", "agents", "skills", "tools", "data"]


def _load_module_metadata(package_name: str) -> list[dict]:
    """Load metadata from all modules in a subpackage."""
    results = []
    package = importlib.import_module(f"salt_agent.prompts.{package_name}")
    pkg_path = Path(package.__file__).parent

    for _, module_name, _ in pkgutil.iter_modules([str(pkg_path)]):
        mod = importlib.import_module(f"salt_agent.prompts.{package_name}.{module_name}")
        if hasattr(mod, 'PROMPT'):
            results.append({
                "name": getattr(mod, 'NAME', module_name),
                "category": getattr(mod, 'CATEGORY', package_name),
                "description": getattr(mod, 'DESCRIPTION', ''),
                "package": package_name,
                "module": module_name,
            })

    return results


def list_prompts(category: str = None) -> list[dict]:
    """
    List all available prompts with metadata.

    Args:
        category: Filter by category ('fragment', 'agent', 'skill', 'tool', 'data').
                  None returns all prompts.

    Returns:
        List of dicts with keys: name, category, description, package, module
    """
    if category:
        pkg = _PACKAGE_MAP.get(category)
        if pkg:
            return _load_module_metadata(pkg)
        return []

    results = []
    for pkg in _ALL_PACKAGES:
        results.extend(_load_module_metadata(pkg))
    return results


def get_prompt(category: str, name: str) -> str:
    """
    Get a specific prompt by category and name.

    Args:
        category: Category ('fragment', 'agent', 'skill', 'tool', 'data')
        name: Module name (e.g., 'doing_tasks_security')

    Returns:
        The prompt text.

    Raises:
        KeyError: If prompt not found.
    """
    pkg = _PACKAGE_MAP.get(category)
    if not pkg:
        raise KeyError(f"Unknown category: {category}")

    try:
        mod = importlib.import_module(f"salt_agent.prompts.{pkg}.{name}")
    except ModuleNotFoundError:
        raise KeyError(f"Prompt not found: {category}/{name}")

    if hasattr(mod, 'PROMPT'):
        return mod.PROMPT
    raise KeyError(f"Module {category}/{name} has no PROMPT constant")


def search_prompts(query: str) -> list[dict]:
    """
    Search prompts by keyword in name or description.

    Args:
        query: Search string (case-insensitive)

    Returns:
        List of matching prompt metadata dicts.
    """
    query_lower = query.lower()
    results = []
    for entry in list_prompts():
        if (query_lower in entry["name"].lower() or
                query_lower in entry["description"].lower()):
            results.append(entry)
    return results

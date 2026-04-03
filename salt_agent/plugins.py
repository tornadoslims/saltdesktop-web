"""Plugin system -- discover and load plugins from directories.

Plugins can provide additional tools, hooks, and prompt fragments.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

from salt_agent.tools.base import Tool


class SaltPlugin(ABC):
    """Base class for SaltAgent plugins.

    Subclass this to create a plugin. Override tools(), hooks(), and/or prompts()
    to extend the agent.
    """

    @abstractmethod
    def name(self) -> str:
        """Return the plugin name."""
        ...

    def tools(self) -> list[Tool]:
        """Return tools to register with the agent."""
        return []

    def hooks(self) -> list[tuple[str, Callable]]:
        """Return hooks as (event_name, callback) tuples."""
        return []

    def prompts(self) -> list[str]:
        """Return additional prompt fragments to inject into the system prompt."""
        return []


class PluginManager:
    """Discover and load plugins from configured directories."""

    def __init__(self, plugin_dirs: list[str] | None = None) -> None:
        self.plugin_dirs = plugin_dirs or []
        self._plugins: list[SaltPlugin] = []
        self._errors: list[str] = []

    @property
    def plugins(self) -> list[SaltPlugin]:
        return list(self._plugins)

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    def discover(self) -> list[SaltPlugin]:
        """Discover and load plugins from configured directories.

        Returns the list of successfully loaded plugins.
        """
        self._plugins.clear()
        self._errors.clear()

        for dir_path_str in self.plugin_dirs:
            path = Path(dir_path_str).expanduser().resolve()
            if not path.exists():
                continue
            if not path.is_dir():
                self._errors.append(f"Plugin path is not a directory: {path}")
                continue

            for plugin_file in sorted(path.glob("*.py")):
                if plugin_file.name.startswith("_"):
                    continue
                try:
                    plugins = self._load_plugin_file(plugin_file)
                    self._plugins.extend(plugins)
                except Exception as e:
                    self._errors.append(f"Error loading {plugin_file}: {e}")

        return list(self._plugins)

    def _load_plugin_file(self, plugin_file: Path) -> list[SaltPlugin]:
        """Load a single plugin file and return SaltPlugin instances found."""
        module_name = f"salt_plugin_{plugin_file.stem}"

        spec = importlib.util.spec_from_file_location(module_name, str(plugin_file))
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module spec for {plugin_file}")

        module = importlib.util.module_from_spec(spec)
        # Don't pollute sys.modules permanently
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise

        # Find all SaltPlugin subclasses in the module
        found: list[SaltPlugin] = []
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, SaltPlugin)
                and obj is not SaltPlugin
                and obj.__module__ == module_name
            ):
                try:
                    instance = obj()
                    found.append(instance)
                except Exception as e:
                    self._errors.append(f"Error instantiating {_name} from {plugin_file}: {e}")

        return found

    def register(self, plugin: SaltPlugin) -> None:
        """Manually register a plugin instance."""
        self._plugins.append(plugin)

    def get_tools(self) -> list[Tool]:
        """Get all tools from all loaded plugins."""
        tools: list[Tool] = []
        for plugin in self._plugins:
            try:
                tools.extend(plugin.tools())
            except Exception:
                pass  # Don't let a bad plugin crash the agent
        return tools

    def get_hooks(self) -> list[tuple[str, Callable]]:
        """Get all hooks from all loaded plugins."""
        hooks: list[tuple[str, Callable]] = []
        for plugin in self._plugins:
            try:
                hooks.extend(plugin.hooks())
            except Exception:
                pass
        return hooks

    def get_prompts(self) -> list[str]:
        """Get all prompt fragments from all loaded plugins."""
        prompts: list[str] = []
        for plugin in self._plugins:
            try:
                prompts.extend(plugin.prompts())
            except Exception:
                pass
        return prompts

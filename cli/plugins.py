"""
Plugin loading via Python's importlib.metadata entry points.

Plugins are external packages that register a callable under a known
entry-point group. The callable receives the CLI instance and may register
commands, hooks, middleware, or modify configuration.

Example plugin package pyproject.toml:

    [project.entry-points."mycli.plugins"]
    audit = "myaudit.plugin:register"

Where ``myaudit.plugin.register(cli: CLI) -> None``.
"""

from __future__ import annotations

import importlib.metadata
import logging
from typing import Any, Callable

PluginCallable = Callable[[Any], None]


class PluginError(Exception):
    """Plugin loading or invocation failed."""


def discover_plugins(group: str) -> list[importlib.metadata.EntryPoint]:
    """Return all entry points registered under the given group."""
    try:
        eps = importlib.metadata.entry_points()
    except Exception as exc:
        raise PluginError(f"Failed to query entry points: {exc}") from exc

    if hasattr(eps, "select"):
        return list(eps.select(group=group))
    return [ep for ep in eps.get(group, [])]


def load_plugins(
    cli: Any,
    group: str,
    fail_fast: bool = False,
    logger: logging.Logger | None = None,
) -> dict[str, bool]:
    """
    Discover and invoke all plugins registered under ``group``.

    Returns a mapping of plugin name to success boolean. With fail_fast=True,
    re-raises the first failure as PluginError after capturing the partial map.
    """
    log = logger or logging.getLogger("cliframework.plugins")
    results: dict[str, bool] = {}

    try:
        entry_points = discover_plugins(group)
    except PluginError as exc:
        log.error(str(exc))
        if fail_fast:
            raise
        return results

    for ep in entry_points:
        name = ep.name
        try:
            register_fn: PluginCallable = ep.load()
        except Exception as exc:
            log.error(f"Failed to load plugin '{name}': {exc}", exc_info=True)
            results[name] = False
            if fail_fast:
                raise PluginError(
                    f"Failed to load plugin '{name}': {exc}"
                ) from exc
            continue

        if not callable(register_fn):
            log.error(
                f"Plugin '{name}' entry point did not resolve to a callable"
            )
            results[name] = False
            if fail_fast:
                raise PluginError(
                    f"Plugin '{name}' is not callable"
                )
            continue

        try:
            register_fn(cli)
            results[name] = True
            log.info(f"Loaded plugin: {name}")
        except Exception as exc:
            log.error(
                f"Plugin '{name}' raised during registration: {exc}",
                exc_info=True,
            )
            results[name] = False
            if fail_fast:
                raise PluginError(
                    f"Plugin '{name}' registration failed: {exc}"
                ) from exc

    return results


__all__ = [
    "PluginError",
    "PluginCallable",
    "discover_plugins",
    "load_plugins",
]

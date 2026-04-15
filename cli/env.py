"""
Environment variable overlay for ConfigProvider.

Wraps an existing ConfigProvider and overlays values read from environment
variables matching a configurable prefix. Convention:

    PREFIX_FOO__BAR=value   ->  config key 'foo.bar'
    PREFIX_TIMEOUT=30       ->  config key 'timeout'

Double underscore acts as the hierarchical separator so single underscores
inside keys are preserved. Values are coerced via JSON parse first (handles
bool, int, float, list, dict, null), falling back to raw string.

The overlay is read-only: set/delete/save go to the inner provider, env
values are runtime overrides only.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import threading
from typing import Any

from .interfaces import ConfigProvider


class EnvOverlayConfigProvider(ConfigProvider):
    """Read-overlay of environment variables on top of an inner provider."""

    def __init__(
        self,
        inner: ConfigProvider,
        prefix: str,
        separator: str = "__",
    ) -> None:
        if not prefix:
            raise ValueError("prefix must be non-empty")
        if not separator:
            raise ValueError("separator must be non-empty")

        self._inner: ConfigProvider = inner
        self._prefix: str = prefix.upper().rstrip("_") + "_"
        self._separator: str = separator
        self._logger: logging.Logger = logging.getLogger(
            "cliframework.env"
        )
        self._lock = threading.RLock()
        self._overlay: dict[str, Any] = self._build_overlay()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            value = self._get_nested(self._overlay, key)
            if value is not None:
                return copy.deepcopy(value) if isinstance(
                    value, (dict, list)
                ) else value
        return self._inner.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._inner.set(key, value)

    def delete(self, key: str) -> bool:
        return self._inner.delete(key)

    def save(self) -> None:
        self._inner.save()

    def get_all(self) -> dict[str, Any]:
        merged = self._inner.get_all()
        with self._lock:
            self._deep_merge_inplace(merged, self._overlay)
        return merged

    def refresh(self) -> None:
        """Re-read environment variables (useful in tests or after env changes)."""
        with self._lock:
            self._overlay = self._build_overlay()

    def overlay_keys(self) -> list[str]:
        """Return flat list of dotted keys currently provided by env overlay."""
        with self._lock:
            return self._flatten_keys(self._overlay)

    def _build_overlay(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        prefix_len = len(self._prefix)
        for env_key, env_val in os.environ.items():
            if not env_key.startswith(self._prefix):
                continue
            tail = env_key[prefix_len:]
            if not tail:
                continue
            dotted = tail.lower().replace(self._separator, ".")
            if not dotted or dotted.startswith(".") or dotted.endswith("."):
                self._logger.debug(
                    f"Skipping malformed env key: {env_key}"
                )
                continue
            value = self._coerce(env_val)
            try:
                self._set_nested(result, dotted, value)
            except ValueError as exc:
                self._logger.warning(
                    f"Skipping conflicting env key {env_key}: {exc}"
                )
        return result

    @staticmethod
    def _coerce(raw: str) -> Any:
        stripped = raw.strip()
        if not stripped:
            return raw
        try:
            return json.loads(stripped)
        except (ValueError, TypeError):
            return raw

    @staticmethod
    def _set_nested(
        target: dict[str, Any], dotted_key: str, value: Any
    ) -> None:
        parts = dotted_key.split(".")
        node = target
        for part in parts[:-1]:
            existing = node.get(part)
            if existing is None:
                new_node: dict[str, Any] = {}
                node[part] = new_node
                node = new_node
            elif isinstance(existing, dict):
                node = existing
            else:
                raise ValueError(
                    f"cannot create nested key under non-dict at '{part}'"
                )
        node[parts[-1]] = value

    @staticmethod
    def _get_nested(source: dict[str, Any], dotted_key: str) -> Any:
        parts = dotted_key.split(".")
        node: Any = source
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node

    @staticmethod
    def _deep_merge_inplace(
        base: dict[str, Any], updates: dict[str, Any]
    ) -> None:
        for key, value in updates.items():
            if (
                key in base
                and isinstance(base[key], dict)
                and isinstance(value, dict)
            ):
                EnvOverlayConfigProvider._deep_merge_inplace(
                    base[key], value
                )
            else:
                base[key] = copy.deepcopy(value)

    @staticmethod
    def _flatten_keys(node: dict[str, Any], prefix: str = "") -> list[str]:
        keys: list[str] = []
        for k, v in node.items():
            full = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys.extend(EnvOverlayConfigProvider._flatten_keys(v, full))
            else:
                keys.append(full)
        return sorted(keys)


__all__ = ["EnvOverlayConfigProvider"]

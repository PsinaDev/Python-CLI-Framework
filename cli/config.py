"""
Configuration management with cross-platform file locking.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import platform
import re
import tempfile
import threading
import time
from typing import Any, Pattern

from .interfaces import ConfigProvider

try:
    import jsonschema

    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

if platform.system() == "Windows":
    import msvcrt

    LOCK_METHOD = "windows"
else:
    import fcntl

    LOCK_METHOD = "posix"

SENSITIVE_KEY_PATTERNS: frozenset[Pattern[str]] = frozenset(
    {
        re.compile(r"^.*password$", re.IGNORECASE),
        re.compile(r"^.*passwd$", re.IGNORECASE),
        re.compile(r"^.*pwd$", re.IGNORECASE),
        re.compile(r"^.*token$", re.IGNORECASE),
        re.compile(r"^.*api[_-]?key$", re.IGNORECASE),
        re.compile(r"^.*apikey$", re.IGNORECASE),
        re.compile(r"^.*api[_-]?secret$", re.IGNORECASE),
        re.compile(r"^.*secret$", re.IGNORECASE),
        re.compile(r"^.*private[_-]?key$", re.IGNORECASE),
        re.compile(r"^.*auth$", re.IGNORECASE),
        re.compile(r"^.*credentials?$", re.IGNORECASE),
        re.compile(r"^.*certificate$", re.IGNORECASE),
    }
)


class ConfigError(Exception):
    """Base exception for configuration errors."""


class ConfigValidationError(ConfigError):
    """Configuration validation failed."""


class ConfigIOError(ConfigError):
    """Configuration I/O operation failed."""


class ConfigLockError(ConfigError):
    """Failed to acquire configuration file lock."""


class FileLock:
    """
    Cross-platform file locking with timeout and stale detection.

    Note: PID-based stale detection cannot fully prevent PID-reuse races.
    The fcntl/msvcrt advisory lock is the actual mutual-exclusion mechanism;
    stale-detection only optimizes cleanup of crashed processes.
    On Windows, the lock applies to the .lock sidecar file.
    """

    def __init__(
        self,
        file_path: str,
        timeout: float = 10.0,
        stale_timeout: float = 300.0,
    ) -> None:
        self.file_path: str = file_path
        self.lock_path: str = f"{file_path}.lock"
        self.timeout: float = timeout
        self.stale_timeout: float = stale_timeout
        self.lock_file: Any | None = None
        self.is_locked: bool = False
        self._logger: logging.Logger = logging.getLogger(
            "cliframework.config.lock"
        )
        self._pid: int = os.getpid()
        try:
            self._uid: int = os.getuid()
        except AttributeError:
            self._uid = 0

    def __enter__(self) -> FileLock:
        if not self.acquire():
            raise ConfigLockError(
                f"Failed to acquire lock within {self.timeout}s timeout"
            )
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()

    def acquire(self, poll_interval: float = 0.1) -> bool:
        if self.is_locked:
            return True

        start_time = time.time()
        lock_file_created_by_us = False

        while time.time() - start_time < self.timeout:
            try:
                os.makedirs(
                    os.path.dirname(self.lock_path) or ".", exist_ok=True
                )

                if os.path.exists(self.lock_path):
                    if self._is_stale_lock():
                        self._safe_remove_lock_file()
                    else:
                        time.sleep(poll_interval)
                        continue

                try:
                    fd = os.open(
                        self.lock_path,
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                        0o600,
                    )
                    os.write(fd, f"{self._pid}:{self._uid}\n".encode("utf-8"))
                    os.close(fd)
                    lock_file_created_by_us = True
                except FileExistsError:
                    if self._is_stale_lock():
                        self._safe_remove_lock_file()
                        continue
                    time.sleep(poll_interval)
                    continue

                self.lock_file = open(self.lock_path, "r+")

                if LOCK_METHOD == "windows":
                    try:
                        msvcrt.locking(
                            self.lock_file.fileno(),
                            msvcrt.LK_NBLCK,
                            0x7FFF0000,
                        )
                        self.is_locked = True
                        return True
                    except (IOError, OSError):
                        self.lock_file.close()
                        self.lock_file = None
                        if lock_file_created_by_us:
                            self._safe_remove_lock_file()
                            lock_file_created_by_us = False
                        time.sleep(poll_interval)
                        continue
                else:
                    try:
                        fcntl.flock(
                            self.lock_file.fileno(),
                            fcntl.LOCK_EX | fcntl.LOCK_NB,
                        )
                        self.is_locked = True
                        return True
                    except (IOError, BlockingIOError, OSError):
                        self.lock_file.close()
                        self.lock_file = None
                        if lock_file_created_by_us:
                            self._safe_remove_lock_file()
                            lock_file_created_by_us = False
                        time.sleep(poll_interval)
                        continue

            except Exception as exc:
                if self.lock_file:
                    try:
                        self.lock_file.close()
                    except (OSError, IOError):
                        pass
                    self.lock_file = None
                if lock_file_created_by_us:
                    self._safe_remove_lock_file()
                self._logger.error(f"Failed to acquire lock: {exc}")
                raise ConfigLockError(f"Failed to acquire lock: {exc}")

        if lock_file_created_by_us:
            self._safe_remove_lock_file()
        return False

    def release(self) -> None:
        if not self.is_locked:
            return
        try:
            if LOCK_METHOD == "windows":
                if self.lock_file:
                    try:
                        msvcrt.locking(
                            self.lock_file.fileno(),
                            msvcrt.LK_UNLCK,
                            0x7FFF0000,
                        )
                    except (IOError, OSError):
                        pass
            elif self.lock_file:
                try:
                    fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                except (IOError, OSError):
                    pass
        finally:
            if self.lock_file:
                try:
                    self.lock_file.close()
                except (OSError, IOError):
                    pass
                self.lock_file = None
            self._safe_remove_lock_file()
            self.is_locked = False

    def _is_stale_lock(self) -> bool:
        try:
            if not os.path.exists(self.lock_path):
                return False
            mtime = os.path.getmtime(self.lock_path)
            if time.time() - mtime <= self.stale_timeout:
                return False

            try:
                with open(self.lock_path, "r") as f:
                    lock_info = f.read().strip()
                if ":" in lock_info:
                    old_pid_str, old_uid_str = lock_info.split(":", 1)
                else:
                    old_pid_str, old_uid_str = lock_info, "0"

                if not old_pid_str.isdigit():
                    return True
                old_pid = int(old_pid_str)

                if platform.system() == "Windows":
                    return self._is_windows_pid_dead(old_pid)
                return self._is_posix_pid_dead(old_pid, old_uid_str)
            except (OSError, IOError, ValueError):
                return True
        except (OSError, IOError):
            return False

    def _is_windows_pid_dead(self, old_pid: int) -> bool:
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, old_pid)
            if not handle:
                error = ctypes.get_last_error()
                if error == 5:
                    return False
                return True
            kernel32.CloseHandle(handle)
            return False
        except Exception:
            return False

    def _is_posix_pid_dead(self, old_pid: int, old_uid_str: str) -> bool:
        try:
            os.kill(old_pid, 0)
            if old_uid_str.isdigit() and int(old_uid_str) != self._uid:
                return False
            return False
        except (OSError, ProcessLookupError):
            if old_uid_str.isdigit() and int(old_uid_str) != self._uid:
                return False
            return True

    def _safe_remove_lock_file(self) -> None:
        try:
            if os.path.exists(self.lock_path):
                os.unlink(self.lock_path)
        except (OSError, IOError, PermissionError):
            pass


def sanitize_for_logging(
    data: dict[str, Any],
    sensitive_patterns: set[Pattern[str]] | None = None,
) -> dict[str, Any]:
    """Sanitize sensitive data for logging; redacts entire subtree under sensitive keys."""
    patterns = SENSITIVE_KEY_PATTERNS
    if sensitive_patterns:
        patterns = patterns | frozenset(sensitive_patterns)

    def is_sensitive(key: str) -> bool:
        return any(p.match(key) for p in patterns)

    def sanitize(value: Any, parent_is_sensitive: bool) -> Any:
        if parent_is_sensitive:
            if isinstance(value, dict):
                return {k: "***REDACTED***" for k in value}
            if isinstance(value, list):
                return ["***REDACTED***"] * len(value)
            return "***REDACTED***"
        if isinstance(value, dict):
            return {
                k: (
                    "***REDACTED***"
                    if is_sensitive(k) and not isinstance(v, (dict, list))
                    else sanitize(v, is_sensitive(k))
                )
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [sanitize(item, False) for item in value]
        return value

    return {
        k: (
            "***REDACTED***"
            if is_sensitive(k) and not isinstance(v, (dict, list))
            else sanitize(v, is_sensitive(k))
        )
        for k, v in data.items()
    }


def deep_merge(
    base: dict[str, Any],
    updates: dict[str, Any],
    on_type_conflict: str = "prefer_base",
) -> dict[str, Any]:
    """
    Deep merge two dictionaries.

    on_type_conflict:
        - "prefer_base": preserve base type when types differ (safer for defaults)
        - "prefer_updates": legacy behavior, updates win
    """
    result = copy.deepcopy(base)
    logger = logging.getLogger("cliframework.config.merge")

    for key, value in updates.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value, on_type_conflict)
        elif (
            key in result
            and type(result[key]) is not type(value)
            and result[key] is not None
            and value is not None
        ):
            if on_type_conflict == "prefer_base":
                logger.warning(
                    f"Type mismatch at key '{key}': base={type(result[key]).__name__}, "
                    f"updates={type(value).__name__}; preserving base"
                )
            else:
                result[key] = copy.deepcopy(value)
        else:
            result[key] = copy.deepcopy(value)

    return result


class JsonConfigProvider(ConfigProvider):
    """JSON-based configuration provider with file locking and schema validation."""

    def __init__(
        self,
        config_path: str,
        default_config: dict[str, Any] | None = None,
        schema: dict[str, Any] | None = None,
        lock_timeout: float = 10.0,
        stale_lock_timeout: float = 300.0,
    ) -> None:
        self._config_path: str = os.path.abspath(
            os.path.expanduser(config_path)
        )
        self._config: dict[str, Any] = (
            copy.deepcopy(default_config) if default_config else {}
        )
        self._schema: dict[str, Any] | None = schema
        self._lock_timeout: float = lock_timeout
        self._stale_lock_timeout: float = stale_lock_timeout
        self._logger: logging.Logger = logging.getLogger("cliframework.config")
        self._mem_lock = threading.RLock()

        if self._schema and not JSONSCHEMA_AVAILABLE:
            self._logger.warning(
                "jsonschema not installed, schema validation disabled"
            )
            self._schema = None

        try:
            os.makedirs(
                os.path.dirname(self._config_path) or ".", exist_ok=True
            )
        except OSError as exc:
            raise ConfigError(f"Failed to create config directory: {exc}")

        if not os.path.exists(self._config_path) and default_config:
            try:
                self._save_to_file(self._config)
            except Exception as exc:
                self._logger.error(f"Failed to create config file: {exc}")

        self._load()

    def get(self, key: str, default: Any = None) -> Any:
        with self._mem_lock:
            parts: list[str] = key.split(".")
            config: Any = self._config
            for part in parts[:-1]:
                if not isinstance(config, dict) or part not in config:
                    return default
                config = config[part]
            if not isinstance(config, dict):
                return default
            value = config.get(parts[-1], default)
            return (
                copy.deepcopy(value) if isinstance(value, (dict, list)) else value
            )

    def set(self, key: str, value: Any) -> None:
        with self._mem_lock:
            parts: list[str] = key.split(".")
            config: dict[str, Any] = self._config
            for part in parts[:-1]:
                if part not in config:
                    config[part] = {}
                elif not isinstance(config[part], dict):
                    self._logger.warning(
                        f"Overwriting non-dict value at key '{part}' "
                        f"to create nested structure"
                    )
                    config[part] = {}
                config = config[part]
            config[parts[-1]] = copy.deepcopy(value)

            try:
                self._validate_schema(self._config)
            except ConfigValidationError:
                self._logger.warning(
                    f"Setting key '{key}' resulted in schema-invalid state"
                )
                raise

    def delete(self, key: str) -> bool:
        with self._mem_lock:
            parts: list[str] = key.split(".")
            config: Any = self._config
            for part in parts[:-1]:
                if not isinstance(config, dict) or part not in config:
                    return False
                config = config[part]
            if not isinstance(config, dict) or parts[-1] not in config:
                return False
            del config[parts[-1]]
            return True

    def save(self) -> None:
        with self._mem_lock:
            snapshot = copy.deepcopy(self._config)

        lock = FileLock(
            self._config_path,
            timeout=self._lock_timeout,
            stale_timeout=self._stale_lock_timeout,
        )
        try:
            with lock:
                self._save_to_file(snapshot)
        except (ConfigLockError, ConfigIOError, ConfigValidationError):
            raise
        except Exception as exc:
            raise ConfigIOError(f"Unexpected error saving config: {exc}")

    def get_all(self) -> dict[str, Any]:
        with self._mem_lock:
            return copy.deepcopy(self._config)

    def update(self, config: dict[str, Any]) -> None:
        with self._mem_lock:
            updated = deep_merge(self._config, config)
            self._validate_schema(updated)
            self._config = updated

    def _validate_schema(self, config: dict[str, Any]) -> None:
        if not self._schema or not JSONSCHEMA_AVAILABLE:
            return
        try:
            jsonschema.validate(instance=config, schema=self._schema)
        except jsonschema.exceptions.ValidationError as exc:
            raise ConfigValidationError(
                f"Configuration validation failed: {exc.message}"
            )

    def _load(self) -> None:
        if not os.path.exists(self._config_path):
            return

        lock = FileLock(
            self._config_path,
            timeout=self._lock_timeout,
            stale_timeout=self._stale_lock_timeout,
        )

        try:
            with lock:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    loaded_config: dict[str, Any] = json.load(f)
                self._validate_schema(loaded_config)
                with self._mem_lock:
                    self._config = deep_merge(self._config, loaded_config)
        except ConfigLockError:
            self._logger.warning(
                "Could not acquire lock for reading config; reading without lock"
            )
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    loaded_config = json.load(f)
                self._validate_schema(loaded_config)
                with self._mem_lock:
                    self._config = deep_merge(self._config, loaded_config)
            except Exception as read_err:
                self._logger.error(
                    f"Failed to read config even without lock: {read_err}"
                )
        except UnicodeDecodeError as exc:
            self._logger.error(f"Encoding error reading config: {exc}")
            self._attempt_recovery()
        except json.JSONDecodeError as exc:
            self._logger.error(f"Invalid JSON in config file: {exc}")
            self._attempt_recovery()
        except ConfigValidationError as exc:
            self._logger.error(f"Config validation failed: {exc}")
            self._attempt_recovery()
        except IOError as exc:
            self._logger.error(f"I/O error reading config: {exc}")
        except Exception as exc:
            self._logger.error(
                f"Unexpected error loading config: {exc}", exc_info=True
            )

    def _attempt_recovery(self) -> None:
        try:
            backup_path = f"{self._config_path}.corrupt.{int(time.time())}"
            if os.path.exists(self._config_path):
                import shutil

                shutil.copy(self._config_path, backup_path)
                self._logger.info(
                    f"Created backup of corrupted config: {backup_path}"
                )

            with self._mem_lock:
                snapshot = copy.deepcopy(self._config)

            if snapshot:
                self._validate_schema(snapshot)
                self._save_to_file(snapshot)
        except Exception as exc:
            self._logger.error(f"Recovery failed: {exc}")
            raise ConfigError(f"Failed to recover configuration: {exc}")

    def _save_to_file(self, config: dict[str, Any]) -> None:
        self._validate_schema(config)
        temp_dir = os.path.dirname(self._config_path) or "."
        temp_fd, temp_path = tempfile.mkstemp(
            suffix=".json",
            prefix=f"{os.path.basename(self._config_path)}.",
            dir=temp_dir,
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                json.dump(
                    config, f, indent=2, ensure_ascii=False, sort_keys=True
                )
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self._config_path)
            try:
                if LOCK_METHOD == "posix":
                    os.chmod(self._config_path, 0o600)
            except OSError as exc:
                self._logger.debug(f"Could not chmod config to 0o600: {exc}")
        except Exception as exc:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except (OSError, IOError):
                pass
            raise ConfigIOError(f"Failed to save config: {exc}")


__all__ = [
    "ConfigError",
    "ConfigValidationError",
    "ConfigIOError",
    "ConfigLockError",
    "FileLock",
    "JsonConfigProvider",
    "SENSITIVE_KEY_PATTERNS",
    "sanitize_for_logging",
    "deep_merge",
]

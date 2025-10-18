"""
Configuration management with cross-platform file locking

Provides secure, thread-safe configuration storage with JSON schemas,
hierarchical key access, and automatic backup recovery.

Note on sensitive keys: Keys containing 'password', 'token', 'secret', etc.
are automatically masked in logs. This may hide non-sensitive fields with
similar names - configure additional sensitive_keys if needed.
"""

import json
import os
import logging
import tempfile
import platform
import time
import copy
from typing import Any, Dict, Optional, Set

try:
    import jsonschema
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False

if platform.system() == 'Windows':
    import msvcrt
    LOCK_METHOD = 'windows'
else:
    import fcntl
    LOCK_METHOD = 'posix'

SENSITIVE_KEYS: Set[str] = {
    'password', 'passwd', 'pwd',
    'token', 'api_key', 'apikey', 'api_secret',
    'secret', 'private_key', 'auth',
    'credentials', 'certificate'
}


class ConfigError(Exception):
    """Base exception for configuration errors"""
    pass


class ConfigValidationError(ConfigError):
    """Configuration validation failed"""
    pass


class ConfigIOError(ConfigError):
    """Configuration I/O operation failed"""
    pass


class ConfigLockError(ConfigError):
    """Failed to acquire configuration file lock"""
    pass


class FileLock:
    """
    Cross-platform file locking mechanism with timeout support

    Configurable stale lock detection prevents deadlocks from crashed processes.
    On POSIX systems, UID isolation ensures user-specific locks.
    """

    def __init__(self, file_path: str, timeout: float = 10.0, stale_timeout: float = 300.0):
        """
        Initialize file lock

        Args:
            file_path: Path to file to lock
            timeout: Maximum time to wait for lock acquisition (seconds)
            stale_timeout: Age threshold for considering lock stale (seconds)
                          Set higher than your longest expected operation
        """
        self.file_path: str = file_path
        self.lock_path: str = f"{file_path}.lock"
        self.timeout: float = timeout
        self.stale_timeout: float = stale_timeout
        self.lock_file: Optional[Any] = None
        self.is_locked: bool = False
        self._logger: logging.Logger = logging.getLogger('cli.config.lock')
        self._pid: int = os.getpid()
        try:
            self._uid: int = os.getuid()
        except AttributeError:
            self._uid: int = 0

    def acquire(self, poll_interval: float = 0.1) -> bool:
        """Acquire lock with timeout and retry logic"""
        if self.is_locked:
            return True

        start_time: float = time.time()

        while time.time() - start_time < self.timeout:
            try:
                os.makedirs(os.path.dirname(self.lock_path) or '.', exist_ok=True)

                try:
                    fd = os.open(
                        self.lock_path,
                        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                        0o600
                    )

                    lock_info = f"{self._pid}:{self._uid}\n"
                    os.write(fd, lock_info.encode('utf-8'))
                    os.close(fd)

                    self.lock_file = open(self.lock_path, 'r+')

                except FileExistsError:
                    if self._is_stale_lock():
                        self._safe_remove_lock_file()
                        continue
                    time.sleep(poll_interval)
                    continue

                if LOCK_METHOD == 'windows':
                    try:
                        msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                        self.is_locked = True
                        self._logger.debug(f"Lock acquired (PID: {self._pid})")
                        return True
                    except (IOError, OSError) as e:
                        self._logger.debug(f"Windows lock failed: {e}")
                        self.lock_file.close()
                        self._safe_remove_lock_file()
                        time.sleep(poll_interval)
                        continue
                else:
                    try:
                        fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        self.is_locked = True
                        self._logger.debug(f"Lock acquired (PID: {self._pid}, UID: {self._uid})")
                        return True
                    except (IOError, BlockingIOError, OSError) as e:
                        self._logger.debug(f"POSIX lock failed: {e}")
                        self.lock_file.close()
                        self._safe_remove_lock_file()
                        time.sleep(poll_interval)
                        continue

            except Exception as e:
                if self.lock_file:
                    try:
                        self.lock_file.close()
                    except (OSError, IOError) as close_err:
                        self._logger.debug(f"Could not close lock file: {close_err}")
                self._safe_remove_lock_file()
                self._logger.error(f"Failed to acquire lock: {e}")
                raise ConfigLockError(f"Failed to acquire lock: {e}")

        self._logger.error(f"Lock acquisition timeout after {self.timeout}s")
        return False

    def _is_stale_lock(self) -> bool:
        """
        Check if lock file is stale

        A lock is considered stale if:
        1. It's older than stale_timeout seconds AND
        2. The owning process no longer exists OR
        3. (On POSIX) The owning process belongs to a different user
        """
        try:
            if not os.path.exists(self.lock_path):
                return False

            mtime = os.path.getmtime(self.lock_path)
            age = time.time() - mtime

            if age <= self.stale_timeout:
                return False

            try:
                with open(self.lock_path, 'r') as f:
                    lock_info = f.read().strip()

                if ':' in lock_info:
                    old_pid_str, old_uid_str = lock_info.split(':', 1)
                else:
                    old_pid_str = lock_info
                    old_uid_str = '0'

                if not old_pid_str.isdigit():
                    self._logger.warning(f"Invalid PID in lock file: {old_pid_str}")
                    return True

                old_pid = int(old_pid_str)

                if platform.system() == 'Windows':
                    try:
                        import ctypes
                        kernel32 = ctypes.windll.kernel32
                        PROCESS_QUERY_INFORMATION = 0x0400
                        handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, old_pid)
                        if handle:
                            kernel32.CloseHandle(handle)
                            return False
                        return True
                    except Exception as e:
                        self._logger.debug(f"Could not check process on Windows: {e}")
                        return True
                else:
                    try:
                        os.kill(old_pid, 0)
                        if old_uid_str.isdigit():
                            old_uid = int(old_uid_str)
                            if old_uid != self._uid:
                                self._logger.debug(
                                    f"Lock owned by different user (UID {old_uid}), not removing"
                                )
                                return False
                        return False
                    except (OSError, ProcessLookupError):
                        return True

            except (OSError, IOError, ValueError) as e:
                self._logger.debug(f"Error reading lock file: {e}")
                return True

        except (OSError, IOError) as e:
            self._logger.debug(f"Error checking stale lock: {e}")
            return False

    def release(self) -> None:
        """Release lock and cleanup lock file"""
        if not self.is_locked:
            return

        try:
            if LOCK_METHOD == 'windows':
                if self.lock_file:
                    try:
                        msvcrt.locking(self.lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    except (IOError, OSError):
                        pass
            else:
                if self.lock_file:
                    try:
                        fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
                    except (IOError, OSError):
                        pass
        finally:
            if self.lock_file:
                try:
                    self.lock_file.close()
                except (OSError, IOError) as e:
                    self._logger.debug(f"Could not close lock file during release: {e}")
                self.lock_file = None

            self._safe_remove_lock_file()
            self.is_locked = False
            self._logger.debug(f"Lock released (PID: {self._pid})")

    def _safe_remove_lock_file(self) -> None:
        """Safely remove lock file, ignoring errors"""
        try:
            if os.path.exists(self.lock_path):
                os.unlink(self.lock_path)
        except (OSError, IOError, PermissionError) as e:
            self._logger.debug(f"Could not remove lock file: {e}")

    def __enter__(self) -> 'FileLock':
        if not self.acquire():
            raise ConfigLockError(f"Failed to acquire lock within {self.timeout}s timeout")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()


def sanitize_for_logging(data: Dict[str, Any], sensitive_keys: Optional[Set[str]] = None) -> Dict[str, Any]:
    """
    Sanitize sensitive data for logging

    Note: Keys are matched by substring, so 'user_password' will be masked.
    This may hide non-sensitive fields - configure additional patterns if needed.
    """
    if sensitive_keys is None:
        sensitive_keys = SENSITIVE_KEYS
    else:
        sensitive_keys = SENSITIVE_KEYS | sensitive_keys

    def _sanitize_value(key: str, value: Any) -> Any:
        key_lower = key.lower()
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            return '***REDACTED***'

        if isinstance(value, dict):
            return {k: _sanitize_value(k, v) for k, v in value.items()}

        if isinstance(value, list):
            return [_sanitize_value(f"{key}[{i}]", item) for i, item in enumerate(value)]

        return value

    return {k: _sanitize_value(k, v) for k, v in data.items()}


def deep_merge(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries"""
    result = copy.deepcopy(base)

    for key, value in updates.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)

    return result


class JsonConfigProvider:
    """JSON-based configuration provider with advanced features"""

    def __init__(self,
                 config_path: str,
                 default_config: Optional[Dict[str, Any]] = None,
                 schema: Optional[Dict[str, Any]] = None,
                 lock_timeout: float = 10.0,
                 stale_lock_timeout: float = 300.0):
        """
        Initialize configuration provider

        Args:
            config_path: Path to config file
            default_config: Default configuration values
            schema: JSON schema for validation
            lock_timeout: Maximum time to wait for lock (seconds)
            stale_lock_timeout: Age threshold for stale locks (seconds)
        """
        self._config_path: str = os.path.abspath(os.path.expanduser(config_path))
        self._config: Dict[str, Any] = copy.deepcopy(default_config) if default_config else {}
        self._schema: Optional[Dict[str, Any]] = schema
        self._lock_timeout: float = lock_timeout
        self._stale_lock_timeout: float = stale_lock_timeout
        self._logger: logging.Logger = logging.getLogger('cli.config')

        if self._schema and not JSONSCHEMA_AVAILABLE:
            self._logger.warning("jsonschema not installed, schema validation disabled")
            self._schema = None

        try:
            os.makedirs(os.path.dirname(self._config_path) or '.', exist_ok=True)
        except OSError as e:
            raise ConfigError(f"Failed to create config directory: {e}")

        if not os.path.exists(self._config_path) and default_config:
            try:
                self._save_to_file(self._config)
                self._logger.info(f"Created new config file: {self._config_path}")
            except Exception as e:
                self._logger.error(f"Failed to create config file: {e}")

        self._load()

    def _validate_schema(self, config: Dict[str, Any]) -> None:
        """Validate configuration against JSON schema"""
        if not self._schema or not JSONSCHEMA_AVAILABLE:
            return

        try:
            jsonschema.validate(instance=config, schema=self._schema)
        except jsonschema.exceptions.ValidationError as e:
            raise ConfigValidationError(f"Configuration validation failed: {e.message}")

    def _load(self) -> None:
        """Load configuration from file with error recovery"""
        if not os.path.exists(self._config_path):
            self._logger.info(f"Config file does not exist: {self._config_path}")
            return

        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                loaded_config: Dict[str, Any] = json.load(f)

            self._validate_schema(loaded_config)
            self._config = deep_merge(self._config, loaded_config)

            self._logger.debug(
                f"Config loaded from {self._config_path}: "
                f"{sanitize_for_logging(self._config)}"
            )

        except UnicodeDecodeError as e:
            self._logger.error(f"Encoding error reading config: {e}")
            self._attempt_recovery()

        except json.JSONDecodeError as e:
            self._logger.error(f"Invalid JSON in config file: {e}")
            self._attempt_recovery()

        except ConfigValidationError as e:
            self._logger.error(f"Config validation failed: {e}")
            self._attempt_recovery()

        except IOError as e:
            self._logger.error(f"I/O error reading config: {e}")

        except Exception as e:
            self._logger.error(f"Unexpected error loading config: {e}", exc_info=True)

    def _attempt_recovery(self) -> None:
        """Attempt to recover from corrupted configuration"""
        try:
            backup_path = f"{self._config_path}.corrupt.{int(time.time())}"

            if os.path.exists(self._config_path):
                import shutil
                shutil.copy(self._config_path, backup_path)
                self._logger.info(f"Created backup of corrupted config: {backup_path}")

            if self._config:
                self._validate_schema(self._config)
                self._save_to_file(self._config)
                self._logger.info("Reset config to defaults")
            else:
                self._logger.warning("No default config available for recovery")

        except Exception as e:
            self._logger.error(f"Recovery failed: {e}")
            raise ConfigError(f"Failed to recover configuration: {e}")

    def _save_to_file(self, config: Dict[str, Any]) -> None:
        """Safely save configuration to file with atomic write"""
        self._validate_schema(config)

        temp_dir = os.path.dirname(self._config_path) or '.'
        temp_fd, temp_path = tempfile.mkstemp(
            suffix='.json',
            prefix=f"{os.path.basename(self._config_path)}.",
            dir=temp_dir
        )

        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename works on all platforms
            os.replace(temp_path, self._config_path)

            self._logger.debug(f"Config saved to {self._config_path}")

        except Exception as e:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except (OSError, IOError) as cleanup_err:
                self._logger.debug(f"Could not cleanup temp file: {cleanup_err}")
            raise ConfigIOError(f"Failed to save config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by hierarchical key"""
        parts: list[str] = key.split('.')
        config: Any = self._config

        for part in parts[:-1]:
            if not isinstance(config, dict) or part not in config:
                return default
            config = config[part]

        if not isinstance(config, dict):
            return default

        return config.get(parts[-1], default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value by hierarchical key"""
        parts: list[str] = key.split('.')
        config: Dict[str, Any] = self._config

        for part in parts[:-1]:
            if part not in config:
                config[part] = {}
            elif not isinstance(config[part], dict):
                self._logger.warning(
                    f"Overwriting non-dict value at key '{part}' to create nested structure"
                )
                config[part] = {}
            config = config[part]

        config[parts[-1]] = value
        self._logger.debug(f"Set config key '{key}'")

    def save(self) -> None:
        """Save configuration to file with locking"""
        lock = FileLock(
            self._config_path,
            timeout=self._lock_timeout,
            stale_timeout=self._stale_lock_timeout
        )

        try:
            with lock:
                self._save_to_file(self._config)
        except ConfigLockError as e:
            self._logger.error(f"Failed to acquire lock for saving: {e}")
            raise
        except (ConfigIOError, ConfigValidationError) as e:
            self._logger.error(f"Failed to save configuration: {e}")
            raise
        except Exception as e:
            self._logger.error(f"Unexpected error saving config: {e}")
            raise ConfigIOError(f"Unexpected error saving config: {e}")

    def get_all(self) -> Dict[str, Any]:
        """Get complete configuration as dictionary"""
        return copy.deepcopy(self._config)

    def update(self, config: Dict[str, Any]) -> None:
        """Update configuration from dictionary with deep merge"""
        updated_config = deep_merge(self._config, config)
        self._validate_schema(updated_config)
        self._config = updated_config
        self._logger.debug("Configuration updated from dictionary")
"""
CLI Framework - A modular framework for building command-line applications.
"""

from __future__ import annotations

import re
import sys

if sys.version_info < (3, 10):
    raise RuntimeError(
        f"CLI Framework requires Python 3.10+, got "
        f"{sys.version_info.major}.{sys.version_info.minor}"
    )

__version__ = "1.3.0"
__author__ = "Psina Dev"

from .application import (
    CLI,
    CLIError,
    CommandExecutionError,
    DEFAULT_CONFIG_SCHEMA,
    cli_context,
)
from .command import (
    CommandRegistryImpl,
    EnhancedArgumentParser,
)
from .completion import Shell, generate_completion
from .config import (
    ConfigError,
    ConfigIOError,
    ConfigLockError,
    ConfigValidationError,
    JsonConfigProvider,
    sanitize_for_logging,
)
from .decorators import (
    BoundDecorators,
    CommandMetadataRegistry,
    argument,
    clear_default_registry,
    clear_registry,
    command,
    example,
    get_default_registry,
    group,
    option,
    register_commands,
)
from .env import EnvOverlayConfigProvider
from .interfaces import (
    ArgumentParser,
    CommandHandler,
    CommandRegistry,
    ConfigProvider,
    Hook,
    MessageProvider,
    Middleware,
    OutputFormatter,
    RESERVED_NAMES,
)
from .messages import (
    ConfigBasedMessageProvider,
    MessageError,
)
from .output import (
    TerminalOutputFormatter,
    echo,
    progress_bar,
    style,
    table,
)
from .plugins import (
    PluginError,
    discover_plugins,
    load_plugins,
)


def _parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse a version string to (major, minor, patch)."""
    match = re.match(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?", version_str.strip())
    if not match:
        return (0, 0, 0)
    return (
        int(match.group(1)),
        int(match.group(2) or 0),
        int(match.group(3) or 0),
    )


def get_version() -> str:
    return __version__


def get_version_tuple() -> tuple[int, int, int]:
    return _parse_version(__version__)


__all__ = [
    "CLI",
    "CLIError",
    "CommandExecutionError",
    "DEFAULT_CONFIG_SCHEMA",
    "cli_context",
    "command",
    "argument",
    "option",
    "example",
    "group",
    "register_commands",
    "clear_registry",
    "clear_default_registry",
    "get_default_registry",
    "CommandMetadataRegistry",
    "BoundDecorators",
    "RESERVED_NAMES",
    "ConfigProvider",
    "MessageProvider",
    "OutputFormatter",
    "CommandRegistry",
    "ArgumentParser",
    "CommandHandler",
    "Middleware",
    "Hook",
    "JsonConfigProvider",
    "ConfigError",
    "ConfigValidationError",
    "ConfigIOError",
    "ConfigLockError",
    "sanitize_for_logging",
    "EnvOverlayConfigProvider",
    "ConfigBasedMessageProvider",
    "MessageError",
    "TerminalOutputFormatter",
    "echo",
    "style",
    "progress_bar",
    "table",
    "CommandRegistryImpl",
    "EnhancedArgumentParser",
    "Shell",
    "generate_completion",
    "PluginError",
    "discover_plugins",
    "load_plugins",
    "__version__",
    "__author__",
    "get_version",
    "get_version_tuple",
]

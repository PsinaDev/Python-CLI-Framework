"""
CLI Framework - Main Package Entry Point

A powerful framework for building professional command-line interfaces in Python.

Features:
- Declarative command definition with decorators
- Async/sync command execution
- Middleware pipeline (async only) for cross-cutting concerns
- Configuration management with JSON schemas
- Multi-language message support
- Rich terminal output (colors, tables, progress bars)
- Tab completion support
- Automatic help generation
- Command aliases and groups
- Thread-safe operation

Requires Python 3.8+ (uses typing.get_origin/get_args from standard library)
"""

import sys

# Check Python version
if sys.version_info < (3, 8):
    raise RuntimeError(
        "CLI Framework requires Python 3.8 or higher. "
        f"You are using Python {sys.version_info.major}.{sys.version_info.minor}. "
        "Please upgrade your Python installation."
    )

from .application import CLI, CLIError, CommandExecutionError
from .decorators import command, argument, option, group, example
from .output import style, progress_bar, table, echo, TerminalOutputFormatter
from .interfaces import (
    ConfigProvider, MessageProvider, OutputFormatter,
    CommandRegistry, ArgumentParser, Middleware, Hook
)
from .config import (
    JsonConfigProvider, ConfigError, ConfigValidationError,
    ConfigIOError, ConfigLockError
)
from .messages import ConfigBasedMessageProvider, MessageError
from .command import CommandRegistryImpl, EnhancedArgumentParser

__version__ = "1.1.0"
__author__ = "Psinadev"

__all__ = [
    # Core application
    'CLI',
    'CLIError',
    'CommandExecutionError',

    # Decorators
    'command',
    'argument',
    'option',
    'group',
    'example',

    # Output utilities
    'style',
    'progress_bar',
    'table',
    'echo',
    'TerminalOutputFormatter',

    # Interfaces
    'ConfigProvider',
    'MessageProvider',
    'OutputFormatter',
    'CommandRegistry',
    'ArgumentParser',
    'Middleware',
    'Hook',

    # Config management
    'JsonConfigProvider',
    'ConfigError',
    'ConfigValidationError',
    'ConfigIOError',
    'ConfigLockError',

    # Message management
    'ConfigBasedMessageProvider',
    'MessageError',

    # Command system
    'CommandRegistryImpl',
    'EnhancedArgumentParser',
]


def _parse_version(version_str: str) -> tuple:
    """
    Parse version string into tuple
    """
    import re
    match = re.match(r'^(\d+)(?:\.(\d+))?(?:\.(\d+))?', version_str)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2)) if match.group(2) else 0
        patch = int(match.group(3)) if match.group(3) else 0
        return (major, minor, patch)

    parts = version_str.split('.')
    numeric_parts = []
    for part in parts:
        try:
            num_match = re.match(r'^(\d+)', part)
            if num_match:
                numeric_parts.append(int(num_match.group(1)))
            else:
                break
        except ValueError:
            break

    while len(numeric_parts) < 3:
        numeric_parts.append(0)

    return tuple(numeric_parts[:3])


# Version info
VERSION_INFO = _parse_version(__version__)


def get_version() -> str:
    """Get framework version string"""
    return __version__


def get_version_info() -> tuple:
    """
    Get framework version as 3-tuple

    Returns:
        Tuple of (major, minor, patch) as integers
    """
    return VERSION_INFO
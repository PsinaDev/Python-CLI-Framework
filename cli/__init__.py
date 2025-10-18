"""
CLI Framework - Main Package Entry Point

A powerful framework for building professional command-line interfaces in Python.

Features:
- Declarative command definition with decorators
- Async/sync command execution
- Middleware pipeline for cross-cutting concerns
- Configuration management with JSON schemas
- Multi-language message support
- Rich terminal output (colors, tables, progress bars)
- Tab completion support
- Automatic help generation
- Command aliases and groups
- Thread-safe operation
"""

from .application import CLI, CLIError, CommandExecutionError
from .decorators import command, argument, option, group, example
from .output import echo, style, progress_bar, table, TerminalOutputFormatter
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
    'echo',
    'style',
    'progress_bar',
    'table',
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

    Handles pre-release versions like "1.1.0b1" by stripping suffix
    """
    import re
    # Extract only numeric parts
    match = re.match(r'^(\d+)\.(\d+)\.(\d+)', version_str)
    if match:
        return tuple(int(x) for x in match.groups())
    # Fallback for simple versions
    parts = version_str.split('.')
    numeric_parts = []
    for part in parts:
        try:
            numeric_parts.append(int(part))
        except ValueError:
            # Stop at first non-numeric part
            break
    return tuple(numeric_parts) if numeric_parts else (0, 0, 0)


# Version info
VERSION_INFO = _parse_version(__version__)


def get_version() -> str:
    """Get framework version string"""
    return __version__


def get_version_info() -> tuple:
    """Get framework version as tuple"""
    return VERSION_INFO
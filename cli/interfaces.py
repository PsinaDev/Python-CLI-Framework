"""
Core interfaces and shared constants for the CLI Framework.
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from typing import (
    Any,
    Awaitable,
    Callable,
    Generic,
    Protocol,
    TextIO,
    TypeVar,
    runtime_checkable,
)

T = TypeVar("T")

RESERVED_NAMES: frozenset[str] = frozenset(
    {"help", "h", "_cli_help", "_cli_show_help"}
)


class ConfigProvider(ABC):
    """Abstract interface for configuration management with hierarchical keys."""

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        ...

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete value at hierarchical key. Returns True if removed."""
        ...

    @abstractmethod
    def save(self) -> None:
        ...

    @abstractmethod
    def get_all(self) -> dict[str, Any]:
        ...


class MessageProvider(ABC):
    """Abstract interface for localized message management."""

    @abstractmethod
    def get_message(
        self, key: str, default: str | None = None, **kwargs: Any
    ) -> str:
        ...

    @abstractmethod
    def set_language(self, language: str) -> None:
        ...

    @abstractmethod
    def get_current_language(self) -> str:
        ...


class OutputFormatter(ABC):
    """Abstract interface for terminal output formatting."""

    @abstractmethod
    def format(self, text: str, style: str | None = None) -> str:
        ...

    @abstractmethod
    def render_table(
        self,
        headers: list[str],
        rows: list[list[str]],
        max_col_width: int | None = None,
        file: TextIO = sys.stdout,
        output_format: str = "text",
    ) -> None:
        ...

    @abstractmethod
    def progress_bar(
        self, total: int, **kwargs: Any
    ) -> Callable[[int], None]:
        ...


class CommandHandler(ABC, Generic[T]):
    """Generic interface for command handlers; T is the return type."""

    @abstractmethod
    async def handle(self, *args: Any, **kwargs: Any) -> T:
        ...


class CommandRegistry(ABC):
    """Abstract interface for command registration, lookup, and autocomplete."""

    @abstractmethod
    def register(
        self, name: str, handler: Callable[..., Any], **metadata: Any
    ) -> None:
        ...

    @abstractmethod
    def get_command(self, name: str) -> dict[str, Any] | None:
        ...

    @abstractmethod
    def list_commands(self) -> list[str]:
        ...

    @abstractmethod
    def autocomplete(self, prefix: str) -> list[str]:
        ...

    def find_by_prefix(self, prefix: str) -> list[str]:
        """Default implementation for hierarchical command lookup."""
        prefix_with_dot = prefix + "."
        return sorted(
            name
            for name in self.list_commands()
            if name.startswith(prefix_with_dot) or name == prefix
        )


class ArgumentParser(ABC):
    """Abstract interface for command-line argument parsing."""

    @abstractmethod
    def parse(self, args: list[str]) -> dict[str, Any]:
        ...

    @abstractmethod
    def generate_help(self, command: str) -> str:
        ...


@runtime_checkable
class Middleware(Protocol):
    """
    Structural protocol for command-execution middleware.

    Any async callable taking the next handler satisfies this protocol;
    explicit subclassing is not required.
    """

    async def __call__(
        self, next_handler: Callable[[], Awaitable[Any]]
    ) -> Any:
        ...


class Hook:
    """
    Lifecycle hook with no-op defaults.

    Override only the methods you need; unused hooks remain no-ops.
    """

    async def on_before_parse(self, args: list[str]) -> list[str]:
        return args

    async def on_after_parse(self, parsed: dict[str, Any]) -> dict[str, Any]:
        return parsed

    async def on_before_execute(
        self, command: str, kwargs: dict[str, Any]
    ) -> None:
        return None

    async def on_after_execute(
        self, command: str, result: Any, exit_code: int
    ) -> None:
        return None

    async def on_error(self, command: str, error: BaseException) -> None:
        return None


__all__ = [
    "RESERVED_NAMES",
    "ConfigProvider",
    "MessageProvider",
    "OutputFormatter",
    "CommandHandler",
    "CommandRegistry",
    "ArgumentParser",
    "Middleware",
    "Hook",
]

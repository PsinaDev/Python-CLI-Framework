"""
Core interfaces for the CLI Framework

Defines abstract base classes that establish contracts for framework components.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Callable, TypeVar, Generic, Awaitable, TextIO
import sys

T = TypeVar('T')


class ConfigProvider(ABC):
    """
    Abstract interface for configuration management

    Implementations handle persistent storage and retrieval of configuration data
    with hierarchical key support.
    """

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """
        Retrieve configuration value by hierarchical key

        Args:
            key: Configuration key (supports dot notation: 'section.subsection.key')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        pass

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value by hierarchical key

        Args:
            key: Configuration key (supports dot notation)
            value: Value to store
        """
        pass

    @abstractmethod
    def save(self) -> None:
        """
        Persist configuration changes to storage

        Raises:
            ConfigError: If save operation fails
        """
        pass

    @abstractmethod
    def get_all(self) -> Dict[str, Any]:
        """
        Get complete configuration as dictionary

        Returns:
            Full configuration dictionary (deep copy)
        """
        pass


class MessageProvider(ABC):
    """
    Abstract interface for localized message management

    Handles multi-language support and message formatting.
    """

    @abstractmethod
    def get_message(self, key: str, default: Optional[str] = None, **kwargs: Any) -> str:
        """
        Get localized message with parameter substitution

        Args:
            key: Message key
            default: Default message if key not found
            **kwargs: Parameters for message formatting

        Returns:
            Formatted message string
        """
        pass

    @abstractmethod
    def set_language(self, language: str) -> None:
        """
        Set current language for messages

        Args:
            language: Language code (e.g., 'en', 'de')

        Raises:
            MessageError: If language not available
        """
        pass

    @abstractmethod
    def get_current_language(self) -> str:
        """
        Get current language code

        Returns:
            Current language code
        """
        pass


class OutputFormatter(ABC):
    """
    Abstract interface for terminal output formatting

    Handles styled text output, tables, progress bars, etc.
    """

    @abstractmethod
    def format(self, text: str, style: Optional[str] = None) -> str:
        """
        Format text with specified style

        Args:
            text: Text to format
            style: Style name (e.g., 'success', 'error', 'warning')

        Returns:
            Formatted text with ANSI codes if supported
        """
        pass

    @abstractmethod
    def render_table(self,
                    headers: List[str],
                    rows: List[List[str]],
                    max_col_width: Optional[int] = None,
                    file: TextIO = sys.stdout) -> None:
        """
        Render a formatted table to output stream

        Args:
            headers: Table column headers
            rows: Table data rows
            max_col_width: Maximum column width (None = auto-calculate)
            file: Output stream (default: stdout)
        """
        pass

    @abstractmethod
    def progress_bar(self, total: int, **kwargs: Any) -> Callable[[int], None]:
        """
        Create and return a progress bar update function

        Args:
            total: Total number of iterations
            **kwargs: Additional progress bar options (width, char, file, etc.)

        Returns:
            Function to update progress bar with current value
        """
        pass


class CommandHandler(ABC, Generic[T]):
    """
    Generic interface for command handlers

    Type parameter T represents the return type of the handler.
    """

    @abstractmethod
    async def handle(self, *args: Any, **kwargs: Any) -> T:
        """
        Execute command handler

        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Handler result of type T
        """
        pass


class CommandRegistry(ABC):
    """
    Abstract interface for command registration and lookup

    Manages the registry of all available commands and their metadata.
    """

    @abstractmethod
    def register(self, name: str, handler: Callable[..., Any], **metadata: Any) -> None:
        """
        Register a command with metadata

        Args:
            name: Command name
            handler: Command handler function
            **metadata: Command metadata including:
                - help (str): Command description
                - arguments (List[Dict]): Positional argument definitions
                - options (List[Dict]): Option definitions
                - aliases (List[str]): Alternative command names
                - examples (List[str]): Usage examples
                - is_async (bool): Whether handler is async
        """
        pass

    @abstractmethod
    def get_command(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve command metadata by name or alias

        Args:
            name: Command name or alias

        Returns:
            Command metadata dictionary (deep copy) or None if not found
        """
        pass

    @abstractmethod
    def list_commands(self) -> List[str]:
        """
        Get list of all registered command names

        Returns:
            List of command names (sorted)
        """
        pass

    @abstractmethod
    def autocomplete(self, prefix: str) -> List[str]:
        """
        Get commands matching prefix for autocomplete

        Args:
            prefix: Command name prefix

        Returns:
            List of matching command names (sorted)
        """
        pass


class ArgumentParser(ABC):
    """
    Abstract interface for command-line argument parsing

    Parses command-line arguments based on command metadata.
    """

    @abstractmethod
    def parse(self, args: List[str]) -> Dict[str, Any]:
        """
        Parse command-line arguments

        Args:
            args: List of command-line argument strings

        Returns:
            Dictionary with parsed command and parameters

        Raises:
            ValueError: If parsing fails
        """
        pass

    @abstractmethod
    def generate_help(self, command: str) -> str:
        """
        Generate detailed help text for a command

        Args:
            command: Command name

        Returns:
            Formatted help text
        """
        pass


class Middleware(ABC):
    """
    Abstract interface for command execution middleware

    Middleware wraps command execution to add cross-cutting concerns
    like logging, timing, authentication, etc.
    """

    @abstractmethod
    async def __call__(self, next_handler: Callable[[], Awaitable[Any]]) -> Any:
        """
        Execute middleware logic

        Args:
            next_handler: Next handler in the middleware chain (async callable)

        Returns:
            Result from handler chain
        """
        pass


class Hook(ABC):
    """
    Abstract interface for lifecycle hooks

    Hooks extend CLI behavior at specific lifecycle points.
    """

    @abstractmethod
    async def on_before_parse(self, args: List[str]) -> List[str]:
        """
        Called before argument parsing

        Args:
            args: Command-line arguments

        Returns:
            Modified arguments (or original)
        """
        pass

    @abstractmethod
    async def on_after_parse(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        Called after argument parsing

        Args:
            parsed: Parsed arguments

        Returns:
            Modified parsed arguments (or original)
        """
        pass

    @abstractmethod
    async def on_before_execute(self, command: str, kwargs: Dict[str, Any]) -> None:
        """
        Called before command execution

        Args:
            command: Command name
            kwargs: Command arguments
        """
        pass

    @abstractmethod
    async def on_after_execute(self, command: str, result: Any, exit_code: int) -> None:
        """
        Called after command execution

        Args:
            command: Command name
            result: Command result
            exit_code: Command exit code
        """
        pass

    @abstractmethod
    async def on_error(self, command: str, error: Exception) -> None:
        """
        Called when command execution fails

        Args:
            command: Command name
            error: Exception that occurred
        """
        pass
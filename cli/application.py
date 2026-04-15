"""
Main CLI application class.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import os
import shlex
import signal
import sys
import threading
import traceback
from contextvars import ContextVar, Token, copy_context
from typing import Any, Awaitable, Callable, Type, Union
from weakref import WeakKeyDictionary

from .command import CommandRegistryImpl, EnhancedArgumentParser
from .config import JsonConfigProvider
from .decorators import (
    BoundDecorators,
    CommandMetadataRegistry,
    is_async_function,
    register_commands,
)
from .interfaces import (
    ArgumentParser,
    CommandRegistry,
    ConfigProvider,
    Hook,
    MessageProvider,
    OutputFormatter,
)
from .messages import ConfigBasedMessageProvider
from .output import TerminalOutputFormatter, echo

_DEFAULT_SENTINEL: Any = object()

cli_context: ContextVar[dict[str, Any] | None] = ContextVar(
    "cli_context", default=None
)


def _get_context() -> dict[str, Any]:
    """Return current context dict or empty dict if unset (never the default)."""
    value = cli_context.get()
    return value if value is not None else {}


DEFAULT_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "version": {"type": "string"},
        "welcome_message": {"type": "string"},
        "help_hint": {"type": "string"},
        "prompt": {"type": "string"},
        "default_language": {"type": "string"},
        "current_language": {"type": "string"},
        "languages": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "messages": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
        },
    },
    "required": ["version", "default_language", "languages"],
}


class CLIError(Exception):
    """Base exception for CLI errors."""


class CommandExecutionError(CLIError):
    """Command execution failed."""


_signature_cache: WeakKeyDictionary[Callable[..., Any], inspect.Signature] = (
    WeakKeyDictionary()
)
_signature_cache_lock = threading.Lock()


def _cached_signature(func: Callable[..., Any]) -> inspect.Signature:
    cached = _signature_cache.get(func)
    if cached is not None:
        return cached
    with _signature_cache_lock:
        cached = _signature_cache.get(func)
        if cached is None:
            cached = inspect.signature(func)
            _signature_cache[func] = cached
        return cached


class MiddlewarePipeline:
    """Manages middleware chain execution."""

    def __init__(self) -> None:
        self._middlewares: list[
            Callable[[Callable[[], Awaitable[Any]]], Awaitable[Any]]
        ] = []
        self._lock = threading.Lock()

    def add(
        self,
        middleware: Callable[
            [Callable[[], Awaitable[Any]]], Awaitable[Any]
        ],
    ) -> None:
        with self._lock:
            if not asyncio.iscoroutinefunction(middleware):
                raise TypeError(
                    "Middleware must be an async function (coroutine)"
                )
            self._middlewares.append(middleware)

    def build(
        self,
        final_handler: Callable[[], Awaitable[Any]],
    ) -> Callable[[], Awaitable[Any]]:
        with self._lock:
            snapshot = list(self._middlewares)

        handler = final_handler
        for middleware in reversed(snapshot):
            def make_wrapper(
                mw: Callable[..., Awaitable[Any]],
                next_h: Callable[[], Awaitable[Any]],
            ) -> Callable[[], Awaitable[Any]]:
                async def wrapper() -> Any:
                    return await mw(next_h)

                return wrapper

            handler = make_wrapper(middleware, handler)
        return handler


class HookManager:
    """Manages global and per-command lifecycle hooks."""

    def __init__(self) -> None:
        self._hooks: list[Hook] = []
        self._per_command: dict[str, dict[str, list[Callable[..., Any]]]] = {}
        self._lock = threading.Lock()
        self._logger = logging.getLogger("cliframework.hooks")

    def add_hook(self, hook: Hook) -> None:
        with self._lock:
            self._hooks.append(hook)

    def add_per_command_hook(
        self,
        command_name: str,
        phase: str,
        func: Callable[..., Any],
    ) -> None:
        if phase not in ("before", "after", "error"):
            raise ValueError(
                f"phase must be 'before', 'after', or 'error', got {phase!r}"
            )
        with self._lock:
            self._per_command.setdefault(
                command_name, {"before": [], "after": [], "error": []}
            )[phase].append(func)

    async def on_before_parse(self, args: list[str]) -> list[str]:
        result = args
        for hook in self._snapshot():
            try:
                result = await hook.on_before_parse(result)
            except Exception as exc:
                self._logger.error(
                    f"Error in hook {hook.__class__.__name__}.on_before_parse: {exc}"
                )
        return result

    async def on_after_parse(
        self, parsed: dict[str, Any]
    ) -> dict[str, Any]:
        result = parsed
        for hook in self._snapshot():
            try:
                result = await hook.on_after_parse(result)
            except Exception as exc:
                self._logger.error(
                    f"Error in hook {hook.__class__.__name__}.on_after_parse: {exc}"
                )
        return result

    async def on_before_execute(
        self, command: str, kwargs: dict[str, Any]
    ) -> None:
        for hook in self._snapshot():
            try:
                await hook.on_before_execute(command, kwargs)
            except Exception as exc:
                self._logger.error(
                    f"Error in hook {hook.__class__.__name__}.on_before_execute: {exc}"
                )
        await self._run_per_command(command, "before", kwargs)

    async def on_after_execute(
        self, command: str, result: Any, exit_code: int
    ) -> None:
        for hook in self._snapshot():
            try:
                await hook.on_after_execute(command, result, exit_code)
            except Exception as exc:
                self._logger.error(
                    f"Error in hook {hook.__class__.__name__}.on_after_execute: {exc}"
                )
        await self._run_per_command(command, "after", result, exit_code)

    async def on_error(
        self, command: str, error: BaseException
    ) -> None:
        for hook in self._snapshot():
            try:
                await hook.on_error(command, error)
            except Exception as exc:
                self._logger.error(
                    f"Error in hook {hook.__class__.__name__}.on_error: {exc}"
                )
        await self._run_per_command(command, "error", error)

    def _snapshot(self) -> list[Hook]:
        with self._lock:
            return list(self._hooks)

    def _per_command_snapshot(
        self, command: str, phase: str
    ) -> list[Callable[..., Any]]:
        with self._lock:
            return list(
                self._per_command.get(command, {}).get(phase, [])
            )

    async def _run_per_command(
        self, command: str, phase: str, *args: Any
    ) -> None:
        for fn in self._per_command_snapshot(command, phase):
            try:
                if asyncio.iscoroutinefunction(fn):
                    await fn(*args)
                else:
                    result = fn(*args)
                    if inspect.isawaitable(result):
                        await result
            except Exception as exc:
                self._logger.error(
                    f"Per-command {phase} hook for '{command}' raised: {exc}",
                    exc_info=True,
                )


class CommandExecutor:
    """Handles command execution with middleware and hooks."""

    def __init__(
        self,
        commands: CommandRegistry,
        messages: MessageProvider,
        output: OutputFormatter,
        pipeline: MiddlewarePipeline,
        hook_manager: HookManager,
        bypass_middleware: set[str] | None = None,
    ) -> None:
        self.commands = commands
        self.messages = messages
        self.output = output
        self.pipeline = pipeline
        self.hook_manager = hook_manager
        self.bypass_middleware: set[str] = bypass_middleware or set()
        self._logger = logging.getLogger("cliframework.executor")

    async def execute(
        self, command: str, cli_instance: Any, **kwargs: Any
    ) -> int:
        command_meta = self.commands.get_command(command)

        if not command_meta:
            error_msg = self.messages.get_message(
                "command_not_found",
                default="Command '{command}' not found",
                command=command,
            )
            echo(error_msg, "error", formatter=self.output)
            suggestions = self._suggest_similar_commands(command)
            if suggestions:
                did_you_mean = self.messages.get_message(
                    "did_you_mean",
                    default="Did you mean: {suggestions}?",
                    suggestions=", ".join(suggestions),
                )
                echo(did_you_mean, "info", formatter=self.output)
            return 1

        handler: Callable[..., Any] = command_meta.get("handler")
        if not handler:
            echo(
                f"Command '{command}' has no handler",
                "error",
                formatter=self.output,
            )
            return 1

        try:
            positional_args, command_kwargs = self._bind_arguments(
                command, handler, kwargs
            )
        except CLIError as exc:
            echo(str(exc), "error", formatter=self.output)
            return 1

        token: Token = cli_context.set(
            {
                "command": command,
                "args": kwargs,
                "cli_instance": cli_instance,
            }
        )

        try:
            await self.hook_manager.on_before_execute(command, command_kwargs)

            async def execute_handler() -> Any:
                if is_async_function(handler):
                    return await handler(*positional_args, **command_kwargs)
                ctx = copy_context()
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: ctx.run(
                        functools.partial(
                            handler, *positional_args, **command_kwargs
                        )
                    ),
                )
                if inspect.isawaitable(result):
                    return await result
                return result

            if command in self.bypass_middleware:
                final_handler = execute_handler
            else:
                final_handler = self.pipeline.build(execute_handler)

            result = await final_handler()
            if inspect.isawaitable(result):
                result = await result

            if isinstance(result, bool):
                exit_code = 1 if result is False else 0
            elif isinstance(result, int):
                exit_code = result
            else:
                exit_code = 0

            await self.hook_manager.on_after_execute(
                command, result, exit_code
            )
            return exit_code

        except asyncio.CancelledError as exc:
            self._logger.info(f"Command '{command}' was cancelled")
            await self.hook_manager.on_error(command, exc)
            raise
        except KeyboardInterrupt:
            self._logger.info("Command execution interrupted by user")
            raise
        except CommandExecutionError:
            raise
        except Exception as exc:
            self._logger.error(
                f"Error executing command '{command}': {exc}", exc_info=True
            )
            await self.hook_manager.on_error(command, exc)

            error_msg = self.messages.get_message(
                "execution_error",
                default="Error: {error}",
                error=str(exc),
            )
            echo(error_msg, "error", formatter=self.output)

            if self._logger.isEnabledFor(logging.DEBUG):
                echo("\nTraceback:", "error", formatter=self.output)
                print(traceback.format_exc(), file=sys.stderr)
            raise CommandExecutionError(str(exc)) from exc
        finally:
            cli_context.reset(token)

    def _bind_arguments(
        self,
        command: str,
        handler: Callable[..., Any],
        kwargs: dict[str, Any],
    ) -> tuple[list[Any], dict[str, Any]]:
        try:
            sig = _cached_signature(handler)
        except (TypeError, ValueError) as exc:
            raise CLIError(f"Cannot inspect handler signature: {exc}")

        positional_args: list[Any] = []
        command_kwargs: dict[str, Any] = {}
        has_var_keyword = False
        param_names: list[str] = []
        required_missing: list[str] = []
        reserved_keys = {"_cli_help", "_cli_show_help"}

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                continue
            if param.kind == inspect.Parameter.VAR_KEYWORD:
                has_var_keyword = True
                continue

            param_names.append(param_name)
            if param_name in kwargs:
                value = kwargs[param_name]
                if param.kind == inspect.Parameter.POSITIONAL_ONLY:
                    positional_args.append(value)
                else:
                    command_kwargs[param_name] = value
            elif param.default is not inspect.Parameter.empty:
                command_kwargs[param_name] = param.default
            else:
                required_missing.append(param_name)

        if required_missing:
            args_str = ", ".join(f"'{n}'" for n in required_missing)
            raise CLIError(
                f"Missing required arguments for command '{command}': {args_str}"
            )

        unknown_keys = [
            k for k in kwargs
            if k not in param_names and k not in reserved_keys
        ]
        if unknown_keys:
            if has_var_keyword:
                for key in unknown_keys:
                    command_kwargs[key] = kwargs[key]
            else:
                unknown_str = ", ".join(f"--{k}" for k in unknown_keys)
                raise CLIError(
                    f"Unknown options for command '{command}': {unknown_str}"
                )

        return positional_args, command_kwargs

    def _suggest_similar_commands(
        self, command: str, max_suggestions: int = 3
    ) -> list[str]:
        def levenshtein(s1: str, s2: str, max_dist: int = 3) -> int:
            if len(s1) < len(s2):
                return levenshtein(s2, s1, max_dist)
            if not s2:
                return len(s1)
            if abs(len(s1) - len(s2)) > max_dist:
                return max_dist + 1

            previous_row = list(range(len(s2) + 1))
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                min_in_row = i + 1
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    val = min(insertions, deletions, substitutions)
                    current_row.append(val)
                    min_in_row = min(min_in_row, val)
                if min_in_row > max_dist:
                    return max_dist + 1
                previous_row = current_row
            return previous_row[-1]

        all_commands = self.commands.list_commands()
        suggestions: list[tuple[int, str]] = []
        command_lower = command.lower()
        for cmd in all_commands:
            if abs(len(cmd) - len(command)) > 3:
                continue
            distance = levenshtein(command_lower, cmd.lower(), max_dist=3)
            if distance <= 3:
                suggestions.append((distance, cmd))
        suggestions.sort(key=lambda x: (x[0], x[1]))
        return [cmd for _, cmd in suggestions[:max_suggestions]]


class InteractiveShell:
    """Interactive REPL shell."""

    def __init__(self, cli_instance: CLI) -> None:
        self.cli = cli_instance
        self._logger = logging.getLogger("cliframework.shell")
        self._interrupt_count = 0

    def setup_readline_completion(self) -> None:
        if not self.cli._use_readline:
            return
        try:
            import readline
        except ImportError:
            try:
                import pyreadline3 as readline
            except ImportError:
                self._logger.warning("readline/pyreadline3 not available")
                self.cli._use_readline = False
                return

        commands = self.cli.commands

        class CommandCompleter:
            def __init__(self) -> None:
                self.matches: list[str] = []

            def complete(self, text: str, state: int) -> str | None:
                if state == 0:
                    if text:
                        self.matches = commands.autocomplete(text)
                    else:
                        self.matches = commands.list_commands()
                try:
                    return self.matches[state]
                except IndexError:
                    return None

        completer = CommandCompleter()
        readline.set_completer(completer.complete)
        readline.parse_and_bind("tab: complete")
        readline.set_completer_delims(" \t\n")

    def handle_interrupt(self) -> bool:
        self._interrupt_count += 1
        if self._interrupt_count == 1:
            echo(
                "\n^C (Press Ctrl+C again to force exit, or type 'exit')",
                "warning",
                formatter=self.cli.output,
            )
            return False
        echo("\nForce exiting...", "error", formatter=self.cli.output)
        return True

    async def run(self) -> int:
        self.setup_readline_completion()

        echo(
            self.cli.config.get(
                "welcome_message", f"Welcome to {self.cli.name}"
            ),
            "info",
            formatter=self.cli.output,
        )
        echo(
            self.cli.config.get(
                "help_hint", "Type 'help' for commands or 'exit' to quit"
            ),
            "info",
            formatter=self.cli.output,
        )
        print("")

        exit_code = 0

        while not self.cli._shutdown_requested:
            iteration_exit_code = 0

            try:
                self._interrupt_count = 0
                self.cli._maybe_print_pending_signal_message()
                prompt: str = self.cli.config.get(
                    "prompt", f"{self.cli.name}> "
                )

                try:
                    user_input: str = input(prompt).strip()
                except UnicodeDecodeError:
                    if self.handle_interrupt():
                        break
                    print("")
                    continue
                except EOFError:
                    echo("\nExiting...", "info", formatter=self.cli.output)
                    break
                except KeyboardInterrupt:
                    if self.handle_interrupt():
                        break
                    print("")
                    continue

                if self.cli._shutdown_requested:
                    echo(
                        "\nShutdown requested, exiting...",
                        "info",
                        formatter=self.cli.output,
                    )
                    break

                if not user_input:
                    continue

                if user_input.lower() in ("exit", "quit", "q"):
                    self.cli._shutdown_requested = True
                    echo("Goodbye!", "info", formatter=self.cli.output)
                    break

                try:
                    if self.cli._shell_posix:
                        input_args = shlex.split(user_input)
                    else:
                        raw_tokens = shlex.split(user_input, posix=False)
                        input_args = [
                            t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'")
                            else t
                            for t in raw_tokens
                        ]
                except ValueError as exc:
                    echo(
                        f"Invalid input: {exc}",
                        "error",
                        formatter=self.cli.output,
                    )
                    continue

                try:
                    input_args = await self.cli.hook_manager.on_before_parse(
                        input_args
                    )
                    parsed = self.cli.parser.parse(input_args)
                    parsed = await self.cli.hook_manager.on_after_parse(parsed)

                    command = parsed.get("command")
                    if not command:
                        echo(
                            "No command specified",
                            "error",
                            formatter=self.cli.output,
                        )
                        continue

                    if parsed.get("_cli_show_help", False):
                        help_text = self.cli.parser.generate_help(command)
                        echo(help_text, "info", formatter=self.cli.output)
                        continue

                    command_kwargs = {
                        k: v
                        for k, v in parsed.items()
                        if k != "command" and not k.startswith("_cli_")
                    }
                    iteration_exit_code = await self.cli.executor.execute(
                        command, self.cli, **command_kwargs
                    )

                    if iteration_exit_code != 0:
                        echo(
                            f"Command returned exit code: {iteration_exit_code}",
                            "warning",
                            formatter=self.cli.output,
                        )

                except asyncio.CancelledError:
                    echo(
                        "\nCommand cancelled",
                        "warning",
                        formatter=self.cli.output,
                    )
                    raise
                except ValueError as exc:
                    echo(f"Error: {exc}", "error", formatter=self.cli.output)
                    iteration_exit_code = 1
                except KeyboardInterrupt:
                    if self.handle_interrupt():
                        break
                except CommandExecutionError:
                    iteration_exit_code = 1
                except Exception as exc:
                    self._logger.error(
                        f"Unexpected error: {exc}", exc_info=True
                    )
                    echo(
                        f"Unexpected error: {exc}",
                        "error",
                        formatter=self.cli.output,
                    )
                    iteration_exit_code = 1

                exit_code = iteration_exit_code
                print("")

            except asyncio.CancelledError:
                break
            except KeyboardInterrupt:
                if self.handle_interrupt():
                    break
                print("")
                continue

        return exit_code


class CLI:
    """Main CLI application class."""

    def __init__(
        self,
        name: str = "app",
        config_path: str | None = None,
        config_provider: ConfigProvider | None = None,
        config_schema: dict[str, Any] | None = None,
        message_provider: MessageProvider | None = None,
        output_formatter: OutputFormatter | None = None,
        command_registry: CommandRegistry | None = None,
        argument_parser: ArgumentParser | None = None,
        log_level: int = logging.INFO,
        auto_logging_middleware: bool = False,
        include_default_registry: bool = True,
        shell_posix: bool | None = None,
    ) -> None:
        self._setup_logging(log_level)
        self._logger: logging.Logger = logging.getLogger(
            f"cliframework.app.{name}"
        )
        self._logger.info(f"Initializing CLI application '{name}'")
        self.name: str = name

        self._registry: CommandMetadataRegistry = CommandMetadataRegistry()
        self._decorators: BoundDecorators = BoundDecorators(self._registry)
        self._include_default_registry: bool = include_default_registry
        from weakref import WeakSet
        self._registered_funcs: WeakSet = WeakSet()

        if config_provider is None:
            if config_path is None:
                config_dir = os.path.expanduser(f"~/.config/{name}")
                os.makedirs(config_dir, exist_ok=True)
                config_path = os.path.join(config_dir, f"{name}.json")

            default_config = self._build_default_config(name)
            schema = config_schema or DEFAULT_CONFIG_SCHEMA
            config_provider = JsonConfigProvider(
                config_path,
                default_config=default_config,
                schema=schema,
            )

        self.config: ConfigProvider = config_provider
        self.messages: MessageProvider = (
            message_provider or ConfigBasedMessageProvider(self.config)
        )
        self.output: OutputFormatter = (
            output_formatter or TerminalOutputFormatter()
        )
        self.commands: CommandRegistry = (
            command_registry or CommandRegistryImpl()
        )
        self.parser: ArgumentParser = (
            argument_parser or EnhancedArgumentParser(self.commands)
        )

        self.pipeline = MiddlewarePipeline()
        self.hook_manager = HookManager()
        self.executor = CommandExecutor(
            self.commands,
            self.messages,
            self.output,
            self.pipeline,
            self.hook_manager,
            bypass_middleware={"help", "version", "exit"},
        )

        self.exit_code: int = 0
        self._running: bool = False
        self._shutdown_requested: bool = False
        self._commands_registered: bool = False
        self._cleanup_callbacks: list[
            Union[Callable[[], None], Callable[[], Awaitable[None]]]
        ] = []
        self._use_readline: bool = True
        self._pending_signal_message: str | None = None
        self._shell_posix: bool = (
            shell_posix if shell_posix is not None else os.name != "nt"
        )

        self._setup_signal_handlers()
        self._register_default_commands()

        if auto_logging_middleware:
            self.use_logging_middleware()

    def _build_default_config(self, name: str) -> dict[str, Any]:
        return {
            "version": "0.1.0",
            "welcome_message": f"Welcome to {name}",
            "help_hint": "Type 'help' for available commands",
            "prompt": f"{name}> ",
            "default_language": "en",
            "current_language": "en",
            "languages": ["en"],
            "messages": {
                "en": {
                    "prompt": f"{name}> ",
                    "unknown_command": "Unknown command. Type 'help' for available commands.",
                    "available_commands": "Available commands:",
                    "app_quit": f"Exiting {name}. Goodbye!",
                    "command_not_found": "Command '{command}' not found.",
                    "execution_error": "Error executing command: {error}",
                    "did_you_mean": "Did you mean: {suggestions}?",
                }
            },
        }

    def _setup_logging(self, log_level: int) -> None:
        logger = logging.getLogger("cliframework")
        logger.setLevel(log_level)
        for handler in logger.handlers:
            handler.setLevel(log_level)
        if not logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(log_level)
            console_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            )
            logger.addHandler(console_handler)

    def _setup_signal_handlers(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            self._logger.warning(
                "Signal handlers can only be registered from main thread"
            )
            return

        def signal_handler(sig: int, frame: Any) -> None:
            signal_name = "SIGINT" if sig == signal.SIGINT else "SIGTERM"
            if not self._shutdown_requested:
                self._shutdown_requested = True
                self._pending_signal_message = (
                    f"Received {signal_name}, shutdown requested"
                )
            else:
                self._pending_signal_message = (
                    f"Received second {signal_name}, forcing exit"
                )
                self._emergency_cleanup()
                os._exit(1)

        try:
            signal.signal(signal.SIGINT, signal_handler)
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, signal_handler)
        except (ValueError, AttributeError, OSError) as exc:
            self._logger.warning(f"Could not set signal handlers: {exc}")

    def _maybe_print_pending_signal_message(self) -> None:
        msg = self._pending_signal_message
        if msg is None:
            return
        self._pending_signal_message = None
        try:
            echo(f"\n{msg}", "warning", formatter=self.output)
        except (OSError, IOError):
            pass

    def _emergency_cleanup(self) -> None:
        for callback in self._cleanup_callbacks:
            try:
                if not asyncio.iscoroutinefunction(callback):
                    callback()
            except Exception as exc:
                self._logger.error(f"Emergency cleanup error: {exc}")

    def _cb_name(self, cb: Any) -> str:
        return getattr(
            cb,
            "__name__",
            getattr(cb, "__qualname__", cb.__class__.__name__),
        )

    async def _run_cleanup_callbacks(self) -> None:
        for callback in self._cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await asyncio.wait_for(callback(), timeout=5.0)
                else:
                    result = callback()
                    if inspect.isawaitable(result):
                        await asyncio.wait_for(result, timeout=5.0)
            except asyncio.TimeoutError:
                self._logger.error(
                    f"Cleanup callback {self._cb_name(callback)} timed out"
                )
            except Exception as exc:
                self._logger.error(
                    f"Error in cleanup callback {self._cb_name(callback)}: {exc}"
                )

    def add_cleanup_callback(
        self,
        callback: Union[Callable[[], None], Callable[[], Awaitable[None]]],
    ) -> None:
        self._cleanup_callbacks.append(callback)

    def add_hook(self, hook: Hook) -> None:
        self.hook_manager.add_hook(hook)

    def use(
        self,
        middleware: Callable[
            [Callable[[], Awaitable[Any]]], Awaitable[Any]
        ],
    ) -> None:
        self.pipeline.add(middleware)

    def use_logging_middleware(self) -> None:
        async def logging_middleware(
            next_handler: Callable[[], Awaitable[Any]],
        ) -> Any:
            ctx = _get_context()
            command = ctx.get("command", "unknown")
            args = ctx.get("args", {})
            self._logger.debug(
                f"[Middleware] Executing '{command}' with args: {args}"
            )
            try:
                result = await next_handler()
                self._logger.debug(
                    f"[Middleware] '{command}' completed: {result}"
                )
                return result
            except Exception as exc:
                self._logger.debug(
                    f"[Middleware] '{command}' failed: {exc}"
                )
                raise

        self.use(logging_middleware)

    def get_context(self) -> dict[str, Any]:
        return dict(_get_context())

    def set_context(self, **kwargs: Any) -> None:
        ctx = dict(_get_context())
        ctx.update(kwargs)
        cli_context.set(ctx)

    def enable_readline(self, enable: bool = True) -> None:
        self._use_readline = enable

    def _format_command_signature(
        self, command_meta: dict[str, Any]
    ) -> str:
        parts: list[str] = []
        for arg in command_meta.get("arguments", []):
            parts.append(
                f"[{arg['name']}]" if arg.get("optional") else f"<{arg['name']}>"
            )
        for opt in command_meta.get("options", []):
            if opt.get("is_flag"):
                if opt.get("default") is True:
                    parts.append(f"[--no-{opt['name']}]")
                else:
                    parts.append(f"[--{opt['name']}]")
            else:
                parts.append(f"[--{opt['name']} <value>]")
        return " ".join(parts)

    def _register_default_commands(self) -> None:
        def help_command(cmd: str | None = None) -> int:
            """Show help for command or list all commands."""
            if cmd:
                cmd_meta = self.commands.get_command(cmd)
                if cmd_meta:
                    try:
                        help_text = self.parser.generate_help(cmd)
                        echo(help_text, "info", formatter=self.output)
                    except Exception as exc:
                        echo(
                            f"Error generating help: {exc}",
                            "error",
                            formatter=self.output,
                        )
                        return 1
                    return 0

                if hasattr(self.commands, "find_by_prefix"):
                    matching_commands = self.commands.find_by_prefix(cmd)
                else:
                    prefix_with_dot = cmd + "."
                    matching_commands = [
                        c for c in self.commands.list_commands()
                        if c.startswith(prefix_with_dot) or c == cmd
                    ]

                if matching_commands:
                    echo(
                        f"Commands under '{cmd}':",
                        "header",
                        formatter=self.output,
                    )
                    print("")
                    for command in sorted(matching_commands):
                        sub_meta = self.commands.get_command(command)
                        if sub_meta:
                            help_text = sub_meta.get("help", "No description")
                            signature = self._format_command_signature(sub_meta)
                            aliases = sub_meta.get("aliases", [])
                            line = f"  {command:30} {help_text}"
                            if signature:
                                line += (
                                    f"\n    {'':30} Usage: {command} {signature}"
                                )
                            if aliases:
                                line += f" (aliases: {', '.join(aliases)})"
                            print(line)
                    print("")
                    echo(
                        "Use 'help <command>' for detailed help on a specific command.",
                        "info",
                        formatter=self.output,
                    )
                    return 0

                error_msg = self.messages.get_message(
                    "command_not_found",
                    default="Command '{command}' not found",
                    command=cmd,
                )
                echo(error_msg, "error", formatter=self.output)
                suggestions = self.executor._suggest_similar_commands(cmd)
                if suggestions:
                    did_you_mean = self.messages.get_message(
                        "did_you_mean",
                        default="Did you mean: {suggestions}?",
                        suggestions=", ".join(suggestions),
                    )
                    echo(did_you_mean, "info", formatter=self.output)
                return 1

            echo(
                self.messages.get_message(
                    "available_commands", "Available commands:"
                ),
                "header",
                formatter=self.output,
            )

            commands = self.commands.list_commands()
            grouped: dict[str, list[str]] = {}
            standalone: list[str] = []
            for command in commands:
                if "." in command:
                    prefix = command.split(".")[0]
                    grouped.setdefault(prefix, []).append(command)
                else:
                    standalone.append(command)

            for command in sorted(standalone):
                cmd_meta = self.commands.get_command(command)
                if cmd_meta:
                    help_text = cmd_meta.get("help", "No description")
                    signature = self._format_command_signature(cmd_meta)
                    aliases = cmd_meta.get("aliases", [])
                    line = f"  {command:20} {help_text}"
                    if signature:
                        line += f"\n    {'':20} Usage: {command} {signature}"
                    if aliases:
                        line += f" (aliases: {', '.join(aliases)})"
                    print(line)

            if grouped:
                print("")
                echo("Command groups:", "header", formatter=self.output)
                for prefix in sorted(grouped):
                    cmds = grouped[prefix]
                    print(
                        f"  {prefix:20} ({len(cmds)} commands) - "
                        f"use 'help {prefix}' for details"
                    )
            return 0

        self.commands.register(
            "help",
            help_command,
            help="Show help information",
            arguments=[
                {
                    "name": "cmd",
                    "help": "Command to show help for",
                    "type": str,
                    "optional": True,
                }
            ],
            options=[],
            is_async=False,
        )

        def version_command() -> int:
            """Display application version."""
            version = self.config.get("version", "unknown")
            echo(
                f"{self.name} version {version}",
                "info",
                formatter=self.output,
            )
            return 0

        self.commands.register(
            "version",
            version_command,
            help="Show application version",
            arguments=[],
            options=[],
            is_async=False,
        )

        def exit_command() -> int:
            """Exit the CLI application."""
            self._shutdown_requested = True
            msg = self.messages.get_message("app_quit", "Goodbye!")
            echo(msg, "info", formatter=self.output)
            return 0

        self.commands.register(
            "exit",
            exit_command,
            help="Exit the application",
            arguments=[],
            options=[],
            aliases=["quit", "q"],
            is_async=False,
        )

    def command(
        self,
        name: str | None = None,
        help: str | None = None,
        aliases: list[str] | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._decorators.command(name, help, aliases)

    def argument(
        self,
        name: str,
        help: str | None = None,
        type: Type[Any] = str,
        optional: bool = False,
        group: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._decorators.argument(name, help, type, optional, group)

    def option(
        self,
        name: str,
        short: str | None = None,
        help: str | None = None,
        type: Type[Any] = str,
        default: Any = _DEFAULT_SENTINEL,
        default_factory: Callable[[], Any] | None = None,
        is_flag: bool | None = None,
        group: str | None = None,
        exclusive_group: str | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        kwargs: dict[str, Any] = {
            "short": short,
            "help": help,
            "type": type,
            "default_factory": default_factory,
            "is_flag": is_flag,
            "group": group,
            "exclusive_group": exclusive_group,
        }
        if default is not _DEFAULT_SENTINEL:
            kwargs["default"] = default
        return self._decorators.option(name, **kwargs)

    def example(
        self, example_text: str
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._decorators.example(example_text)

    def group(
        self,
        name: str | None = None,
        help: str | None = None,
    ) -> Callable[[Type[Any]], Type[Any]]:
        return self._decorators.group(name, help)

    def before(
        self, command_name: str
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a per-command pre-execution hook."""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.hook_manager.add_per_command_hook(
                command_name, "before", func
            )
            return func
        return decorator

    def after(
        self, command_name: str
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a per-command post-execution hook."""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.hook_manager.add_per_command_hook(
                command_name, "after", func
            )
            return func
        return decorator

    def on_error_for(
        self, command_name: str
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a per-command error hook."""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.hook_manager.add_per_command_hook(
                command_name, "error", func
            )
            return func
        return decorator

    def load_plugins(
        self, group: str, fail_fast: bool = False
    ) -> dict[str, bool]:
        """Discover and invoke plugins via importlib.metadata entry points."""
        from .plugins import load_plugins as _load_plugins
        return _load_plugins(self, group, fail_fast=fail_fast)

    def generate_completion(self, shell: str) -> str:
        """Return shell completion script for bash/zsh/fish."""
        from .completion import generate_completion as _gen
        if not self._commands_registered:
            self.register_all_commands()
            self._commands_registered = True
        return _gen(self, shell)

    def install_completion(
        self, shell: str, path: str | None = None
    ) -> str:
        """Write completion script to disk; returns the path written."""
        script = self.generate_completion(shell)
        if path is None:
            home = os.path.expanduser("~")
            defaults = {
                "bash": os.path.join(
                    home, ".bash_completion.d", f"{self.name}.bash"
                ),
                "zsh": os.path.join(
                    home, ".zsh", "completions", f"_{self.name}"
                ),
                "fish": os.path.join(
                    home, ".config", "fish", "completions",
                    f"{self.name}.fish",
                ),
            }
            if shell.lower() not in defaults:
                raise ValueError(f"Unsupported shell: {shell}")
            path = defaults[shell.lower()]
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(script)
        return path

    def generate_from(
        self,
        obj: Union[Type[Any], object, Callable[..., Any]],
        safe_mode: bool = True,
    ) -> None:
        if inspect.isclass(obj):
            try:
                instance = obj()
            except TypeError as exc:
                if safe_mode:
                    self._logger.warning(
                        f"Skipping class {obj.__name__}: cannot instantiate "
                        f"without arguments ({exc})"
                    )
                    return
                raise ValueError(f"Cannot instantiate class: {exc}")
            except Exception as exc:
                self._logger.error(f"Failed to instantiate class {obj}: {exc}")
                if safe_mode:
                    return
                raise ValueError(f"Cannot instantiate class: {exc}")
            self._generate_from_instance(instance, safe_mode)
        elif inspect.isfunction(obj) or inspect.ismethod(obj):
            self._generate_from_function(obj, safe_mode)
        elif hasattr(obj, "__dict__"):
            self._generate_from_instance(obj, safe_mode)
        else:
            raise ValueError(f"Cannot generate CLI from {type(obj)}")

    def _generate_from_instance(
        self, instance: Any, safe_mode: bool
    ) -> None:
        class_name = instance.__class__.__name__.lower()
        for attr_name in dir(instance):
            if safe_mode and attr_name.startswith("_"):
                continue
            try:
                attr_obj = getattr(type(instance), attr_name, None)
                if attr_obj is None or not callable(attr_obj):
                    continue
                attr = getattr(instance, attr_name)
                if not callable(attr):
                    continue
                command_name = f"{class_name}.{attr_name}"
                self._auto_generate_command(command_name, attr)
            except Exception as exc:
                self._logger.warning(f"Error processing {attr_name}: {exc}")

    def _generate_from_function(
        self, func: Callable[..., Any], safe_mode: bool
    ) -> None:
        func_name = func.__name__
        if safe_mode and func_name.startswith("_"):
            raise ValueError(f"Cannot expose private function: {func_name}")
        self._auto_generate_command(func_name, func)

    def _auto_generate_command(
        self, name: str, func: Callable[..., Any]
    ) -> None:
        from .decorators import _is_flag_param

        sig = _cached_signature(func)
        doc = inspect.getdoc(func) or f"Command {name}"

        arguments: list[dict[str, Any]] = []
        options: list[dict[str, Any]] = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_type = (
                param.annotation
                if param.annotation is not inspect.Parameter.empty
                else str
            )

            if param.default is not inspect.Parameter.empty:
                options.append(
                    {
                        "name": param_name,
                        "help": f"Option {param_name}",
                        "type": param_type,
                        "default": param.default,
                        "is_flag": _is_flag_param(param_type, param.default),
                    }
                )
            else:
                arguments.append(
                    {
                        "name": param_name,
                        "help": f"Argument {param_name}",
                        "type": param_type,
                        "optional": False,
                    }
                )

        self.commands.register(
            name,
            func,
            help=doc,
            arguments=arguments,
            options=options,
            is_async=is_async_function(func),
        )

    def register_all_commands(self) -> int:
        count = register_commands(
            self, include_default=self._include_default_registry
        )
        self._logger.info(
            f"Registered {count} decorator-defined commands"
        )
        return count

    @staticmethod
    def _extract_config_file_arg(
        args: list[str],
    ) -> tuple[str | None, list[str]]:
        """Pull --config-file value out of args before normal parsing."""
        out: list[str] = []
        config_file: str | None = None
        i = 0
        while i < len(args):
            tok = args[i]
            if tok == "--config-file":
                if i + 1 >= len(args):
                    raise ValueError(
                        "--config-file requires a path argument"
                    )
                config_file = args[i + 1]
                i += 2
                continue
            if tok.startswith("--config-file="):
                config_file = tok.split("=", 1)[1]
                i += 1
                continue
            out.append(tok)
            i += 1
        return config_file, out

    def _reload_config_from(self, path: str) -> None:
        """Replace current config provider with one loaded from path."""
        default_config = self._build_default_config(self.name)
        self.config = JsonConfigProvider(
            path,
            default_config=default_config,
            schema=DEFAULT_CONFIG_SCHEMA,
        )
        self.messages = ConfigBasedMessageProvider(self.config)
        self.executor.messages = self.messages

    async def run_interactive(self) -> int:
        if not self._commands_registered:
            self.register_all_commands()
            self._commands_registered = True

        self._running = True
        shell = InteractiveShell(self)
        try:
            exit_code = await shell.run()
            self.exit_code = exit_code
            return exit_code
        except asyncio.CancelledError:
            self.exit_code = 130
            raise
        finally:
            self._running = False
            await self._run_cleanup_callbacks()

    async def run_async(self, args: list[str] | None = None) -> int:
        if args is None:
            args = sys.argv[1:]

        try:
            config_file, args = self._extract_config_file_arg(args)
        except ValueError as exc:
            echo(f"Error: {exc}", "error", formatter=self.output)
            self.exit_code = 1
            return 1
        if config_file:
            try:
                self._reload_config_from(config_file)
            except Exception as exc:
                echo(
                    f"Failed to load config from {config_file}: {exc}",
                    "error",
                    formatter=self.output,
                )
                self.exit_code = 1
                return 1

        if not self._commands_registered:
            self.register_all_commands()
            self._commands_registered = True

        if not args:
            return await self.run_interactive()

        try:
            args = await self.hook_manager.on_before_parse(args)
            parsed = self.parser.parse(args)
            parsed = await self.hook_manager.on_after_parse(parsed)

            command = parsed.get("command")
            if not command:
                echo(
                    "No command specified. Use 'help' for available commands.",
                    "error",
                    formatter=self.output,
                )
                self.exit_code = 1
                return 1

            if parsed.get("_cli_show_help", False):
                help_text = self.parser.generate_help(command)
                echo(help_text, "info", formatter=self.output)
                self.exit_code = 0
                return 0

            command_kwargs = {
                k: v
                for k, v in parsed.items()
                if k != "command" and not k.startswith("_cli_")
            }

            try:
                exit_code = await self.executor.execute(
                    command, self, **command_kwargs
                )
                self.exit_code = exit_code
                return exit_code
            except CommandExecutionError:
                self.exit_code = 1
                return 1

        except ValueError as exc:
            echo(f"Error: {exc}", "error", formatter=self.output)
            self.exit_code = 1
            return 1
        except KeyboardInterrupt:
            echo("\nInterrupted by user", "warning", formatter=self.output)
            self.exit_code = 130
            return 130
        except asyncio.CancelledError:
            self.exit_code = 130
            raise
        except Exception as exc:
            self._logger.error(f"Unexpected error: {exc}", exc_info=True)
            echo(f"Unexpected error: {exc}", "error", formatter=self.output)
            self.exit_code = 1
            return 1
        finally:
            await self._run_cleanup_callbacks()

    def run(self, args: list[str] | None = None) -> int:
        try:
            return asyncio.run(self.run_async(args))
        except KeyboardInterrupt:
            echo("\nInterrupted by user", "warning", formatter=self.output)
            return 130


__all__ = [
    "CLI",
    "CLIError",
    "CommandExecutionError",
    "MiddlewarePipeline",
    "HookManager",
    "CommandExecutor",
    "InteractiveShell",
    "DEFAULT_CONFIG_SCHEMA",
    "cli_context",
]
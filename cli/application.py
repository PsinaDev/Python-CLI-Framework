"""
Main CLI application class

Provides the core CLI application with command execution, middleware support,
async operations, signal handling, and configuration management.
"""

import asyncio
import inspect
import os
import sys
import logging
import traceback
import signal
import threading
import functools
from typing import Any, Callable, Dict, List, Optional, Union, Type, Awaitable
from contextvars import ContextVar, copy_context

from .interfaces import (
    ConfigProvider, MessageProvider, OutputFormatter,
    CommandRegistry, ArgumentParser
)
from .config import JsonConfigProvider
from .messages import ConfigBasedMessageProvider
from .output import TerminalOutputFormatter, echo
from .command import CommandRegistryImpl, EnhancedArgumentParser
from .decorators import register_commands, is_async_function

cli_context: ContextVar[Dict[str, Any]] = ContextVar('cli_context', default={})

DEFAULT_CONFIG_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "version": {
            "type": "string"
        },
        "welcome_message": {
            "type": "string"
        },
        "help_hint": {
            "type": "string"
        },
        "prompt": {
            "type": "string"
        },
        "default_language": {
            "type": "string"
        },
        "current_language": {
            "type": "string"
        },
        "languages": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1
        },
        "messages": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "additionalProperties": {"type": "string"}
            }
        }
    },
    "required": ["version", "default_language", "languages"]
}


class CLIError(Exception):
    """Base exception for CLI errors"""
    pass


class CommandExecutionError(CLIError):
    """Command execution failed"""
    pass


class MiddlewarePipeline:
    """
    Manages middleware chain execution

    Middleware Contract:
    - Each middleware must be a callable that accepts next_handler: Callable[[], Awaitable[Any]]
    - Middleware must call `await next_handler()` to continue the chain
    - Middleware receives no command-specific arguments; use cli_context.get() to access context
    - Return value is propagated through the chain
    """

    def __init__(self):
        self._middlewares: List[Callable[[Callable[[], Awaitable[Any]]], Awaitable[Any]]] = []
        self._logger = logging.getLogger('cli.middleware')

    def add(self, middleware: Union[Callable[[Callable[[], Awaitable[Any]]], Awaitable[Any]],
                                   Callable[[Callable[[], Awaitable[Any]]], Any]]) -> None:
        """Add middleware to pipeline"""
        if asyncio.iscoroutinefunction(middleware):
            self._middlewares.append(middleware)
        elif callable(middleware):
            @functools.wraps(middleware)
            async def async_wrapper(next_handler: Callable[[], Awaitable[Any]]) -> Any:
                result = middleware(next_handler)
                if inspect.isawaitable(result):
                    return await result
                return result
            self._middlewares.append(async_wrapper)
        else:
            raise TypeError("Middleware must be a callable")

    def build(self, final_handler: Callable[[], Awaitable[Any]]) -> Callable[[], Awaitable[Any]]:
        """
        Build middleware chain with proper closure handling
        """
        handler = final_handler

        # Build chain in reverse order
        for middleware in reversed(self._middlewares):
            # Create a proper wrapper that captures current middleware and handler
            def make_wrapper(mw: Callable, next_h: Callable) -> Callable[[], Awaitable[Any]]:
                async def wrapper() -> Any:
                    return await mw(next_h)
                return wrapper

            handler = make_wrapper(middleware, handler)

        return handler


class CommandExecutor:
    """Handles command execution with middleware support"""

    def __init__(self, commands: CommandRegistry, messages: MessageProvider,
                 output: OutputFormatter, pipeline: MiddlewarePipeline):
        self.commands = commands
        self.messages = messages
        self.output = output
        self.pipeline = pipeline
        self._logger = logging.getLogger('cli.executor')

    def _suggest_similar_commands(self, command: str, max_suggestions: int = 3) -> List[str]:
        """
        Find similar commands using Levenshtein distance
        """
        def levenshtein_distance(s1: str, s2: str) -> int:
            if len(s1) < len(s2):
                return levenshtein_distance(s2, s1)
            if len(s2) == 0:
                return len(s1)
            previous_row = range(len(s2) + 1)
            for i, c1 in enumerate(s1):
                current_row = [i + 1]
                for j, c2 in enumerate(s2):
                    insertions = previous_row[j + 1] + 1
                    deletions = current_row[j] + 1
                    substitutions = previous_row[j] + (c1 != c2)
                    current_row.append(min(insertions, deletions, substitutions))
                previous_row = current_row
            return previous_row[-1]

        all_commands = self.commands.list_commands()
        suggestions = []
        command_lower = command.lower()

        for cmd in all_commands:
            distance = levenshtein_distance(command_lower, cmd.lower())
            if distance <= 3 and len(cmd) >= 3 and cmd[:2].lower() == command_lower[:2]:
                suggestions.append((distance, cmd))
        suggestions.sort(key=lambda x: (x[0], x[1]))
        return [cmd for _, cmd in suggestions[:max_suggestions]]

    async def execute(self, command: str, cli_instance: Any, **kwargs: Any) -> int:
        """Execute command with error handling and middleware"""
        command_meta: Optional[Dict[str, Any]] = self.commands.get_command(command)

        if not command_meta:
            error_msg: str = self.messages.get_message(
                'command_not_found',
                default="Command '{command}' not found",
                command=command
            )
            print(self.output.format(error_msg, 'error'))

            suggestions = self._suggest_similar_commands(command)
            if suggestions:
                suggestion_str = ', '.join(suggestions)
                did_you_mean = self.messages.get_message(
                    'did_you_mean',
                    default="Did you mean: {suggestions}?",
                    suggestions=suggestion_str
                )
                print(self.output.format(did_you_mean, 'info'))
            return 1

        handler: Callable[..., Any] = command_meta.get('handler')
        if not handler:
            print(self.output.format(f"Command '{command}' has no handler", 'error'))
            return 1
        try:
            sig: inspect.Signature = inspect.signature(handler)
            positional_args: List[Any] = []
            command_kwargs: Dict[str, Any] = {}
            has_var_keyword: bool = False
            param_names: List[str] = []
            required_missing: List[str] = []

            for param_name, param in sig.parameters.items():
                if param_name in ('self', 'cls'):
                    continue
                if param.kind == inspect.Parameter.VAR_POSITIONAL:
                    continue
                elif param.kind == inspect.Parameter.VAR_KEYWORD:
                    has_var_keyword = True
                    continue

                param_names.append(param_name)
                if param_name in kwargs:
                    value = kwargs[param_name]
                    if param.kind == inspect.Parameter.POSITIONAL_ONLY:
                        positional_args.append(value)
                    else:
                        command_kwargs[param_name] = value
                elif param.default != inspect.Parameter.empty:
                    command_kwargs[param_name] = param.default
                else:
                    required_missing.append(param_name)

            if required_missing:
                args_str = ', '.join(f"'{n}'" for n in required_missing)
                error_msg = f"Missing required arguments for command '{command}': {args_str}"
                print(self.output.format(error_msg, 'error'))
                return 1

            reserved_keys = {'help', 'show_help'}
            unknown_keys = [k for k in kwargs.keys()
                          if k not in param_names and k not in reserved_keys]

            if unknown_keys:
                if has_var_keyword:
                    for key in unknown_keys:
                        command_kwargs[key] = kwargs[key]
                else:
                    unknown_str = ', '.join(f'--{k}' for k in unknown_keys)
                    error_msg = f"Unknown options for command '{command}': {unknown_str}"
                    print(self.output.format(error_msg, 'error'))
                    return 1

        except (TypeError, ValueError, KeyError) as e:
            self._logger.error(f"Error preparing command arguments: {e}")
            print(self.output.format(f"Invalid arguments: {e}", 'error'))
            return 1

        try:
            cli_context.set({
                'command': command,
                'args': kwargs,
                'cli_instance': cli_instance
            })

            async def execute_handler() -> Any:
                if is_async_function(handler):
                    return await handler(*positional_args, **command_kwargs)
                else:
                    ctx = copy_context()
                    loop = asyncio.get_running_loop()
                    return await loop.run_in_executor(
                        None,
                        lambda: ctx.run(
                            functools.partial(handler, *positional_args, **command_kwargs)
                        )
                    )

            final_handler = self.pipeline.build(execute_handler)
            result: Any = await final_handler()

            if isinstance(result, int):
                return result
            elif result is False:
                return 1
            else:
                return 0

        except KeyboardInterrupt:
            self._logger.info("Command execution interrupted by user")
            raise
        except CommandExecutionError:
            raise
        except Exception as e:
            self._logger.error(f"Error executing command '{command}': {e}", exc_info=True)
            error_msg = self.messages.get_message(
                'execution_error',
                default='Error: {error}',
                error=str(e)
            )
            print(self.output.format(error_msg, 'error'))

            if self._logger.isEnabledFor(logging.DEBUG):
                print(self.output.format("\nTraceback:", 'error'))
                print(traceback.format_exc())
            raise CommandExecutionError(str(e)) from e
        finally:
            cli_context.set({})


class InteractiveShell:
    """Interactive REPL shell"""

    def __init__(self, cli_instance: 'CLI'):
        self.cli = cli_instance
        self._logger = logging.getLogger('cli.shell')
        self._interrupt_count = 0

    def setup_readline_completion(self) -> None:
        """Setup tab completion for interactive mode"""
        if not self.cli._use_readline:
            return

        try:
            import readline
        except ImportError:
            try:
                import pyreadline3 as readline
                self._logger.debug("Using pyreadline3 for Windows tab completion")
            except ImportError:
                self._logger.warning("readline/pyreadline3 not available. Install pyreadline3 for tab completion: pip install pyreadline3")
                self.cli._use_readline = False
                return

        class CommandCompleter:
            def __init__(self, commands: CommandRegistry):
                self.commands = commands
                self.matches: List[str] = []

            def complete(self, text: str, state: int) -> Optional[str]:
                if state == 0:
                    if text:
                        self.matches = self.commands.autocomplete(text)
                    else:
                        self.matches = self.commands.list_commands()
                try:
                    return self.matches[state]
                except IndexError:
                    return None

        completer = CommandCompleter(self.cli.commands)
        readline.set_completer(completer.complete)
        readline.parse_and_bind('tab: complete')
        readline.set_completer_delims(' \t\n')
        self._logger.debug("Readline tab completion enabled")

    def handle_interrupt(self) -> bool:
        """Handle KeyboardInterrupt, returns True if should exit"""
        self._interrupt_count += 1
        if self._interrupt_count == 1:
            print(self.cli.output.format("\n^C (Press Ctrl+C again to force exit, or type 'exit')", "warning"))
            return False
        else:
            self._logger.warning("Force exit requested")
            print(self.cli.output.format("\nForce exiting...", "error"))
            return True

    async def run(self) -> int:
        """Run interactive REPL"""
        self.setup_readline_completion()

        print(self.cli.output.format(
            self.cli.config.get('welcome_message', f"Welcome to {self.cli.name}"),
            'info'
        ))
        print(self.cli.output.format(
            self.cli.config.get('help_hint', "Type 'help' for commands or 'exit' to quit"),
            'info'
        ))
        print("")

        exit_code = 0
        last_had_error = False

        while not self.cli._shutdown_requested:
            try:
                self._interrupt_count = 0
                prompt: str = self.cli.config.get('prompt', f"{self.cli.name}> ")

                try:
                    user_input: str = input(prompt).strip()
                except EOFError:
                    print(self.cli.output.format("\nExiting...", 'info'))
                    break
                except KeyboardInterrupt:
                    if self.handle_interrupt():
                        break
                    print("")
                    continue

                if self.cli._shutdown_requested:
                    print(self.cli.output.format("\nShutdown requested, exiting...", 'info'))
                    break

                if not user_input:
                    continue

                if user_input.lower() in ('exit', 'quit', 'q'):
                    self.cli._shutdown_requested = True
                    print(self.cli.output.format("Goodbye!", 'info'))
                    break

                import shlex
                try:
                    input_args: List[str] = shlex.split(user_input)
                except ValueError as e:
                    print(self.cli.output.format(f"Invalid input: {e}", 'error'))
                    last_had_error = True
                    continue

                self._logger.debug(f"Parsed args: {input_args}")

                try:
                    parsed: Dict[str, Any] = self.cli.parser.parse(input_args)
                    self._logger.debug(f"Parsed result: {parsed}")

                    command: Optional[str] = parsed.get('command')
                    if not command:
                        print(self.cli.output.format("No command specified", 'error'))
                        last_had_error = True
                        continue

                    if parsed.get('show_help', False):
                        help_text: str = self.cli.parser.generate_help(command)
                        print(self.cli.output.format(help_text, 'info'))
                        last_had_error = False
                        continue

                    command_kwargs = {k: v for k, v in parsed.items() if k != 'command'}
                    exit_code = await self.cli.executor.execute(command, self.cli, **command_kwargs)

                    if exit_code != 0 and not last_had_error:
                        print(self.cli.output.format(
                            f"Command returned exit code: {exit_code}",
                            'warning'
                        ))
                        last_had_error = True
                    else:
                        last_had_error = False

                except ValueError as e:
                    print(self.cli.output.format(f"Error: {e}", 'error'))
                    exit_code = 1
                    last_had_error = True
                except KeyboardInterrupt:
                    if self.handle_interrupt():
                        break
                    last_had_error = False
                except CommandExecutionError:
                    exit_code = 1
                    last_had_error = True
                except Exception as e:
                    self._logger.error(f"Unexpected error: {e}", exc_info=True)
                    print(self.cli.output.format(f"Unexpected error: {e}", 'error'))
                    exit_code = 1
                    last_had_error = True

                print("")

            except KeyboardInterrupt:
                if self.handle_interrupt():
                    break
                print("")
                continue

        return exit_code


class CLI:
    """
    Main CLI application class

    Features:
    - Declarative command definition via decorators
    - Automatic CLI generation from classes/functions
    - Async command execution
    - Configuration persistence
    - Message localization
    - Formatted output
    - Middleware support
    - Graceful shutdown

    Note on generate_from:
    - Methods starting with '_' are skipped in safe_mode
    - Only callable attributes on the class/instance are considered
    - Instance attributes that shadow methods will be skipped
    """

    def __init__(self,
                 name: str = 'app',
                 config_path: Optional[str] = None,
                 config_provider: Optional[ConfigProvider] = None,
                 config_schema: Optional[Dict[str, Any]] = None,
                 message_provider: Optional[MessageProvider] = None,
                 output_formatter: Optional[OutputFormatter] = None,
                 command_registry: Optional[CommandRegistry] = None,
                 argument_parser: Optional[ArgumentParser] = None,
                 log_level: int = logging.INFO,
                 auto_logging_middleware: bool = False):
        """Initialize CLI application"""
        self._setup_logging(log_level)
        self._logger: logging.Logger = logging.getLogger(f'cliframework.{name}')
        self._logger.info(f"Initializing CLI application '{name}'")

        self.name: str = name

        if config_provider is None:
            if config_path is None:
                config_dir: str = os.path.expanduser(f"~/.config/{name}")
                os.makedirs(config_dir, exist_ok=True)
                config_path = os.path.join(config_dir, f"{name}.json")

            default_config: Dict[str, Any] = {
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
                        "did_you_mean": "Did you mean: {suggestions}?"
                    }
                }
            }

            schema: Optional[Dict[str, Any]] = config_schema or DEFAULT_CONFIG_SCHEMA
            config_provider = JsonConfigProvider(
                config_path,
                default_config=default_config,
                schema=schema
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
        self.executor = CommandExecutor(self.commands, self.messages, self.output, self.pipeline)

        self.exit_code: int = 0
        self._running: bool = False
        self._shutdown_requested: bool = False
        self._commands_registered: bool = False
        self._cleanup_callbacks: List[Union[Callable[[], None], Callable[[], Awaitable[None]]]] = []
        self._use_readline: bool = True

        self._setup_signal_handlers()
        self._register_default_commands()

        if auto_logging_middleware:
            self.use_logging_middleware()

        self._logger.debug("CLI application initialized successfully")

    def _setup_logging(self, log_level: int) -> None:
        """Configure logging for CLI application"""
        logger: logging.Logger = logging.getLogger('cliframework')
        logger.setLevel(log_level)

        if not logger.handlers:
            console_handler: logging.StreamHandler = logging.StreamHandler()
            console_handler.setLevel(log_level)
            formatter: logging.Formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

    def _setup_signal_handlers(self) -> None:
        """
        Setup signal handlers for graceful shutdown
        """
        if threading.current_thread() is not threading.main_thread():
            self._logger.warning("Signal handlers can only be registered from main thread; skipping")
            return

        def signal_handler(sig: int, frame: Any) -> None:
            signal_name = 'SIGINT' if sig == signal.SIGINT else 'SIGTERM'
            self._logger.info(f"Received {signal_name}, requesting shutdown")

            if not self._shutdown_requested:
                self._shutdown_requested = True
                try:
                    print("\nShutdown requested. Finishing current operation...", file=sys.stderr)
                except (OSError, IOError) as e:
                    self._logger.debug(f"Could not print shutdown message: {e}")
                try:
                    loop = asyncio.get_running_loop()
                    loop.call_soon_threadsafe(loop.stop)
                except RuntimeError:
                    pass
            else:
                self._logger.warning(f"Received second {signal_name}, forcing exit")
                try:
                    print("\nForce exiting...", file=sys.stderr)
                except (OSError, IOError) as e:
                    self._logger.debug(f"Could not print force exit message: {e}")
                self._emergency_cleanup()
                sys.exit(1)

        try:
            signal.signal(signal.SIGINT, signal_handler)
            if hasattr(signal, 'SIGTERM'):
                signal.signal(signal.SIGTERM, signal_handler)
                self._logger.debug("Signal handlers registered for SIGINT and SIGTERM")
            else:
                self._logger.debug("Signal handler registered for SIGINT (SIGTERM not available)")
        except (ValueError, AttributeError, OSError) as e:
            self._logger.warning(f"Could not set signal handlers: {e}")

    def _emergency_cleanup(self) -> None:
        """Perform synchronous cleanup on forced exit"""
        for callback in self._cleanup_callbacks:
            try:
                if not asyncio.iscoroutinefunction(callback):
                    callback()
            except Exception as e:
                self._logger.error(f"Emergency cleanup error: {e}")

    def _cb_name(self, cb: Any) -> str:
        """Safely extract callback name for logging"""
        return getattr(cb, '__name__',
                      getattr(cb, '__qualname__',
                             cb.__class__.__name__))

    async def _run_cleanup_callbacks(self) -> None:
        """Run all cleanup callbacks"""
        for callback in self._cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await asyncio.wait_for(callback(), timeout=5.0)
                    self._logger.debug(f"Executed async cleanup callback: {self._cb_name(callback)}")
                else:
                    result = callback()
                    if inspect.isawaitable(result):
                        await asyncio.wait_for(result, timeout=5.0)
                        self._logger.debug(f"Executed async callable cleanup: {self._cb_name(callback)}")
                    else:
                        self._logger.debug(f"Executed sync cleanup callback: {self._cb_name(callback)}")
            except asyncio.TimeoutError:
                self._logger.error(f"Cleanup callback {self._cb_name(callback)} timed out")
            except Exception as e:
                self._logger.error(f"Error in cleanup callback {self._cb_name(callback)}: {e}")

    def add_cleanup_callback(self, callback: Union[Callable[[], None], Callable[[], Awaitable[None]]]) -> None:
        """Add callback to be executed on shutdown"""
        self._cleanup_callbacks.append(callback)
        callback_type = "async" if asyncio.iscoroutinefunction(callback) else "sync"
        self._logger.debug(f"Added {callback_type} cleanup callback: {self._cb_name(callback)}")

    def use(self, middleware: Union[Callable[[Callable[[], Awaitable[Any]]], Awaitable[Any]],
                                   Callable[[Callable[[], Awaitable[Any]]], Any]]) -> None:
        """Add middleware to execution chain"""
        self.pipeline.add(middleware)
        self._logger.debug(f"Added middleware: {self._cb_name(middleware)}")

    def use_logging_middleware(self) -> None:
        """Add built-in logging middleware for debugging"""
        async def logging_middleware(next_handler: Callable[[], Awaitable[Any]]) -> Any:
            ctx = cli_context.get()
            command = ctx.get('command', 'unknown')
            args = ctx.get('args', {})
            self._logger.debug(f"[Middleware] Executing command '{command}' with args: {args}")

            try:
                result = await next_handler()
                self._logger.debug(f"[Middleware] Command '{command}' completed successfully")
                return result
            except Exception as e:
                self._logger.debug(f"[Middleware] Command '{command}' failed with error: {e}")
                raise

        self.use(logging_middleware)
        self._logger.info("Built-in logging middleware enabled")

    def get_context(self) -> Dict[str, Any]:
        """Get current CLI context"""
        return cli_context.get().copy()

    def set_context(self, **kwargs: Any) -> None:
        """Set CLI context variables"""
        ctx = cli_context.get().copy()
        ctx.update(kwargs)
        cli_context.set(ctx)

    def enable_readline(self, enable: bool = True) -> None:
        """Enable or disable readline tab completion"""
        self._use_readline = enable
        self._logger.debug(f"Readline {'enabled' if enable else 'disabled'}")

    def _format_command_signature(self, command_meta: Dict[str, Any]) -> str:
        """Generate brief signature for command"""
        parts = []
        for arg in command_meta.get('arguments', []):
            parts.append(f"<{arg['name']}>")
        for opt in command_meta.get('options', []):
            if opt.get('is_flag'):
                parts.append(f"[--{opt['name']}]")
            else:
                parts.append(f"[--{opt['name']} <value>]")
        return ' '.join(parts)

    def _register_default_commands(self) -> None:
        """Register built-in default commands"""
        def help_command(cmd: Optional[str] = None) -> int:
            """Show help for command or list all commands"""
            if cmd:
                try:
                    help_text: str = self.parser.generate_help(cmd)
                    print(self.output.format(help_text, 'info'))
                except Exception as e:
                    print(self.output.format(f"Error generating help: {e}", 'error'))
                    return 1
            else:
                print(self.output.format(
                    self.messages.get_message('available_commands', 'Available commands:'),
                    'header'
                ))
                commands: List[str] = self.commands.list_commands()
                for command in sorted(commands):
                    cmd_meta: Optional[Dict[str, Any]] = self.commands.get_command(command)
                    if cmd_meta:
                        help_text = cmd_meta.get('help', 'No description')
                        signature = self._format_command_signature(cmd_meta)
                        aliases = cmd_meta.get('aliases', [])

                        line = f"  {command:20} {help_text}"
                        if signature:
                            line += f"\n    {'':20} Usage: {command} {signature}"
                        if aliases:
                            alias_str = f" (aliases: {', '.join(aliases)})"
                            line += alias_str
                        print(line)
            return 0

        self.commands.register(
            'help', help_command, help='Show help information',
            arguments=[{'name': 'cmd', 'help': 'Command to show help for', 'type': str}],
            options=[], is_async=False
        )

        def version_command() -> int:
            """Display application version"""
            version: str = self.config.get('version', 'unknown')
            print(self.output.format(f"{self.name} version {version}", 'info'))
            return 0

        self.commands.register(
            'version', version_command, help='Show application version',
            arguments=[], options=[], is_async=False
        )

        def exit_command() -> int:
            """Exit the CLI application"""
            self._shutdown_requested = True
            msg = self.messages.get_message('app_quit', 'Goodbye!')
            print(self.output.format(msg, 'info'))
            return 0

        self.commands.register(
            'exit', exit_command, help='Exit the application',
            arguments=[], options=[], aliases=['quit', 'q'], is_async=False
        )

    def command(self, name: Optional[str] = None, help: Optional[str] = None,
                aliases: Optional[List[str]] = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for defining command"""
        from .decorators import command as cmd_decorator
        return cmd_decorator(name, help, aliases)

    def argument(self, name: str, help: Optional[str] = None,
                 type: Type[Any] = str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for defining positional argument"""
        from .decorators import argument as arg_decorator
        return arg_decorator(name, help, type)

    def option(self, name: str, short: Optional[str] = None, help: Optional[str] = None,
               type: Type[Any] = str, default: Any = None,
               is_flag: bool = False) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for defining command option"""
        from .decorators import option as opt_decorator
        return opt_decorator(name, short, help, type, default, is_flag)

    def example(self, example_text: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for adding command example"""
        from .decorators import example as ex_decorator
        return ex_decorator(example_text)

    def group(self, name: Optional[str] = None,
              help: Optional[str] = None) -> Callable[[Type[Any]], Type[Any]]:
        """Decorator for defining command group"""
        from .decorators import group as group_decorator
        return group_decorator(name, help)

    def generate_from(self, obj: Union[Type[Any], object, Callable[..., Any]],
                      safe_mode: bool = True) -> None:
        """
        Generate CLI commands from object (class, instance, or function)

        Note: In safe_mode, only public attributes (not starting with '_') are exposed.
        Methods that are shadowed by instance attributes will not be detected.
        """
        self._logger.debug(f"Generating CLI from {obj}")

        if inspect.isclass(obj):
            try:
                instance: Any = obj()
                self._generate_from_instance(instance, safe_mode)
            except Exception as e:
                self._logger.error(f"Failed to instantiate class {obj}: {e}")
                raise ValueError(f"Cannot instantiate class: {e}")
        elif inspect.isfunction(obj) or inspect.ismethod(obj):
            self._generate_from_function(obj, safe_mode)
        elif hasattr(obj, '__dict__'):
            self._generate_from_instance(obj, safe_mode)
        else:
            raise ValueError(f"Cannot generate CLI from {type(obj)}")

    def _generate_from_instance(self, instance: Any, safe_mode: bool) -> None:
        """Generate commands from object instance"""
        class_name: str = instance.__class__.__name__.lower()

        for attr_name in dir(instance):
            if safe_mode and attr_name.startswith('_'):
                continue

            try:
                attr_obj = getattr(type(instance), attr_name, None)
                if attr_obj is None or not callable(attr_obj):
                    continue

                attr: Any = getattr(instance, attr_name)
                if not callable(attr):
                    continue

                command_name: str = f"{class_name}.{attr_name}"
                self._auto_generate_command(command_name, attr)
            except Exception as e:
                self._logger.warning(f"Error processing {attr_name}: {e}")

    def _generate_from_function(self, func: Callable[..., Any], safe_mode: bool) -> None:
        """Generate command from single function"""
        func_name: str = func.__name__
        if safe_mode and func_name.startswith('_'):
            raise ValueError(f"Cannot expose private function: {func_name}")
        self._auto_generate_command(func_name, func)

    def _auto_generate_command(self, name: str, func: Callable[..., Any]) -> None:
        """Automatically generate and register command from function"""
        sig: inspect.Signature = inspect.signature(func)
        doc: Optional[str] = inspect.getdoc(func) or f"Command {name}"

        arguments: List[Dict[str, Any]] = []
        options: List[Dict[str, Any]] = []

        for param_name, param in sig.parameters.items():
            if param_name in ('self', 'cls'):
                continue

            param_type: Type[Any] = (
                param.annotation if param.annotation != inspect.Parameter.empty else str
            )

            if param.default != inspect.Parameter.empty:
                is_flag = (
                    isinstance(param.default, bool) or
                    param_type is bool or
                    (hasattr(param_type, '__origin__') and param_type.__origin__ is bool)
                )
                options.append({
                    'name': param_name,
                    'help': f"Option {param_name}",
                    'type': param_type,
                    'default': param.default,
                    'is_flag': is_flag
                })
            else:
                arguments.append({
                    'name': param_name,
                    'help': f"Argument {param_name}",
                    'type': param_type
                })

        is_async = is_async_function(func)
        self.commands.register(
            name, func, help=doc, arguments=arguments,
            options=options, is_async=is_async
        )
        self._logger.info(
            f"Auto-generated {'async' if is_async else 'sync'} command '{name}'"
        )

    def register_all_commands(self) -> int:
        """Register all decorator-defined commands"""
        self._logger.debug("Registering all decorated commands")
        count = register_commands(self)
        self._logger.info(f"Registered {count} decorator-defined commands")
        return count

    async def run_interactive(self) -> int:
        """Run CLI in interactive REPL mode"""
        if not self._commands_registered:
            self.register_all_commands()
            self._commands_registered = True

        self._running = True
        shell = InteractiveShell(self)

        try:
            exit_code = await shell.run()
            self.exit_code = exit_code
            return exit_code
        finally:
            self._running = False
            await self._run_cleanup_callbacks()
            try:
                self.config.save()
                self._logger.debug("Configuration saved on exit")
            except Exception as e:
                self._logger.error(f"Failed to save configuration: {e}")

    async def run_async(self, args: Optional[List[str]] = None, interactive: bool = False) -> int:
        """Run CLI application asynchronously"""
        if interactive:
            return await self.run_interactive()

        if args is None:
            args = sys.argv[1:]

        if '--help' in args or '-h' in args:
            if not args or args[0] in ('--help', '-h'):
                if not self._commands_registered:
                    self.register_all_commands()
                    self._commands_registered = True

                print(self.output.format(
                    self.config.get('welcome_message', f"Welcome to {self.name}"),
                    'info'
                ))
                print("")
                print(self.output.format(
                    self.messages.get_message('available_commands', 'Available commands:'),
                    'header'
                ))
                commands = self.commands.list_commands()
                for command in sorted(commands):
                    cmd_meta = self.commands.get_command(command)
                    if cmd_meta:
                        help_text = cmd_meta.get('help', 'No description')
                        signature = self._format_command_signature(cmd_meta)
                        line = f"  {command:20} {help_text}"
                        if signature:
                            line += f"\n    {'':20} Usage: {command} {signature}"
                        print(line)
                print("")
                print(self.output.format(
                    "Use '<command> --help' for more information about a command.",
                    'info'
                ))
                return 0

        if not self._commands_registered:
            self.register_all_commands()
            self._commands_registered = True

        if not args:
            return await self.run_interactive()

        self._running = True

        try:
            parsed: Dict[str, Any] = self.parser.parse(args)
            command: Optional[str] = parsed.get('command')

            if not command:
                print(self.output.format(
                    self.config.get('welcome_message', f"Welcome to {self.name}"),
                    'info'
                ))
                print(self.output.format(
                    self.config.get('help_hint', "Type 'help' for commands"),
                    'info'
                ))
                return 0

            if parsed.get('show_help', False):
                help_text: str = self.parser.generate_help(command)
                print(self.output.format(help_text, 'info'))
                return 0

            command_kwargs = {k: v for k, v in parsed.items() if k != 'command'}
            exit_code: int = await self.executor.execute(command, self, **command_kwargs)
            self.exit_code = exit_code
            return exit_code

        except ValueError as e:
            print(self.output.format(f"Error: {e}", 'error'))
            self.exit_code = 1
            return 1
        except KeyboardInterrupt:
            self._logger.info("Interrupted by user")
            self.exit_code = 130
            return 130
        except CommandExecutionError:
            self.exit_code = 1
            return 1
        except Exception as e:
            self._logger.error(f"Unexpected error: {e}", exc_info=True)
            print(self.output.format(f"Unexpected error: {e}", 'error'))
            self.exit_code = 1
            return 1
        finally:
            self._running = False
            await self._run_cleanup_callbacks()
            try:
                self.config.save()
                self._logger.debug("Configuration saved on exit")
            except Exception as e:
                self._logger.error(f"Failed to save configuration: {e}")

    def run(self, args: Optional[List[str]] = None, interactive: bool = False) -> int:
        """Run CLI application (synchronous wrapper)"""
        return asyncio.run(self.run_async(args, interactive))
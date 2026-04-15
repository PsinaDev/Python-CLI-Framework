# CLI Framework — Documentation

[**Русский**](DOCS_RU.md)

Python 3.10+. Optional: `jsonschema` for config schema validation,
`readline` (or `pyreadline3` on Windows) for REPL tab completion.

## Contents

- [Core concepts](#core-concepts)
- [Decorators](#decorators)
- [Output](#output)
- [Configuration](#configuration)
- [Localization](#localization)
- [Async commands](#async-commands)
- [Middleware](#middleware)
- [Hooks](#hooks)
- [CLI context](#cli-context)
- [Cleanup callbacks](#cleanup-callbacks)
- [Interactive REPL](#interactive-repl)
- [Shell completion](#shell-completion)
- [Plugins](#plugins)
- [Auto-generation](#auto-generation)
- [API reference](#api-reference)
- [Troubleshooting](#troubleshooting)

---

## Core concepts

### Command lifecycle

```
sys.argv ──► run() ──► run_async()
                       │
                       ├─ extract --config-file (if present), reload provider
                       ├─ Hook.on_before_parse(args)
                       ├─ parser.parse(args)
                       ├─ Hook.on_after_parse(parsed)
                       └─ executor.execute(command, **kwargs)
                            │
                            ├─ middleware chain (outer → inner)
                            ├─ Hook.on_before_execute  +  per-command before
                            ├─ handler(**kwargs)
                            ├─ Hook.on_after_execute   +  per-command after
                            └─ middleware unwind
                       │
                       └─ cleanup callbacks (sync or async, 5 s timeout each)
```

`cli.run()` is the sync entry point that just calls `asyncio.run(run_async)`.
Sync handlers are invoked directly; async handlers are awaited.

### Reserved names

```
help, h, _cli_help, _cli_show_help
```

Exported as `cli.RESERVED_NAMES`. Using them for commands, aliases,
options, short flags, or function parameters raises `ValueError` at
decoration time.

Passing `-h` or `--help` after any registered command short-circuits the
parser and prints that command's help instead of executing the handler:

```bash
python app.py greet --help
python app.py greet -h
```

### Decorator stacking

Python applies decorators bottom-up, so the **first** `@cli.argument`
listed gets pushed onto the arguments list **last**. List arguments in
reverse order to match the function signature:

```python
@cli.command()
@cli.argument("b", type=int)
@cli.argument("a", type=int)
def add(a: int, b: int) -> int: ...
```

Order of `@cli.option` only affects help-text display — options are keyed
by name when parsing.

### Default and per-CLI registries

Two ways to register commands:

1. **Module-level** decorators (`from cli import command, argument, option`)
   write to a process-wide default registry. Any later-created CLI picks
   them up unless constructed with `include_default_registry=False`.
2. **Bound** decorators on a specific instance (`cli.command()`,
   `cli.argument()`, …) write to that instance's private registry only.
   Multiple `CLI` instances in the same process do not collide.

`BoundDecorators(registry)` lets you bind decorators to a custom registry
explicitly.

---

## Decorators

### `@cli.command`

```python
cli.command(
    name: str | None = None,
    help: str | None = None,
    aliases: list[str] | None = None,
)
```

`name` defaults to the function name; `help` overrides the docstring
summary; `aliases` adds extra invocation names.

### `@cli.argument`

```python
cli.argument(
    name: str,
    help: str | None = None,
    type: type = str,
    optional: bool = False,
    group: str | None = None,
)
```

Supported `type`: `str`, `int`, `float`, `bool`, `list`, `dict`, `tuple`,
`Enum` subclasses, `Optional[T]`. `list` and `dict` accept either JSON or
simple `key=value` / CSV syntax on the command line.

`optional=True` makes the positional argument optional; it must come last.
`group` is a display-only label.

### `@cli.option`

```python
cli.option(
    name: str,
    short: str | None = None,
    help: str | None = None,
    type: type = str,
    default: Any = ...,            # required if no default_factory
    default_factory: Callable[[], Any] | None = None,
    is_flag: bool | None = None,   # auto-detected from type
    group: str | None = None,
    exclusive_group: str | None = None,
)
```

- `name` accepts `"--verbose"` or `"verbose"`; `short` accepts `"-v"` or `"v"` (single char).
- `is_flag` auto-resolves to `True` for `bool` types or `bool` defaults.
- `default_factory` produces a fresh value each parse — use for `list`/`dict` defaults to avoid sharing.
- `exclusive_group`: options sharing a label become mutually exclusive at the parser level.

```python
@cli.option("--verbose", "-v", is_flag=True)
@cli.option("--retries", "-r", type=int, default=3)
@cli.option("--mode", default="dev", exclusive_group="mode")
@cli.option("--prod", is_flag=True, exclusive_group="mode")
```

### `@cli.example`

```python
cli.example(example_text: str)
```

Adds a usage example to the command's help output. Stackable.

### `@cli.group`

```python
cli.group(name: str | None = None, help: str | None = None)
```

Class-level decorator. Methods decorated with `@cli.command` become dotted
commands under the group's namespace.

The class is instantiated **once** per CLI registration with no
arguments — provide an argument-free `__init__` (or none) and rely on
instance state if you need per-group storage:

```python
@cli.group(name="users")
class UserCommands:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    @cli.command()
    @cli.argument("username")
    def add(self, username: str) -> int:
        self._store[username] = "user"
        return 0
```

---

## Output

### `echo`

```python
echo(
    text: str,
    style: str | None = None,
    file: TextIO = sys.stdout,
    formatter: TerminalOutputFormatter | None = None,
) -> None
```

Style names: `success`, `error`, `warning`, `info`, `header`, `debug`,
`code`. `None` writes plain text.

### `style`

```python
style(
    text: str,
    fg: str | None = None,
    bg: str | None = None,
    bold: bool = False,
    underline: bool = False,
    blink: bool = False,
    formatter: TerminalOutputFormatter | None = None,
) -> str
```

Returns the wrapped ANSI string. Accepts standard 8 colors plus
`bright_*` variants.

### `table`

```python
table(
    headers: list[str],
    rows: list[list[str]],
    max_col_width: int | None = None,
    file: TextIO = sys.stdout,
    formatter: TerminalOutputFormatter | None = None,
) -> None
```

Auto-sized box-drawn table; ANSI codes inside cells are accounted for
when measuring width.

### `progress_bar`

```python
progress_bar(
    total: int,
    width: int | None = None,
    char: str = "█",
    empty_char: str = "·",
    show_percent: bool = True,
    show_count: bool = True,
    prefix: str = "",
    suffix: str = "",
    color_low: str = "yellow",
    color_mid: str = "blue",
    color_high: str = "green",
    color_threshold_low: float = 0.33,
    color_threshold_high: float = 0.66,
    brackets: tuple[str, str] = ("[", "]"),
    file: TextIO = sys.stdout,
    force_inline: bool | None = None,
    formatter: TerminalOutputFormatter | None = None,
) -> Callable[[int], None]
```

Returns an `update(current)` callable. When `file` is not a TTY and
`force_inline` is `None`, output falls back to one line per update.

---

## Configuration

### `JsonConfigProvider`

```python
JsonConfigProvider(
    path: str,
    default_config: dict[str, Any] | None = None,
    schema: dict[str, Any] | None = None,
)
```

Thread-safe, file-locked JSON storage. Methods on the `ConfigProvider`
interface:

- `get(key, default=None)` — hierarchical access via dotted keys
- `set(key, value)` — write to the in-memory copy
- `update(mapping)` — deep merge
- `delete(key)` — remove a leaf
- `save()` — atomic write back to disk
- `get_all()` — full snapshot

### Hierarchical keys

```python
cli.config.set("database.host", "localhost")
cli.config.set("database.port", 5432)
cli.config.update({"app": {"theme": "dark", "language": "en"}})
host = cli.config.get("database.host")
cli.config.save()
```

### Schema validation

If `jsonschema` is installed and a `schema` is provided, every load and
save validates against it. The framework ships `DEFAULT_CONFIG_SCHEMA`
covering the localization fields it itself uses:

```python
from cli import DEFAULT_CONFIG_SCHEMA, JsonConfigProvider

provider = JsonConfigProvider(
    "myapp.json",
    default_config={"version": "1.0.0",
                    "default_language": "en", "languages": ["en"]},
    schema=DEFAULT_CONFIG_SCHEMA,
)
```

Errors: `ConfigError`, `ConfigValidationError`, `ConfigIOError`,
`ConfigLockError`. `sanitize_for_logging(value)` strips
secret-looking fields from a config dict before logging it.

### `EnvOverlayConfigProvider`

```python
EnvOverlayConfigProvider(
    inner: ConfigProvider,
    prefix: str,
    separator: str = "__",
)
```

Read-overlay of environment variables on top of any inner provider:

```
APP_FOO=bar              -> foo = "bar"
APP_DATABASE__HOST=db    -> database.host = "db"
APP_TIMEOUT=30           -> timeout = 30          (parsed as int)
APP_FEATURES='["a","b"]' -> features = ["a","b"]  (parsed as JSON)
```

Values are JSON-decoded first; on failure they fall through as raw
strings. `set()`, `delete()`, and `save()` pass through to the inner
provider — the overlay itself is read-only. Call `refresh()` after
mutating `os.environ` to reread.

### `--config-file` flag

Every CLI built with the framework accepts `--config-file PATH` before
any command. The provider is swapped before parsing runs:

```bash
python myapp.py --config-file /etc/myapp/prod.json deploy
```

---

## Localization

`ConfigBasedMessageProvider` reads strings from
`config["messages"][<lang>][<key>]`:

```python
cli.messages.get_message("greeting", default="Hello, {name}!", name="Alice")
cli.messages.set_language("ru")
cli.messages.get_current_language()
cli.messages.get_available_languages()
```

To add a language, write to the config and save:

```python
cli.config.update({
    "messages": {
        "ru": {"prompt": "приложение> ", "app_quit": "Выход."}
    }
})
cli.config.save()
cli.messages.set_language("ru")
```

Format placeholders use a safe formatter that ignores missing keys
instead of raising. Errors: `MessageError`.

---

## Async commands

```python
import asyncio

@cli.command()
@cli.argument("url")
async def fetch(url: str) -> int:
    await asyncio.sleep(0.5)
    return 0
```

The executor always runs through `asyncio.run` at the top level. Sync
handlers are invoked directly without thread offloading.

---

## Middleware

```python
from typing import Any, Awaitable, Callable

async def middleware(next_handler: Callable[[], Awaitable[Any]]) -> Any:
    # before
    try:
        return await next_handler()
    finally:
        # after / on error
        ...

cli.use(middleware)
```

Only async middlewares are accepted (`TypeError` otherwise). The pipeline
runs in registration order around the handler:

```
cli.use(a); cli.use(b)
# call: a → b → handler → b unwind → a unwind
```

`cli.use_logging_middleware()` registers a built-in tracer using the
framework logger.

The executor's `bypass_middleware` set (`{"help", "version", "exit"}` by
default) skips the chain for those commands.

---

## Hooks

### Global `Hook` interface

Subclass `Hook` and override only the phases you need. All five default
to no-ops.

```python
from cli import Hook

class AuditHook(Hook):
    async def on_before_parse(self, args: list[str]) -> list[str]:
        return args
    async def on_after_parse(self, parsed: dict[str, Any]) -> dict[str, Any]:
        return parsed
    async def on_before_execute(self, command: str, kwargs: dict[str, Any]) -> None: ...
    async def on_after_execute(self, command: str, result: Any, exit_code: int) -> None: ...
    async def on_error(self, command: str, error: BaseException) -> None: ...

cli.add_hook(AuditHook())
```

`on_before_parse` and `on_after_parse` may return modified data to
influence the rest of the pipeline. Exceptions in any global hook are
caught and logged — they do not abort execution.

### Per-command hooks

```python
@cli.before("ping")
async def _before(kwargs: dict[str, Any]) -> None: ...

@cli.after("ping")
async def _after(result: Any, exit_code: int) -> None: ...

@cli.on_error_for("boom")
async def _on_error(error: BaseException) -> None: ...
```

Per-command hook signatures **do not** include the command name (unlike
the global `Hook` methods). Their exceptions are also logged-not-raised,
so they cannot abort execution. For input validation, return a non-zero
exit code from the handler instead.

---

## CLI context

A `ContextVar` populated by the executor for the duration of each
command. Readable from middleware and the handler:

```python
ctx = cli.get_context()
# {
#   "command":      "greet",
#   "args":         {"name": "Alice"},
#   "cli_instance": <CLI ...>,
# }

cli.set_context(user_id=42, request_id="abc-123")
```

Updates merge into the existing context dict.

---

## Cleanup callbacks

```python
def flush() -> None: ...
async def close_db() -> None: ...

cli.add_cleanup_callback(flush)
cli.add_cleanup_callback(close_db)
```

Run after `run_async` returns (success or failure) and before the process
exits. Each callback gets a 5-second timeout; timeouts and exceptions are
logged but don't stop other callbacks. On a second `SIGINT` or `SIGTERM`,
sync callbacks run via an emergency path before `os._exit(1)`.

---

## Interactive REPL

`cli.run()` with no arguments enters the REPL automatically. Features:

- readline-based history and tab completion (long options + command names via prefix trie)
- `help`, `version`, `exit` / `quit` / `q` built-ins
- one `Ctrl+C` cancels the current input line; a second within ~2 s exits
- Fuzzy-suggest "did you mean ..." for unknown commands (Levenshtein ≤ 2)

```python
cli.enable_readline(False)   # disable readline integration
```

---

## Shell completion

```python
cli.generate_completion("bash")            # returns the script
cli.install_completion("zsh")              # writes to default location
cli.install_completion("fish", "/tmp/x")   # writes to custom path
```

`Shell` enum (`Shell.BASH`, `Shell.ZSH`, `Shell.FISH`) is also exported.
Default install paths:

| Shell | Path |
|-------|------|
| bash  | `~/.bash_completion.d/<name>.bash` |
| zsh   | `~/.zsh/completions/_<name>` |
| fish  | `~/.config/fish/completions/<name>.fish` |

---

## Plugins

Discover and invoke external packages registered under an
`importlib.metadata` entry-point group:

```python
results = cli.load_plugins("myapp.plugins", fail_fast=False)
# {"audit": True, "metrics": False, ...}
```

Plugin package's `pyproject.toml`:

```toml
[project.entry-points."myapp.plugins"]
audit = "myaudit.plugin:register"
```

Where `myaudit.plugin.register(cli)` registers commands, hooks, or
middleware.

Standalone helpers: `discover_plugins(group)`, `load_plugins(cli, group)`.
Errors: `PluginError`.

---

## Auto-generation

`cli.generate_from(obj, safe_mode=True)` introspects a function, class,
or instance and produces commands without decorators. With `safe_mode`,
private attributes (leading underscore) are skipped and unconstructable
classes are warned-and-skipped instead of raising.

```python
class Math:
    def add(self, a: int, b: int) -> int:
        return 0
    def mul(self, a: int, b: int) -> int:
        return 0

cli.generate_from(Math)   # registers "math.add", "math.mul"
```

Parameters with defaults become options; parameters without become
required positional arguments. Booleans become flags.

---

## API reference

### `CLI`

```python
CLI(
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
)
```

`shell_posix` controls how the interactive REPL splits input lines. `True`
uses `shlex` POSIX mode (quotes are interpreted and stripped). `False` keeps
tokens raw and only strips matching outer quotes — useful on Windows so
paths like `C:\Users\foo` don't need escaping. `None` (default) picks POSIX
on Unix, non-POSIX on Windows.

Methods (selected; full list in `cli/application.py`):

| Method | Purpose |
|--------|---------|
| `command`, `argument`, `option`, `example`, `group` | bound decorators |
| `before`, `after`, `on_error_for` | per-command hooks |
| `use(middleware)` | append async middleware |
| `use_logging_middleware()` | register the built-in tracer |
| `add_hook(hook)` | register a global `Hook` instance |
| `add_cleanup_callback(cb)` | sync or async callback |
| `get_context()` / `set_context(**kwargs)` | command-scoped `ContextVar` |
| `enable_readline(enable=True)` | toggle REPL readline integration |
| `load_plugins(group, fail_fast=False)` | invoke entry-point plugins |
| `generate_completion(shell)` | return completion script string |
| `install_completion(shell, path=None)` | write completion script to disk |
| `generate_from(obj, safe_mode=True)` | auto-register from class/function |
| `register_all_commands()` | force registry walk (called on first run) |
| `run(args=None)` | sync entry point → exit code |
| `run_async(args=None)` | async entry point → exit code |
| `run_interactive()` | enter the REPL directly |

Attributes:

| Attribute | Type |
|-----------|------|
| `config` | `ConfigProvider` |
| `messages` | `MessageProvider` |
| `output` | `OutputFormatter` |
| `commands` | `CommandRegistry` |
| `parser` | `ArgumentParser` |
| `pipeline` | `MiddlewarePipeline` |
| `hook_manager` | `HookManager` |
| `executor` | `CommandExecutor` |
| `exit_code` | `int` (last command result) |

### Public exports from `cli`

```
CLI, CLIError, CommandExecutionError, DEFAULT_CONFIG_SCHEMA, cli_context

command, argument, option, example, group, register_commands,
clear_registry, clear_default_registry, get_default_registry,
CommandMetadataRegistry, BoundDecorators, RESERVED_NAMES

ConfigProvider, MessageProvider, OutputFormatter, CommandRegistry,
ArgumentParser, CommandHandler, Middleware, Hook

JsonConfigProvider, ConfigError, ConfigValidationError, ConfigIOError,
ConfigLockError, sanitize_for_logging, EnvOverlayConfigProvider

ConfigBasedMessageProvider, MessageError

TerminalOutputFormatter, echo, style, progress_bar, table

CommandRegistryImpl, EnhancedArgumentParser

Shell, generate_completion

PluginError, discover_plugins, load_plugins

__version__, get_version, get_version_tuple
```

---

## Troubleshooting

### Colors not displaying

Output is detected as non-TTY (piped or redirected). Force colors by
passing a custom `TerminalOutputFormatter` with `force_color=True`, or
emit ANSI manually via `style()`.

### Tab completion not working in the REPL

Requires `readline` (stdlib on Linux/macOS) or `pyreadline3` on Windows.
Verify with `cli.enable_readline(True)`. Completion only kicks in for the
first whitespace-separated token (command name) and long options.

### `RuntimeError: CLI Framework requires Python 3.10+`

Raised from `cli/__init__.py` on import. Upgrade Python.

### Reserved name conflict

`help`, `h`, `_cli_help`, `_cli_show_help` cannot be commands, aliases,
options, short flags, or function parameters. Rename or alias.

### Per-command hook didn't abort the command

By design — exceptions in `before` / `after` / `on_error_for` are logged
but not propagated. For input validation, fail inside the handler
itself.

### Argument order wrong

Decorators stack bottom-up; list `@cli.argument` calls in reverse so the
**first** function parameter is the **last** decorator written above the
function.

### Group commands lose state between invocations

The group class is instantiated once per `cli.run()`. In CLI mode that
means a fresh instance per process — use module-level state or persist
to disk (see `examples/08_todo_app.py`).

### Async cleanup callback timed out

Each cleanup callback has a 5-second budget. Move long-running work out
of cleanup or split into smaller callbacks.

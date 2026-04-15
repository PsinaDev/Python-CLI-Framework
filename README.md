# Python CLI Framework

[**Русский**](README_RU.md)

Async-first Python framework for building CLIs. Decorator API, middleware
and hooks, JSON config with env overlay, shell completion, REPL.

Python 3.10+.

## Quick start

```python
from cli import CLI, echo

cli = CLI(name="myapp")

@cli.command(aliases=["hi"])
@cli.argument("name")
@cli.option("--count", "-c", type=int, default=1)
@cli.option("--shout", is_flag=True)
def hello(name: str, count: int = 1, shout: bool = False) -> int:
    """Greet someone."""
    text = f"Hello, {name}!"
    if shout:
        text = text.upper()
    for _ in range(count):
        echo(text, "success")
    return 0

if __name__ == "__main__":
    raise SystemExit(cli.run())
```

```bash
python app.py hello Alice --count 3 --shout
python app.py help hello
python app.py                  # interactive REPL
```

## Decorator stacking gotcha

Decorators apply bottom-up, so the **first** `@cli.argument` listed is
parsed **last**. To keep positional order matching the function
signature, list arguments in reverse:

```python
@cli.command()
@cli.argument("b", type=int)   # 2nd positional
@cli.argument("a", type=int)   # 1st positional
def add(a: int, b: int) -> int: ...
```

## Features at a glance

- Sync and async handlers
- Class-based command groups (`@cli.group` → dotted commands like `db.init`)
- Middleware pipeline + global `Hook` interface + per-command `before` / `after` / `on_error_for`
- `JsonConfigProvider` (file-locked, hierarchical keys, optional JSON-schema validation)
- `EnvOverlayConfigProvider` — `APP_DATABASE__HOST=db.local` overrides `database.host`
- `--config-file PATH` flag swaps the active provider before parsing
- Output: `echo`, `style`, `table`, `progress_bar`
- Shell completion (`bash`, `zsh`, `fish`)
- Plugin discovery via `importlib.metadata` entry points
- Interactive REPL with readline tab completion when invoked without args
- Cleanup callbacks (sync or async, 5 s timeout)

## Repo layout

```
cli/             package
examples/        runnable single-topic demos (see examples/README.md)
tests/           unit tests
documentation/   full reference (DOCS.md / DOCS_RU.md)
```

## Examples

| File | Topic |
|------|-------|
| `01_basics.py` | Commands, args, options, flags, aliases, `@example` |
| `02_async_progress.py` | Async handlers and progress-bar styles |
| `03_groups.py` | Class-based command groups |
| `04_middleware_hooks.py` | Middleware + global `Hook` + per-command hooks |
| `05_config_env.py` | `JsonConfigProvider`, env overlay, `--config-file` |
| `06_output.py` | `echo`, `style`, `table` |
| `07_completion.py` | Shell completion generation |
| `08_todo_app.py` | Mini todo manager combining most features |

```bash
python examples/01_basics.py hello Alice --count 3 --shout
```

## Documentation

[`documentation/DOCS.md`](documentation/DOCS.md).

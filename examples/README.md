# CLI Framework Examples

Each file is a self-contained, runnable demonstration of one feature area.
Run any example with:

```bash
python examples/<file>.py [args...]
```

Calling an example without args drops into the interactive REPL.

| File | Topic |
|------|-------|
| `01_basics.py` | Commands, arguments, options, flags, aliases, `@example` |
| `02_async_progress.py` | Async commands and `progress_bar` styles |
| `03_groups.py` | Class-based command groups (`@cli.group`) |
| `04_middleware_hooks.py` | Middleware pipeline + global `Hook` + per-command hooks |
| `05_config_env.py` | Custom config path, `EnvOverlayConfigProvider`, `--config-file` |
| `06_output.py` | `echo`, `style`, `table` |
| `07_completion.py` | Generating bash/zsh/fish completion scripts |
| `08_todo_app.py` | End-to-end mini app combining most features |

## Quick tour

```bash
# Basics
python examples/01_basics.py hello Alice --count 3 --uppercase

# Async + progress
python examples/02_async_progress.py download https://example.com --size 60

# Groups
python examples/03_groups.py db.status

# Middleware & hooks
python examples/04_middleware_hooks.py ping --times 3

# Config & env overlay
APP_PROMPT="env> " python examples/05_config_env.py show-config

# Output
python examples/06_output.py demo

# Completion
python examples/07_completion.py --shell bash > /tmp/myapp.bash

# Todo app
python examples/08_todo_app.py add "Write docs" --priority high
python examples/08_todo_app.py list
```

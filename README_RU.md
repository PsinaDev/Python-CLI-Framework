# Python CLI Framework

[**English**](README.md)

Async-first фреймворк для Python CLI. Декораторы, middleware и хуки,
JSON-конфиг с overlay из переменных окружения, shell completion, REPL.

Python 3.10+.

## Быстрый старт

```python
from cli import CLI, echo

cli = CLI(name="myapp")

@cli.command(aliases=["hi"])
@cli.argument("name")
@cli.option("--count", "-c", type=int, default=1)
@cli.option("--shout", is_flag=True)
def hello(name: str, count: int = 1, shout: bool = False) -> int:
    """Поздороваться."""
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
python app.py                  # интерактивный REPL
```

## Грабля порядка декораторов

Декораторы применяются снизу вверх — **первый** в списке `@cli.argument`
парсится **последним** позиционно. Чтобы порядок соответствовал
сигнатуре функции, аргументы перечисляются в обратном порядке:

```python
@cli.command()
@cli.argument("b", type=int)   # 2-й позиционный
@cli.argument("a", type=int)   # 1-й позиционный
def add(a: int, b: int) -> int: ...
```

## Что умеет

- Sync и async-обработчики команд
- Группы команд через классы (`@cli.group` → точечные имена `db.init`)
- Middleware-цепочка + глобальный `Hook` + per-command `before` / `after` / `on_error_for`
- `JsonConfigProvider` (file lock, иерархические ключи, опциональная JSON-schema валидация)
- `EnvOverlayConfigProvider` — `APP_DATABASE__HOST=db.local` перекрывает `database.host`
- Флаг `--config-file PATH` подменяет активный провайдер до парсинга
- Вывод: `echo`, `style`, `table`, `progress_bar`
- Генерация completion-скриптов для `bash`, `zsh`, `fish`
- Поиск плагинов через entry points (`importlib.metadata`)
- Интерактивный REPL с readline-автодополнением при запуске без аргументов
- Cleanup-коллбэки (sync или async, таймаут 5 с)

## Структура репозитория

```
cli/             пакет фреймворка
examples/        запускаемые однотемные примеры (см. examples/README.md)
tests/           юнит-тесты
documentation/   полный референс (DOCS.md / DOCS_RU.md)
```

## Примеры

| Файл | Тема |
|------|------|
| `01_basics.py` | Команды, аргументы, опции, флаги, алиасы, `@example` |
| `02_async_progress.py` | Async-команды и стили progress-bar |
| `03_groups.py` | Группы команд через классы |
| `04_middleware_hooks.py` | Middleware + глобальный `Hook` + per-command хуки |
| `05_config_env.py` | `JsonConfigProvider`, env overlay, `--config-file` |
| `06_output.py` | `echo`, `style`, `table` |
| `07_completion.py` | Генерация completion-скриптов |
| `08_todo_app.py` | Мини-todo, использующий большую часть фич |

```bash
python examples/01_basics.py hello Alice --count 3 --shout
```

## Документация

[`documentation/DOCS_RU.md`](documentation/DOCS_RU.md).

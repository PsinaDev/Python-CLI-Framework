# CLI Framework — Документация

[**English**](DOCS.md)

Python 3.10+. Опционально: `jsonschema` для валидации схемы конфига,
`readline` (или `pyreadline3` на Windows) для tab-completion в REPL.

## Содержание

- [Базовые понятия](#базовые-понятия)
- [Декораторы](#декораторы)
- [Вывод](#вывод)
- [Конфигурация](#конфигурация)
- [Локализация](#локализация)
- [Async-команды](#async-команды)
- [Middleware](#middleware)
- [Хуки](#хуки)
- [CLI context](#cli-context)
- [Cleanup-коллбэки](#cleanup-коллбэки)
- [Интерактивный REPL](#интерактивный-repl)
- [Shell completion](#shell-completion)
- [Плагины](#плагины)
- [Auto-generation](#auto-generation)
- [Справка по API](#справка-по-api)
- [Траблшутинг](#траблшутинг)

---

## Базовые понятия

### Жизненный цикл команды

```
sys.argv ──► run() ──► run_async()
                       │
                       ├─ извлечение --config-file (если есть), смена провайдера
                       ├─ Hook.on_before_parse(args)
                       ├─ parser.parse(args)
                       ├─ Hook.on_after_parse(parsed)
                       └─ executor.execute(command, **kwargs)
                            │
                            ├─ middleware-цепочка (внешние → внутренние)
                            ├─ Hook.on_before_execute  +  per-command before
                            ├─ handler(**kwargs)
                            ├─ Hook.on_after_execute   +  per-command after
                            └─ unwind middleware
                       │
                       └─ cleanup-коллбэки (sync или async, таймаут 5 с на каждый)
```

`cli.run()` — синхронная точка входа, внутри `asyncio.run(run_async)`.
Sync-обработчики вызываются напрямую; async-обработчики await-ятся.

### Зарезервированные имена

```
help, h, _cli_help, _cli_show_help
```

Экспортируются как `cli.RESERVED_NAMES`. Использование их для команд,
алиасов, опций, коротких флагов или параметров функции вызывает
`ValueError` на этапе декорирования.

Передача `-h` или `--help` после имени любой зарегистрированной команды
коротит парсер и печатает help этой команды вместо вызова handler-а:

```bash
python app.py greet --help
python app.py greet -h
```

### Порядок декораторов

Python применяет декораторы снизу вверх — **первый** в списке
`@cli.argument` пушится в список аргументов **последним**. Чтобы
позиционный порядок совпал с сигнатурой функции, аргументы перечисляются
в обратном порядке:

```python
@cli.command()
@cli.argument("b", type=int)
@cli.argument("a", type=int)
def add(a: int, b: int) -> int: ...
```

Порядок `@cli.option` влияет только на отображение в help — при парсинге
опции ищутся по имени.

### Default- и per-CLI-реестры

Два способа регистрации команд:

1. **Module-level** декораторы (`from cli import command, argument, option`)
   пишут в process-wide default registry. Любой созданный позже CLI
   подхватывает их, если не передать `include_default_registry=False`.
2. **Bound** декораторы конкретного экземпляра (`cli.command()`,
   `cli.argument()`, …) пишут только в приватный реестр этого CLI.
   Несколько `CLI`-экземпляров в одном процессе не конфликтуют.

`BoundDecorators(registry)` позволяет привязать декораторы к
произвольному реестру явно.

---

## Декораторы

### `@cli.command`

```python
cli.command(
    name: str | None = None,
    help: str | None = None,
    aliases: list[str] | None = None,
)
```

`name` по умолчанию — имя функции; `help` перекрывает первую строку
docstring; `aliases` добавляет альтернативные имена.

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

Поддерживаемые `type`: `str`, `int`, `float`, `bool`, `list`, `dict`,
`tuple`, наследники `Enum`, `Optional[T]`. `list` и `dict` принимают
JSON или упрощённый синтаксис `key=value` / CSV в командной строке.

`optional=True` делает позиционный аргумент опциональным; такой аргумент
обязан идти последним. `group` — display-only метка.

### `@cli.option`

```python
cli.option(
    name: str,
    short: str | None = None,
    help: str | None = None,
    type: type = str,
    default: Any = ...,            # обязателен, если нет default_factory
    default_factory: Callable[[], Any] | None = None,
    is_flag: bool | None = None,   # автоопределение по типу
    group: str | None = None,
    exclusive_group: str | None = None,
)
```

- `name` принимает `"--verbose"` или `"verbose"`; `short` — `"-v"` или `"v"` (один символ).
- `is_flag` автоматически становится `True` для `bool`-типа или `bool`-default.
- `default_factory` создаёт свежее значение на каждый парс — нужно для дефолтов-`list`/`dict`, чтобы они не шарились между запусками.
- `exclusive_group`: опции с одинаковой меткой становятся взаимоисключающими на уровне парсера.

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

Добавляет пример использования в help команды. Стекается.

### `@cli.group`

```python
cli.group(name: str | None = None, help: str | None = None)
```

Декоратор класса. Методы класса, помеченные `@cli.command`, становятся
точечными командами в namespace группы.

Класс инстанцируется **один раз** на регистрацию CLI без аргументов —
либо предоставьте `__init__` без обязательных параметров (или вообще
без него), либо опирайтесь на module-level state, если нужно
персистировать данные:

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

## Вывод

### `echo`

```python
echo(
    text: str,
    style: str | None = None,
    file: TextIO = sys.stdout,
    formatter: TerminalOutputFormatter | None = None,
) -> None
```

Имена стилей: `success`, `error`, `warning`, `info`, `header`, `debug`,
`code`. `None` — нестилизованный вывод.

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

Возвращает строку, обёрнутую ANSI-последовательностями. Поддерживает 8
стандартных цветов и `bright_*` варианты.

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

Авторазмерная таблица с box-drawing символами; ANSI-коды внутри ячеек
учитываются при измерении ширины.

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

Возвращает `update(current)`. Если `file` — не TTY и `force_inline=None`,
вывод переключается на одну строку на обновление.

---

## Конфигурация

### `JsonConfigProvider`

```python
JsonConfigProvider(
    path: str,
    default_config: dict[str, Any] | None = None,
    schema: dict[str, Any] | None = None,
)
```

Thread-safe JSON-хранилище с file lock. Методы интерфейса
`ConfigProvider`:

- `get(key, default=None)` — иерархический доступ через точку
- `set(key, value)` — пишет в in-memory копию
- `update(mapping)` — deep merge
- `delete(key)` — удалить лист
- `save()` — атомарная запись на диск
- `get_all()` — полный snapshot

### Иерархические ключи

```python
cli.config.set("database.host", "localhost")
cli.config.set("database.port", 5432)
cli.config.update({"app": {"theme": "dark", "language": "en"}})
host = cli.config.get("database.host")
cli.config.save()
```

### Валидация схемой

Если установлен `jsonschema` и передана `schema`, каждая загрузка и
запись валидируется против неё. Фреймворк поставляет
`DEFAULT_CONFIG_SCHEMA`, покрывающую поля локализации, которые он сам
использует:

```python
from cli import DEFAULT_CONFIG_SCHEMA, JsonConfigProvider

provider = JsonConfigProvider(
    "myapp.json",
    default_config={"version": "1.0.0",
                    "default_language": "en", "languages": ["en"]},
    schema=DEFAULT_CONFIG_SCHEMA,
)
```

Ошибки: `ConfigError`, `ConfigValidationError`, `ConfigIOError`,
`ConfigLockError`. `sanitize_for_logging(value)` вырезает поля,
похожие на секреты, перед логированием.

### `EnvOverlayConfigProvider`

```python
EnvOverlayConfigProvider(
    inner: ConfigProvider,
    prefix: str,
    separator: str = "__",
)
```

Read-overlay переменных окружения поверх любого внутреннего провайдера:

```
APP_FOO=bar              -> foo = "bar"
APP_DATABASE__HOST=db    -> database.host = "db"
APP_TIMEOUT=30           -> timeout = 30          (распарсится как int)
APP_FEATURES='["a","b"]' -> features = ["a","b"]  (распарсится как JSON)
```

Значения сначала пытаются распарситься как JSON; при ошибке —
возвращаются как сырые строки. `set()`, `delete()`, `save()`
проксируются во внутренний провайдер — overlay сам по себе read-only.
После мутации `os.environ` нужно вызвать `refresh()` для перечитки.

### Флаг `--config-file`

Любой CLI на этом фреймворке принимает `--config-file PATH` перед
именем команды. Провайдер подменяется до начала парсинга:

```bash
python myapp.py --config-file /etc/myapp/prod.json deploy
```

---

## Локализация

`ConfigBasedMessageProvider` читает строки из
`config["messages"][<lang>][<key>]`:

```python
cli.messages.get_message("greeting", default="Hello, {name}!", name="Alice")
cli.messages.set_language("ru")
cli.messages.get_current_language()
cli.messages.get_available_languages()
```

Чтобы добавить язык, пишем в конфиг и сохраняем:

```python
cli.config.update({
    "messages": {
        "ru": {"prompt": "приложение> ", "app_quit": "Выход."}
    }
})
cli.config.save()
cli.messages.set_language("ru")
```

Плейсхолдеры формата подставляются через safe formatter, который
игнорирует отсутствующие ключи вместо исключения. Ошибки: `MessageError`.

---

## Async-команды

```python
import asyncio

@cli.command()
@cli.argument("url")
async def fetch(url: str) -> int:
    await asyncio.sleep(0.5)
    return 0
```

Executor всегда работает через `asyncio.run` на верхнем уровне.
Sync-обработчики вызываются напрямую без оффлоада в поток.

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

Только async middleware принимаются (`TypeError` иначе). Цепочка
вызывается в порядке регистрации вокруг handler-а:

```
cli.use(a); cli.use(b)
# вызов: a → b → handler → b unwind → a unwind
```

`cli.use_logging_middleware()` регистрирует встроенный tracer,
использующий логгер фреймворка.

Множество `bypass_middleware` исполнителя (`{"help", "version", "exit"}`
по умолчанию) пропускает цепочку для этих команд.

---

## Хуки

### Глобальный интерфейс `Hook`

Наследуйте `Hook` и переопределяйте только нужные фазы. Все пять — no-op
по умолчанию.

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

`on_before_parse` и `on_after_parse` могут вернуть изменённые данные,
чтобы повлиять на последующие этапы пайплайна. Исключения в любом
глобальном хуке ловятся и логируются — выполнение не прерывается.

### Per-command хуки

```python
@cli.before("ping")
async def _before(kwargs: dict[str, Any]) -> None: ...

@cli.after("ping")
async def _after(result: Any, exit_code: int) -> None: ...

@cli.on_error_for("boom")
async def _on_error(error: BaseException) -> None: ...
```

Сигнатуры per-command хуков **не** содержат имя команды (в отличие от
методов глобального `Hook`). Их исключения тоже логируются и не
прерывают выполнение, поэтому валидацию входов делайте внутри handler-а
с возвратом ненулевого exit code.

---

## CLI context

`ContextVar`, который executor наполняет на время выполнения команды.
Доступен из middleware и из handler-а:

```python
ctx = cli.get_context()
# {
#   "command":      "greet",
#   "args":         {"name": "Alice"},
#   "cli_instance": <CLI ...>,
# }

cli.set_context(user_id=42, request_id="abc-123")
```

Обновления мержатся в существующий dict.

---

## Cleanup-коллбэки

```python
def flush() -> None: ...
async def close_db() -> None: ...

cli.add_cleanup_callback(flush)
cli.add_cleanup_callback(close_db)
```

Запускаются после возврата из `run_async` (успех или ошибка) перед
завершением процесса. На каждый коллбэк — таймаут 5 секунд; таймауты и
исключения логируются, но не останавливают остальные. На второй
`SIGINT`/`SIGTERM` синхронные коллбэки запускаются по emergency-пути
перед `os._exit(1)`.

---

## Интерактивный REPL

`cli.run()` без аргументов автоматически входит в REPL. Возможности:

- история и tab-completion на readline (длинные опции + имена команд через prefix trie)
- встроенные `help`, `version`, `exit` / `quit` / `q`
- одно `Ctrl+C` отменяет ввод текущей строки; второе в течение ~2 с — выход
- fuzzy-suggest "did you mean ..." для неизвестных команд (Levenshtein ≤ 2)

```python
cli.enable_readline(False)   # отключить интеграцию с readline
```

---

## Shell completion

```python
cli.generate_completion("bash")            # вернёт сам скрипт
cli.install_completion("zsh")              # запишет в дефолтное место
cli.install_completion("fish", "/tmp/x")   # запишет по указанному пути
```

Также экспортируется enum `Shell` (`Shell.BASH`, `Shell.ZSH`,
`Shell.FISH`). Дефолтные пути установки:

| Shell | Путь |
|-------|------|
| bash  | `~/.bash_completion.d/<n>.bash` |
| zsh   | `~/.zsh/completions/_<n>` |
| fish  | `~/.config/fish/completions/<n>.fish` |

---

## Плагины

Поиск и вызов внешних пакетов, зарегистрированных под группой entry
points (`importlib.metadata`):

```python
results = cli.load_plugins("myapp.plugins", fail_fast=False)
# {"audit": True, "metrics": False, ...}
```

В `pyproject.toml` плагин-пакета:

```toml
[project.entry-points."myapp.plugins"]
audit = "myaudit.plugin:register"
```

`myaudit.plugin.register(cli)` регистрирует команды, хуки или middleware.

Standalone-хелперы: `discover_plugins(group)`, `load_plugins(cli, group)`.
Ошибки: `PluginError`.

---

## Auto-generation

`cli.generate_from(obj, safe_mode=True)` интроспектирует функцию, класс
или экземпляр и регистрирует команды без декораторов. С `safe_mode`
приватные атрибуты (с подчёркиванием) пропускаются, а
неинстанцируемые классы вызывают warning вместо исключения.

```python
class Math:
    def add(self, a: int, b: int) -> int:
        return 0
    def mul(self, a: int, b: int) -> int:
        return 0

cli.generate_from(Math)   # зарегистрирует "math.add", "math.mul"
```

Параметры с дефолтами становятся опциями; без дефолтов — обязательными
позиционными аргументами. Boolean-параметры становятся флагами.

---

## Справка по API

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

`shell_posix` управляет тем, как REPL разбивает строки ввода на токены.
`True` — режим `shlex` POSIX (кавычки интерпретируются и снимаются).
`False` — токены сохраняются сырыми, фреймворк только снимает совпадающие
внешние кавычки; удобно на Windows, чтобы пути вида `C:\Users\foo` не
требовали экранирования. `None` (по умолчанию) — POSIX на Unix,
non-POSIX на Windows.

Методы (выборка; полный список — в `cli/application.py`):

| Метод | Назначение |
|-------|------------|
| `command`, `argument`, `option`, `example`, `group` | bound-декораторы |
| `before`, `after`, `on_error_for` | per-command хуки |
| `use(middleware)` | добавить async middleware |
| `use_logging_middleware()` | зарегистрировать встроенный tracer |
| `add_hook(hook)` | зарегистрировать глобальный `Hook` |
| `add_cleanup_callback(cb)` | sync или async коллбэк |
| `get_context()` / `set_context(**kwargs)` | command-scoped `ContextVar` |
| `enable_readline(enable=True)` | переключение readline в REPL |
| `load_plugins(group, fail_fast=False)` | вызов entry-point плагинов |
| `generate_completion(shell)` | вернуть строку с completion-скриптом |
| `install_completion(shell, path=None)` | записать completion-скрипт на диск |
| `generate_from(obj, safe_mode=True)` | автогенерация из класса/функции |
| `register_all_commands()` | принудительный обход реестра (вызывается на первом запуске) |
| `run(args=None)` | sync entry point → exit code |
| `run_async(args=None)` | async entry point → exit code |
| `run_interactive()` | войти в REPL напрямую |

Атрибуты:

| Атрибут | Тип |
|---------|-----|
| `config` | `ConfigProvider` |
| `messages` | `MessageProvider` |
| `output` | `OutputFormatter` |
| `commands` | `CommandRegistry` |
| `parser` | `ArgumentParser` |
| `pipeline` | `MiddlewarePipeline` |
| `hook_manager` | `HookManager` |
| `executor` | `CommandExecutor` |
| `exit_code` | `int` (результат последней команды) |

### Публичные экспорты `cli`

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

## Траблшутинг

### Цвета не отображаются

Вывод определён как не-TTY (пайп или редирект). Принудительно включить
цвета можно через свой `TerminalOutputFormatter` с `force_color=True`,
либо вручную выводить ANSI через `style()`.

### Tab-completion не работает в REPL

Нужен `readline` (стандартная библиотека на Linux/macOS) либо
`pyreadline3` на Windows. Проверка: `cli.enable_readline(True)`.
Completion срабатывает только для первого whitespace-разделённого
токена (имя команды) и длинных опций.

### `RuntimeError: CLI Framework requires Python 3.10+`

Бросается из `cli/__init__.py` при импорте. Обновить Python.

### Конфликт зарезервированного имени

`help`, `h`, `_cli_help`, `_cli_show_help` нельзя использовать как
команды, алиасы, опции, короткие флаги или параметры функции.
Переименовать или сделать алиас.

### Per-command хук не прервал команду

Это by design — исключения в `before` / `after` / `on_error_for`
логируются, но не пробрасываются. Для валидации входов фейлите внутри
самого handler-а.

### Неправильный порядок аргументов

Декораторы стекаются снизу вверх; `@cli.argument` пишутся в обратном
порядке так, чтобы **первый** параметр функции соответствовал
**последнему** декоратору сверху функции.

### Группа теряет состояние между вызовами

Класс группы инстанцируется один раз на `cli.run()`. В CLI-режиме это
значит свежий instance на процесс — используйте module-level state или
персистите на диск (см. `examples/08_todo_app.py`).

### Async cleanup-коллбэк отвалился по таймауту

На каждый cleanup-коллбэк есть бюджет 5 секунд. Вынесите долгую работу
из cleanup или разбейте на несколько коллбэков.

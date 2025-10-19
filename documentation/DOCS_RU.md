# CLI Framework - Документация

[English](documentation/DOCS.md) | **Русский**

## Содержание

- [Введение](#введение)
- [Установка](#установка)
- [Быстрый старт](#быстрый-старт)
- [Основные концепции](#основные-концепции)
- [Декораторы команд](#декораторы-команд)
- [Форматированный вывод](#форматированный-вывод)
- [Конфигурация](#конфигурация)
- [Локализация](#локализация)
- [Расширенные возможности](#расширенные-возможности)
- [API Reference](#api-reference)
- [Примеры](#примеры)
- [Решение проблем](#решение-проблем)

---

## Введение

**CLI Framework** — профессиональная библиотека Python для создания интерфейсов командной строки с богатым функционалом.

### Ключевые особенности

- **Декларативный синтаксис** через декораторы Python
- **Автоматическая типизация** и валидация аргументов
- **Асинхронные команды** с поддержкой `async/await`
- **Форматированный вывод** (цвета, таблицы, прогресс-бары)
- **Многоязычность** через систему сообщений
- **Безопасная конфигурация** с файловыми блокировками
- **Автогенерация CLI** из классов и функций
- **Middleware и хуки** для расширения функциональности
- **CLI Context** для обмена данными между middleware и командами
- **Кроссплатформенность** (Windows, Linux, macOS)

### Требования

- **Python 3.8+** (использует `typing.get_origin`/`get_args` из стандартной библиотеки)
- Опционально: `jsonschema` (для валидации конфигурации)

---

## Установка

```bash
# Клонируйте репозиторий
git clone https://github.com/yourusername/cli-framework.git

# Установите опциональные зависимости
pip install jsonschema  # опционально
```

---

## Быстрый старт

Создайте файл `app.py`:

```python
from cliframework import CLI, echo

cli = CLI(name='myapp')

@cli.command()
@cli.argument('name', help='Имя для приветствия')
@cli.option('--greeting', '-g', default='Привет', help='Текст приветствия')
def greet(name, greeting):
    """Поприветствовать пользователя"""
    echo(f"{greeting}, {name}!", 'success')

if __name__ == '__main__':
    cli.run()
```

Запустите приложение:

```bash
# Вызов команды
python app.py greet Мир --greeting="Здравствуй"
# Выведет: Здравствуй, Мир!

# Справка
python app.py help greet

# Интерактивный режим
python app.py
```

---

## Основные концепции

### Структура команды

Команда состоит из:
- **Имя** — уникальный идентификатор команды
- **Обработчик** — функция, выполняющая логику команды
- **Аргументы** — обязательные позиционные параметры
- **Опции** — необязательные именованные параметры
- **Справка** — описание команды и её параметров
- **Примеры** — примеры использования

### Зарезервированные имена

Следующие имена зарезервированы и не могут использоваться для аргументов, опций или команд:
- `help`, `h` — зарезервированы для флага справки
- `_cli_help`, `_cli_show_help` — внутренняя обработка справки

Использование зарезервированных имён вызовет чёткую ошибку при регистрации команды.

### Жизненный цикл команды

1. **Парсинг** — CLI парсит аргументы командной строки
2. **Валидация** — проверка типов и обязательных параметров
3. **Хуки: Before Parse** — модификация аргументов перед парсингом
4. **Хуки: After Parse** — модификация результатов парсинга
5. **Настройка контекста** — заполнение CLI context
6. **Хуки: Before Execute** — логика перед выполнением
7. **Цепочка Middleware** — выполнение middleware в порядке регистрации
8. **Выполнение** — вызов обработчика команды
9. **Хуки: After Execute** — логика после выполнения
10. **Обработка результата** — возврат кода завершения
11. **Очистка** — выполнение cleanup callbacks

---

## Декораторы команд

### @command

Определяет команду:

```python
@cli.command(name='hello', help='Сказать привет', aliases=['hi', 'greet'])
def hello_command():
    echo('Привет, мир!', 'info')
```

**Параметры:**
- `name` (str, optional) — имя команды (по умолчанию — имя функции)
- `help` (str, optional) — описание команды (по умолчанию — docstring)
- `aliases` (List[str], optional) — альтернативные имена команды

### @argument

Добавляет позиционный аргумент:

```python
@cli.command()
@cli.argument('filename', help='Путь к файлу', type=str)
@cli.argument('count', help='Количество строк', type=int)
@cli.argument('output', help='Выходной файл', type=str, optional=True)
def process(filename, count, output=None):
    echo(f'Обработка {filename}, строк: {count}')
    if output:
        echo(f'Вывод в: {output}')
```

**Параметры:**
- `name` (str) — имя аргумента
- `help` (str, optional) — описание аргумента
- `type` (Type, optional) — тип аргумента (по умолчанию `str`)
- `optional` (bool, optional) — является ли аргумент опциональным (по умолчанию `False`)

**Важно:** Разрешён только один опциональный позиционный аргумент, и он должен быть последним.

**Поддерживаемые типы:** `str`, `int`, `float`, `bool`, `list`, `dict`, `tuple`

### @option

Добавляет именованную опцию:

```python
@cli.command()
@cli.option('--verbose', '-v', is_flag=True, help='Подробный вывод')
@cli.option('--output', '-o', type=str, default='output.txt', help='Выходной файл')
@cli.option('--count', '-c', type=int, default=1, help='Количество повторений')
def process(verbose, output, count):
    if verbose:
        echo(f'Вывод в {output}, повторов: {count}', 'info')
```

**Параметры:**
- `name` (str) — имя опции (с `--` или без)
- `short` (str, optional) — короткое имя (с `-` или без)
- `help` (str, optional) — описание опции
- `type` (Type, optional) — тип опции (по умолчанию `str`)
- `default` (Any, optional) — значение по умолчанию
- `is_flag` (bool, optional) — булев флаг (True/False)

**Флаги с default=True:** Используйте `--no-<имя>` для отключения (например, `--no-verbose`)

### @example

Добавляет пример использования:

```python
@cli.command()
@cli.argument('source', help='Исходный файл')
@cli.argument('dest', help='Целевой файл')
@cli.option('--force', '-f', is_flag=True, help='Принудительная перезапись')
@cli.example('copy input.txt output.txt')
@cli.example('copy data.json backup.json --force')
def copy(source, dest, force):
    echo(f'Копирование {source} -> {dest}')
```

### @group

Создаёт группу команд из класса:

```python
@cli.group(name='database', help='Команды для работы с БД')
class Database:
    @cli.command()
    def init(self):
        """Инициализировать базу данных"""
        echo('Инициализация БД...', 'info')
    
    @cli.command()
    @cli.option('--dry-run', is_flag=True, help='Тестовый запуск')
    def migrate(self, dry_run):
        """Запустить миграции"""
        if dry_run:
            echo('Тестовый режим миграций', 'warning')
        else:
            echo('Запуск миграций...', 'info')

# Команды доступны как: database.init, database.migrate
```

---

## Форматированный вывод

### Функция echo()

Функция `echo()` выводит стилизованный текст:

```python
from cliframework import echo
import sys

# Простой вывод
echo('Привет, мир!')

# Предопределённые стили
echo('Успех!', 'success')      # Зелёный
echo('Внимание!', 'warning')   # Жёлтый
echo('Ошибка!', 'error')       # Красный
echo('Информация', 'info')     # Синий
echo('Заголовок', 'header')    # Жирный белый
echo('Отладка', 'debug')       # Серый

# Вывод в stderr
echo('Произошла ошибка!', 'error', file=sys.stderr)

# Пользовательский форматтер
from cliframework import TerminalOutputFormatter
formatter = TerminalOutputFormatter(use_colors=True)
echo('Пользовательское форматирование', 'success', formatter=formatter)
```

**Доступные стили:** `success`, `error`, `warning`, `info`, `header`, `debug`, `emphasis`, `code`, `highlight`

### Кастомное форматирование

Функция `style()` применяет произвольное форматирование:

```python
from cliframework import style

# Цвета переднего плана
text = style('Красный текст', fg='red')
text = style('Яркий синий', fg='bright_blue')

# Цвета фона
text = style('Текст на жёлтом фоне', fg='black', bg='yellow')

# Стили текста
text = style('Жирный', bold=True)
text = style('Подчёркнутый', underline=True)
text = style('Жирный красный', fg='red', bold=True)

print(text)
```

**Доступные цвета:** `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`, `bright_*` (варианты)

### Таблицы

Функция `table()` выводит форматированные таблицы:

```python
from cliframework import table
import sys

headers = ['Имя', 'Возраст', 'Город']
rows = [
    ['Алексей', '28', 'Москва'],
    ['Мария', '32', 'Санкт-Петербург'],
    ['Иван', '25', 'Новосибирск']
]

# Вывод в stdout (по умолчанию)
table(headers, rows)

# Вывод в stderr
table(headers, rows, file=sys.stderr)

# С указанной шириной колонок
table(headers, rows, max_col_width=20)
```

### Индикаторы прогресса

Функция `progress_bar()` создаёт интерактивный прогресс-бар:

```python
from cliframework import progress_bar
import time
import sys

total = 100

# Базовое использование
update = progress_bar(total)
for i in range(total + 1):
    update(i)
    time.sleep(0.02)

# Расширенное использование
update = progress_bar(
    total,
    width=50,                    # Ширина бара
    char='█',                    # Символ заполнения
    empty_char='·',              # Символ пустоты
    show_percent=True,           # Показать процент
    show_count=True,             # Показать счётчик (текущий/всего)
    prefix='Загрузка:',          # Текст перед баром
    suffix='завершено',          # Текст после бара
    color_low='yellow',          # Цвет для 0-33%
    color_mid='blue',            # Цвет для 33-66%
    color_high='green',          # Цвет для 66-100%
    brackets=('[', ']'),         # Символы скобок
    file=sys.stdout,             # Поток вывода
    force_inline=None            # Принудительное inline обновление (None=автоопределение)
)

for i in range(total + 1):
    update(i)
    time.sleep(0.02)
```

**Поддержка потоков:** Все функции вывода (`echo`, `table`, `progress_bar`) поддерживают пользовательские потоки через параметр `file`.

---

## Конфигурация

CLI Framework предоставляет безопасное хранилище конфигурации с автоматическими блокировками.

### Работа с конфигурацией

```python
from cliframework import CLI

cli = CLI(name='myapp')

# Сохранение значений
cli.config.set('app.name', 'My Application')
cli.config.set('app.version', '1.0.0')
cli.config.set('database.host', 'localhost')
cli.config.set('database.port', 5432)
cli.config.save()

# Чтение значений
app_name = cli.config.get('app.name', 'Default')
db_host = cli.config.get('database.host', 'localhost')

# Получение всей конфигурации
config_dict = cli.config.get_all()
```

### Обновление конфигурации

**Метод 1: Использование set() для иерархических ключей (рекомендуется)**
```python
cli.config.set('app.theme', 'dark')
cli.config.set('app.language', 'ru')
cli.config.save()
```

**Метод 2: Использование update() с вложенными словарями**
```python
# Правильно: вложенная структура
cli.config.update({
    'app': {
        'theme': 'dark',
        'language': 'ru'
    }
})
cli.config.save()

# НЕПРАВИЛЬНО: плоские ключи с точками
# cli.config.update({'app.theme': 'dark'})  # Создаст буквальный ключ 'app.theme'
```

### Иерархический доступ

Конфигурация поддерживает доступ через точки для вложенных структур:

```python
# Установка вложенных значений
cli.config.set('server.database.credentials.username', 'admin')
cli.config.set('server.database.credentials.password', 'secret')

# Чтение вложенных значений
username = cli.config.get('server.database.credentials.username')
```

**Примечание:** Чувствительные ключи (содержащие 'password', 'token', 'secret' и т.д.) автоматически маскируются в логах.

---

## Локализация

CLI Framework поддерживает многоязычность через систему сообщений.

### Использование сообщений

```python
from cliframework import CLI, echo

cli = CLI(name='myapp')

@cli.command()
@cli.argument('name', help='Имя пользователя')
def greet(name):
    """Поприветствовать пользователя"""
    message = cli.messages.get_message(
        'greeting',
        default='Hello, {name}!',
        name=name
    )
    echo(message, 'success')
```

**Примечание:** Кэш сообщений теперь правильно обрабатывает параметр `default`, гарантируя, что разные defaults для одного ключа не вернут закэшированное неверное значение.

### Добавление языков

```python
# Добавление русского языка
ru_messages = {
    'greeting': 'Привет, {name}!',
    'goodbye': 'До свидания!',
}

cli.messages.add_language('ru', ru_messages)

# Переключение языка
cli.messages.set_language('ru')

# Удаление языка (сохраняет сообщения по умолчанию)
cli.messages.remove_language('ru', purge=False)

# Удаление языка и сообщений
cli.messages.remove_language('ru', purge=True)
```

---

## Расширенные возможности

### Асинхронные команды

CLI Framework полностью поддерживает асинхронные команды:

```python
import asyncio
from cliframework import CLI, echo

cli = CLI(name='myapp')

@cli.command()
@cli.argument('url', help='URL для загрузки')
async def download(url):
    """Асинхронная загрузка данных"""
    echo(f'Загрузка {url}...', 'info')
    await asyncio.sleep(2)
    echo('Загрузка завершена!', 'success')
    return 0

if __name__ == '__main__':
    cli.run()
```

### Middleware

Middleware позволяет добавлять функциональность к выполнению команд. Весь middleware должен быть асинхронными функциями.

#### Базовый Middleware

```python
from cliframework import CLI, echo
import time

cli = CLI(name='myapp')

# Middleware для измерения времени
async def timing_middleware(next_handler):
    start = time.time()
    result = await next_handler()
    elapsed = time.time() - start
    echo(f'Выполнено за {elapsed:.2f}s', 'debug')
    return result

# Middleware для логирования
async def logging_middleware(next_handler):
    echo('→ Начало выполнения команды', 'debug')
    result = await next_handler()
    echo('← Команда завершена', 'debug')
    return result

# Регистрация middleware (выполняются в порядке регистрации)
cli.use(logging_middleware)
cli.use(timing_middleware)

@cli.command()
def hello():
    """Тестовая команда"""
    echo('Привет, мир!', 'info')
    time.sleep(1)

if __name__ == '__main__':
    cli.run()
```

**Важно:** Поддерживается только асинхронный middleware. Синхронный middleware не может правильно реализовать around-паттерн, требуемый фреймворком.

#### Встроенное Logging Middleware

CLI Framework предоставляет встроенное middleware для отладки:

**Способ 1: Включить при инициализации**
```python
import logging
cli = CLI(name='myapp', auto_logging_middleware=True, log_level=logging.DEBUG)
```

**Способ 2: Добавить вручную**
```python
import logging
cli = CLI(name='myapp', log_level=logging.DEBUG)
cli.use_logging_middleware()
```

Это middleware логирует (на уровне DEBUG):
- Имя команды и аргументы перед выполнением
- Результат выполнения после завершения
- Ошибки выполнения

### Хуки жизненного цикла

Хуки позволяют расширить поведение CLI в определённых точках. Все методы хуков асинхронные.

```python
from cliframework import CLI, echo
from cliframework.interfaces import Hook

cli = CLI(name='myapp')

class LoggingHook(Hook):
    async def on_before_parse(self, args):
        echo(f'Парсинг: {args}', 'debug')
        return args
    
    async def on_after_parse(self, parsed):
        echo(f'Распарсено: {parsed}', 'debug')
        return parsed
    
    async def on_before_execute(self, command, kwargs):
        echo(f'Выполнение: {command}({kwargs})', 'debug')
    
    async def on_after_execute(self, command, result, exit_code):
        echo(f'Завершено: {command} -> {exit_code}', 'debug')
    
    async def on_error(self, command, error):
        echo(f'Ошибка в {command}: {error}', 'error')

cli.add_hook(LoggingHook())
```

### CLI Context

CLI Context позволяет обмениваться данными между middleware и командами.

#### Доступ к контексту в Middleware

```python
async def context_aware_middleware(next_handler):
    # Получить контекст выполнения
    ctx = cli.get_context()
    command = ctx.get('command')           # имя команды
    args = ctx.get('args', {})             # аргументы команды
    cli_instance = ctx.get('cli_instance') # экземпляр CLI
    
    echo(f"[{command}] Выполнение с: {args}", 'debug')
    
    result = await next_handler()
    return result

cli.use(context_aware_middleware)
```

#### Установка пользовательских данных

```python
async def auth_middleware(next_handler):
    # Установить данные в контекст
    cli.set_context(
        user_id=123,
        role='admin',
        timestamp=time.time()
    )
    
    result = await next_handler()
    return result

async def audit_middleware(next_handler):
    # Прочитать данные из контекста
    ctx = cli.get_context()
    user_id = ctx.get('user_id', 'anonymous')
    command = ctx.get('command', 'unknown')
    
    echo(f"Пользователь {user_id} выполняет '{command}'", 'debug')
    
    result = await next_handler()
    return result

cli.use(auth_middleware)
cli.use(audit_middleware)
```

**Примечание:** Контекст доступен только во время выполнения команды (в middleware). Он недоступен напрямую в обработчиках команд. Для доступа к данным контекста в командах сохраните их в переменных уровня модуля или класса из middleware.

### Автогенерация CLI

Создавайте CLI автоматически из существующих классов:

```python
from cliframework import CLI, echo

cli = CLI(name='filetools')

class FileManager:
    def list(self, path='.', show_hidden=False):
        """Вывести список файлов"""
        import os
        for item in os.listdir(path):
            if not show_hidden and item.startswith('.'):
                continue
            echo(item)
    
    def info(self, filepath):
        """Показать информацию о файле"""
        import os
        stats = os.stat(filepath)
        echo(f'Размер: {stats.st_size} байт')

# Автоматическая генерация команд
cli.generate_from(FileManager)

# Команды: filemanager.list, filemanager.info
```

**Безопасный режим (по умолчанию):** Доступны только публичные методы (не начинающиеся с `_`).

### Callback при завершении

Регистрируйте функции очистки:

```python
cli = CLI(name='myapp')

# Синхронная очистка
def cleanup():
    echo('Очистка ресурсов...', 'info')

cli.add_cleanup_callback(cleanup)

# Асинхронная очистка
async def async_cleanup():
    echo('Асинхронная очистка...', 'info')
    await asyncio.sleep(0.1)

cli.add_cleanup_callback(async_cleanup)
```

**Вызываются при:**
- Нормальном выходе
- Ctrl+C (graceful shutdown)
- Исключении

**Примечание:** Экстренная очистка (force exit) выполняет только синхронные callbacks.

### Интерактивный режим (REPL)

```python
cli = CLI(name='myapp')

@cli.command()
def status():
    """Показать статус"""
    echo('Всё работает!', 'success')

if __name__ == '__main__':
    cli.run(interactive=True)
```

**Tab completion:** Включён по умолчанию. Для Windows: `pip install pyreadline3`

---

## API Reference (краткий)

### CLI

```python
CLI(name, config_path=None, log_level=logging.INFO, auto_logging_middleware=False, ...)
```

**Методы:**
- `command()`, `argument()`, `option()`, `example()`, `group()` — декораторы
- `use(middleware)` — добавить async middleware
- `add_hook(hook)` — добавить хук жизненного цикла
- `get_context()` / `set_context(**kwargs)` — работа с контекстом
- `add_cleanup_callback()` — регистрация cleanup
- `run()`, `run_async()`, `run_interactive()` — запуск

### Функции вывода

```python
echo(text, style=None, file=sys.stdout, formatter=None)
style(text, fg=None, bg=None, bold=False, underline=False, ...)
table(headers, rows, max_col_width=None, file=sys.stdout, formatter=None)
progress_bar(total, width=None, char='█', file=sys.stdout, ...) -> Callable[[int], None]
```

---

## Решение проблем

### Цвета не отображаются

```python
cli = CLI(name='app', output_formatter=TerminalOutputFormatter(use_colors=True))
```

### Tab completion не работает (Windows)

```bash
pip install pyreadline3
```

### Ошибка версии Python

Требуется Python 3.8+. Проверьте: `python --version`

### Конфликт зарезервированных имён

Избегайте: `help`, `h`, `_cli_help`, `_cli_show_help`

```python
# Неправильно
@cli.argument('help')

# Правильно
@cli.argument('help_text')
```

### Контекст недоступен в команде

Контекст доступен только в middleware. Сохраните данные в переменных модуля:

```python
current_context = {}

async def store_middleware(next_handler):
    ctx = cli.get_context()
    current_context.update(ctx)
    return await next_handler()

cli.use(store_middleware)

@cli.command()
def cmd():
    username = current_context.get('username')
```

### Вывод не перенаправляется

Используйте параметр `file`:

```python
import sys

echo('Ошибка', 'error', file=sys.stderr)
table(headers, rows, file=sys.stderr)

with open('log.txt', 'w') as f:
    echo('В файл', file=f)
```

---

## Архитектура

Модульная архитектура с чёткими интерфейсами:

- **CLI** — главный оркестратор
- **CommandRegistry** — хранилище команд с Trie-автодополнением
- **ArgumentParser** — парсинг с LRU кэшем
- **ConfigProvider** — конфигурация с блокировками
- **MessageProvider** — локализация с кэшированием
- **OutputFormatter** — форматированный вывод
- **Middleware** — расширяемая цепочка обработки
- **Hook** — система событий жизненного цикла

Все компоненты реализуют абстрактные интерфейсы из `interfaces.py`, позволяя легко заменять их пользовательскими реализациями.

---

## Версия

CLI Framework **v1.1.0** от **Psinadev**

Полная английская документация: [DOCS.md](DOCS.md)

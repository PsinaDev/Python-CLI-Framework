# CLI Framework - Документация

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
  - [Асинхронные команды](#асинхронные-команды)
  - [Middleware](#middleware)
  - [CLI Context](#cli-context)
  - [Автогенерация CLI](#автогенерация-cli)
  - [Callback при завершении](#callback-при-завершении)
  - [Интерактивный режим (REPL)](#интерактивный-режим-repl)
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
- **Middleware** для расширения функциональности
- **CLI Context** для обмена данными между middleware и командами
- **Кроссплатформенность** (Windows, Linux, macOS)

### Требования

- Python 3.7+
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
from cli import CLI, echo

# Создайте экземпляр CLI
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

### Жизненный цикл команды

1. **Парсинг** — CLI парсит аргументы командной строки
2. **Валидация** — проверка типов и обязательных параметров
3. **Настройка контекста** — заполнение CLI context
4. **Цепочка Middleware** — выполнение middleware в порядке регистрации
5. **Выполнение** — вызов обработчика команды
6. **Обработка результата** — возврат кода завершения
7. **Очистка** — выполнение cleanup callbacks

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
def process(filename, count):
    echo(f'Обработка {filename}, строк: {count}')
```

**Параметры:**
- `name` (str) — имя аргумента
- `help` (str, optional) — описание аргумента
- `type` (Type, optional) — тип аргумента (по умолчанию `str`)

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

### Цветной текст

Функция `echo()` выводит стилизованный текст:

```python
from cli import echo

# Предопределённые стили
echo('Успешно выполнено!', 'success')   # Зелёный
echo('Внимание!', 'warning')             # Жёлтый
echo('Ошибка!', 'error')                 # Красный
echo('Информация', 'info')               # Синий
echo('Заголовок', 'header')              # Жирный белый
echo('Отладка', 'debug')                 # Серый
```

**Доступные стили:** `success`, `error`, `warning`, `info`, `header`, `debug`, `emphasis`, `code`, `highlight`

### Кастомное форматирование

Функция `style()` применяет произвольное форматирование:

```python
from cli import style

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

**Доступные цвета:** `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`, `bright_*` (версии для каждого цвета)

### Таблицы

Функция `table()` выводит форматированные таблицы:

```python
from cli import table

headers = ['Имя', 'Возраст', 'Город']
rows = [
    ['Алексей', '28', 'Москва'],
    ['Мария', '32', 'Санкт-Петербург'],
    ['Иван', '25', 'Новосибирск']
]

table(headers, rows)
```

### Индикаторы прогресса

Функция `progress_bar()` создаёт интерактивный прогресс-бар:

```python
from cli import progress_bar
import time

total = 100
update = progress_bar(
    total,
    prefix='Загрузка:',
    suffix='завершено',
    char='█',
    empty_char='░',
    show_percent=True,
    show_count=True
)

for i in range(total + 1):
    update(i)
    time.sleep(0.02)
```

---

## Конфигурация

CLI Framework предоставляет безопасное хранилище конфигурации с автоматическими блокировками.

### Работа с конфигурацией

```python
from cli import CLI

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

# Обновление из словаря
cli.config.update({
    'app.theme': 'dark',
    'app.language': 'ru'
})
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

---

## Локализация

CLI Framework поддерживает многоязычность через систему сообщений.

### Использование сообщений

```python
from cli import CLI, echo

cli = CLI(name='myapp')

@cli.command()
@cli.argument('name', help='Имя пользователя')
def greet(name):
    """Поприветствовать пользователя"""
    message = cli.messages.get_message(
        'greeting',
        'Hello, {name}!',
        name=name
    )
    echo(message, 'success')
```

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
```

---

## Расширенные возможности

### Асинхронные команды

CLI Framework полностью поддерживает асинхронные команды:

```python
import asyncio
from cli import CLI, echo

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

Middleware позволяет добавлять функциональность к выполнению команд.

#### Базовый Middleware

```python
from cli import CLI, echo
import time

cli = CLI(name='myapp')

# Middleware для измерения времени выполнения
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

# Регистрация middleware
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

#### Встроенное Logging Middleware

CLI Framework предоставляет встроенное middleware для отладки:

**Способ 1: Включить при инициализации**
```python
cli = CLI(name='myapp', auto_logging_middleware=True)
```

**Способ 2: Добавить вручную**
```python
cli = CLI(name='myapp')
cli.use_logging_middleware()
```

Это middleware логирует:
- Имя команды и аргументы перед выполнением
- Результат выполнения или ошибки
- Выполнение на уровне DEBUG

Пример вывода:
```
[Middleware] Executing command 'greet' with args: {'name': 'Мир', 'greeting': 'Привет'}
[Middleware] Command 'greet' completed successfully with result: 0
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

#### Установка пользовательских данных в контекст

Вы можете сохранять пользовательские данные в контексте для использования в цепочке middleware:

```python
async def auth_middleware(next_handler):
    # Установить пользовательские данные в контекст
    cli.set_context(
        user_id=123,
        role='admin',
        timestamp=time.time()
    )
    
    result = await next_handler()
    return result

async def audit_middleware(next_handler):
    # Прочитать пользовательские данные из контекста
    ctx = cli.get_context()
    user_id = ctx.get('user_id', 'anonymous')
    command = ctx.get('command', 'unknown')
    
    echo(f"Пользователь {user_id} выполняет '{command}'", 'debug')
    
    result = await next_handler()
    return result

cli.use(auth_middleware)
cli.use(audit_middleware)
```

#### Доступные данные в контексте

CLI context содержит:
- `command` (str) — имя выполняемой команды
- `args` (dict) — распарсенные аргументы команды
- `cli_instance` (CLI) — ссылка на экземпляр CLI
- Любые пользовательские данные, установленные через `set_context()`

#### Полный пример с контекстом

```python
from cli import CLI, echo
import time

cli = CLI(name='myapp')

# Middleware аутентификации
async def auth_middleware(next_handler):
    # Имитация аутентификации
    cli.set_context(
        authenticated=True,
        user_id=123,
        username='ivan_ivanov',
        permissions=['read', 'write']
    )
    
    echo('✓ Пользователь аутентифицирован', 'success')
    result = await next_handler()
    return result

# Middleware авторизации
async def authz_middleware(next_handler):
    ctx = cli.get_context()
    
    if not ctx.get('authenticated', False):
        echo('✗ Не аутентифицирован', 'error')
        return 1
    
    command = ctx.get('command')
    permissions = ctx.get('permissions', [])
    
    # Проверка прав
    if command == 'delete' and 'write' not in permissions:
        echo('✗ Недостаточно прав', 'error')
        return 1
    
    result = await next_handler()
    return result

# Middleware аудита
async def audit_middleware(next_handler):
    ctx = cli.get_context()
    
    username = ctx.get('username', 'anonymous')
    command = ctx.get('command', 'unknown')
    args = ctx.get('args', {})
    
    start = time.time()
    
    echo(f'[AUDIT] {username} -> {command}({args})', 'debug')
    
    result = await next_handler()
    elapsed = time.time() - start
    
    echo(f'[AUDIT] {username} <- {command} (exit={result}, time={elapsed:.2f}s)', 'debug')
    
    return result

# Регистрация middleware
cli.use(auth_middleware)
cli.use(authz_middleware)
cli.use(audit_middleware)

@cli.command()
@cli.argument('filename', help='Файл для чтения')
def read(filename):
    """Прочитать файл"""
    ctx = cli.get_context()
    username = ctx.get('username', 'unknown')
    
    echo(f'{username} читает {filename}', 'info')
    return 0

@cli.command()
@cli.argument('filename', help='Файл для удаления')
def delete(filename):
    """Удалить файл"""
    ctx = cli.get_context()
    username = ctx.get('username', 'unknown')
    
    echo(f'{username} удаляет {filename}', 'warning')
    return 0

if __name__ == '__main__':
    cli.run()
```

### Автогенерация CLI

Создавайте CLI автоматически из существующих классов:

```python
from cli import CLI

cli = CLI(name='filetools')

class FileManager:
    def list(self, path='.', show_hidden=False):
        """Вывести список файлов"""
        import os
        for item in os.listdir(path):
            if not show_hidden and item.startswith('.'):
                continue
            print(item)
    
    def info(self, filepath):
        """Показать информацию о файле"""
        import os
        stats = os.stat(filepath)
        print(f'Размер: {stats.st_size} байт')
        print(f'Изменён: {stats.st_mtime}')

# Автоматическая генерация команд
cli.generate_from(FileManager)

# Команды будут доступны как:
# filemanager.list
# filemanager.info
```

### Callback при завершении

Регистрируйте функции очистки для graceful shutdown:

```python
cli = CLI(name='myapp')

# Синхронная очистка
def cleanup():
    print('Очистка ресурсов...')
    # Закрытие соединений, сохранение состояния и т.д.

cli.add_cleanup_callback(cleanup)

# Асинхронная очистка
async def async_cleanup():
    print('Асинхронная очистка...')
    await asyncio.sleep(0.1)
    # Асинхронные задачи очистки

cli.add_cleanup_callback(async_cleanup)

# Cleanup callbacks вызываются при:
# - Нормальном выходе (команда exit)
# - Ctrl+C (graceful shutdown)
# - Исключении во время выполнения
```

**Примечание:** Асинхронные cleanup callbacks выполняются только при нормальном async завершении. Они пропускаются в signal handlers для безопасности.

### Интерактивный режим (REPL)

#### Базовый интерактивный режим

```python
cli = CLI(name='myapp')

@cli.command()
def status():
    """Показать статус"""
    echo('Всё работает!', 'success')

if __name__ == '__main__':
    # Запуск в интерактивном режиме
    cli.run(interactive=True)
```

Пример сессии:
```
Welcome to myapp
Type 'help' for available commands

myapp> status
Всё работает!

myapp> help
Available commands:
  status    Показать статус
  help      Показать справку
  exit      Выйти из приложения

myapp> exit
Goodbye!
```

#### Tab Completion

Tab completion включён по умолчанию в интерактивном режиме:

```python
cli = CLI(name='myapp')

# Включить tab completion (по умолчанию)
cli.enable_readline(True)

# Отключить tab completion
cli.enable_readline(False)

cli.run(interactive=True)
```

**Возможности:**
- Tab completion для имён команд
- История команд с помощью стрелок
- Работает на Linux/macOS (readline) и Windows (pyreadline3)

**Установка для Windows:**
```bash
pip install pyreadline3
```

---

## API Reference

### CLI

```python
CLI(
    name: str = 'app',
    config_path: Optional[str] = None,
    config_provider: Optional[ConfigProvider] = None,
    config_schema: Optional[Dict[str, Any]] = None,
    message_provider: Optional[MessageProvider] = None,
    output_formatter: Optional[OutputFormatter] = None,
    command_registry: Optional[CommandRegistry] = None,
    argument_parser: Optional[ArgumentParser] = None,
    log_level: int = logging.INFO,
    auto_logging_middleware: bool = False
)
```

**Параметры:**
- `name` — имя приложения
- `config_path` — путь к файлу конфигурации
- `config_provider` — пользовательский провайдер конфигурации
- `config_schema` — JSON схема для валидации
- `message_provider` — пользовательский провайдер сообщений
- `output_formatter` — пользовательский форматтер вывода
- `command_registry` — пользовательский реестр команд
- `argument_parser` — пользовательский парсер аргументов
- `log_level` — уровень логирования (по умолчанию: INFO)
- `auto_logging_middleware` — включить встроенное logging middleware (по умолчанию: False)

**Методы:**

- `command(name, help, aliases)` — декоратор команды
- `argument(name, help, type)` — декоратор аргумента
- `option(name, short, help, type, default, is_flag)` — декоратор опции
- `example(example_text)` — декоратор примера
- `group(name, help)` — декоратор группы
- `generate_from(obj, safe_mode=True)` — генерация CLI из объекта
- `register_all_commands()` — регистрация всех декорированных команд
- `use(middleware)` — добавление middleware
- `use_logging_middleware()` — добавление встроенного logging middleware
- `get_context() -> Dict[str, Any]` — получить текущий CLI context
- `set_context(**kwargs)` — установить переменные context
- `add_cleanup_callback(callback)` — регистрация callback при завершении
- `enable_readline(enable=True)` — включить/выключить tab completion
- `run(args=None, interactive=False) -> int` — запуск CLI (синхронный)
- `run_async(args=None, interactive=False) -> int` — запуск CLI (асинхронный)
- `run_interactive() -> int` — запуск в интерактивном режиме

**Атрибуты:**

- `config` — провайдер конфигурации
- `messages` — провайдер сообщений
- `output` — форматтер вывода
- `commands` — реестр команд
- `parser` — парсер аргументов
- `exit_code` — код завершения последней команды

### Функции вывода

#### echo()

```python
echo(text: str, style: Optional[str] = None, file: TextIO = sys.stdout) -> None
```

Вывод стилизованного текста.

#### style()

```python
style(
    text: str,
    fg: Optional[str] = None,
    bg: Optional[str] = None,
    bold: bool = False,
    underline: bool = False,
    blink: bool = False
) -> str
```

Применение стилей к тексту.

#### table()

```python
table(headers: List[str], rows: List[List[str]]) -> None
```

Вывод таблицы.

#### progress_bar()

```python
progress_bar(total: int, **kwargs) -> Callable[[int], None]
```

Создание прогресс-бара. Возвращает функцию обновления.

---

## Примеры

### Полный пример: Менеджер задач

```python
from cli import CLI, echo, table, progress_bar
import time

cli = CLI(name='tasks', auto_logging_middleware=True)

# Хранилище
tasks = []

# Middleware аутентификации
async def auth_middleware(next_handler):
    cli.set_context(user_id=1, username='admin')
    result = await next_handler()
    return result

cli.use(auth_middleware)

@cli.command()
@cli.argument('title', help='Название задачи')
@cli.option('--priority', '-p', type=int, default=1, help='Приоритет (1-5)')
def add(title, priority):
    """Добавить новую задачу"""
    ctx = cli.get_context()
    username = ctx.get('username', 'unknown')
    
    task = {
        'id': len(tasks) + 1,
        'title': title,
        'priority': priority,
        'done': False,
        'created_by': username
    }
    tasks.append(task)
    
    echo(f'✓ Задача #{task["id"]} добавлена пользователем {username}', 'success')
    return 0

@cli.command()
def list():
    """Список всех задач"""
    if not tasks:
        echo('Задачи не найдены', 'warning')
        return 0
    
    headers = ['ID', 'Название', 'Приоритет', 'Статус', 'Создал']
    rows = []
    
    for task in tasks:
        status = '✓ Выполнено' if task['done'] else '○ В ожидании'
        rows.append([
            str(task['id']),
            task['title'],
            str(task['priority']),
            status,
            task['created_by']
        ])
    
    table(headers, rows)
    return 0

@cli.command()
@cli.argument('task_id', type=int, help='ID задачи')
def done(task_id):
    """Отметить задачу как выполненную"""
    for task in tasks:
        if task['id'] == task_id:
            task['done'] = True
            echo(f'✓ Задача #{task_id} отмечена как выполненная', 'success')
            return 0
    
    echo(f'✗ Задача #{task_id} не найдена', 'error')
    return 1

@cli.command()
@cli.option('--delay', '-d', type=float, default=0.5, help='Задержка на задачу')
def process_all(delay):
    """Обработать все задачи в ожидании"""
    pending = [t for t in tasks if not t['done']]
    
    if not pending:
        echo('Нет задач в ожидании', 'info')
        return 0
    
    update = progress_bar(
        len(pending),
        prefix='Обработка:',
        suffix='завершено'
    )
    
    for i, task in enumerate(pending, 1):
        time.sleep(delay)
        task['done'] = True
        update(i)
    
    echo(f'✓ Обработано {len(pending)} задач', 'success')
    return 0

if __name__ == '__main__':
    cli.run()
```

---

## Решение проблем

### Цвета не отображаются

**Проблема:** Цвета не работают в терминале.

**Решение:**
```python
from cli import TerminalOutputFormatter

cli = CLI(
    name='myapp',
    output_formatter=TerminalOutputFormatter(use_colors=True)
)
```

### Tab Completion не работает (Windows)

**Проблема:** Tab completion не работает на Windows.

**Решение:** Установите pyreadline3:
```bash
pip install pyreadline3
```

### Context недоступен в команде

**Проблема:** `cli.get_context()` возвращает пустой словарь в обработчике команды.

**Решение:** Context доступен только во время выполнения команды через middleware. Получайте его в middleware или сохраняйте данные context в своём хранилище, если нужен доступ в командах:

```python
async def store_context_middleware(next_handler):
    ctx = cli.get_context()
    # Сохранить в глобальную или классовую переменную для доступа в командах
    global current_user
    current_user = ctx.get('username')
    
    result = await next_handler()
    return result
```

---

## Архитектура

CLI Framework использует модульную архитектуру с чёткими интерфейсами для лёгкой кастомизации и расширения.

### Компоненты

- **CLI** — главный оркестратор
- **CommandRegistry** — хранилище команд с Trie-based автодополнением
- **ArgumentParser** — парсинг аргументов с LRU кэшем
- **ConfigProvider** — хранение конфигурации с файловыми блокировками
- **MessageProvider** — локализация с кэшированием сообщений
- **OutputFormatter** — форматированный вывод в терминал
- **Middleware** — расширяемая цепочка обработки команд

---

## Лицензия

CLI Framework разработан **Psinadev**. Версия 1.0.0.

---

## Поддержка

Для вопросов и поддержки обращайтесь к этой документации или создавайте issue в репозитории проекта.
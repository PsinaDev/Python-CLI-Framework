# Python CLI Framework

[English](README.md) | **Русский**

Мощный Python-фреймворк для создания полнофункциональных интерфейсов командной строки с декларативным синтаксисом, расширенным форматированием вывода, локализацией и поддержкой асинхронности. Создавайте профессиональные CLI с минимальным количеством кода.

## Возможности

- **Декларативный API**: Легко определяйте команды через декораторы
- **Типобезопасность**: Автоматическая валидация и преобразование типов
- **Поддержка асинхронности**: Встроенная поддержка `async/await` для I/O операций
- **Расширенный вывод**: Цветной текст, таблицы, прогресс-бары с поддержкой потоков
- **Интернационализация**: Встроенная поддержка локализации с правильным кэшированием
- **Управление конфигурацией**: Хранение и загрузка настроек с блокировками и иерархическим доступом
- **Хуки жизненного цикла**: Расширение поведения в определённых точках выполнения
- **Автогенерация**: Создание CLI из существующих классов и функций
- **Модульная архитектура**: Заменяемые компоненты для максимальной гибкости

## Требования

- **Python 3.8+** (использует `typing.get_origin`/`get_args` из стандартной библиотеки)
- Опционально: `jsonschema` (для валидации конфигурации)

## Установка

Фреймворк пока недоступен в PyPI. Для установки:

```bash
# Клонируйте репозиторий
git clone https://github.com/yourusername/cli-framework.git
cd cli-framework

# Установите опциональные зависимости
pip install jsonschema  # опционально, для валидации конфигурации
```

## Быстрый старт

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

Запустите команду:
```bash
python example.py greet Мир --greeting="Здравствуй"
# Вывод: Здравствуй, Мир!
```

Получите справку:
```bash
python example.py help greet
```

Интерактивный режим:
```bash
python example.py
# Откроется интерактивная консоль с автодополнением по Tab
```

## Документация

Полная документация доступна в файле [documentation/DOCS_RU.md](DOCS_RU.md).

### Основные разделы:

- [Быстрый старт](documentation/DOCS_RU.md#быстрый-старт) — Начните за 5 минут
- [Декораторы команд](documentation/DOCS_RU.md#декораторы-команд) — Определение команд, аргументов, опций
- [Форматированный вывод](documentation/DOCS_RU.md#форматированный-вывод) — Цвета, таблицы, прогресс-бары
- [Конфигурация](documentation/DOCS_RU.md#конфигурация) — Постоянные настройки с иерархическим доступом
- [Локализация](documentation/DOCS_RU.md#локализация) — Поддержка многих языков
- [Асинхронные команды](documentation/DOCS_RU.md#асинхронные-команды) — Поддержка async/await
- [Middleware и хуки](documentation/DOCS_RU.md#middleware) — Расширение функциональности
- [CLI Context](documentation/DOCS_RU.md#cli-context) — Обмен данными между middleware и командами
- [API Reference](documentation/DOCS_RU.md#api-reference) — Полная документация API
- [Примеры](documentation/DOCS_RU.md#примеры) — Примеры из реальной практики
- [Решение проблем](documentation/DOCS_RU.md#решение-проблем) — Частые вопросы и решения

## Примеры использования

### Простая команда

```python
from cli import CLI, echo

cli = CLI(name='greeter')

@cli.command()
@cli.argument('name', help='Имя пользователя')
def hello(name):
    """Поприветствовать пользователя"""
    echo(f'Привет, {name}!', 'success')

if __name__ == '__main__':
    cli.run()
```

### Команда с опциями

```python
from cli import CLI, echo

cli = CLI(name='filetools')

@cli.command()
@cli.argument('path', help='Путь к директории')
@cli.option('--recursive', '-r', is_flag=True, help='Рекурсивный обход')
@cli.option('--hidden', is_flag=True, help='Показать скрытые файлы')
def list_files(path, recursive, hidden):
    """Список файлов в директории"""
    import os
    
    for item in os.listdir(path):
        if not hidden and item.startswith('.'):
            continue
        echo(item)
    
    if recursive:
        echo('Режим рекурсии включён', 'info')

if __name__ == '__main__':
    cli.run()
```

### Группы команд

```python
from cli import CLI, echo

cli = CLI(name='filetools')

@cli.group(name='file', help='Операции с файлами')
class FileCommands:
    @cli.command()
    @cli.argument('path', help='Путь к директории')
    def list(self, path):
        """Список файлов"""
        import os
        for item in os.listdir(path):
            echo(item)
    
    @cli.command()
    @cli.argument('source', help='Исходный файл')
    @cli.argument('dest', help='Целевой файл')
    @cli.option('--force', '-f', is_flag=True, help='Перезаписать если существует')
    def copy(self, source, dest, force):
        """Копировать файл"""
        import shutil
        import os
        if force or not os.path.exists(dest):
            shutil.copy2(source, dest)
            echo(f'Скопировано: {source} -> {dest}', 'success')
        else:
            echo(f'Файл существует: {dest}', 'warning')

if __name__ == '__main__':
    cli.run()
```

### Асинхронные команды

```python
from cli import CLI, echo
import asyncio

cli = CLI(name='fetcher')

@cli.command()
@cli.argument('url', help='URL для загрузки')
async def download(url):
    """Асинхронная загрузка"""
    echo(f'Загрузка {url}...', 'info')
    await asyncio.sleep(1)  # Имитация загрузки
    echo('Готово!', 'success')

if __name__ == '__main__':
    cli.run()
```

### Форматированный вывод

```python
from cli import CLI, echo, table, progress_bar
import time

cli = CLI(name='demo')

@cli.command()
def demo():
    """Демонстрация возможностей вывода"""
    
    # Цветной текст
    echo('Успех!', 'success')
    echo('Предупреждение!', 'warning')
    echo('Ошибка!', 'error')
    
    # Таблица
    headers = ['Имя', 'Статус', 'Прогресс']
    rows = [
        ['Задача 1', 'Завершена', '100%'],
        ['Задача 2', 'В процессе', '45%'],
        ['Задача 3', 'Ожидает', '0%']
    ]
    table(headers, rows)
    
    # Прогресс-бар
    total = 100
    update = progress_bar(total, prefix='Загрузка:')
    for i in range(total + 1):
        update(i)
        time.sleep(0.02)

if __name__ == '__main__':
    cli.run()
```

### Middleware и Context

```python
from cli import CLI, echo
import time

cli = CLI(name='myapp')

# Middleware для измерения времени
async def timing_middleware(next_handler):
    start = time.time()
    result = await next_handler()
    elapsed = time.time() - start
    echo(f'Выполнено за {elapsed:.2f}s', 'debug')
    return result

# Middleware аутентификации с контекстом
async def auth_middleware(next_handler):
    cli.set_context(user_id=123, username='admin')
    result = await next_handler()
    return result

cli.use(auth_middleware)
cli.use(timing_middleware)

@cli.command()
def status():
    """Проверить статус"""
    ctx = cli.get_context()
    username = ctx.get('username', 'guest')
    echo(f'Статус OK (пользователь: {username})', 'success')

if __name__ == '__main__':
    cli.run()
```

### Хуки жизненного цикла

```python
from cli import CLI, echo
from cli.interfaces import Hook

cli = CLI(name='myapp')

class AuditHook(Hook):
    async def on_before_parse(self, args):
        echo(f'Парсинг: {args}', 'debug')
        return args
    
    async def on_after_parse(self, parsed):
        return parsed
    
    async def on_before_execute(self, command, kwargs):
        echo(f'Выполнение: {command}', 'info')
    
    async def on_after_execute(self, command, result, exit_code):
        echo(f'Завершено с кодом: {exit_code}', 'info')
    
    async def on_error(self, command, error):
        echo(f'Ошибка: {error}', 'error')

cli.add_hook(AuditHook())
```

## Ключевые возможности

### Декларативные команды

Определяйте команды простыми декораторами:

```python
@cli.command(name='hello', aliases=['hi'])
@cli.argument('name', help='Имя пользователя', type=str)
@cli.option('--loud', '-l', is_flag=True, help='Громко!')
@cli.example('hello Мир --loud')
def hello_command(name, loud):
    """Сказать привет"""
    msg = f'ПРИВЕТ, {name.upper()}!' if loud else f'Привет, {name}'
    echo(msg, 'success' if loud else 'info')
```

### Преобразование типов

Автоматическая валидация и преобразование типов:

```python
@cli.option('--count', type=int, default=1)
@cli.option('--items', type=list, help='JSON массив или CSV')
@cli.option('--config', type=dict, help='JSON объект или key=val')
@cli.option('--verbose', is_flag=True)
def process(count, items, config, verbose):
    # Типы автоматически валидируются и преобразуются
    for i in range(count):
        echo(f'Обработка элемента {i}')
```

**Поддерживаемые типы:** `str`, `int`, `float`, `bool`, `list`, `dict`, `tuple`, `Optional[T]`

### Безопасная конфигурация

Потокобезопасная конфигурация с файловыми блокировками:

```python
# Иерархические ключи
cli.config.set('database.host', 'localhost')
cli.config.set('database.port', 5432)

# Вложенные обновления
cli.config.update({
    'app': {
        'theme': 'dark',
        'language': 'ru'
    }
})

cli.config.save()
```

### Поддержка потоков

Все функции вывода поддерживают пользовательские потоки:

```python
import sys

# Вывод в stderr
echo('Произошла ошибка', 'error', file=sys.stderr)
table(headers, rows, file=sys.stderr)

# Прогресс в файл
with open('log.txt', 'w') as f:
    update = progress_bar(100, file=f, force_inline=False)
    for i in range(101):
        update(i)
```

### Форматирование вывода

Богатый терминальный вывод:

```python
# Предопределённые стили
echo('Успех!', 'success')      # Зелёный
echo('Ошибка!', 'error')        # Красный
echo('Внимание!', 'warning')    # Жёлтый
echo('Инфо', 'info')            # Синий

# Таблицы с авторазмером
table(['Имя', 'Значение'], [['foo', '1'], ['bar', '2']])

# Прогресс-бары с цветами
update = progress_bar(
    100,
    prefix='Загрузка:',
    char='█',
    color_low='yellow',
    color_mid='blue',
    color_high='green'
)
```

## Что нового в v1.1.0

- **Поддержка потоков**: Все функции вывода теперь принимают параметр `file`
- **Опциональные аргументы**: Декоратор `@argument` поддерживает параметр `optional`
- **Защита зарезервированных имён**: Чёткие ошибки для зарезервированных имён (`help`, `h` и т.д.)
- **Улучшенные подсказки типов**: Лучшая обработка `List[T]`, `Dict[K,V]`
- **Улучшенный кэш**: Кэш сообщений правильно обрабатывает параметр `default`
- **Хуки жизненного цикла**: Новая система Hook для расширения поведения
- **Явные интерфейсы**: `JsonConfigProvider` теперь явно наследует `ConfigProvider`
- **Улучшенная документация**: Полный API reference с документированными параметрами

## Миграция с v1.0.0

Большая часть кода будет работать без изменений. Основные обновления:

1. **Опциональные аргументы**: Теперь поддерживаются через параметр `optional=True`
   ```python
   @cli.argument('output', optional=True)
   def cmd(output=None):
       pass
   ```

2. **Зарезервированные имена**: Вызовут ошибки при использовании
   ```python
   # Избегайте: 'help', 'h', '_cli_help', '_cli_show_help'
   ```

3. **Поддержка потоков**: Добавьте параметр `file` для пользовательского вывода
   ```python
   table(headers, rows, file=sys.stderr)
   ```

## Лицензия

Этот проект лицензирован по лицензии MIT - подробности см. в файле LICENSE.

## Автор

**Psinadev** - CLI Framework **v1.1.0**

---

**[Полная документация](documentation/DOCS_RU.md)** | **[English README](README.md)**

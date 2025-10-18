# Python CLI Framework

[English](README.md) | **Русский**

Мощный Python-фреймворк для создания полнофункциональных интерфейсов командной строки с декларативным синтаксисом, расширенным форматированием вывода, локализацией и поддержкой асинхронности. Создавайте профессиональные CLI с минимальным количеством кода.

## Возможности

- **Декларативный API**: Легко определяйте команды через декораторы
- **Типобезопасность**: Автоматическая валидация и преобразование типов
- **Поддержка асинхронности**: Встроенная поддержка `async/await` для I/O операций
- **Расширенный вывод**: Цветной текст, таблицы, прогресс-бары и многое другое
- **Интернационализация**: Встроенная поддержка локализации
- **Управление конфигурацией**: Хранение и загрузка настроек с иерархическим доступом
- **Автогенерация**: Создание CLI из существующих классов и функций
- **Модульная архитектура**: Заменяемые компоненты для максимальной гибкости

## Установка

Фреймворк пока недоступен в PyPI. Для установки:

```bash
# Клонируйте репозиторий
git clone https://github.com/yourusername/cli-framework.git

# Или скачайте и распакуйте исходный код
```

Требования:
- Python 3.7+
- Опционально: `jsonschema` (для валидации конфигурации)

```bash
pip install jsonschema  # опционально
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
# Откроется интерактивная консоль
```

## Документация

Полная документация доступна в файле [DOCS_RU.md](documentation/DOCS_RU.md).

### Основные разделы:

- [Быстрый старт](documentation/DOCS_RU.md#быстрый-старт)
- [Декораторы команд](documentation/DOCS_RU.md#декораторы-команд)
- [Форматированный вывод](documentation/DOCS_RU.md#форматированный-вывод)
- [Конфигурация](documentation/DOCS_RU.md#конфигурация)
- [Локализация](documentation/DOCS_RU.md#локализация)
- [Асинхронные команды](documentation/DOCS_RU.md#асинхронные-команды)
- [API Reference](documentation/DOCS_RU.md#api-reference)
- [Примеры](documentation/DOCS_RU.md#примеры)

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
    def copy(self, source, dest):
        """Копировать файл"""
        import shutil
        shutil.copy2(source, dest)
        echo(f'Скопировано: {source} -> {dest}', 'success')

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
from cli import CLI, echo, table, progress_bar, style
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
    
    # Кастомное форматирование
    text = style('Жирный красный текст', fg='red', bold=True)
    print(text)

if __name__ == '__main__':
    cli.run()
```

## Лицензия

Этот проект лицензирован по лицензии MIT - подробности см. в файле LICENSE.

## Автор

**Psinadev** - CLI Framework v1.0.0

---

**[English README](README.md)** | **[Полная документация на русском](documentation/DOCS_RU.md)**
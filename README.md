# Python CLI Framework

**English** | [Русский](README_RU.md)

A powerful Python framework for building feature-rich command-line interfaces with declarative syntax, advanced output formatting, localization, and asynchronous support. Create professional CLIs with minimal code.

## Features

- **Declarative API**: Easily define commands using decorators
- **Type Safety**: Automatic type validation and conversion
- **Asynchronous Support**: Built-in `async/await` support for I/O operations
- **Enhanced Output**: Colored text, tables, progress bars, and more
- **Internationalization**: Built-in localization support
- **Configuration Management**: Store and load settings with hierarchical access
- **Auto-generation**: Create CLI from existing classes and functions
- **Modular Architecture**: Replaceable components for maximum flexibility

## Installation

The framework is not yet available on PyPI. To install:

```bash
# Clone the repository
git clone https://github.com/yourusername/cli-framework.git

# Or download and extract the source code
```

Requirements:
- Python 3.7+
- Optional: `jsonschema` (for configuration validation)

```bash
pip install jsonschema  # optional
```

## Quick Start

```python
from cli import CLI, echo

# Create CLI instance
cli = CLI(name='myapp')

@cli.command()
@cli.argument('name', help='Name to greet')
@cli.option('--greeting', '-g', default='Hello', help='Greeting text')
def greet(name, greeting):
    """Greet a user"""
    echo(f"{greeting}, {name}!", 'success')

if __name__ == '__main__':
    cli.run()
```

Run the command:
```bash
python example.py greet World --greeting="Hi"
# Output: Hi, World!
```

Get help:
```bash
python example.py help greet
```

Interactive mode:
```bash
python example.py
# Opens interactive console
```

## Documentation

Full documentation is available in [DOCS.md](documentation/DOCS.md).

### Main Sections:

- [Quick Start](documentation/DOCS.md#quick-start)
- [Command Decorators](documentation/DOCS.md#command-decorators)
- [Formatted Output](documentation/DOCS.md#formatted-output)
- [Configuration](documentation/DOCS.md#configuration)
- [Localization](documentation/DOCS.md#localization)
- [Async Commands](documentation/DOCS.md#async-commands)
- [API Reference](documentation/DOCS.md#api-reference)
- [Examples](documentation/DOCS.md#examples)

## Usage Examples

### Simple Command

```python
from cli import CLI, echo

cli = CLI(name='greeter')

@cli.command()
@cli.argument('name', help='User name')
def hello(name):
    """Greet a user"""
    echo(f'Hello, {name}!', 'success')

if __name__ == '__main__':
    cli.run()
```

### Command Groups

```python
from cli import CLI, echo

cli = CLI(name='filetools')

@cli.group(name='file', help='File operations')
class FileCommands:
    @cli.command()
    @cli.argument('path', help='Directory path')
    def list(self, path):
        """List files"""
        import os
        for item in os.listdir(path):
            echo(item)
    
    @cli.command()
    @cli.argument('source', help='Source file')
    @cli.argument('dest', help='Destination file')
    def copy(self, source, dest):
        """Copy file"""
        import shutil
        shutil.copy2(source, dest)
        echo(f'Copied: {source} -> {dest}', 'success')

if __name__ == '__main__':
    cli.run()
```

### Async Commands

```python
from cli import CLI, echo
import asyncio

cli = CLI(name='fetcher')

@cli.command()
@cli.argument('url', help='URL to download')
async def download(url):
    """Async download"""
    echo(f'Downloading {url}...', 'info')
    await asyncio.sleep(1)  # Simulate download
    echo('Done!', 'success')

if __name__ == '__main__':
    cli.run()
```

### Formatted Output

```python
from cli import CLI, echo, table, progress_bar, style
import time

cli = CLI(name='demo')

@cli.command()
def demo():
    """Demonstrate output capabilities"""
    
    # Colored text
    echo('Success!', 'success')
    echo('Warning!', 'warning')
    echo('Error!', 'error')
    
    # Table
    headers = ['Name', 'Status', 'Progress']
    rows = [
        ['Task 1', 'Complete', '100%'],
        ['Task 2', 'In Progress', '45%'],
        ['Task 3', 'Pending', '0%']
    ]
    table(headers, rows)
    
    # Progress bar
    total = 100
    update = progress_bar(total, prefix='Loading:')
    for i in range(total + 1):
        update(i)
        time.sleep(0.02)
    
    # Custom formatting
    text = style('Bold red text', fg='red', bold=True)
    print(text)

if __name__ == '__main__':
    cli.run()
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

**Psinadev** - CLI Framework v1.0.0

---

**[Russian README](README_RU.md)** | **[Full English Documentation](documentation/DOCS.md)**
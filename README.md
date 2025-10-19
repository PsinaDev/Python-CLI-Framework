# Python CLI Framework
English | [**Русский**](README_RU.md)

A powerful Python framework for building feature-rich command-line interfaces with declarative syntax, advanced output formatting, localization, and asynchronous support. Create professional CLIs with minimal code.

## Features

- **Declarative API**: Easily define commands using decorators
- **Type Safety**: Automatic type validation and conversion
- **Asynchronous Support**: Built-in `async/await` support for I/O operations
- **Enhanced Output**: Colored text, tables, progress bars with stream support
- **Internationalization**: Built-in localization support with proper caching
- **Configuration Management**: Store and load settings with file locking and hierarchical access
- **Lifecycle Hooks**: Extend behavior at specific execution points
- **Auto-generation**: Create CLI from existing classes and functions
- **Modular Architecture**: Replaceable components for maximum flexibility

## Requirements

- **Python 3.8+** (uses `typing.get_origin`/`get_args` from standard library)
- Optional: `jsonschema` (for configuration validation)

## Installation

The framework is not yet available on PyPI. To install:

```bash
# Clone the repository
git clone https://github.com/yourusername/cli-framework.git
cd cli-framework

# Install optional dependencies
pip install jsonschema  # optional, for config validation
```

## Quick Start

```python
from cliframework import CLI, echo

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
# Opens interactive console with tab completion
```

## Documentation

Full documentation is available in [DOCS.md](documentation/DOCS.md).

### Main Sections:

- [Quick Start](documentation/DOCS.md#quick-start) — Get started in 5 minutes
- [Command Decorators](documentation/DOCS.md#command-decorators) — Define commands, arguments, options
- [Formatted Output](documentation/DOCS.md#formatted-output) — Colors, tables, progress bars
- [Configuration](documentation/DOCS.md#configuration) — Persistent settings with hierarchical access
- [Localization](documentation/DOCS.md#localization) — Multi-language support
- [Async Commands](documentation/DOCS.md#async-commands) — Async/await support
- [Middleware & Hooks](documentation/DOCS.md#middleware) — Extend functionality
- [CLI Context](documentation/DOCS.md#cli-context) — Share data between middleware and commands
- [API Reference](documentation/DOCS.md#api-reference) — Complete API documentation
- [Examples](documentation/DOCS.md#examples) — Real-world examples
- [Troubleshooting](documentation/DOCS.md#troubleshooting) — Common issues and solutions

## Usage Examples

### Simple Command

```python
from cliframework import CLI, echo

cli = CLI(name='greeter')

@cli.command()
@cli.argument('name', help='User name')
def hello(name):
    """Greet a user"""
    echo(f'Hello, {name}!', 'success')

if __name__ == '__main__':
    cli.run()
```

### Command with Options

```python
from cliframework import CLI, echo

cli = CLI(name='filetools')

@cli.command()
@cli.argument('path', help='Directory path')
@cli.option('--recursive', '-r', is_flag=True, help='Recursive listing')
@cli.option('--hidden', is_flag=True, help='Show hidden files')
def list_files(path, recursive, hidden):
    """List files in directory"""
    import os
    
    for item in os.listdir(path):
        if not hidden and item.startswith('.'):
            continue
        echo(item)
    
    if recursive:
        echo('Recursive mode enabled', 'info')

if __name__ == '__main__':
    cli.run()
```

### Command Groups

```python
from cliframework import CLI, echo

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
    @cli.option('--force', '-f', is_flag=True, help='Overwrite if exists')
    def copy(self, source, dest, force):
        """Copy file"""
        import shutil
        if force or not os.path.exists(dest):
            shutil.copy2(source, dest)
            echo(f'Copied: {source} -> {dest}', 'success')
        else:
            echo(f'File exists: {dest}', 'warning')

if __name__ == '__main__':
    cli.run()
```

### Async Commands

```python
from cliframework import CLI, echo
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
from cliframework import CLI, echo, table, progress_bar
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

if __name__ == '__main__':
    cli.run()
```

### Middleware & Context

```python
from cliframework import CLI, echo
import time

cli = CLI(name='myapp')

# Timing middleware
async def timing_middleware(next_handler):
    start = time.time()
    result = await next_handler()
    elapsed = time.time() - start
    echo(f'Executed in {elapsed:.2f}s', 'debug')
    return result

# Authentication middleware with context
async def auth_middleware(next_handler):
    cli.set_context(user_id=123, username='admin')
    result = await next_handler()
    return result

cli.use(auth_middleware)
cli.use(timing_middleware)

@cli.command()
def status():
    """Check status"""
    ctx = cli.get_context()
    username = ctx.get('username', 'guest')
    echo(f'Status OK (user: {username})', 'success')

if __name__ == '__main__':
    cli.run()
```

### Lifecycle Hooks

```python
from cliframework import CLI, echo
from cliframework.interfaces import Hook

cli = CLI(name='myapp')

class AuditHook(Hook):
    async def on_before_parse(self, args):
        echo(f'Parsing: {args}', 'debug')
        return args
    
    async def on_after_parse(self, parsed):
        return parsed
    
    async def on_before_execute(self, command, kwargs):
        echo(f'Executing: {command}', 'info')
    
    async def on_after_execute(self, command, result, exit_code):
        echo(f'Completed with code: {exit_code}', 'info')
    
    async def on_error(self, command, error):
        echo(f'Error: {error}', 'error')

cli.add_hook(AuditHook())
```

## Key Features

### Declarative Commands

Define commands with simple decorators:

```python
@cli.command(name='hello', aliases=['hi'])
@cli.argument('name', help='User name', type=str)
@cli.option('--loud', '-l', is_flag=True, help='Shout!')
@cli.example('hello World --loud')
def hello_command(name, loud):
    """Say hello"""
    msg = f'HELLO, {name.upper()}!' if loud else f'Hello, {name}'
    echo(msg, 'success' if loud else 'info')
```

### Type Conversion

Automatic type validation and conversion:

```python
@cli.option('--count', type=int, default=1)
@cli.option('--items', type=list, help='JSON array or CSV')
@cli.option('--config', type=dict, help='JSON object or key=val')
@cli.option('--verbose', is_flag=True)
def process(count, items, config, verbose):
    # Types are automatically validated and converted
    for i in range(count):
        echo(f'Processing item {i}')
```

**Supported types:** `str`, `int`, `float`, `bool`, `list`, `dict`, `tuple`, `Optional[T]`

### Safe Configuration

Thread-safe configuration with file locking:

```python
# Hierarchical keys
cli.config.set('database.host', 'localhost')
cli.config.set('database.port', 5432)

# Nested updates
cli.config.update({
    'app': {
        'theme': 'dark',
        'language': 'en'
    }
})

cli.config.save()
```

### Stream Support

All output functions support custom streams:

```python
import sys

# Output to stderr
echo('Error occurred', 'error', file=sys.stderr)
table(headers, rows, file=sys.stderr)

# Progress to custom stream
with open('log.txt', 'w') as f:
    update = progress_bar(100, file=f, force_inline=False)
    for i in range(101):
        update(i)
```

### Output Formatting

Rich terminal output:

```python
# Predefined styles
echo('Success!', 'success')  # Green
echo('Error!', 'error')      # Red
echo('Warning!', 'warning')  # Yellow
echo('Info', 'info')         # Blue

# Tables with auto-sizing
table(['Name', 'Value'], [['foo', '1'], ['bar', '2']])

# Progress bars with colors
update = progress_bar(
    100,
    prefix='Loading:',
    char='█',
    color_low='yellow',
    color_mid='blue',
    color_high='green'
)
```

## What's New in v1.1.0

- **Stream Support**: All output functions now accept `file` parameter for custom streams
- **Optional Arguments**: `@argument` decorator now supports `optional` parameter
- **Reserved Names Protection**: Clear errors for reserved names (`help`, `h`, etc.)
- **Improved Type Hints**: Better handling of `List[T]`, `Dict[K,V]` type hints
- **Better Cache**: Message cache now properly handles `default` parameter
- **Lifecycle Hooks**: New Hook system for extending behavior at specific points
- **Explicit Interfaces**: `JsonConfigProvider` now explicitly inherits `ConfigProvider`
- **Improved Docs**: Complete API reference with all parameters documented

## Migration from v1.0.0

Most code will work without changes. Key updates:

1. **Optional Arguments**: Now supported via `optional=True` parameter
   ```python
   @cli.argument('output', optional=True)
   def cmd(output=None):
       pass
   ```

2. **Reserved Names**: Will raise errors if used (previously silent issues)
   ```python
   # Avoid: 'help', 'h', '_cli_help', '_cli_show_help'
   ```

3. **Stream Support**: Add `file` parameter for custom output
   ```python
   table(headers, rows, file=sys.stderr)
   ```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Author

**Psinadev** - CLI Framework **v1.1.0**

---

**[Full Documentation](documentation/DOCS.md)** | **[Russian README](README_RU.md)**

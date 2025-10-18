# CLI Framework - Documentation

## Table of Contents

- [Introduction](#introduction)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Command Decorators](#command-decorators)
- [Formatted Output](#formatted-output)
- [Configuration](#configuration)
- [Localization](#localization)
- [Advanced Features](#advanced-features)
  - [Async Commands](#async-commands)
  - [Middleware](#middleware)
  - [CLI Context](#cli-context)
  - [CLI Auto-generation](#cli-auto-generation)
  - [Cleanup Callbacks](#cleanup-callbacks)
  - [Interactive Mode (REPL)](#interactive-mode-repl)
- [API Reference](#api-reference)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

---

## Introduction

**CLI Framework** is a professional Python library for building feature-rich command-line interfaces.

### Key Features

- **Declarative syntax** via Python decorators
- **Automatic type validation** and conversion
- **Async commands** with `async/await` support
- **Formatted output** (colors, tables, progress bars)
- **Multi-language support** through message system
- **Safe configuration** with file locking
- **CLI auto-generation** from classes and functions
- **Middleware** for extending functionality
- **CLI Context** for sharing data between middleware and commands
- **Cross-platform** (Windows, Linux, macOS)

### Requirements

- Python 3.7+
- Optional: `jsonschema` (for configuration validation)

---

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/cli-framework.git

# Install optional dependencies
pip install jsonschema  # optional
```

---

## Quick Start

Create `app.py`:

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

Run the application:

```bash
# Execute command
python app.py greet World --greeting="Hi"
# Output: Hi, World!

# Show help
python app.py help greet

# Interactive mode
python app.py
```

---

## Core Concepts

### Command Structure

A command consists of:
- **Name** — unique command identifier
- **Handler** — function executing command logic
- **Arguments** — required positional parameters
- **Options** — optional named parameters
- **Help** — command and parameter descriptions
- **Examples** — usage examples

### Command Lifecycle

1. **Parsing** — CLI parses command-line arguments
2. **Validation** — type checking and required parameters
3. **Context Setup** — CLI context is populated
4. **Middleware Chain** — execution of middleware in registration order
5. **Execution** — command handler invocation
6. **Result Handling** — return exit code
7. **Cleanup** — cleanup callbacks execution

---

## Command Decorators

### @command

Define a command:

```python
@cli.command(name='hello', help='Say hello', aliases=['hi', 'greet'])
def hello_command():
    echo('Hello, world!', 'info')
```

**Parameters:**
- `name` (str, optional) — command name (defaults to function name)
- `help` (str, optional) — command description (defaults to docstring)
- `aliases` (List[str], optional) — alternative command names

### @argument

Add a positional argument:

```python
@cli.command()
@cli.argument('filename', help='Path to file', type=str)
@cli.argument('count', help='Number of lines', type=int)
def process(filename, count):
    echo(f'Processing {filename}, lines: {count}')
```

**Parameters:**
- `name` (str) — argument name
- `help` (str, optional) — argument description
- `type` (Type, optional) — argument type (default `str`)

**Supported types:** `str`, `int`, `float`, `bool`, `list`, `dict`, `tuple`

### @option

Add a named option:

```python
@cli.command()
@cli.option('--verbose', '-v', is_flag=True, help='Verbose output')
@cli.option('--output', '-o', type=str, default='output.txt', help='Output file')
@cli.option('--count', '-c', type=int, default=1, help='Repeat count')
def process(verbose, output, count):
    if verbose:
        echo(f'Output to {output}, repeats: {count}', 'info')
```

**Parameters:**
- `name` (str) — option name (with or without `--`)
- `short` (str, optional) — short name (with or without `-`)
- `help` (str, optional) — option description
- `type` (Type, optional) — option type (default `str`)
- `default` (Any, optional) — default value
- `is_flag` (bool, optional) — boolean flag (True/False)

### @example

Add usage example:

```python
@cli.command()
@cli.argument('source', help='Source file')
@cli.argument('dest', help='Destination file')
@cli.option('--force', '-f', is_flag=True, help='Force overwrite')
@cli.example('copy input.txt output.txt')
@cli.example('copy data.json backup.json --force')
def copy(source, dest, force):
    echo(f'Copying {source} -> {dest}')
```

### @group

Create a command group from a class:

```python
@cli.group(name='database', help='Database commands')
class Database:
    @cli.command()
    def init(self):
        """Initialize database"""
        echo('Initializing database...', 'info')
    
    @cli.command()
    @cli.option('--dry-run', is_flag=True, help='Test run')
    def migrate(self, dry_run):
        """Run migrations"""
        if dry_run:
            echo('Test mode for migrations', 'warning')
        else:
            echo('Running migrations...', 'info')

# Commands available as: database.init, database.migrate
```

---

## Formatted Output

### Colored Text

The `echo()` function outputs styled text:

```python
from cli import echo

# Predefined styles
echo('Success!', 'success')    # Green
echo('Warning!', 'warning')     # Yellow
echo('Error!', 'error')         # Red
echo('Information', 'info')     # Blue
echo('Header', 'header')        # Bold white
echo('Debug', 'debug')          # Gray
```

**Available styles:** `success`, `error`, `warning`, `info`, `header`, `debug`, `emphasis`, `code`, `highlight`

### Custom Formatting

The `style()` function applies arbitrary formatting:

```python
from cli import style

# Foreground colors
text = style('Red text', fg='red')
text = style('Bright blue', fg='bright_blue')

# Background colors
text = style('Text on yellow background', fg='black', bg='yellow')

# Text styles
text = style('Bold', bold=True)
text = style('Underlined', underline=True)
text = style('Bold red', fg='red', bold=True)

print(text)
```

**Available colors:** `black`, `red`, `green`, `yellow`, `blue`, `magenta`, `cyan`, `white`, `bright_*` (variants for each color)

### Tables

The `table()` function outputs formatted tables:

```python
from cli import table

headers = ['Name', 'Age', 'City']
rows = [
    ['Alex', '28', 'Moscow'],
    ['Maria', '32', 'St. Petersburg'],
    ['John', '25', 'Novosibirsk']
]

table(headers, rows)
```

### Progress Bars

The `progress_bar()` function creates an interactive progress bar:

```python
from cli import progress_bar
import time

total = 100
update = progress_bar(
    total,
    prefix='Loading:',
    suffix='complete',
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

## Configuration

CLI Framework provides safe configuration storage with automatic file locking.

### Working with Configuration

```python
from cli import CLI

cli = CLI(name='myapp')

# Save values
cli.config.set('app.name', 'My Application')
cli.config.set('app.version', '1.0.0')
cli.config.set('database.host', 'localhost')
cli.config.set('database.port', 5432)
cli.config.save()

# Read values
app_name = cli.config.get('app.name', 'Default')
db_host = cli.config.get('database.host', 'localhost')

# Get entire configuration
config_dict = cli.config.get_all()

# Update from dictionary
cli.config.update({
    'app.theme': 'dark',
    'app.language': 'en'
})
```

### Hierarchical Access

Configuration supports dot notation for nested structures:

```python
# Set nested values
cli.config.set('server.database.credentials.username', 'admin')
cli.config.set('server.database.credentials.password', 'secret')

# Read nested values
username = cli.config.get('server.database.credentials.username')
```

---

## Localization

CLI Framework supports multi-language applications through the message system.

### Using Messages

```python
from cli import CLI, echo

cli = CLI(name='myapp')

@cli.command()
@cli.argument('name', help='User name')
def greet(name):
    """Greet a user"""
    message = cli.messages.get_message(
        'greeting',
        'Hello, {name}!',
        name=name
    )
    echo(message, 'success')
```

### Adding Languages

```python
# Add Russian language
ru_messages = {
    'greeting': 'Привет, {name}!',
    'goodbye': 'До свидания!',
}

cli.messages.add_language('ru', ru_messages)

# Switch language
cli.messages.set_language('ru')
```

---

## Advanced Features

### Async Commands

CLI Framework fully supports async commands:

```python
import asyncio
from cli import CLI, echo

cli = CLI(name='myapp')

@cli.command()
@cli.argument('url', help='URL to download')
async def download(url):
    """Async data download"""
    echo(f'Downloading {url}...', 'info')
    await asyncio.sleep(2)
    echo('Download complete!', 'success')
    return 0

if __name__ == '__main__':
    cli.run()
```

### Middleware

Middleware allows adding functionality to command execution.

#### Basic Middleware

```python
from cli import CLI, echo
import time

cli = CLI(name='myapp')

# Timing middleware
async def timing_middleware(next_handler):
    start = time.time()
    result = await next_handler()
    elapsed = time.time() - start
    echo(f'Executed in {elapsed:.2f}s', 'debug')
    return result

# Logging middleware
async def logging_middleware(next_handler):
    echo('→ Starting command execution', 'debug')
    result = await next_handler()
    echo('← Command completed', 'debug')
    return result

# Register middleware
cli.use(logging_middleware)
cli.use(timing_middleware)

@cli.command()
def hello():
    """Test command"""
    echo('Hello, world!', 'info')
    time.sleep(1)

if __name__ == '__main__':
    cli.run()
```

#### Built-in Logging Middleware

CLI Framework provides built-in debugging middleware:

**Method 1: Enable at initialization**
```python
cli = CLI(name='myapp', auto_logging_middleware=True)
```

**Method 2: Add manually**
```python
cli = CLI(name='myapp')
cli.use_logging_middleware()
```

This middleware logs:
- Command name and arguments before execution
- Execution result or errors
- Execution at DEBUG level

Example output:
```
[Middleware] Executing command 'greet' with args: {'name': 'World', 'greeting': 'Hello'}
[Middleware] Command 'greet' completed successfully with result: 0
```

### CLI Context

CLI Context allows sharing data between middleware and commands.

#### Accessing Context in Middleware

```python
async def context_aware_middleware(next_handler):
    # Get execution context
    ctx = cli.get_context()
    command = ctx.get('command')           # command name
    args = ctx.get('args', {})             # command arguments
    cli_instance = ctx.get('cli_instance') # CLI instance
    
    echo(f"[{command}] Executing with: {args}", 'debug')
    
    result = await next_handler()
    return result

cli.use(context_aware_middleware)
```

#### Setting Custom Context Data

You can store custom data in the context for use across middleware chain:

```python
async def auth_middleware(next_handler):
    # Set custom data in context
    cli.set_context(
        user_id=123,
        role='admin',
        timestamp=time.time()
    )
    
    result = await next_handler()
    return result

async def audit_middleware(next_handler):
    # Read custom data from context
    ctx = cli.get_context()
    user_id = ctx.get('user_id', 'anonymous')
    command = ctx.get('command', 'unknown')
    
    echo(f"User {user_id} executing '{command}'", 'debug')
    
    result = await next_handler()
    return result

cli.use(auth_middleware)
cli.use(audit_middleware)
```

#### Context Available Data

The CLI context contains:
- `command` (str) — name of the executing command
- `args` (dict) — parsed command arguments
- `cli_instance` (CLI) — reference to CLI instance
- Any custom data set via `set_context()`

#### Complete Example with Context

```python
from cli import CLI, echo
import time

cli = CLI(name='myapp')

# Authentication middleware
async def auth_middleware(next_handler):
    # Simulate authentication
    cli.set_context(
        authenticated=True,
        user_id=123,
        username='john_doe',
        permissions=['read', 'write']
    )
    
    echo('✓ User authenticated', 'success')
    result = await next_handler()
    return result

# Authorization middleware
async def authz_middleware(next_handler):
    ctx = cli.get_context()
    
    if not ctx.get('authenticated', False):
        echo('✗ Not authenticated', 'error')
        return 1
    
    command = ctx.get('command')
    permissions = ctx.get('permissions', [])
    
    # Check permissions
    if command == 'delete' and 'write' not in permissions:
        echo('✗ Insufficient permissions', 'error')
        return 1
    
    result = await next_handler()
    return result

# Audit logging middleware
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

# Register middleware
cli.use(auth_middleware)
cli.use(authz_middleware)
cli.use(audit_middleware)

@cli.command()
@cli.argument('filename', help='File to read')
def read(filename):
    """Read file"""
    ctx = cli.get_context()
    username = ctx.get('username', 'unknown')
    
    echo(f'{username} is reading {filename}', 'info')
    return 0

@cli.command()
@cli.argument('filename', help='File to delete')
def delete(filename):
    """Delete file"""
    ctx = cli.get_context()
    username = ctx.get('username', 'unknown')
    
    echo(f'{username} is deleting {filename}', 'warning')
    return 0

if __name__ == '__main__':
    cli.run()
```

### CLI Auto-generation

Create CLI automatically from existing classes:

```python
from cli import CLI

cli = CLI(name='filetools')

class FileManager:
    def list(self, path='.', show_hidden=False):
        """List files"""
        import os
        for item in os.listdir(path):
            if not show_hidden and item.startswith('.'):
                continue
            print(item)
    
    def info(self, filepath):
        """Show file information"""
        import os
        stats = os.stat(filepath)
        print(f'Size: {stats.st_size} bytes')
        print(f'Modified: {stats.st_mtime}')

# Automatic command generation
cli.generate_from(FileManager)

# Commands will be available as:
# filemanager.list
# filemanager.info
```

### Cleanup Callbacks

Register cleanup functions for graceful shutdown:

```python
cli = CLI(name='myapp')

# Synchronous cleanup
def cleanup():
    print('Cleaning up resources...')
    # Close connections, save state, etc.

cli.add_cleanup_callback(cleanup)

# Asynchronous cleanup
async def async_cleanup():
    print('Async cleanup...')
    await asyncio.sleep(0.1)
    # Async cleanup tasks

cli.add_cleanup_callback(async_cleanup)

# Cleanup callbacks are called on:
# - Normal exit (exit command)
# - Ctrl+C (graceful shutdown)
# - Exception during execution
```

**Note:** Async cleanup callbacks are only executed during normal async shutdown. They are skipped in signal handlers for safety.

### Interactive Mode (REPL)

#### Basic Interactive Mode

```python
cli = CLI(name='myapp')

@cli.command()
def status():
    """Show status"""
    echo('Everything is working!', 'success')

if __name__ == '__main__':
    # Run in interactive mode
    cli.run(interactive=True)
```

Example session:
```
Welcome to myapp
Type 'help' for available commands

myapp> status
Everything is working!

myapp> help
Available commands:
  status    Show status
  help      Show help information
  exit      Exit the application

myapp> exit
Goodbye!
```

#### Tab Completion

Tab completion is enabled by default in interactive mode:

```python
cli = CLI(name='myapp')

# Enable tab completion (default)
cli.enable_readline(True)

# Disable tab completion
cli.enable_readline(False)

cli.run(interactive=True)
```

**Features:**
- Tab completion for command names
- Command history with arrow keys
- Works on Linux/macOS (readline) and Windows (pyreadline3)

**Installation for Windows:**
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

**Parameters:**
- `name` — application name
- `config_path` — path to configuration file
- `config_provider` — custom configuration provider
- `config_schema` — JSON schema for validation
- `message_provider` — custom message provider
- `output_formatter` — custom output formatter
- `command_registry` — custom command registry
- `argument_parser` — custom argument parser
- `log_level` — logging level (default: INFO)
- `auto_logging_middleware` — enable built-in logging middleware (default: False)

**Methods:**

- `command(name, help, aliases)` — command decorator
- `argument(name, help, type)` — argument decorator
- `option(name, short, help, type, default, is_flag)` — option decorator
- `example(example_text)` — example decorator
- `group(name, help)` — group decorator
- `generate_from(obj, safe_mode=True)` — generate CLI from object
- `register_all_commands()` — register all decorated commands
- `use(middleware)` — add middleware
- `use_logging_middleware()` — add built-in logging middleware
- `get_context() -> Dict[str, Any]` — get current CLI context
- `set_context(**kwargs)` — set context variables
- `add_cleanup_callback(callback)` — register cleanup callback
- `enable_readline(enable=True)` — enable/disable tab completion
- `run(args=None, interactive=False) -> int` — run CLI (synchronous)
- `run_async(args=None, interactive=False) -> int` — run CLI (asynchronous)
- `run_interactive() -> int` — run in interactive mode

**Attributes:**

- `config` — configuration provider
- `messages` — message provider
- `output` — output formatter
- `commands` — command registry
- `parser` — argument parser
- `exit_code` — last command exit code

### Output Functions

#### echo()

```python
echo(text: str, style: Optional[str] = None, file: TextIO = sys.stdout) -> None
```

Output styled text.

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

Apply styles to text.

#### table()

```python
table(headers: List[str], rows: List[List[str]]) -> None
```

Output table.

#### progress_bar()

```python
progress_bar(total: int, **kwargs) -> Callable[[int], None]
```

Create progress bar. Returns update function.

---

## Examples

### Complete Example: Task Manager

```python
from cli import CLI, echo, table, progress_bar
import time

cli = CLI(name='tasks', auto_logging_middleware=True)

# Storage
tasks = []

# Authentication middleware
async def auth_middleware(next_handler):
    cli.set_context(user_id=1, username='admin')
    result = await next_handler()
    return result

cli.use(auth_middleware)

@cli.command()
@cli.argument('title', help='Task title')
@cli.option('--priority', '-p', type=int, default=1, help='Priority (1-5)')
def add(title, priority):
    """Add new task"""
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
    
    echo(f'✓ Task #{task["id"]} added by {username}', 'success')
    return 0

@cli.command()
def list():
    """List all tasks"""
    if not tasks:
        echo('No tasks found', 'warning')
        return 0
    
    headers = ['ID', 'Title', 'Priority', 'Status', 'Created By']
    rows = []
    
    for task in tasks:
        status = '✓ Done' if task['done'] else '○ Pending'
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
@cli.argument('task_id', type=int, help='Task ID')
def done(task_id):
    """Mark task as done"""
    for task in tasks:
        if task['id'] == task_id:
            task['done'] = True
            echo(f'✓ Task #{task_id} marked as done', 'success')
            return 0
    
    echo(f'✗ Task #{task_id} not found', 'error')
    return 1

@cli.command()
@cli.option('--delay', '-d', type=float, default=0.5, help='Delay per task')
def process_all(delay):
    """Process all pending tasks"""
    pending = [t for t in tasks if not t['done']]
    
    if not pending:
        echo('No pending tasks', 'info')
        return 0
    
    update = progress_bar(
        len(pending),
        prefix='Processing:',
        suffix='complete'
    )
    
    for i, task in enumerate(pending, 1):
        time.sleep(delay)
        task['done'] = True
        update(i)
    
    echo(f'✓ Processed {len(pending)} tasks', 'success')
    return 0

if __name__ == '__main__':
    cli.run()
```

---

## Troubleshooting

### Colors Not Displaying

**Problem:** Colors don't work in terminal.

**Solution:**
```python
from cli import TerminalOutputFormatter

cli = CLI(
    name='myapp',
    output_formatter=TerminalOutputFormatter(use_colors=True)
)
```

### Tab Completion Not Working (Windows)

**Problem:** Tab completion doesn't work on Windows.

**Solution:** Install pyreadline3:
```bash
pip install pyreadline3
```

### Context Not Available in Command

**Problem:** `cli.get_context()` returns empty dict in command handler.

**Solution:** Context is only available during command execution through middleware. Access it in middleware or store context data in your own storage if needed in commands:

```python
async def store_context_middleware(next_handler):
    ctx = cli.get_context()
    # Store in global or class variable for access in commands
    global current_user
    current_user = ctx.get('username')
    
    result = await next_handler()
    return result
```

---

## Architecture

CLI Framework uses modular architecture with clear interfaces for easy customization and extension.

### Components

- **CLI** — main orchestrator
- **CommandRegistry** — command storage with Trie-based autocomplete
- **ArgumentParser** — argument parsing with LRU cache
- **ConfigProvider** — configuration storage with file locking
- **MessageProvider** — localization with message caching
- **OutputFormatter** — formatted terminal output
- **Middleware** — extensible command processing chain

---

## License

CLI Framework is developed by **Psinadev**. Version 1.0.0.

---

## Support

For questions and support, refer to this documentation or create issues in the project repository.
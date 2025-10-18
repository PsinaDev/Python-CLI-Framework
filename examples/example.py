"""
Example CLI Application demonstrating all features

This example shows how to use:
- Regular and async commands
- Command groups
- Middleware
- Arguments and options
- Interactive REPL mode
- Graceful shutdown
- Configuration
"""

import asyncio
import time
from cli import CLI, echo

cli = CLI(
    name='example-app',
    log_level=20
)


@cli.command(name='hello', aliases=['hi', 'greet'])
@cli.argument('name', help='Name to greet', type=str)
@cli.option('--count', '-c', type=int, default=1, help='Number of greetings')
@cli.option('--uppercase', '-u', is_flag=True, help='Use uppercase')
@cli.example('hello Alice --count=3')
@cli.example('hello Bob --uppercase')
def hello_command(name: str, count: int = 1, uppercase: bool = False) -> int:
    """Greet someone"""
    greeting = f"Hello, {name}!"

    if uppercase:
        greeting = greeting.upper()

    for i in range(count):
        echo(greeting, 'success')

    return 0


@cli.command(name='fetch')
@cli.argument('url', help='URL to fetch', type=str)
@cli.option('--timeout', '-t', type=int, default=30, help='Request timeout')
async def fetch_command(url: str, timeout: int = 30) -> int:
    """Fetch data from URL (async example)"""
    echo(f"Fetching {url} with timeout {timeout}s...", 'info')

    await asyncio.sleep(2)

    echo(f"Successfully fetched data from {url}", 'success')
    return 0


@cli.command(name='download')
@cli.argument('url', help='URL to download', type=str)
@cli.option('--size', '-s', type=int, default=100, help='Simulated download size')
@cli.option('--style', help='Progress bar style', default='default')
async def download_command(url: str, size: int = 100, style: str = 'default') -> int:
    """Download file with customizable progress bar"""
    from cli import progress_bar

    echo(f"Downloading {url}...", 'info')

    styles = {
        'default': {
            'prefix': 'Download:',
            'suffix': 'complete'
        },
        'fancy': {
            'char': '▓',
            'empty_char': '░',
            'prefix': f'{url}:',
            'suffix': 'done',
            'color_low': 'red',
            'color_mid': 'yellow',
            'color_high': 'green'
        },
        'minimal': {
            'char': '=',
            'empty_char': ' ',
            'brackets': ('', ''),
            'prefix': 'Progress:',
            'show_count': False
        },
        'dots': {
            'char': '●',
            'empty_char': '○',
            'brackets': ('(', ')'),
            'prefix': 'Loading:',
            'color_low': 'blue',
            'color_mid': 'cyan',
            'color_high': 'green'
        },
        'classic': {
            'char': '#',
            'empty_char': '-',
            'brackets': ('|', '|'),
            'prefix': 'Downloading:',
            'width': 40
        }
    }

    style_config = styles.get(style, styles['default'])
    update = progress_bar(size, **style_config)

    for i in range(size):
        await asyncio.sleep(0.03)
        update(i + 1)

    echo(f"Downloaded {url} successfully!", 'success')
    return 0


@cli.command(name='upload')
@cli.argument('filename', help='File to upload', type=str)
@cli.option('--chunks', '-c', type=int, default=50, help='Number of chunks')
async def upload_command(filename: str, chunks: int = 50) -> int:
    """Upload file with arrow-style progress bar"""
    from cli import progress_bar

    echo(f"Uploading {filename}...", 'info')

    update = progress_bar(
        chunks,
        char='▶',
        empty_char='▷',
        brackets=('⟨', '⟩'),
        prefix=f'Uploading {filename}:',
        suffix='uploaded',
        color_low='magenta',
        color_mid='cyan',
        color_high='bright_green',
        color_threshold_low=0.3,
        color_threshold_high=0.7
    )

    for i in range(chunks):
        await asyncio.sleep(0.04)
        update(i + 1)

    echo(f"Upload complete!", 'success')
    return 0


@cli.command(name='install')
@cli.argument('package', help='Package name to install', type=str)
@cli.option('--steps', type=int, default=75, help='Installation steps')
async def install_command(package: str, steps: int = 75) -> int:
    """Install package with gradient-style progress bar"""
    from cli import progress_bar

    echo(f"Installing {package}...", 'info')

    update = progress_bar(
        steps,
        char='━',
        empty_char='─',
        brackets=('┃', '┃'),
        prefix=f'Installing {package}:',
        suffix='installed',
        color_low='bright_red',
        color_mid='bright_yellow',
        color_high='bright_green',
        width=50
    )

    for i in range(steps):
        await asyncio.sleep(0.02)
        update(i + 1)

    echo(f"Package {package} installed successfully!", 'success')
    return 0


@cli.command(name='build')
@cli.argument('project', help='Project to build', type=str)
@cli.option('--stages', type=int, default=60, help='Build stages')
async def build_command(project: str, stages: int = 60) -> int:
    """Build project with square-style progress bar"""
    from cli import progress_bar

    echo(f"Building {project}...", 'info')

    update = progress_bar(
        stages,
        char='■',
        empty_char='□',
        brackets=('⟦', '⟧'),
        prefix=f'Building {project}:',
        suffix='built',
        color_low='yellow',
        color_mid='blue',
        color_high='green',
        color_threshold_low=0.25,
        color_threshold_high=0.80
    )

    for i in range(stages):
        await asyncio.sleep(0.03)
        update(i + 1)

    echo(f"Build complete!", 'success')
    return 0


@cli.command(name='sync')
@cli.argument('source', help='Source directory', type=str)
@cli.argument('dest', help='Destination directory', type=str)
@cli.option('--files', type=int, default=40, help='Number of files')
async def sync_command(source: str, dest: str, files: int = 40) -> int:
    """Sync directories with compact progress bar"""
    from cli import progress_bar

    echo(f"Syncing {source} → {dest}...", 'info')

    update = progress_bar(
        files,
        char='█',
        empty_char='░',
        prefix=f'{source}→{dest}:',
        width=30,
        show_percent=True,
        show_count=True,
        color_low='cyan',
        color_mid='blue',
        color_high='bright_blue'
    )

    for i in range(files):
        await asyncio.sleep(0.05)
        update(i + 1)

    echo(f"Sync complete!", 'success')
    return 0


@cli.command(name='benchmark')
@cli.option('--iterations', '-i', type=int, default=100, help='Number of iterations')
@cli.option('--no-colors', is_flag=True, help='Disable colors')
async def benchmark_command(iterations: int = 100, no_colors: bool = False) -> int:
    """Run benchmark with performance-focused progress bar"""
    from cli import progress_bar

    echo(f"Running benchmark with {iterations} iterations...", 'info')

    if no_colors:
        update = progress_bar(
            iterations,
            char='#',
            empty_char='-',
            brackets=('[', ']'),
            prefix='Benchmark:',
            suffix='complete',
            width=40
        )
    else:
        update = progress_bar(
            iterations,
            char='▰',
            empty_char='▱',
            prefix='Benchmark:',
            suffix='ops',
            color_low='red',
            color_mid='yellow',
            color_high='green',
            color_threshold_low=0.4,
            color_threshold_high=0.8
        )

    for i in range(iterations):
        await asyncio.sleep(0.01)
        update(i + 1)

    echo(f"Benchmark complete! Average: {iterations / 10:.1f} ops/sec", 'success')
    return 0


@cli.command(name='progress-demo')
async def progress_demo_command() -> int:
    """Demonstrate all progress bar styles"""
    from cli import progress_bar

    echo("=== Progress Bar Styles Demo ===", 'header')
    print()

    demos = [
        {
            'name': 'Default Style',
            'config': {'prefix': 'Default:', 'width': 30}
        },
        {
            'name': 'Blocks',
            'config': {
                'char': '▓',
                'empty_char': '░',
                'prefix': 'Blocks:',
                'width': 30,
                'color_low': 'red',
                'color_high': 'green'
            }
        },
        {
            'name': 'Arrows',
            'config': {
                'char': '▶',
                'empty_char': '▷',
                'brackets': ('⟨', '⟩'),
                'prefix': 'Arrows:',
                'width': 30
            }
        },
        {
            'name': 'Dots',
            'config': {
                'char': '●',
                'empty_char': '○',
                'brackets': ('(', ')'),
                'prefix': 'Dots:',
                'width': 30
            }
        },
        {
            'name': 'ASCII',
            'config': {
                'char': '#',
                'empty_char': '-',
                'brackets': ('|', '|'),
                'prefix': 'ASCII:',
                'width': 30
            }
        },
        {
            'name': 'Lines',
            'config': {
                'char': '━',
                'empty_char': '─',
                'brackets': ('┃', '┃'),
                'prefix': 'Lines:',
                'width': 30
            }
        },
        {
            'name': 'Minimal',
            'config': {
                'char': '=',
                'empty_char': ' ',
                'brackets': ('', ''),
                'prefix': 'Minimal:',
                'width': 30,
                'show_count': False
            }
        }
    ]

    for demo in demos:
        echo(f"{demo['name']}:", 'info')
        update = progress_bar(50, **demo['config'])
        for i in range(51):
            await asyncio.sleep(0.02)
            update(i)
        print()

    echo("Demo complete!", 'success')
    return 0


@cli.group(name='database', help='Database operations')
class DatabaseCommands:
    """Group of database-related commands"""

    @cli.command()
    def init(self) -> int:
        """Initialize database"""
        echo("Initializing database...", 'info')
        time.sleep(1)
        echo("Database initialized successfully", 'success')
        return 0

    @cli.command()
    @cli.option('--backup', '-b', is_flag=True, help='Create backup first')
    async def migrate(self, backup: bool = False) -> int:
        """Run database migrations"""
        if backup:
            echo("Creating backup...", 'warning')
            await asyncio.sleep(1)

        echo("Running migrations...", 'info')
        await asyncio.sleep(2)
        echo("Migrations completed successfully", 'success')
        return 0

    @cli.command()
    def status(self) -> int:
        """Show database status"""
        from cli import table

        echo("Database Status:", 'header')

        headers = ["Component", "Status", "Details"]
        rows = [
            ["Connection", "OK", "localhost:5432"],
            ["Auth", "OK", "user: admin"],
            ["Tables", "OK", "42 tables"],
            ["Size", "OK", "1.2 GB"]
        ]

        table(headers, rows)
        return 0


async def timing_middleware(next_handler):
    """Middleware that times command execution"""
    start_time = time.time()

    echo("[Timing] Command started", 'debug')
    result = await next_handler()

    elapsed = time.time() - start_time
    echo(f"[Timing] Command completed in {elapsed:.2f}s", 'debug')

    return result


async def logging_middleware(next_handler):
    """Middleware that logs command execution"""
    echo("[Log] Executing command...", 'debug')

    try:
        result = await next_handler()
        echo("[Log] Command succeeded", 'debug')
        return result
    except Exception as e:
        echo(f"[Log] Command failed: {e}", 'error')
        raise


cli.use(timing_middleware)
cli.use(logging_middleware)


def cleanup_handler():
    """Called on graceful shutdown"""
    echo("\n[Cleanup] Saving state...", 'warning')
    echo("[Cleanup] Done", 'success')


cli.add_cleanup_callback(cleanup_handler)


@cli.command(name='demo')
def demo_command() -> int:
    """Run demonstration of all features"""
    from cli import style, table, progress_bar
    import time

    echo("=== CLI Framework Demo ===", 'header')
    print()

    echo("1. Styled Text:", 'info')
    echo("   " + style("Success", fg='green', bold=True))
    echo("   " + style("Warning", fg='yellow', bold=True))
    echo("   " + style("Error", fg='red', bold=True))
    print()

    echo("2. Tables:", 'info')
    headers = ["Feature", "Status", "Notes"]
    rows = [
        ["Async Support", "✓", "Full asyncio support"],
        ["Middleware", "✓", "Chainable middleware"],
        ["Type Safety", "✓", "Runtime validation"],
        ["Graceful Shutdown", "✓", "Signal handling"]
    ]
    table(headers, rows)
    print()

    echo("3. Progress Bars:", 'info')

    echo("   Default style:")
    update = progress_bar(50, prefix="Default:", width=30)
    for i in range(51):
        update(i)
        time.sleep(0.02)

    echo("   Block style:")
    update = progress_bar(50, char='▓', empty_char='░', prefix="Blocks:", width=30,
                          color_low='red', color_mid='yellow', color_high='green')
    for i in range(51):
        update(i)
        time.sleep(0.02)

    echo("   Custom brackets:")
    update = progress_bar(50, char='>', empty_char='-', brackets=('|', '|'),
                          prefix="Custom:", width=30)
    for i in range(51):
        update(i)
        time.sleep(0.02)

    print()

    echo("4. Try these commands:", 'info')
    examples = [
        "hello Alice --count=3",
        "download https://example.com --style=fancy",
        "upload myfile.zip --chunks=30",
        "install numpy --steps=50",
        "build myproject",
        "sync /source /dest --files=25",
        "benchmark --iterations=80",
        "progress-demo",
        "database.status",
    ]

    for example in examples:
        echo(f"   {example}", 'code')

    print()
    echo("Press Ctrl+C to test graceful shutdown", 'warning')

    return 0


if __name__ == '__main__':
    import sys

    exit_code = cli.run()
    sys.exit(exit_code)
"""
Basics: commands, arguments, options, flags, aliases, examples.

Run:
    python examples/01_basics.py hello Alice --count 3 --uppercase
    python examples/01_basics.py add 2 3
    python examples/01_basics.py echo "hi" --repeat 2 --shout
    python examples/01_basics.py                 # interactive REPL
"""

from __future__ import annotations

import logging
import sys

from cli import CLI, echo

cli = CLI(name="basics", log_level=logging.WARNING)


@cli.command(name="hello", aliases=["hi", "greet"])
@cli.argument("name", help="Name to greet")
@cli.option("--count", "-c", type=int, default=1, help="Number of greetings")
@cli.option("--uppercase", "-u", is_flag=True, help="Shout the greeting")
@cli.example("hello Alice --count 3")
@cli.example("hi Bob -u")
def hello(name: str, count: int = 1, uppercase: bool = False) -> int:
    """Greet someone by name."""
    text = f"Hello, {name}!"
    if uppercase:
        text = text.upper()
    for _ in range(count):
        echo(text, "success")
    return 0


@cli.command(name="add")
@cli.argument("b", type=int, help="Second number")
@cli.argument("a", type=int, help="First number")
def add(a: int, b: int) -> int:
    """Add two integers."""
    echo(f"{a} + {b} = {a + b}", "info")
    return 0


@cli.command(name="echo")
@cli.argument("text", help="Text to print")
@cli.option("--repeat", "-r", type=int, default=1, help="How many times")
@cli.option("--shout", is_flag=True, help="Uppercase output")
def echo_cmd(text: str, repeat: int = 1, shout: bool = False) -> int:
    """Print text, optionally repeated and shouted."""
    payload = text.upper() if shout else text
    for _ in range(repeat):
        echo(payload)
    return 0


@cli.command(name="divide")
@cli.argument("b", type=float)
@cli.argument("a", type=float)
@cli.option("--strict", is_flag=True, help="Raise on division by zero")
def divide(a: float, b: float, strict: bool = False) -> int:
    """Divide a by b. Demonstrates non-zero exit on error."""
    if b == 0:
        if strict:
            raise ZeroDivisionError("denominator is zero")
        echo("Division by zero, returning inf", "warning")
        return 2
    echo(f"{a} / {b} = {a / b}", "info")
    return 0


if __name__ == "__main__":
    sys.exit(cli.run())

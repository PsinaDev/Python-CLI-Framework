"""
Output helpers: `echo` levels, `style` for inline coloring, `table`.

Run:
    python examples/06_output.py demo
    python examples/06_output.py levels
    python examples/06_output.py grid --rows 5
"""

from __future__ import annotations

import logging
import sys

from cli import CLI, echo, style, table

cli = CLI(name="output-demo", log_level=logging.WARNING)


@cli.command(name="levels")
def levels() -> int:
    """Show every echo level."""
    for level in ("debug", "info", "success", "warning", "error", "header"):
        echo(f"this is {level!r}", level)
    return 0


@cli.command(name="demo")
def demo() -> int:
    """Mixed styled output."""
    echo("=== Output Demo ===", "header")
    echo("plain line")
    echo("info line", "info")
    echo("success line", "success")
    echo("warning line", "warning")
    echo("error line", "error")

    echo(
        "Inline: " + style("RED", fg="red", bold=True)
        + " " + style("GREEN", fg="green")
        + " " + style("BLUE", fg="blue", underline=True)
    )

    echo("", "info")
    echo("Table:", "header")
    table(
        ["Component", "Status", "Notes"],
        [
            ["parser", style("OK", fg="green"), "argparse-based"],
            ["middleware", style("OK", fg="green"), "async chain"],
            ["hooks", style("OK", fg="green"), "global + per-command"],
            ["completion", style("OK", fg="green"), "bash/zsh/fish"],
        ],
    )
    return 0


@cli.command(name="grid")
@cli.option("--rows", "-r", type=int, default=3)
@cli.option("--cols", "-c", type=int, default=4)
def grid(rows: int = 3, cols: int = 4) -> int:
    """Generate an arbitrary table."""
    headers = [f"col{i + 1}" for i in range(cols)]
    data = [
        [f"r{r + 1}c{c + 1}" for c in range(cols)] for r in range(rows)
    ]
    table(headers, data)
    return 0


if __name__ == "__main__":
    sys.exit(cli.run())

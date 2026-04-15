"""
Generate shell completion scripts for the registered commands.

`cli.generate_completion(shell)` returns the script as a string.
`cli.install_completion(shell, path=None)` writes it to a default location.

Run:
    python examples/07_completion.py emit --shell bash
    python examples/07_completion.py emit --shell zsh > _myapp
    python examples/07_completion.py install --shell fish --path /tmp/myapp.fish
    python examples/07_completion.py list
"""

from __future__ import annotations

import logging
import sys

from cli import CLI, Shell, echo

cli = CLI(name="myapp", log_level=logging.WARNING)


# A few real commands so completion has something to enumerate.

@cli.command(name="build")
@cli.argument("target")
@cli.option("--release", is_flag=True)
def build(target: str, release: bool = False) -> int:
    """Pretend to build a target."""
    echo(f"build {target} (release={release})")
    return 0


@cli.command(name="deploy")
@cli.argument("env")
@cli.option("--dry-run", is_flag=True)
def deploy(env: str, dry_run: bool = False) -> int:
    """Pretend to deploy."""
    echo(f"deploy {env} (dry_run={dry_run})")
    return 0


@cli.command(name="emit")
@cli.option("--shell", "-s", default="bash", help="bash | zsh | fish")
def emit(shell: str = "bash") -> int:
    """Print the completion script to stdout."""
    try:
        script = cli.generate_completion(shell)
    except ValueError as exc:
        echo(str(exc), "error")
        return 1
    print(script)
    return 0


@cli.command(name="install")
@cli.option("--shell", "-s", default="bash")
@cli.option("--path", "-p", default=None, help="Custom destination")
def install(shell: str = "bash", path: str | None = None) -> int:
    """Write completion script to disk."""
    try:
        written = cli.install_completion(shell, path=path)
    except ValueError as exc:
        echo(str(exc), "error")
        return 1
    echo(f"Wrote {shell} completion to {written}", "success")
    return 0


@cli.command(name="list")
def list_shells() -> int:
    """List supported shells."""
    for s in Shell:
        echo(f"  {s.value}")
    return 0


if __name__ == "__main__":
    sys.exit(cli.run())

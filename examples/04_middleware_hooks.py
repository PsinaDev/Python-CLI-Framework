"""
Middleware pipeline + global `Hook` subclass + per-command hooks.

Execution order for a command:
    middleware (outer → inner) → before hooks → handler → after hooks → middleware unwind

Run:
    python examples/04_middleware_hooks.py ping --times 3
    python examples/04_middleware_hooks.py boom        # triggers error hook
    python examples/04_middleware_hooks.py slow
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from typing import Any, Awaitable, Callable

from cli import CLI, Hook, echo

cli = CLI(name="hooks-demo", log_level=logging.WARNING)


# --- Middleware -------------------------------------------------------------


async def timing_middleware(
    next_handler: Callable[[], Awaitable[Any]],
) -> Any:
    """Measure wall-clock time of every command."""
    start = time.perf_counter()
    try:
        return await next_handler()
    finally:
        elapsed = time.perf_counter() - start
        echo(f"[timing] {elapsed * 1000:.1f} ms", "debug")


async def logging_middleware(
    next_handler: Callable[[], Awaitable[Any]],
) -> Any:
    """Log entry and exit of each command."""
    echo("[mw] enter", "debug")
    try:
        result = await next_handler()
        echo(f"[mw] exit ok ({result})", "debug")
        return result
    except Exception as exc:
        echo(f"[mw] exit error: {exc}", "error")
        raise


cli.use(timing_middleware)
cli.use(logging_middleware)


# --- Global lifecycle hook --------------------------------------------------


class AuditHook(Hook):
    """Hook subclass demonstrating each lifecycle phase."""

    async def on_before_parse(self, args: list[str]) -> list[str]:
        echo(f"[audit] raw args: {args}", "debug")
        return args

    async def on_after_parse(self, parsed: dict[str, Any]) -> dict[str, Any]:
        echo(f"[audit] parsed command: {parsed.get('command')}", "debug")
        return parsed

    async def on_before_execute(
        self, command: str, kwargs: dict[str, Any]
    ) -> None:
        echo(f"[audit] → {command}({kwargs})", "debug")

    async def on_after_execute(
        self, command: str, result: Any, exit_code: int
    ) -> None:
        echo(f"[audit] ← {command} exit={exit_code}", "debug")

    async def on_error(self, command: str, error: BaseException) -> None:
        echo(f"[audit] !! {command}: {error.__class__.__name__}", "error")


cli.add_hook(AuditHook())


# --- Per-command hooks ------------------------------------------------------


@cli.before("ping")
async def _ping_before(kwargs: dict[str, Any]) -> None:
    echo(f"[before:ping] kwargs={kwargs}", "debug")


@cli.after("ping")
async def _ping_after(result: Any, exit_code: int) -> None:
    echo(f"[after:ping] result={result} code={exit_code}", "debug")


@cli.on_error_for("boom")
async def _boom_error(error: BaseException) -> None:
    echo(f"[error:boom] handled {type(error).__name__}", "warning")


# --- Commands ---------------------------------------------------------------


@cli.command(name="ping")
@cli.option("--times", "-n", type=int, default=1)
async def ping(times: int = 1) -> int:
    """Print pong N times."""
    for i in range(1, times + 1):
        echo(f"pong {i}", "success")
        await asyncio.sleep(0.05)
    return 0


@cli.command(name="boom")
def boom() -> int:
    """Always raise; triggers error hooks."""
    raise RuntimeError("kaboom")


@cli.command(name="slow")
async def slow() -> int:
    """Sleep for half a second so the timing middleware is visible."""
    await asyncio.sleep(0.5)
    return 0


def cleanup() -> None:
    echo("[cleanup] flushing buffers", "warning")


cli.add_cleanup_callback(cleanup)


if __name__ == "__main__":
    sys.exit(cli.run())

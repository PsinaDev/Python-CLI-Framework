"""
Async commands and the `progress_bar` helper.

Run:
    python examples/02_async_progress.py download https://example.com --size 60
    python examples/02_async_progress.py upload data.bin --chunks 40
    python examples/02_async_progress.py styles
"""

from __future__ import annotations

import asyncio
import logging
import sys

from cli import CLI, echo, progress_bar

cli = CLI(name="async-demo", log_level=logging.WARNING)


@cli.command(name="download")
@cli.argument("url", help="URL to fetch")
@cli.option("--size", "-s", type=int, default=80, help="Simulated work units")
@cli.option("--delay", type=float, default=0.02, help="Per-step delay in seconds")
async def download(url: str, size: int = 80, delay: float = 0.02) -> int:
    """Simulate an async download with a colored progress bar."""
    echo(f"Downloading {url}", "info")
    update = progress_bar(
        size,
        prefix="GET",
        suffix="done",
        color_low="red",
        color_mid="yellow",
        color_high="green",
    )
    for i in range(1, size + 1):
        await asyncio.sleep(delay)
        update(i)
    echo(f"Saved {url}", "success")
    return 0


@cli.command(name="upload")
@cli.argument("filename", help="File path to upload")
@cli.option("--chunks", "-c", type=int, default=50)
async def upload(filename: str, chunks: int = 50) -> int:
    """Async upload with arrow-style progress bar."""
    echo(f"Uploading {filename}", "info")
    update = progress_bar(
        chunks,
        char="▶",
        empty_char="▷",
        brackets=("⟨", "⟩"),
        prefix=f"PUT {filename}",
        color_high="bright_green",
    )
    for i in range(1, chunks + 1):
        await asyncio.sleep(0.03)
        update(i)
    echo("Upload complete", "success")
    return 0


@cli.command(name="parallel")
@cli.option("--workers", "-w", type=int, default=4)
@cli.option("--per-worker", type=int, default=20)
async def parallel(workers: int = 4, per_worker: int = 20) -> int:
    """Run multiple async tasks concurrently."""
    echo(f"Spawning {workers} workers x {per_worker} steps each", "info")

    async def worker(idx: int) -> None:
        for step in range(per_worker):
            await asyncio.sleep(0.01)
            if step % 5 == 0:
                echo(f"  worker {idx} step {step}", "debug")

    await asyncio.gather(*(worker(i) for i in range(workers)))
    echo("All workers finished", "success")
    return 0


@cli.command(name="styles")
async def styles() -> int:
    """Show a few progress bar style presets."""
    presets: list[tuple[str, dict]] = [
        ("default", {"prefix": "default", "width": 30}),
        (
            "blocks",
            {
                "char": "▓",
                "empty_char": "░",
                "prefix": "blocks",
                "width": 30,
                "color_low": "red",
                "color_high": "green",
            },
        ),
        (
            "ascii",
            {
                "char": "#",
                "empty_char": "-",
                "brackets": ("|", "|"),
                "prefix": "ascii",
                "width": 30,
            },
        ),
        (
            "minimal",
            {
                "char": "=",
                "empty_char": " ",
                "brackets": ("", ""),
                "prefix": "minimal",
                "width": 30,
                "show_count": False,
            },
        ),
    ]
    for name, cfg in presets:
        echo(name, "info")
        update = progress_bar(40, **cfg)
        for i in range(1, 41):
            await asyncio.sleep(0.015)
            update(i)
    echo("Done", "success")
    return 0


if __name__ == "__main__":
    sys.exit(cli.run())

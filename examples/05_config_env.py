"""
Custom config path, environment overlay, and `--config-file` switch.

The framework auto-creates `~/.config/<name>/<name>.json` on first run.
Here we point it at a project-local file so the example is self-contained.

`EnvOverlayConfigProvider` layers env vars on top of the JSON provider:
    APP_PROMPT="env> "          -> overrides "prompt"
    APP_MESSAGES__EN__APP_QUIT  -> overrides nested "messages.en.app_quit"

Run:
    python examples/05_config_env.py show-config
    APP_PROMPT="env> " python examples/05_config_env.py show-config
    python examples/05_config_env.py set-version 2.0.0
    python examples/05_config_env.py --config-file /tmp/other.json show-config
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile

from cli import (
    CLI,
    DEFAULT_CONFIG_SCHEMA,
    EnvOverlayConfigProvider,
    JsonConfigProvider,
    echo,
    table,
)

CONFIG_PATH = os.path.join(tempfile.gettempdir(), "cli-config-demo.json")

DEFAULT_CONFIG: dict = {
    "version": "1.0.0",
    "welcome_message": "Welcome to config-demo",
    "help_hint": "Type 'help'",
    "prompt": "config-demo> ",
    "default_language": "en",
    "current_language": "en",
    "languages": ["en"],
    "messages": {
        "en": {
            "prompt": "config-demo> ",
            "app_quit": "Bye!",
        }
    },
}

inner = JsonConfigProvider(
    CONFIG_PATH,
    default_config=DEFAULT_CONFIG,
    schema=DEFAULT_CONFIG_SCHEMA,
)
overlay = EnvOverlayConfigProvider(inner, prefix="APP")

cli = CLI(
    name="config-demo",
    config_provider=overlay,
    log_level=logging.WARNING,
)


@cli.command(name="show-config")
def show_config() -> int:
    """Print the merged effective configuration."""
    data = cli.config.get_all()
    echo(f"Config file: {CONFIG_PATH}", "info")
    rows = [
        ["version", str(data.get("version"))],
        ["prompt", repr(data.get("prompt"))],
        ["welcome_message", str(data.get("welcome_message"))],
        ["languages", ", ".join(data.get("languages", []))],
    ]
    table(["Key", "Value"], rows)
    return 0


@cli.command(name="set-version")
@cli.argument("value", help="New version string")
def set_version(value: str) -> int:
    """Persist a new version string to the underlying JSON file."""
    cli.config.set("version", value)
    cli.config.save()
    echo(f"Saved version={value} to {CONFIG_PATH}", "success")
    return 0


@cli.command(name="dump-file")
def dump_file() -> int:
    """Print the raw JSON file (without env overlay)."""
    if not os.path.exists(CONFIG_PATH):
        echo("Config file not yet written", "warning")
        return 0
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        echo(json.dumps(json.load(f), indent=2))
    return 0


@cli.command(name="env-keys")
def env_keys() -> int:
    """List APP_* environment variables currently in effect."""
    found = sorted(k for k in os.environ if k.startswith("APP_"))
    if not found:
        echo("No APP_* vars set", "warning")
        return 0
    for k in found:
        echo(f"  {k}={os.environ[k]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(cli.run())

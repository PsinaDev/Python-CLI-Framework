"""
Class-based command groups via `@cli.group`.

Group methods become dotted commands: `db.init`, `db.migrate`, `users.add`, ...

Run:
    python examples/03_groups.py db.status
    python examples/03_groups.py db.migrate --backup
    python examples/03_groups.py users.add alice --role admin
    python examples/03_groups.py help db
"""

from __future__ import annotations

import asyncio
import logging
import sys

from cli import CLI, echo, table

cli = CLI(name="groups-demo", log_level=logging.WARNING)


@cli.group(name="db", help="Database operations")
class DatabaseCommands:
    """Group of database-related commands."""

    @cli.command()
    def init(self) -> int:
        """Initialize the database."""
        echo("Initializing database...", "info")
        echo("Database ready", "success")
        return 0

    @cli.command()
    @cli.option("--backup", "-b", is_flag=True, help="Create backup first")
    async def migrate(self, backup: bool = False) -> int:
        """Run pending migrations."""
        if backup:
            echo("Creating backup...", "warning")
            await asyncio.sleep(0.3)
        echo("Applying migrations...", "info")
        await asyncio.sleep(0.5)
        echo("Migrations applied", "success")
        return 0

    @cli.command()
    def status(self) -> int:
        """Show database status."""
        echo("Database status:", "header")
        table(
            ["Component", "Status", "Details"],
            [
                ["Connection", "OK", "localhost:5432"],
                ["Auth", "OK", "user: admin"],
                ["Tables", "OK", "42 tables"],
                ["Size", "OK", "1.2 GB"],
            ],
        )
        return 0


@cli.group(name="users", help="User management")
class UserCommands:
    """In-memory user store."""

    def __init__(self) -> None:
        self._users: dict[str, str] = {}

    @cli.command()
    @cli.argument("username", help="Login name")
    @cli.option("--role", "-r", default="user", help="User role")
    def add(self, username: str, role: str = "user") -> int:
        """Add a user."""
        if username in self._users:
            echo(f"User {username!r} already exists", "error")
            return 1
        self._users[username] = role
        echo(f"Added {username} ({role})", "success")
        return 0

    @cli.command(name="list")
    def list_users(self) -> int:
        """List known users."""
        if not self._users:
            echo("(no users)", "warning")
            return 0
        table(
            ["Username", "Role"],
            [[u, r] for u, r in sorted(self._users.items())],
        )
        return 0

    @cli.command()
    @cli.argument("username")
    def remove(self, username: str) -> int:
        """Remove a user."""
        if username not in self._users:
            echo(f"Unknown user: {username}", "error")
            return 1
        del self._users[username]
        echo(f"Removed {username}", "success")
        return 0


if __name__ == "__main__":
    sys.exit(cli.run())

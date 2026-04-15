"""
End-to-end mini todo manager combining most framework features:

- Persistent JSON state in a temp file
- Class-based command group (`todo.*`)
- Standalone commands
- Sync and async handlers
- Aliases, examples, flags
- Middleware (timing) and a global `Hook` for audit logging
- Per-command `before` hook for input validation
- Cleanup callback that flushes state on exit

Run:
    python examples/08_todo_app.py todo.add "Write docs" --priority high
    python examples/08_todo_app.py todo.add "Buy milk"
    python examples/08_todo_app.py todo.list
    python examples/08_todo_app.py todo.done 1
    python examples/08_todo_app.py stats
    python examples/08_todo_app.py reset
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Awaitable, Callable

from cli import CLI, Hook, echo, style, table

STATE_PATH = os.path.join(tempfile.gettempdir(), "cli-todo-app.json")


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Todo:
    id: int
    title: str
    priority: Priority = Priority.MEDIUM
    done: bool = False
    created_at: float = field(default_factory=time.time)


@dataclass
class Store:
    todos: list[Todo] = field(default_factory=list)
    next_id: int = 1

    @classmethod
    def load(cls, path: str) -> "Store":
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return cls()
        todos = [
            Todo(
                id=t["id"],
                title=t["title"],
                priority=Priority(t.get("priority", "medium")),
                done=bool(t.get("done", False)),
                created_at=float(t.get("created_at", time.time())),
            )
            for t in raw.get("todos", [])
        ]
        return cls(todos=todos, next_id=int(raw.get("next_id", 1)))

    def save(self, path: str) -> None:
        payload = {
            "next_id": self.next_id,
            "todos": [asdict(t) for t in self.todos],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def add(self, title: str, priority: Priority) -> Todo:
        todo = Todo(id=self.next_id, title=title, priority=priority)
        self.todos.append(todo)
        self.next_id += 1
        return todo

    def get(self, todo_id: int) -> Todo | None:
        return next((t for t in self.todos if t.id == todo_id), None)

    def remove(self, todo_id: int) -> bool:
        before = len(self.todos)
        self.todos = [t for t in self.todos if t.id != todo_id]
        return len(self.todos) != before


store = Store.load(STATE_PATH)
cli = CLI(name="todo", log_level=logging.WARNING)


# --- Middleware & hooks -----------------------------------------------------


async def timing_middleware(
    next_handler: Callable[[], Awaitable[Any]],
) -> Any:
    start = time.perf_counter()
    try:
        return await next_handler()
    finally:
        elapsed = (time.perf_counter() - start) * 1000
        echo(f"[{elapsed:.1f} ms]", "debug")


cli.use(timing_middleware)


class AuditHook(Hook):
    async def on_before_execute(
        self, command: str, kwargs: dict[str, Any]
    ) -> None:
        echo(f"[audit] {command} {kwargs}", "debug")


cli.add_hook(AuditHook())


@cli.before("todo.add")
async def _trace_add(kwargs: dict[str, Any]) -> None:
    echo(f"[before:todo.add] {kwargs}", "debug")


def _flush() -> None:
    store.save(STATE_PATH)
    echo(f"[cleanup] saved state to {STATE_PATH}", "debug")


cli.add_cleanup_callback(_flush)


# --- Commands ---------------------------------------------------------------


@cli.group(name="todo", help="Manage todo items")
class TodoCommands:
    """All operations on the todo list."""

    @cli.command()
    @cli.argument("title", help="Item description")
    @cli.option(
        "--priority", "-p", default="medium",
        help="low | medium | high",
    )
    @cli.example('todo.add "Write docs" --priority high')
    def add(self, title: str, priority: str = "medium") -> int:
        """Add a new item."""
        if not title.strip():
            echo("title must not be empty", "error")
            return 1
        try:
            prio = Priority(priority.lower())
        except ValueError:
            echo(f"Invalid priority: {priority}", "error")
            return 1
        todo = store.add(title.strip(), prio)
        store.save(STATE_PATH)
        echo(f"Added #{todo.id}: {todo.title} [{todo.priority}]", "success")
        return 0

    @cli.command(name="list", aliases=["ls"])
    @cli.option("--all", "-a", is_flag=True, help="Include completed items")
    def list_items(self, all: bool = False) -> int:
        """List items."""
        items = store.todos if all else [t for t in store.todos if not t.done]
        if not items:
            echo("Nothing to show", "warning")
            return 0
        rows = []
        for t in sorted(items, key=lambda x: (x.done, -_priority_rank(x.priority))):
            mark = style("✓", fg="green") if t.done else style("·", fg="yellow")
            rows.append([str(t.id), mark, t.priority.value, t.title])
        table(["ID", "✓", "Prio", "Title"], rows)
        return 0

    @cli.command()
    @cli.argument("todo_id", type=int)
    def done(self, todo_id: int) -> int:
        """Mark an item complete."""
        todo = store.get(todo_id)
        if todo is None:
            echo(f"No todo with id {todo_id}", "error")
            return 1
        todo.done = True
        store.save(STATE_PATH)
        echo(f"Marked #{todo.id} done", "success")
        return 0

    @cli.command(aliases=["rm"])
    @cli.argument("todo_id", type=int)
    def remove(self, todo_id: int) -> int:
        """Delete an item."""
        if not store.remove(todo_id):
            echo(f"No todo with id {todo_id}", "error")
            return 1
        store.save(STATE_PATH)
        echo(f"Removed #{todo_id}", "success")
        return 0


@cli.command(name="stats")
async def stats() -> int:
    """Show counts by priority and status (async, just to demonstrate)."""
    await asyncio.sleep(0)
    by_prio: dict[str, int] = {p.value: 0 for p in Priority}
    done_count = 0
    for t in store.todos:
        by_prio[t.priority.value] += 1
        if t.done:
            done_count += 1
    total = len(store.todos)
    table(
        ["Metric", "Value"],
        [
            ["total", str(total)],
            ["done", str(done_count)],
            ["open", str(total - done_count)],
            *[[f"prio:{k}", str(v)] for k, v in by_prio.items()],
        ],
    )
    return 0


@cli.command(name="reset")
def reset() -> int:
    """Wipe all todos."""
    store.todos.clear()
    store.next_id = 1
    store.save(STATE_PATH)
    echo("State reset", "warning")
    return 0


def _priority_rank(p: Priority) -> int:
    return {Priority.LOW: 0, Priority.MEDIUM: 1, Priority.HIGH: 2}[p]


if __name__ == "__main__":
    sys.exit(cli.run())

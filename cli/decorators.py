"""
Decorators for defining CLI commands.

Supports three registration models:

1. Module-level ``@command``/``@argument``/``@option`` — writes to a process-wide
   ``_default_registry``. Picked up by any CLI that calls
   ``register_all_commands(include_default=True)`` (default behavior).

2. Instance-bound via ``cli.command()`` etc. — writes directly to that CLI's
   private registry. Multiple CLIs in the same process do not collide.

3. ``BoundDecorators(registry)`` — explicit binding to a custom registry.

Per-CLI tracking of "already registered" lives on the CLI object, not on
the registry, so the same metadata can be claimed by multiple CLIs.
"""

from __future__ import annotations

import copy
import inspect
import logging
import threading
import warnings
from typing import Any, Callable, Type, TypeVar, get_args, get_origin
from weakref import WeakKeyDictionary, WeakSet

from .interfaces import RESERVED_NAMES

_logger: logging.Logger = logging.getLogger("cliframework.decorators")

F = TypeVar("F", bound=Callable[..., Any])

_MISSING = object()


def is_async_function(func: Callable[..., Any]) -> bool:
    return inspect.iscoroutinefunction(func)


def _unwrap(func: Callable[..., Any]) -> Callable[..., Any]:
    seen: set[int] = set()
    current = func
    while hasattr(current, "__wrapped__"):
        marker = id(current)
        if marker in seen:
            break
        seen.add(marker)
        current = current.__wrapped__
    return current


def _is_flag_param(param_type: Any, default: Any) -> bool:
    if isinstance(default, bool):
        return True
    if param_type is bool:
        return True
    origin = get_origin(param_type)
    if origin is not None:
        args = get_args(param_type)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and non_none[0] is bool:
            return True
    return False


def _validate_name_not_reserved(name: str, context: str) -> None:
    if name in RESERVED_NAMES or name.lstrip("-") in RESERVED_NAMES:
        raise ValueError(
            f"{context.capitalize()} name '{name}' conflicts with reserved help flag. "
            f"Reserved names: {', '.join(sorted(RESERVED_NAMES))}"
        )


class CommandMetadataRegistry:
    """Thread-safe registry for command metadata using weak references."""

    def __init__(self) -> None:
        self._metadata: WeakKeyDictionary[Callable[..., Any], dict[str, Any]] = (
            WeakKeyDictionary()
        )
        self._group_methods: WeakSet[Callable[..., Any]] = WeakSet()
        self._group_classes: dict[str, Type[Any]] = {}
        self._lock = threading.RLock()

    def get_metadata(
        self, func: Callable[..., Any]
    ) -> dict[str, Any] | None:
        with self._lock:
            meta = self._metadata.get(func)
            return copy.deepcopy(meta) if meta is not None else None

    def set_metadata(
        self, func: Callable[..., Any], metadata: dict[str, Any]
    ) -> None:
        with self._lock:
            self._metadata[func] = copy.deepcopy(metadata)

    def update_metadata(
        self, func: Callable[..., Any], updates: dict[str, Any]
    ) -> None:
        with self._lock:
            current = self._metadata.get(func, {})
            current.update(copy.deepcopy(updates))
            self._metadata[func] = current

    def register_group_class(
        self, group_name: str, cls: Type[Any]
    ) -> None:
        with self._lock:
            self._group_classes[group_name] = cls

    def get_group_classes(self) -> dict[str, Type[Any]]:
        with self._lock:
            return dict(self._group_classes)

    def mark_as_group_method(self, func: Callable[..., Any]) -> None:
        with self._lock:
            self._group_methods.add(func)

    def is_group_method(self, func: Callable[..., Any]) -> bool:
        with self._lock:
            return func in self._group_methods

    def all_functions(self) -> list[Callable[..., Any]]:
        with self._lock:
            return list(self._metadata.keys())

    def clear(self) -> None:
        with self._lock:
            self._metadata.clear()
            self._group_classes.clear()
            self._group_methods.clear()


_default_registry = CommandMetadataRegistry()


def get_default_registry() -> CommandMetadataRegistry:
    """Return the process-wide default registry used by module-level decorators."""
    return _default_registry


def _ensure_command_metadata(
    func: Callable[..., Any],
    registry: CommandMetadataRegistry,
) -> dict[str, Any]:
    target = _unwrap(func)
    existing = registry.get_metadata(target)
    if existing is not None:
        return existing

    cmd_name: str = func.__name__
    help_text: str = inspect.getdoc(func) or f"Command {cmd_name}"
    sig: inspect.Signature = inspect.signature(func)

    arguments: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue
        _validate_name_not_reserved(param_name, "parameter")

        param_type: Any = (
            param.annotation
            if param.annotation is not inspect.Parameter.empty
            else str
        )

        if param.default is not inspect.Parameter.empty:
            options.append(
                {
                    "name": param_name,
                    "help": f"Option {param_name}",
                    "type": param_type,
                    "default": param.default,
                    "default_factory": None,
                    "is_flag": _is_flag_param(param_type, param.default),
                    "group": None,
                    "exclusive_group": None,
                }
            )
        else:
            arguments.append(
                {
                    "name": param_name,
                    "help": f"Argument {param_name}",
                    "type": param_type,
                    "optional": False,
                    "group": None,
                }
            )

    metadata: dict[str, Any] = {
        "name": cmd_name,
        "help": help_text,
        "handler": func,
        "arguments": arguments,
        "options": options,
        "signature": sig,
        "aliases": [],
        "examples": [],
        "is_async": is_async_function(func),
        "is_group": False,
    }
    registry.set_metadata(target, metadata)
    return metadata


def _make_command(registry: CommandMetadataRegistry):
    def command(
        name: str | None = None,
        help: str | None = None,
        aliases: list[str] | None = None,
    ) -> Callable[[F], F]:
        def decorator(func: F) -> F:
            if not callable(func):
                raise TypeError("@command can only be applied to callable")
            target = _unwrap(func)
            _ensure_command_metadata(func, registry)

            updates: dict[str, Any] = {}
            if name is not None:
                _validate_name_not_reserved(name, "command name")
                updates["name"] = name
            if help is not None:
                updates["help"] = help
            if aliases is not None:
                for alias in aliases:
                    _validate_name_not_reserved(alias, "command alias")
                updates["aliases"] = list(aliases)

            if updates:
                registry.update_metadata(target, updates)
            return func

        return decorator

    return command


def _make_argument(registry: CommandMetadataRegistry):
    def argument(
        name: str,
        help: str | None = None,
        type: Type[Any] = str,
        optional: bool = False,
        group: str | None = None,
    ) -> Callable[[F], F]:
        def decorator(func: F) -> F:
            if not callable(func):
                raise TypeError("@argument can only be applied to callable")
            _validate_name_not_reserved(name, "argument")
            target = _unwrap(func)
            metadata = _ensure_command_metadata(func, registry)

            arguments = list(metadata.get("arguments", []))
            options = list(metadata.get("options", []))

            if name in [a["name"] for a in arguments]:
                arguments = [a for a in arguments if a["name"] != name]
            if name in [o["name"] for o in options]:
                warnings.warn(
                    f"Option '{name}' being redefined as argument in command "
                    f"'{metadata['name']}'",
                    stacklevel=2,
                )
                options = [o for o in options if o["name"] != name]

            arguments.append(
                {
                    "name": name,
                    "help": help or f"Argument {name}",
                    "type": type,
                    "optional": optional,
                    "group": group,
                }
            )
            registry.update_metadata(
                target, {"arguments": arguments, "options": options}
            )
            return func

        return decorator

    return argument


def _validate_short_uniqueness(
    options: list[dict[str, Any]],
    new_short: str | None,
    new_name: str,
    command_name: str,
) -> None:
    if new_short is None:
        return
    for opt in options:
        if opt["name"] == new_name:
            continue
        if opt.get("short") == new_short:
            raise ValueError(
                f"Short option '-{new_short}' conflicts with existing option "
                f"'--{opt['name']}' in command '{command_name}'"
            )


def _make_option(registry: CommandMetadataRegistry):
    def option(
        name: str,
        short: str | None = None,
        help: str | None = None,
        type: Type[Any] = str,
        default: Any = _MISSING,
        default_factory: Callable[[], Any] | None = None,
        is_flag: bool | None = None,
        group: str | None = None,
        exclusive_group: str | None = None,
    ) -> Callable[[F], F]:
        if default is not _MISSING and default_factory is not None:
            raise ValueError(
                "Cannot specify both 'default' and 'default_factory'"
            )

        def decorator(func: F) -> F:
            if not callable(func):
                raise TypeError("@option can only be applied to callable")

            normalized_name: str = name[2:] if name.startswith("--") else name
            _validate_name_not_reserved(normalized_name, "option")

            normalized_short: str | None = None
            if short:
                normalized_short = short[1:] if short.startswith("-") else short
                if len(normalized_short) != 1:
                    raise ValueError(
                        f"Short option must be a single character, got: '{short}'"
                    )
                _validate_name_not_reserved(normalized_short, "short option")

            target = _unwrap(func)
            metadata = _ensure_command_metadata(func, registry)

            options = list(metadata.get("options", []))
            arguments = list(metadata.get("arguments", []))

            _validate_short_uniqueness(
                options, normalized_short, normalized_name, metadata["name"]
            )

            if normalized_name in [o["name"] for o in options]:
                options = [
                    o for o in options if o["name"] != normalized_name
                ]
            if normalized_name in [a["name"] for a in arguments]:
                warnings.warn(
                    f"Argument '{normalized_name}' being redefined as option in "
                    f"command '{metadata['name']}'",
                    stacklevel=2,
                )
                arguments = [
                    a for a in arguments if a["name"] != normalized_name
                ]

            resolved_default: Any = (
                None if default is _MISSING else default
            )
            resolved_is_flag = (
                is_flag if is_flag is not None
                else _is_flag_param(type, resolved_default)
            )

            options.append(
                {
                    "name": normalized_name,
                    "short": normalized_short,
                    "help": help or f"Option {normalized_name}",
                    "type": type,
                    "default": resolved_default,
                    "default_factory": default_factory,
                    "is_flag": resolved_is_flag,
                    "group": group,
                    "exclusive_group": exclusive_group,
                }
            )
            registry.update_metadata(
                target, {"options": options, "arguments": arguments}
            )
            return func

        return decorator

    return option


def _make_example(registry: CommandMetadataRegistry):
    def example(example_text: str) -> Callable[[F], F]:
        def decorator(func: F) -> F:
            if not callable(func):
                raise TypeError("@example can only be applied to callable")
            target = _unwrap(func)
            metadata = _ensure_command_metadata(func, registry)
            examples = list(metadata.get("examples", []))
            examples.append(example_text)
            registry.update_metadata(target, {"examples": examples})
            return func

        return decorator

    return example


def _make_group(registry: CommandMetadataRegistry):
    def group(
        name: str | None = None, help: str | None = None
    ) -> Callable[[Type[Any]], Type[Any]]:
        def decorator(cls: Type[Any]) -> Type[Any]:
            group_name: str = name or cls.__name__.lower()
            group_help: str = (
                help or inspect.getdoc(cls) or f"Command group {group_name}"
            )

            command_methods: list[tuple[str, Callable[..., Any]]] = []
            for attr_name in dir(cls):
                if attr_name.startswith("_"):
                    continue
                try:
                    attr = getattr(cls, attr_name)
                except AttributeError:
                    continue
                if not callable(attr):
                    continue
                target = _unwrap(attr)
                if registry.get_metadata(target) is not None:
                    registry.mark_as_group_method(target)
                    command_methods.append((attr_name, attr))

            cls.__cli_group_info__ = {
                "name": group_name,
                "help": group_help,
                "methods": command_methods,
            }
            registry.register_group_class(group_name, cls)
            return cls

        return decorator

    return group


class BoundDecorators:
    """Container of decorators bound to a specific CommandMetadataRegistry."""

    def __init__(self, registry: CommandMetadataRegistry) -> None:
        self.registry = registry
        self.command = _make_command(registry)
        self.argument = _make_argument(registry)
        self.option = _make_option(registry)
        self.example = _make_example(registry)
        self.group = _make_group(registry)


_default_decorators = BoundDecorators(_default_registry)
command = _default_decorators.command
argument = _default_decorators.argument
option = _default_decorators.option
example = _default_decorators.example
group = _default_decorators.group


def register_commands(
    cli_instance: Any,
    registries: list[CommandMetadataRegistry] | None = None,
    include_default: bool = True,
) -> int:
    """
    Register decorator-defined commands with the CLI instance.

    Walks the CLI's own registry (cli._registry) and optionally the process
    default registry. Functions already in cli._registered_funcs are skipped.
    """
    if registries is None:
        registries = []
        own = getattr(cli_instance, "_registry", None)
        if own is not None:
            registries.append(own)
        if include_default and own is not _default_registry:
            registries.append(_default_registry)

    registered: WeakSet[Callable[..., Any]] = getattr(
        cli_instance, "_registered_funcs", WeakSet()
    )
    if not hasattr(cli_instance, "_registered_funcs"):
        cli_instance._registered_funcs = registered

    count = 0
    for registry in registries:
        count += _register_from(cli_instance, registry, registered)
    return count


def _register_from(
    cli_instance: Any,
    registry: CommandMetadataRegistry,
    registered: WeakSet[Callable[..., Any]],
) -> int:
    count = 0
    for func in registry.all_functions():
        if func in registered or registry.is_group_method(func):
            continue
        metadata = registry.get_metadata(func)
        if metadata is None:
            continue
        try:
            payload = {
                "help": metadata.get("help", ""),
                "arguments": list(metadata.get("arguments", [])),
                "options": list(metadata.get("options", [])),
                "aliases": list(metadata.get("aliases", [])),
                "examples": list(metadata.get("examples", [])),
                "is_async": metadata.get("is_async", False),
                "is_group": metadata.get("is_group", False),
            }
            cli_instance.commands.register(
                metadata["name"], metadata["handler"], **payload
            )
            registered.add(func)
            count += 1
        except Exception as exc:
            _logger.error(
                f"Error registering command '{metadata.get('name')}': {exc}",
                exc_info=True,
            )

    for group_name, group_class in registry.get_group_classes().items():
        try:
            instance = group_class()
        except TypeError as exc:
            _logger.error(
                f"Cannot instantiate group '{group_name}' without args: {exc}"
            )
            continue
        except Exception as exc:
            _logger.error(
                f"Error instantiating group '{group_name}': {exc}",
                exc_info=True,
            )
            continue

        group_info = group_class.__cli_group_info__
        for method_name, method in group_info["methods"]:
            target = _unwrap(method)
            if target in registered:
                continue
            metadata = registry.get_metadata(target)
            if not metadata:
                continue

            bound_method = getattr(instance, method_name)
            full_name = f"{group_name}.{metadata['name']}"
            payload = {
                "help": metadata.get("help", ""),
                "arguments": list(metadata.get("arguments", [])),
                "options": list(metadata.get("options", [])),
                "aliases": list(metadata.get("aliases", [])),
                "examples": list(metadata.get("examples", [])),
                "is_async": metadata.get("is_async", False),
                "is_group": False,
            }
            try:
                cli_instance.commands.register(
                    full_name, bound_method, **payload
                )
                registered.add(target)
                count += 1
            except Exception as exc:
                _logger.error(
                    f"Error registering group command '{full_name}': {exc}",
                    exc_info=True,
                )
    return count


def clear_default_registry() -> None:
    """Clear the process-wide default registry (test helper)."""
    _default_registry.clear()


def clear_registry() -> None:
    """Backward-compat alias for clear_default_registry."""
    _default_registry.clear()


__all__ = [
    "command",
    "argument",
    "option",
    "example",
    "group",
    "is_async_function",
    "register_commands",
    "clear_registry",
    "clear_default_registry",
    "get_default_registry",
    "CommandMetadataRegistry",
    "BoundDecorators",
]

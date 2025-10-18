"""
Decorators for defining CLI commands

Provides decorators for command definition, arguments, options,
groups, and examples with automatic async detection.
"""

import inspect
import functools
import logging
import warnings
import asyncio
import threading
import copy
from typing import Any, Callable, Dict, List, Optional, Set, Type, TypeVar, cast

_logger: logging.Logger = logging.getLogger('cliframework.decorators')

F = TypeVar('F', bound=Callable[..., Any])


class CommandMetadataRegistry:
    """Thread-safe registry for command metadata"""

    def __init__(self):
        self._metadata: Dict[int, Dict[str, Any]] = {}
        self._registered: Set[int] = set()
        self._lock = threading.Lock()
        self._group_classes: Dict[str, Type[Any]] = {}
        self._group_method_ids: Set[int] = set()

    def get_metadata(self, func_id: int) -> Optional[Dict[str, Any]]:
        """Get metadata by function id"""
        with self._lock:
            return copy.deepcopy(self._metadata.get(func_id))

    def set_metadata(self, func_id: int, metadata: Dict[str, Any]) -> None:
        """Set metadata for function"""
        with self._lock:
            self._metadata[func_id] = copy.deepcopy(metadata)

    def update_metadata(self, func_id: int, updates: Dict[str, Any]) -> None:
        """Update metadata for function"""
        with self._lock:
            if func_id not in self._metadata:
                self._metadata[func_id] = {}
            self._metadata[func_id].update(copy.deepcopy(updates))

    def is_registered(self, func_id: int) -> bool:
        """Check if function is already registered"""
        with self._lock:
            return func_id in self._registered

    def mark_registered(self, func_id: int) -> None:
        """Mark function as registered"""
        with self._lock:
            self._registered.add(func_id)

    def register_group_class(self, group_name: str, cls: Type[Any]) -> None:
        """Register a command group class (without instantiating)"""
        with self._lock:
            self._group_classes[group_name] = cls

    def get_group_classes(self) -> Dict[str, Type[Any]]:
        """Get all registered group classes"""
        with self._lock:
            return self._group_classes.copy()

    def mark_as_group_method(self, func_id: int) -> None:
        """Mark function ID as belonging to a group method"""
        with self._lock:
            self._group_method_ids.add(func_id)

    def is_group_method(self, func_id: int) -> bool:
        """Check if function ID belongs to a group method"""
        with self._lock:
            return func_id in self._group_method_ids

    def clear(self) -> None:
        """Clear all metadata (useful for testing)"""
        with self._lock:
            self._metadata.clear()
            self._registered.clear()
            self._group_classes.clear()
            self._group_method_ids.clear()

    def get_all_metadata(self) -> Dict[int, Dict[str, Any]]:
        """Get all metadata (deep copy)"""
        with self._lock:
            return {fid: copy.deepcopy(meta) for fid, meta in self._metadata.items()}


# Global registry instance
_registry = CommandMetadataRegistry()


def is_async_function(func: Callable[..., Any]) -> bool:
    """Check if function is async (coroutine function)"""
    return inspect.iscoroutinefunction(func)


def _get_func_id(func: Callable[..., Any]) -> int:
    """Get unique ID for function"""
    original = func
    while hasattr(original, '__wrapped__'):
        original = original.__wrapped__
    return id(original)


def _ensure_command_metadata(func: Callable[..., Any]) -> Dict[str, Any]:
    """Ensure function has command metadata dictionary"""
    func_id = _get_func_id(func)
    metadata = _registry.get_metadata(func_id)

    if metadata is not None:
        return metadata

    cmd_name: str = func.__name__
    help_text: Optional[str] = inspect.getdoc(func) or f"Command {cmd_name}"
    sig: inspect.Signature = inspect.signature(func)

    arguments: List[Dict[str, Any]] = []
    options: List[Dict[str, Any]] = []

    for param_name, param in sig.parameters.items():
        if param_name in ('self', 'cls'):
            continue

        param_type: Type[Any] = (
            param.annotation
            if param.annotation != inspect.Parameter.empty
            else str
        )

        if param.default != inspect.Parameter.empty:
            options.append({
                'name': param_name,
                'help': f"Option {param_name}",
                'type': param_type,
                'default': param.default,
                'is_flag': isinstance(param.default, bool)
            })
        else:
            arguments.append({
                'name': param_name,
                'help': f"Argument {param_name}",
                'type': param_type
            })

    is_async = is_async_function(func)

    metadata = {
        'name': cmd_name,
        'help': help_text,
        'handler': func,
        'arguments': arguments,
        'options': options,
        'signature': sig,
        'aliases': [],
        'examples': [],
        'is_async': is_async,
        'is_group': False
    }

    _registry.set_metadata(func_id, metadata)
    _logger.debug(
        f"Created metadata for {'async ' if is_async else ''}command {cmd_name}"
    )

    return metadata


def command(name: Optional[str] = None,
            help: Optional[str] = None,
            aliases: Optional[List[str]] = None) -> Callable[[F], F]:
    """Decorator to define CLI command"""

    def decorator(func: F) -> F:
        if not callable(func):
            raise TypeError("@command can only be applied to callable")

        func_id = _get_func_id(func)
        metadata = _ensure_command_metadata(func)

        updates: Dict[str, Any] = {}
        if name is not None:
            updates['name'] = name
        if help is not None:
            updates['help'] = help
        if aliases is not None:
            updates['aliases'] = list(aliases)

        if updates:
            _registry.update_metadata(func_id, updates)

        func.__cli_func_id__ = func_id
        return func

    return decorator


def argument(name: str,
             help: Optional[str] = None,
             type: Type[Any] = str) -> Callable[[F], F]:
    """Decorator to define positional argument"""

    def decorator(func: F) -> F:
        if not callable(func):
            raise TypeError("@argument can only be applied to callable")

        func_id = _get_func_id(func)
        metadata = _ensure_command_metadata(func)

        arguments = list(metadata.get('arguments', []))
        options = list(metadata.get('options', []))

        existing_arg_names = [arg['name'] for arg in arguments]
        existing_opt_names = [opt['name'] for opt in options]

        if name in existing_arg_names:
            arguments = [arg for arg in arguments if arg['name'] != name]

        if name in existing_opt_names:
            warnings.warn(
                f"Option '{name}' being redefined as argument in command '{metadata['name']}'"
            )
            options = [opt for opt in options if opt['name'] != name]

        arguments.append({
            'name': name,
            'help': help or f"Argument {name}",
            'type': type
        })

        _registry.update_metadata(func_id, {
            'arguments': arguments,
            'options': options
        })

        func.__cli_func_id__ = func_id
        return func

    return decorator


def _validate_short_uniqueness(options: List[Dict[str, Any]], new_short: Optional[str], new_name: str, command_name: str) -> None:
    """Validate that short option is unique within command"""
    if new_short is None:
        return

    for opt in options:
        if opt['name'] == new_name:
            continue
        existing_short = opt.get('short')
        if existing_short == new_short:
            raise ValueError(
                f"Short option '-{new_short}' conflicts with existing option "
                f"'--{opt['name']}' in command '{command_name}'. "
                f"Each short option must be unique."
            )


def option(name: str,
           short: Optional[str] = None,
           help: Optional[str] = None,
           type: Type[Any] = str,
           default: Any = None,
           is_flag: bool = False) -> Callable[[F], F]:
    """Decorator to define command option"""

    def decorator(func: F) -> F:
        if not callable(func):
            raise TypeError("@option can only be applied to callable")

        normalized_name: str = name[2:] if name.startswith('--') else name

        normalized_short: Optional[str] = None
        if short:
            normalized_short = short[1:] if short.startswith('-') else short
            if len(normalized_short) != 1:
                raise ValueError(
                    f"Short option must be a single character, got: '{short}'"
                )

        func_id = _get_func_id(func)
        metadata = _ensure_command_metadata(func)

        options = list(metadata.get('options', []))
        arguments = list(metadata.get('arguments', []))

        # Validate short option uniqueness
        _validate_short_uniqueness(options, normalized_short, normalized_name, metadata['name'])

        existing_opt_names = [opt['name'] for opt in options]
        existing_arg_names = [arg['name'] for arg in arguments]

        if normalized_name in existing_opt_names:
            options = [opt for opt in options if opt['name'] != normalized_name]

        if normalized_name in existing_arg_names:
            warnings.warn(
                f"Argument '{normalized_name}' being redefined as option in command '{metadata['name']}'"
            )
            arguments = [arg for arg in arguments if arg['name'] != normalized_name]

        options.append({
            'name': normalized_name,
            'short': normalized_short,
            'help': help or f"Option {normalized_name}",
            'type': type,
            'default': default,
            'is_flag': is_flag
        })

        _registry.update_metadata(func_id, {
            'options': options,
            'arguments': arguments
        })

        func.__cli_func_id__ = func_id
        return func

    return decorator


def example(example_text: str) -> Callable[[F], F]:
    """Decorator to add usage example to command"""

    def decorator(func: F) -> F:
        if not callable(func):
            raise TypeError("@example can only be applied to callable")

        func_id = _get_func_id(func)
        metadata = _ensure_command_metadata(func)

        examples = list(metadata.get('examples', []))
        examples.append(example_text)

        _registry.update_metadata(func_id, {'examples': examples})

        func.__cli_func_id__ = func_id
        return func

    return decorator


def group(name: Optional[str] = None,
          help: Optional[str] = None) -> Callable[[Type[Any]], Type[Any]]:
    """
    Decorator to define command group
    """

    def decorator(cls: Type[Any]) -> Type[Any]:
        group_name: str = name or cls.__name__.lower()
        group_help: str = help or inspect.getdoc(cls) or f"Command group {group_name}"

        # Scan class methods for decorated commands (without instantiating)
        command_methods: List[tuple[str, Any]] = []

        for attr_name in dir(cls):
            if attr_name.startswith('_'):
                continue

            try:
                attr = getattr(cls, attr_name)
                if not callable(attr):
                    continue

                if hasattr(attr, '__cli_func_id__'):
                    func_id = attr.__cli_func_id__
                    _registry.mark_as_group_method(func_id)
                    command_methods.append((attr_name, attr))
            except AttributeError:
                # Skip attributes that can't be accessed on the class
                continue

        cls.__cli_group_info__ = {
            'name': group_name,
            'help': group_help,
            'methods': command_methods
        }

        # Register the class (not an instance)
        _registry.register_group_class(group_name, cls)

        _logger.debug(
            f"Registered command group class '{group_name}' with {len(command_methods)} commands"
        )

        return cls

    return decorator


def register_commands(cli_instance: Any) -> int:
    """
    Register all decorated commands with CLI instance
    """
    registered_count: int = 0
    all_metadata = _registry.get_all_metadata()

    # Register standalone commands (excluding group methods)
    for func_id, metadata in all_metadata.items():
        if _registry.is_registered(func_id):
            continue

        # Skip if this is a group method
        if _registry.is_group_method(func_id):
            continue

        try:
            command_name: str = metadata['name']
            handler: Callable[..., Any] = metadata['handler']

            metadata_copy = {
                'help': metadata.get('help', ''),
                'arguments': list(metadata.get('arguments', [])),
                'options': list(metadata.get('options', [])),
                'aliases': list(metadata.get('aliases', [])),
                'examples': list(metadata.get('examples', [])),
                'is_async': metadata.get('is_async', False),
                'is_group': metadata.get('is_group', False),
            }

            cli_instance.commands.register(command_name, handler, **metadata_copy)
            _registry.mark_registered(func_id)
            registered_count += 1

            _logger.debug(f"Registered command: {command_name}")

        except Exception as e:
            _logger.error(f"Error registering command: {e}")
            import traceback
            _logger.error(traceback.format_exc())

    # Process explicitly registered group classes
    group_classes = _registry.get_group_classes()

    for group_name, group_class in group_classes.items():
        try:
            # NOW we instantiate, but only for explicitly registered groups
            instance = group_class()

            group_info = group_class.__cli_group_info__

            for method_name, method in group_info['methods']:
                bound_method = getattr(instance, method_name)
                func_id = _get_func_id(method)

                if _registry.is_registered(func_id):
                    continue

                metadata = _registry.get_metadata(func_id)
                if not metadata:
                    continue

                orig_name = metadata['name']
                full_name = f"{group_name}.{orig_name}"

                metadata_copy = {
                    'help': metadata.get('help', ''),
                    'arguments': list(metadata.get('arguments', [])),
                    'options': list(metadata.get('options', [])),
                    'aliases': list(metadata.get('aliases', [])),
                    'examples': list(metadata.get('examples', [])),
                    'is_async': metadata.get('is_async', False),
                    'is_group': False,
                }

                cli_instance.commands.register(full_name, bound_method, **metadata_copy)
                _registry.mark_registered(func_id)
                registered_count += 1

                _logger.debug(f"Registered group command: {full_name}")

        except Exception as e:
            _logger.error(f"Error instantiating group '{group_name}': {e}")
            import traceback
            _logger.error(traceback.format_exc())
            continue

    return registered_count


def clear_registry() -> None:
    """Clear command registry (useful for testing)"""
    _registry.clear()
    _logger.debug("Command registry cleared")
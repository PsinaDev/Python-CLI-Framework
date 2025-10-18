"""
Command registry and argument parsing

Provides command registration, lookup, and command-line argument parsing
with type validation and help generation.
"""

import argparse
import json
import logging
import copy
import threading
from typing import Any, Dict, List, Optional, Set, Type, Callable, Union, Tuple, get_origin, get_args
from collections import OrderedDict
from .interfaces import CommandRegistry, ArgumentParser


class _TrieNode:
    """Single node in command trie"""

    def __init__(self) -> None:
        self.children: Dict[str, '_TrieNode'] = {}
        self.is_end: bool = False
        self.command_name: Optional[str] = None


class CommandTrie:
    """Trie for efficient command autocomplete"""

    def __init__(self) -> None:
        self.root: _TrieNode = _TrieNode()

    def insert(self, command: str) -> None:
        """Insert command into trie"""
        node: _TrieNode = self.root
        for char in command:
            if char not in node.children:
                node.children[char] = _TrieNode()
            node = node.children[char]
        node.is_end = True
        node.command_name = command

    def autocomplete(self, prefix: str) -> List[str]:
        """Find all commands matching prefix"""
        node: _TrieNode = self.root
        for char in prefix:
            if char not in node.children:
                return []
            node = node.children[char]
        return self._collect_commands(node, prefix)

    def _collect_commands(self, node: _TrieNode, prefix: str) -> List[str]:
        """Iteratively collect all command names from node"""
        results: List[str] = []
        stack: List[Tuple[_TrieNode, str]] = [(node, prefix)]

        while stack:
            current_node, current_prefix = stack.pop()

            if current_node.is_end and current_node.command_name:
                results.append(current_node.command_name)

            for char, child_node in current_node.children.items():
                stack.append((child_node, current_prefix + char))

        return sorted(results)

    def remove(self, command: str) -> bool:
        """Remove command from trie"""
        def _remove_helper(node: _TrieNode, cmd: str, depth: int) -> Tuple[bool, bool]:
            if depth == len(cmd):
                if not node.is_end:
                    return False, False
                node.is_end = False
                node.command_name = None
                should_delete = len(node.children) == 0
                return True, should_delete

            char = cmd[depth]
            if char not in node.children:
                return False, False

            child = node.children[char]
            was_removed, should_delete = _remove_helper(child, cmd, depth + 1)

            if should_delete:
                del node.children[char]
                node_should_delete = not node.is_end and len(node.children) == 0
                return was_removed, node_should_delete

            return was_removed, False

        was_removed, _ = _remove_helper(self.root, command, 0)
        return was_removed


class CommandMeta:
    """Immutable command metadata"""

    def __init__(self, handler: Callable[..., Any], **metadata: Any):
        self._handler = handler
        self._metadata = copy.deepcopy(metadata)
        self._metadata['handler'] = handler

    def get(self, key: str, default: Any = None) -> Any:
        """Get metadata value"""
        return self._metadata.get(key, default)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return copy.deepcopy(self._metadata)

    @property
    def handler(self) -> Callable[..., Any]:
        """Get handler function"""
        return self._handler


class CommandRegistryImpl(CommandRegistry):
    """Thread-safe command registry with aliases and groups"""

    def __init__(self) -> None:
        self._commands: Dict[str, CommandMeta] = {}
        self._aliases: Dict[str, str] = {}
        self._groups: Dict[str, Dict[str, Any]] = {}
        self._trie: CommandTrie = CommandTrie()
        self._logger: logging.Logger = logging.getLogger('cliframework.command_registry')
        self._parser_cache_invalidator: Optional[Callable[[str], None]] = None
        self._lock = threading.Lock()

    def register(self, name: str, handler: Callable[..., Any], **metadata: Any) -> None:
        """Register command with metadata"""
        with self._lock:
            try:
                if metadata.get('is_group', False):
                    self._groups[name] = copy.deepcopy(metadata)
                    self._logger.info(f"Registered command group: {name}")
                    return

                if name in self._commands:
                    old_meta = self._commands[name]
                    old_aliases = old_meta.get('aliases', [])

                    for alias in old_aliases:
                        if alias in self._aliases and self._aliases[alias] == name:
                            del self._aliases[alias]
                            self._trie.remove(alias)
                            self._logger.debug(f"Removed old alias '{alias}' for command '{name}'")

                    self._trie.remove(name)

                requested_aliases = list(metadata.get('aliases', []))
                registered_aliases = []

                for alias in requested_aliases:
                    if alias in self._commands:
                        self._logger.warning(
                            f"Alias '{alias}' conflicts with existing command, skipping"
                        )
                        continue

                    if alias in self._aliases:
                        old_target = self._aliases[alias]
                        if old_target != name:
                            self._logger.warning(
                                f"Alias '{alias}' previously pointed to '{old_target}', "
                                f"now reassigning to '{name}'"
                            )
                            self._trie.remove(alias)

                    self._aliases[alias] = name
                    self._trie.insert(alias)
                    registered_aliases.append(alias)
                    self._logger.debug(f"Registered alias '{alias}' for command '{name}'")

                metadata_copy = copy.deepcopy(metadata)
                metadata_copy['aliases'] = registered_aliases

                cmd_meta = CommandMeta(handler, **metadata_copy)
                self._commands[name] = cmd_meta
                self._trie.insert(name)
                self._logger.info(f"Registered command: {name}")

                if self._parser_cache_invalidator:
                    self._parser_cache_invalidator(name)
                    for alias in registered_aliases:
                        self._parser_cache_invalidator(alias)

            except Exception as e:
                self._logger.error(f"Error registering command '{name}': {e}")
                raise

    def get_command(self, name: str) -> Optional[Dict[str, Any]]:
        """Get command metadata by name or alias"""
        with self._lock:
            if name in self._aliases:
                real_name: str = self._aliases[name]
                cmd_meta = self._commands.get(real_name)
                return cmd_meta.to_dict() if cmd_meta else None

            cmd_meta = self._commands.get(name)
            return cmd_meta.to_dict() if cmd_meta else None

    def list_commands(self) -> List[str]:
        """Get list of all command names"""
        with self._lock:
            return sorted(self._commands.keys())

    def autocomplete(self, prefix: str) -> List[str]:
        """Get commands matching prefix using trie"""
        with self._lock:
            return self._trie.autocomplete(prefix)

    def remove_command(self, name: str) -> bool:
        """Remove command from registry"""
        with self._lock:
            if name not in self._commands:
                return False

            cmd_meta: CommandMeta = self._commands[name]
            aliases: List[str] = cmd_meta.get('aliases', [])

            del self._commands[name]
            self._trie.remove(name)

            for alias in aliases:
                if alias in self._aliases and self._aliases[alias] == name:
                    del self._aliases[alias]
                    self._trie.remove(alias)

            if self._parser_cache_invalidator:
                self._parser_cache_invalidator(name)
                for alias in aliases:
                    self._parser_cache_invalidator(alias)

            self._logger.info(f"Removed command: {name}")
            return True

    def set_parser_cache_invalidator(self, invalidator: Callable[[str], None]) -> None:
        """Set callback to invalidate parser cache"""
        self._parser_cache_invalidator = invalidator

    def get_all_groups(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered command groups"""
        with self._lock:
            return copy.deepcopy(self._groups)


VALID_BASIC_TYPES: Set[Type[Any]] = {str, int, float, bool}


def validate_type(param_type: Any, strict: bool = False) -> Union[Type[Any], Callable[[str], Any]]:
    """
    Validate and normalize parameter type

    Args:
        param_type: Type to validate
        strict: If True, raise ValueError for unsupported types

    Returns:
        Validated type or converter function
    """
    logger = logging.getLogger('cliframework.command')

    if param_type in VALID_BASIC_TYPES:
        return param_type

    if callable(param_type) and not isinstance(param_type, type):
        return param_type

    origin = get_origin(param_type)

    if origin is not None:
        if origin in (list, dict, tuple):
            args = get_args(param_type)
            if args:
                type_repr = f"{origin.__name__}[{', '.join(str(a) for a in args)}]"
                logger.info(
                    f"Parameter type {type_repr} has element types specified. "
                    f"Note: element types will not be validated during parsing"
                )
            return origin

        if origin is Union:
            args = get_args(param_type)
            non_none_args = [arg for arg in args if arg is not type(None)]

            if len(non_none_args) == 1:
                return validate_type(non_none_args[0], strict)
            elif len(non_none_args) > 1:
                basic_types = [arg for arg in non_none_args if arg in VALID_BASIC_TYPES]

                if len(basic_types) == len(non_none_args):
                    type_names = [t.__name__ for t in non_none_args]
                    if strict:
                        raise ValueError(
                            f"Union of multiple types {param_type} ({', '.join(type_names)}) is not supported"
                        )
                    logger.warning(
                        f"Union type {param_type} ({', '.join(type_names)}) will use 'str' as fallback"
                    )
                    return str
                else:
                    raise TypeError(
                        f"Complex Union type {param_type} is not supported for command-line arguments"
                    )

    type_repr = str(param_type)
    if strict:
        raise ValueError(
            f"Unsupported parameter type {type_repr}"
        )
    logger.warning(
        f"Unsupported parameter type {type_repr}, using 'str' as fallback"
    )
    return str


RESERVED_NAMES = {'help', 'h', '_cli_help'}


class EnhancedArgumentParser(ArgumentParser):
    """Enhanced argument parser with caching and type validation"""

    def __init__(self, command_registry: CommandRegistry, max_cache_size: int = 128):
        """Initialize argument parser"""
        self._command_registry: CommandRegistry = command_registry
        self._max_cache_size: int = max_cache_size
        self._parser_cache: OrderedDict[str, argparse.ArgumentParser] = OrderedDict()
        self._logger: logging.Logger = logging.getLogger('cliframework.argument_parser')

        if hasattr(command_registry, 'set_parser_cache_invalidator'):
            command_registry.set_parser_cache_invalidator(self.invalidate_command)

    def parse(self, args: List[str]) -> Dict[str, Any]:
        """Parse command-line arguments"""
        if not args:
            return {'command': None}

        command: str = args[0]
        remaining_args: List[str] = args[1:]
        result: Dict[str, Any] = {'command': command}

        # Check for help flag before argparse to avoid required argument errors
        if '--help' in remaining_args or '-h' in remaining_args:
            result['_cli_show_help'] = True
            return result

        command_meta: Optional[Dict[str, Any]] = self._command_registry.get_command(command)
        if not command_meta:
            return result

        parser: argparse.ArgumentParser = self._get_parser_for_command(command, command_meta)

        try:
            parsed_args: argparse.Namespace = parser.parse_args(remaining_args)
            result.update(vars(parsed_args))
            return result

        except SystemExit as e:
            if e.code == 0:
                result['_cli_show_help'] = True
                return result
            else:
                raise ValueError(
                    f"Invalid arguments for command '{command}'.\n"
                    f"Use '{command} --help' for detailed help."
                )
        except Exception as e:
            self._logger.error(f"Error parsing arguments: {e}")
            raise ValueError(f"Argument parsing error: {e}")

    def _get_parser_for_command(self, command: str,
                                command_meta: Dict[str, Any]) -> argparse.ArgumentParser:
        """Get cached parser or create new one"""
        if command in self._parser_cache:
            self._parser_cache.move_to_end(command)
            return self._parser_cache[command]

        parser: argparse.ArgumentParser = self._create_parser(command, command_meta)

        if len(self._parser_cache) >= self._max_cache_size:
            self._parser_cache.popitem(last=False)

        self._parser_cache[command] = parser
        return parser

    def _create_parser(self, command: str,
                       command_meta: Dict[str, Any]) -> argparse.ArgumentParser:
        """Create ArgumentParser for command"""
        parser = argparse.ArgumentParser(
            prog=command,
            description=command_meta.get('help', ''),
            add_help=False,
            formatter_class=argparse.RawDescriptionHelpFormatter
        )

        parser.add_argument(
            '--help', '-h',
            action='store_true',
            dest='_cli_help',
            help='Show this help message'
        )

        arguments = command_meta.get('arguments', [])
        optional_count = sum(1 for arg in arguments if arg.get('optional'))

        if optional_count > 1:
            raise ValueError(
                f"Command '{command}' has {optional_count} optional positional arguments. "
                f"Only one optional positional argument is allowed at the end"
            )

        found_optional = False
        for i, arg_meta in enumerate(arguments):
            is_optional = arg_meta.get('optional', False)
            if found_optional and not is_optional:
                raise ValueError(
                    f"Command '{command}': Optional positional argument '{arguments[i-1]['name']}' "
                    f"must come after all required arguments"
                )
            if is_optional:
                found_optional = True

        for arg_meta in arguments:
            arg_name: str = arg_meta['name']

            if arg_name in RESERVED_NAMES:
                raise ValueError(
                    f"Argument name '{arg_name}' conflicts with reserved name in command '{command}'"
                )

            arg_type: Type[Any] = validate_type(arg_meta.get('type', str))
            arg_help: str = arg_meta.get('help', '')

            parser.add_argument(
                arg_name,
                type=self._get_type_converter(arg_type),
                help=arg_help,
                nargs='?' if arg_meta.get('optional') else None
            )

        for opt_meta in command_meta.get('options', []):
            opt_name: str = opt_meta['name']
            opt_short: Optional[str] = opt_meta.get('short')

            if opt_name in RESERVED_NAMES or (opt_short and opt_short in RESERVED_NAMES):
                raise ValueError(
                    f"Option '--{opt_name}' or '-{opt_short}' conflicts with reserved name in command '{command}'"
                )

            opt_type: Type[Any] = validate_type(opt_meta.get('type', str))
            opt_default: Any = opt_meta.get('default')
            opt_is_flag: bool = opt_meta.get('is_flag', False)
            opt_help: str = opt_meta.get('help', '')

            names: List[str] = [f'--{opt_name}']
            if opt_short:
                names.append(f'-{opt_short}')

            if opt_is_flag:
                if opt_default is True:
                    no_names = [f'--no-{opt_name}']
                    if opt_help and opt_help.strip():
                        help_text = f"{opt_help} (enabled by default, use --no-{opt_name} to disable)"
                    else:
                        help_text = f"Disable {opt_name} (enabled by default)"
                    parser.add_argument(
                        *no_names,
                        action='store_false',
                        dest=opt_name,
                        default=True,
                        help=help_text
                    )
                else:
                    if opt_help and opt_help.strip():
                        help_text = f"{opt_help} (disabled by default)"
                    else:
                        help_text = f'Enable {opt_name}'
                    parser.add_argument(
                        *names,
                        action='store_true',
                        dest=opt_name,
                        default=False,
                        help=help_text
                    )
            else:
                type_converter = self._get_type_converter(opt_type)
                enhanced_help = opt_help
                if opt_type in (list, dict, tuple):
                    examples = self._get_type_examples(opt_type)
                    if examples and opt_help:
                        enhanced_help = f"{opt_help} {examples}"
                    elif examples:
                        enhanced_help = f"Value for {opt_name} {examples}"

                parser.add_argument(
                    *names,
                    type=type_converter,
                    default=opt_default,
                    help=enhanced_help or opt_help
                )

        return parser

    def _get_type_examples(self, type_obj: Type[Any]) -> str:
        """Generate usage examples for complex types"""
        if type_obj is list:
            return '(e.g., "a,b,c" or \'["a","b","c"]\')'
        elif type_obj is dict:
            return '(e.g., \'{"key":"val"}\' or "k1=v1,k2=v2")'
        elif type_obj is tuple:
            return '(e.g., \'[1,2,3]\' for JSON)'
        return ''

    def _get_type_converter(self, type_obj: Type[Any]) -> Callable[[str], Any]:
        """Get converter function for type with support for complex types"""
        if callable(type_obj) and not isinstance(type_obj, type):
            return type_obj

        if type_obj is bool:
            def bool_converter(s: str) -> bool:
                v = s.strip().lower()
                if v in ('true', 'yes', 'y', '1', 'on'):
                    return True
                if v in ('false', 'no', 'n', '0', 'off'):
                    return False
                raise ValueError(
                    f"Invalid boolean value: '{s}'. "
                    f"Valid values: true/false, yes/no, y/n, 1/0, on/off"
                )
            return bool_converter

        if type_obj is list:
            def list_converter(s: str) -> List[Any]:
                if s.startswith('[') and s.endswith(']'):
                    try:
                        result = json.loads(s)
                        if isinstance(result, list):
                            return result
                        self._logger.warning(f"JSON parsed but not a list: {s}")
                    except (json.JSONDecodeError, ValueError) as e:
                        self._logger.warning(f"Invalid JSON list format: {s}, error: {e}")
                        raise ValueError(f"Invalid JSON list format: {s}") from e

                if not s:
                    return []
                return [item.strip() for item in s.split(',') if item.strip()]
            return list_converter

        if type_obj is dict:
            def dict_converter(s: str) -> Dict[str, Any]:
                if s.startswith('{') and s.endswith('}'):
                    try:
                        result = json.loads(s)
                        if isinstance(result, dict):
                            return result
                        self._logger.warning(f"JSON parsed but not a dict: {s}")
                    except (json.JSONDecodeError, ValueError) as e:
                        self._logger.warning(f"Invalid JSON dict format: {s}, error: {e}")
                        raise ValueError(f"Invalid JSON dict format: {s}") from e

                result = {}
                if not s:
                    return result

                for pair in s.split(','):
                    pair = pair.strip()
                    if '=' in pair:
                        key, value = pair.split('=', 1)
                        result[key.strip()] = value.strip()
                    else:
                        self._logger.warning(f"Invalid key=value pair: {pair}")
                return result
            return dict_converter

        if type_obj is tuple:
            def tuple_converter(s: str) -> tuple:
                if s.startswith('[') and s.endswith(']'):
                    try:
                        result = json.loads(s)
                        if isinstance(result, list):
                            return tuple(result)
                        self._logger.warning(f"JSON parsed but not a list: {s}")
                        raise ValueError(f"Invalid JSON tuple format: {s}")
                    except (json.JSONDecodeError, ValueError) as e:
                        self._logger.warning(f"Invalid JSON tuple format: {s}, error: {e}")
                        raise ValueError(f"Invalid JSON tuple format: {s}") from e

                if not s:
                    return ()
                return tuple(item.strip() for item in s.split(',') if item.strip())
            return tuple_converter

        return type_obj

    def generate_help(self, command: str) -> str:
        """Generate detailed help text for command"""
        command_meta: Optional[Dict[str, Any]] = self._command_registry.get_command(command)
        if not command_meta:
            return f"Unknown command: {command}"

        parser: argparse.ArgumentParser = self._get_parser_for_command(command, command_meta)
        help_text: str = parser.format_help()

        has_default_true_flags = False
        for opt_meta in command_meta.get('options', []):
            if opt_meta.get('is_flag') and opt_meta.get('default') is True:
                has_default_true_flags = True
                break

        has_complex_types = False
        for opt_meta in command_meta.get('options', []):
            opt_type = opt_meta.get('type', str)
            if opt_type in (list, dict, tuple):
                has_complex_types = True
                break

        if has_default_true_flags or has_complex_types:
            help_text += "\nNotes:\n"

            if has_default_true_flags:
                help_text += "  • Flags marked as 'enabled by default' use --no-<name> to disable\n"

            if has_complex_types:
                help_text += "\nType Conversion:\n"
                help_text += "  list:  JSON: '[\"a\",\"b\"]' or CSV: 'a,b,c'\n"
                help_text += "  dict:  JSON: '{\"k\":\"v\"}' or key=value: 'k1=v1,k2=v2'\n"
                help_text += "  tuple: JSON: '[x,y]' (CSV not recommended)\n"
                help_text += "  bool:  true/false, yes/no, y/n, 1/0, on/off\n"

        examples: List[str] = command_meta.get('examples', [])
        if examples:
            help_text += "\nExamples:\n"
            for example in examples:
                help_text += f"  {example}\n"

        return help_text

    def clear_cache(self) -> None:
        """Clear parser cache"""
        self._parser_cache.clear()
        self._logger.debug("Parser cache cleared")

    def invalidate_command(self, command: str) -> None:
        """Invalidate cache for specific command"""
        if command in self._parser_cache:
            del self._parser_cache[command]
            self._logger.debug(f"Invalidated parser cache for command: {command}")
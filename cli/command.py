"""
Command registry and argument parsing.
"""

from __future__ import annotations

import argparse
import copy
import enum
import json
import logging
import threading
from collections import OrderedDict
from typing import Any, Callable, Type, get_args, get_origin
from typing import Union as _Union

from .interfaces import ArgumentParser, CommandRegistry, RESERVED_NAMES


class _TrieNode:
    """Single node in command trie."""

    def __init__(self) -> None:
        self.children: dict[str, _TrieNode] = {}
        self.is_end: bool = False
        self.command_name: str | None = None


class CommandTrie:
    """Trie for efficient command autocomplete."""

    def __init__(self) -> None:
        self.root: _TrieNode = _TrieNode()

    def insert(self, command: str) -> None:
        node: _TrieNode = self.root
        for char in command:
            node = node.children.setdefault(char, _TrieNode())
        node.is_end = True
        node.command_name = command

    def autocomplete(self, prefix: str) -> list[str]:
        node: _TrieNode = self.root
        for char in prefix:
            if char not in node.children:
                return []
            node = node.children[char]
        return self._collect_commands(node, prefix)

    def remove(self, command: str) -> bool:
        def _remove_helper(
            node: _TrieNode, cmd: str, depth: int
        ) -> tuple[bool, bool]:
            if depth == len(cmd):
                if not node.is_end:
                    return False, False
                node.is_end = False
                node.command_name = None
                return True, len(node.children) == 0

            char = cmd[depth]
            if char not in node.children:
                return False, False
            child = node.children[char]
            removed, should_delete = _remove_helper(child, cmd, depth + 1)
            if should_delete:
                del node.children[char]
                return removed, not node.is_end and len(node.children) == 0
            return removed, False

        removed, _ = _remove_helper(self.root, command, 0)
        return removed

    def _collect_commands(self, node: _TrieNode, prefix: str) -> list[str]:
        results: list[str] = []
        stack: list[tuple[_TrieNode, str]] = [(node, prefix)]
        while stack:
            current_node, current_prefix = stack.pop()
            if current_node.is_end and current_node.command_name:
                results.append(current_node.command_name)
            for char, child_node in current_node.children.items():
                stack.append((child_node, current_prefix + char))
        return sorted(results)


class CommandMeta:
    """Command metadata wrapper with shallow snapshot semantics."""

    def __init__(self, handler: Callable[..., Any], **metadata: Any) -> None:
        self._handler = handler
        self._metadata: dict[str, Any] = copy.deepcopy(metadata)
        self._metadata["handler"] = handler

    def get(self, key: str, default: Any = None) -> Any:
        return self._metadata.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        snapshot = dict(self._metadata)
        snapshot["arguments"] = [dict(a) for a in self._metadata.get("arguments", [])]
        snapshot["options"] = [dict(o) for o in self._metadata.get("options", [])]
        snapshot["aliases"] = list(self._metadata.get("aliases", []))
        snapshot["examples"] = list(self._metadata.get("examples", []))
        return snapshot

    @property
    def handler(self) -> Callable[..., Any]:
        return self._handler


class CommandRegistryImpl(CommandRegistry):
    """Thread-safe command registry with aliases and groups."""

    def __init__(self) -> None:
        self._commands: dict[str, CommandMeta] = {}
        self._aliases: dict[str, str] = {}
        self._groups: dict[str, dict[str, Any]] = {}
        self._trie: CommandTrie = CommandTrie()
        self._logger: logging.Logger = logging.getLogger(
            "cliframework.command_registry"
        )
        self._parser_cache_invalidator: Callable[[str], None] | None = None
        self._lock = threading.RLock()

    def register(
        self, name: str, handler: Callable[..., Any], **metadata: Any
    ) -> None:
        with self._lock:
            if metadata.get("is_group", False):
                self._groups[name] = copy.deepcopy(metadata)
                self._logger.info(f"Registered command group: {name}")
                return

            if name in self._commands:
                old_meta = self._commands[name]
                for alias in old_meta.get("aliases", []):
                    if (
                        alias in self._aliases
                        and self._aliases[alias] == name
                    ):
                        del self._aliases[alias]
                        self._trie.remove(alias)
                self._trie.remove(name)

            requested_aliases = list(metadata.get("aliases", []))
            registered_aliases: list[str] = []

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
                            f"reassigning to '{name}'"
                        )
                        self._trie.remove(alias)
                self._aliases[alias] = name
                self._trie.insert(alias)
                registered_aliases.append(alias)

            metadata_copy = copy.deepcopy(metadata)
            metadata_copy["aliases"] = registered_aliases

            self._commands[name] = CommandMeta(handler, **metadata_copy)
            self._trie.insert(name)
            self._logger.info(f"Registered command: {name}")

            if self._parser_cache_invalidator:
                self._parser_cache_invalidator(name)
                for alias in registered_aliases:
                    self._parser_cache_invalidator(alias)

    def get_command(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            real_name = self._aliases.get(name, name)
            cmd_meta = self._commands.get(real_name)
            return cmd_meta.to_dict() if cmd_meta else None

    def list_commands(self) -> list[str]:
        with self._lock:
            return sorted(self._commands.keys())

    def autocomplete(self, prefix: str) -> list[str]:
        with self._lock:
            return self._trie.autocomplete(prefix)

    def remove_command(self, name: str) -> bool:
        with self._lock:
            cmd_meta = self._commands.get(name)
            if cmd_meta is None:
                return False
            aliases = cmd_meta.get("aliases", [])
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

    def set_parser_cache_invalidator(
        self, invalidator: Callable[[str], None]
    ) -> None:
        self._parser_cache_invalidator = invalidator

    def get_all_groups(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._groups)

    def find_by_prefix(self, prefix: str) -> list[str]:
        with self._lock:
            prefix_with_dot = prefix + "."
            return sorted(
                name
                for name in self._commands
                if name.startswith(prefix_with_dot) or name == prefix
            )

    def get_subcommand_groups(self, prefix: str) -> dict[str, list[str]]:
        with self._lock:
            prefix_with_dot = prefix + "." if prefix else ""
            prefix_len = len(prefix_with_dot)
            groups: dict[str, list[str]] = {}
            for name in self._commands:
                if prefix and not name.startswith(prefix_with_dot):
                    continue
                if not prefix and "." not in name:
                    continue
                remainder = name[prefix_len:] if prefix else name
                immediate_child = (
                    remainder.split(".")[0] if "." in remainder else remainder
                )
                groups.setdefault(immediate_child, []).append(name)
            return {k: sorted(v) for k, v in sorted(groups.items())}


VALID_BASIC_TYPES: frozenset[Type[Any]] = frozenset({str, int, float, bool})


def validate_type(
    param_type: Any, strict: bool = False
) -> Type[Any] | Callable[[str], Any]:
    """Validate and normalize parameter type."""
    logger = logging.getLogger("cliframework.command")

    if param_type in VALID_BASIC_TYPES:
        return param_type

    if isinstance(param_type, type) and issubclass(param_type, enum.Enum):
        return param_type

    origin = get_origin(param_type)
    if origin is not None:
        if origin in (list, dict, tuple):
            return origin

        if origin is _Union:
            args = get_args(param_type)
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return validate_type(non_none[0], strict)
            if len(non_none) > 1:
                basic_types = [a for a in non_none if a in VALID_BASIC_TYPES]
                if len(basic_types) == len(non_none):
                    if strict:
                        raise ValueError(
                            f"Union of multiple types {param_type} is not supported"
                        )
                    logger.warning(
                        f"Union type {param_type} will use 'str' as fallback"
                    )
                    return str
                raise TypeError(
                    f"Complex Union type {param_type} is not supported"
                )

    if isinstance(param_type, type):
        return param_type

    if callable(param_type):
        return param_type

    if strict:
        raise ValueError(f"Unsupported parameter type {param_type}")
    logger.warning(
        f"Unsupported parameter type {param_type}, using 'str' as fallback"
    )
    return str


class _ArgparseError(Exception):
    """Raised when the embedded argparse parser fails."""


class _SilentArgumentParser(argparse.ArgumentParser):
    """argparse parser that raises instead of printing to stderr and exiting."""

    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgparseError(message)

    def exit(self, status: int = 0, message: str | None = None) -> None:  # type: ignore[override]
        raise _ArgparseError(message or f"argparse exit status={status}")


_TRUE_LITERALS = frozenset({"true", "t", "yes", "y", "1", "on"})
_FALSE_LITERALS = frozenset({"false", "f", "no", "n", "0", "off"})


class EnhancedArgumentParser(ArgumentParser):
    """Enhanced argument parser with caching and type validation."""

    def __init__(
        self,
        command_registry: CommandRegistry,
        max_cache_size: int = 128,
    ) -> None:
        self._command_registry: CommandRegistry = command_registry
        self._max_cache_size: int = max_cache_size
        self._parser_cache: OrderedDict[str, argparse.ArgumentParser] = (
            OrderedDict()
        )
        self._logger: logging.Logger = logging.getLogger(
            "cliframework.argument_parser"
        )

        if hasattr(command_registry, "set_parser_cache_invalidator"):
            command_registry.set_parser_cache_invalidator(
                self.invalidate_command
            )

    def parse(self, args: list[str]) -> dict[str, Any]:
        if not args:
            return {"command": None}

        command: str = args[0]
        remaining_args: list[str] = args[1:]
        result: dict[str, Any] = {"command": command}

        command_meta = self._command_registry.get_command(command)
        if not command_meta:
            return result

        parser = self._get_parser_for_command(command, command_meta)

        if any(a in ("-h", "--help") for a in remaining_args):
            result["_cli_show_help"] = True
            return result

        try:
            parsed_args = parser.parse_args(remaining_args)
        except _ArgparseError as exc:
            ns = self._partial_parse(parser, remaining_args)
            if ns is not None and getattr(ns, "_cli_help", False):
                result["_cli_show_help"] = True
                return result
            raise ValueError(
                f"Invalid arguments for command '{command}': {exc}.\n"
                f"Use '{command} --help' for detailed help."
            )

        if getattr(parsed_args, "_cli_help", False):
            result["_cli_show_help"] = True
            return result

        result.update(vars(parsed_args))
        result.pop("_cli_help", None)

        for opt_meta in command_meta.get("options", []):
            factory = opt_meta.get("default_factory")
            if factory is None:
                continue
            opt_name = opt_meta["name"]
            if result.get(opt_name) is None:
                try:
                    result[opt_name] = factory()
                except Exception as exc:
                    raise ValueError(
                        f"default_factory for option '--{opt_name}' raised: {exc}"
                    ) from exc

        return result

    def generate_help(self, command: str) -> str:
        command_meta = self._command_registry.get_command(command)
        if not command_meta:
            return f"Unknown command: {command}"

        parser = self._get_parser_for_command(command, command_meta)
        help_text = parser.format_help()

        notes: list[str] = []

        if any(
            o.get("is_flag") and o.get("default") is True
            for o in command_meta.get("options", [])
        ):
            notes.append(
                "  - Flags marked as 'enabled by default' use --no-<n> to disable"
            )

        if any(
            o.get("type") in (list, dict, tuple)
            for o in command_meta.get("options", [])
        ):
            notes.append("\nType Conversion:")
            notes.append("  list:  JSON: '[\"a\",\"b\"]' or CSV: 'a,b,c'")
            notes.append("  dict:  JSON: '{\"k\":\"v\"}' or key=value: 'k1=v1,k2=v2'")
            notes.append("  tuple: JSON: '[x,y]' (CSV not recommended)")
            notes.append("  bool:  true/false, t/f, yes/no, y/n, 1/0, on/off")

        enum_options = [
            o
            for o in command_meta.get("options", [])
            if isinstance(o.get("type"), type)
            and issubclass(o["type"], enum.Enum)
        ]
        if enum_options:
            notes.append("\nEnum Options:")
            for o in enum_options:
                values = ", ".join(m.name for m in o["type"])
                notes.append(f"  --{o['name']}: {values}")

        if notes:
            help_text += "\nNotes:\n" + "\n".join(notes) + "\n"

        examples = command_meta.get("examples", [])
        if examples:
            help_text += "\nExamples:\n"
            for ex in examples:
                help_text += f"  {ex}\n"

        return help_text

    def clear_cache(self) -> None:
        self._parser_cache.clear()
        self._logger.debug("Parser cache cleared")

    def invalidate_command(self, command: str) -> None:
        if command in self._parser_cache:
            del self._parser_cache[command]

    def _partial_parse(
        self,
        parser: argparse.ArgumentParser,
        remaining_args: list[str],
    ) -> argparse.Namespace | None:
        try:
            ns, _ = parser.parse_known_args(remaining_args)
            return ns
        except _ArgparseError:
            return None
        except SystemExit:
            return None

    def _get_parser_for_command(
        self,
        command: str,
        command_meta: dict[str, Any],
    ) -> argparse.ArgumentParser:
        if command in self._parser_cache:
            self._parser_cache.move_to_end(command)
            return self._parser_cache[command]

        parser = self._create_parser(command, command_meta)
        if len(self._parser_cache) >= self._max_cache_size:
            self._parser_cache.popitem(last=False)
        self._parser_cache[command] = parser
        return parser

    def _create_parser(
        self,
        command: str,
        command_meta: dict[str, Any],
    ) -> argparse.ArgumentParser:
        parser = _SilentArgumentParser(
            prog=command,
            description=command_meta.get("help", ""),
            add_help=False,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )

        parser.add_argument(
            "--help",
            "-h",
            action="store_true",
            dest="_cli_help",
            help="Show this help message",
        )

        arguments = command_meta.get("arguments", [])
        optional_count = sum(1 for a in arguments if a.get("optional"))
        if optional_count > 1:
            raise ValueError(
                f"Command '{command}' has {optional_count} optional positional "
                f"arguments. Only one is allowed at the end"
            )

        found_optional = False
        for i, arg_meta in enumerate(arguments):
            is_optional = arg_meta.get("optional", False)
            if found_optional and not is_optional:
                raise ValueError(
                    f"Command '{command}': Optional positional '{arguments[i - 1]['name']}' "
                    f"must come after all required arguments"
                )
            if is_optional:
                found_optional = True

        named_arg_groups: dict[str, Any] = {}
        for arg_meta in arguments:
            arg_name: str = arg_meta["name"]
            if arg_name in RESERVED_NAMES:
                raise ValueError(
                    f"Argument name '{arg_name}' conflicts with reserved name"
                )

            arg_type = validate_type(arg_meta.get("type", str))
            kwargs: dict[str, Any] = {
                "type": self._get_type_converter(arg_type),
                "help": arg_meta.get("help", ""),
            }
            if arg_meta.get("optional"):
                kwargs["nargs"] = "?"

            group_name = arg_meta.get("group")
            target = parser
            if group_name:
                if group_name not in named_arg_groups:
                    named_arg_groups[group_name] = parser.add_argument_group(
                        group_name
                    )
                target = named_arg_groups[group_name]
            target.add_argument(arg_name, **kwargs)

        named_opt_groups: dict[str, Any] = {}
        exclusive_groups: dict[str, Any] = {}
        for opt_meta in command_meta.get("options", []):
            self._add_option(
                parser,
                command,
                opt_meta,
                named_opt_groups,
                exclusive_groups,
            )

        return parser

    def _add_option(
        self,
        parser: argparse.ArgumentParser,
        command: str,
        opt_meta: dict[str, Any],
        named_opt_groups: dict[str, Any] | None = None,
        exclusive_groups: dict[str, Any] | None = None,
    ) -> None:
        opt_name: str = opt_meta["name"]
        opt_short: str | None = opt_meta.get("short")

        if opt_name in RESERVED_NAMES or (
            opt_short and opt_short in RESERVED_NAMES
        ):
            raise ValueError(
                f"Option '--{opt_name}' or '-{opt_short}' conflicts with reserved name"
            )

        opt_type = validate_type(opt_meta.get("type", str))
        opt_default: Any = opt_meta.get("default")
        opt_default_factory = opt_meta.get("default_factory")
        opt_is_flag: bool = bool(opt_meta.get("is_flag", False))
        opt_help: str = opt_meta.get("help", "")
        opt_group_name: str | None = opt_meta.get("group")
        opt_exclusive: str | None = opt_meta.get("exclusive_group")

        target = parser
        if opt_group_name and named_opt_groups is not None:
            if opt_group_name not in named_opt_groups:
                named_opt_groups[opt_group_name] = parser.add_argument_group(
                    opt_group_name
                )
            target = named_opt_groups[opt_group_name]

        if opt_exclusive and exclusive_groups is not None:
            if opt_exclusive not in exclusive_groups:
                exclusive_groups[opt_exclusive] = (
                    target.add_mutually_exclusive_group()
                )
            target = exclusive_groups[opt_exclusive]

        names: list[str] = [f"--{opt_name}"]
        if opt_short:
            names.append(f"-{opt_short}")

        if opt_type is bool and not opt_is_flag:
            opt_is_flag = True

        if opt_is_flag:
            if opt_default is True:
                no_names = [f"--no-{opt_name}"]
                help_text = (
                    f"{opt_help} (enabled by default, use --no-{opt_name} to disable)"
                    if opt_help.strip()
                    else f"Disable {opt_name} (enabled by default)"
                )
                target.add_argument(
                    *no_names,
                    action="store_false",
                    dest=opt_name,
                    default=True,
                    help=help_text,
                )
            else:
                help_text = (
                    f"{opt_help} (disabled by default)"
                    if opt_help.strip()
                    else f"Enable {opt_name}"
                )
                target.add_argument(
                    *names,
                    action="store_true",
                    dest=opt_name,
                    default=False,
                    help=help_text,
                )
            return

        type_converter = self._get_type_converter(opt_type)
        enhanced_help = opt_help
        if opt_type in (list, dict, tuple):
            examples = self._get_type_examples(opt_type)
            if examples and opt_help:
                enhanced_help = f"{opt_help} {examples}"
            elif examples:
                enhanced_help = f"Value for {opt_name} {examples}"
        elif isinstance(opt_type, type) and issubclass(opt_type, enum.Enum):
            values = ", ".join(m.name for m in opt_type)
            enhanced_help = (
                f"{opt_help} (choices: {values})"
                if opt_help
                else f"Choices: {values}"
            )

        target.add_argument(
            *names,
            type=type_converter,
            default=opt_default,
            help=enhanced_help or opt_help,
        )

    def _get_type_examples(self, type_obj: Type[Any]) -> str:
        if type_obj is list:
            return '(e.g., "a,b,c" or \'["a","b","c"]\')'
        if type_obj is dict:
            return '(e.g., \'{"key":"val"}\' or "k1=v1,k2=v2")'
        if type_obj is tuple:
            return "(e.g., '[1,2,3]' for JSON)"
        return ""

    def _get_type_converter(
        self, type_obj: Type[Any]
    ) -> Callable[[str], Any]:
        if isinstance(type_obj, type) and issubclass(type_obj, enum.Enum):
            return self._make_enum_converter(type_obj)

        if callable(type_obj) and not isinstance(type_obj, type):
            return type_obj

        if type_obj is bool:
            return self._bool_converter
        if type_obj is list:
            return self._list_converter
        if type_obj is dict:
            return self._dict_converter
        if type_obj is tuple:
            return self._tuple_converter

        return type_obj

    @staticmethod
    def _make_enum_converter(
        enum_cls: Type[enum.Enum],
    ) -> Callable[[str], enum.Enum]:
        members_by_name = {m.name.lower(): m for m in enum_cls}
        members_by_value = {str(m.value).lower(): m for m in enum_cls}

        def convert(raw: str) -> enum.Enum:
            key = raw.strip().lower()
            if key in members_by_name:
                return members_by_name[key]
            if key in members_by_value:
                return members_by_value[key]
            valid = ", ".join(m.name for m in enum_cls)
            raise ValueError(
                f"Invalid value '{raw}' for {enum_cls.__name__}. "
                f"Valid values: {valid}"
            )

        return convert

    @staticmethod
    def _bool_converter(raw: str) -> bool:
        v = raw.strip().lower()
        if v in _TRUE_LITERALS:
            return True
        if v in _FALSE_LITERALS:
            return False
        raise ValueError(
            f"Invalid boolean value: '{raw}'. "
            f"Valid values: true/false, t/f, yes/no, y/n, 1/0, on/off"
        )

    def _list_converter(self, raw: str) -> list[Any]:
        if raw.startswith("[") and raw.endswith("]"):
            try:
                result = json.loads(raw)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"Invalid JSON list format: {raw}") from exc
            if isinstance(result, list):
                return result
            raise ValueError(f"JSON parsed but not a list: {raw}")
        if not raw:
            return []
        return [item.strip() for item in raw.split(",") if item.strip()]

    def _dict_converter(self, raw: str) -> dict[str, Any]:
        if raw.startswith("{") and raw.endswith("}"):
            try:
                result = json.loads(raw)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"Invalid JSON dict format: {raw}") from exc
            if isinstance(result, dict):
                return result
            raise ValueError(f"JSON parsed but not a dict: {raw}")
        result: dict[str, Any] = {}
        if not raw:
            return result
        for pair in raw.split(","):
            pair = pair.strip()
            if "=" in pair:
                key, value = pair.split("=", 1)
                result[key.strip()] = value.strip()
            else:
                self._logger.warning(f"Invalid key=value pair: {pair}")
        return result

    def _tuple_converter(self, raw: str) -> tuple:
        if raw.startswith("[") and raw.endswith("]"):
            try:
                result = json.loads(raw)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"Invalid JSON tuple format: {raw}") from exc
            if isinstance(result, list):
                return tuple(result)
            raise ValueError(f"JSON parsed but not a list: {raw}")
        if not raw:
            return ()
        return tuple(item.strip() for item in raw.split(",") if item.strip())


__all__ = [
    "CommandRegistryImpl",
    "EnhancedArgumentParser",
    "CommandTrie",
    "CommandMeta",
    "validate_type",
    "VALID_BASIC_TYPES",
]
"""
Localized message management for CLI applications.

Uses a restricted str.Formatter that rejects attribute access and indexing
in field names to prevent format-string attacks via config-injected templates.
"""

from __future__ import annotations

import hashlib
import json
import logging
import string
import threading
from collections import OrderedDict
from typing import Any

from .interfaces import ConfigProvider, MessageProvider


class MessageError(Exception):
    """Base exception for message-related errors."""


class _SafeFormatter(string.Formatter):
    """Formatter rejecting attribute access and indexing in field names."""

    def get_field(
        self, field_name: str, args: tuple, kwargs: dict[str, Any]
    ) -> tuple[Any, Any]:
        if "." in field_name or "[" in field_name:
            raise MessageError(
                f"Attribute access or indexing not allowed in message templates: "
                f"'{field_name}'"
            )
        return super().get_field(field_name, args, kwargs)


_safe_formatter = _SafeFormatter()


class ConfigBasedMessageProvider(MessageProvider):
    """Configuration-based message provider with LRU caching and warn-once."""

    def __init__(
        self,
        config: ConfigProvider,
        default_language: str = "en",
        cache_size: int = 100,
    ) -> None:
        if cache_size < 1:
            raise ValueError(f"cache_size must be >= 1, got {cache_size}")

        self._config: ConfigProvider = config
        self._logger: logging.Logger = logging.getLogger(
            "cliframework.messages"
        )
        self._cache_size: int = cache_size
        self._message_cache: OrderedDict[str, str] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._warned_keys: set[str] = set()

        self._default_language: str = config.get(
            "default_language", default_language
        )
        self._current_language: str = config.get(
            "current_language", self._default_language
        )

        config_langs: list[Any] = config.get("languages", []) or []
        self._available_languages: set[str] = (
            set(config_langs) if config_langs else {self._default_language}
        )
        self._available_languages.add(self._default_language)
        self._available_languages.add(self._current_language)

        if set(config_langs) != self._available_languages:
            try:
                config.set("languages", sorted(self._available_languages))
            except Exception as exc:
                self._logger.debug(
                    f"Could not persist available_languages sync: {exc}"
                )

    def get_message(
        self,
        key: str,
        default: str | None = None,
        **kwargs: Any,
    ) -> str:
        with self._state_lock:
            current_language = self._current_language

        cache_key = self._cache_key(current_language, key, default, kwargs)

        with self._cache_lock:
            if cache_key in self._message_cache:
                self._message_cache.move_to_end(cache_key)
                return self._message_cache[cache_key]

        message: str | None = self._config.get(
            f"messages.{current_language}.{key}"
        )
        if message is None and current_language != self._default_language:
            message = self._config.get(
                f"messages.{self._default_language}.{key}"
            )

        if message is None:
            message = default if default is not None else key
            # A caller-supplied default is an intentional fallback; only a
            # key with nothing to fall back on is worth a warning.
            with self._state_lock:
                if default is None and key not in self._warned_keys:
                    self._warned_keys.add(key)
                    self._logger.warning(
                        f"Message '{key}' not found in any language; "
                        f"using fallback. Further occurrences silenced."
                    )

        if kwargs:
            try:
                message = _safe_formatter.format(message, **kwargs)
            except MessageError as exc:
                self._logger.error(
                    f"Unsafe template for message '{key}': {exc}"
                )
            except KeyError as exc:
                self._logger.warning(
                    f"Missing parameter {exc} for message '{key}'"
                )
            except Exception as exc:
                self._logger.error(
                    f"Error formatting message '{key}': {exc}"
                )

        with self._cache_lock:
            if len(self._message_cache) >= self._cache_size:
                self._message_cache.popitem(last=False)
            self._message_cache[cache_key] = message

        return message

    def set_language(self, language: str) -> None:
        with self._state_lock:
            if language not in self._available_languages:
                available_str = ", ".join(sorted(self._available_languages))
                raise MessageError(
                    f"Language '{language}' not available. "
                    f"Available languages: {available_str}"
                )
            self._current_language = language
            self._config.set("current_language", language)
            with self._cache_lock:
                self._message_cache.clear()

        try:
            self._config.save()
        except Exception as exc:
            self._logger.error(f"Failed to save language change: {exc}")

        self._logger.info(f"Language set to '{language}'")

    def get_current_language(self) -> str:
        with self._state_lock:
            return self._current_language

    def get_available_languages(self) -> set[str]:
        with self._state_lock:
            return set(self._available_languages)

    def add_language(
        self, language: str, messages: dict[str, str]
    ) -> None:
        with self._state_lock:
            try:
                existing_messages: dict[str, str] = (
                    self._config.get(f"messages.{language}", {}) or {}
                )
                existing_messages.update(messages)
                self._config.set(f"messages.{language}", existing_messages)
                self._available_languages.add(language)
                self._config.set(
                    "languages", sorted(self._available_languages)
                )
                with self._cache_lock:
                    self._message_cache.clear()
            except Exception as exc:
                self._logger.error(
                    f"Error adding language '{language}': {exc}"
                )
                raise MessageError(
                    f"Failed to add language '{language}': {exc}"
                )

        try:
            self._config.save()
        except Exception as exc:
            self._logger.error(f"Failed to persist add_language: {exc}")

        self._logger.info(
            f"Added/updated language '{language}' with {len(messages)} messages"
        )

    def remove_language(self, language: str, purge: bool = False) -> None:
        with self._state_lock:
            if language == self._default_language:
                raise MessageError(
                    f"Cannot remove default language '{language}'"
                )
            if language == self._current_language:
                raise MessageError(
                    f"Cannot remove currently active language '{language}'"
                )
            if language not in self._available_languages:
                raise MessageError(f"Language '{language}' not found")

            try:
                self._available_languages.discard(language)
                self._config.set(
                    "languages", sorted(self._available_languages)
                )
                if purge:
                    self._config.delete(f"messages.{language}")
                with self._cache_lock:
                    self._message_cache.clear()
            except Exception as exc:
                self._logger.error(
                    f"Error removing language '{language}': {exc}"
                )
                raise MessageError(
                    f"Failed to remove language '{language}': {exc}"
                )

        try:
            self._config.save()
        except Exception as exc:
            self._logger.error(f"Failed to persist remove_language: {exc}")

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._message_cache.clear()

    @staticmethod
    def _cache_key(
        language: str,
        key: str,
        default: str | None,
        kwargs: dict[str, Any],
    ) -> str:
        parts = [language, key]
        if default is not None:
            parts.append(
                hashlib.blake2b(
                    default.encode("utf-8"), digest_size=4
                ).hexdigest()
            )
        if kwargs:
            sorted_items = sorted(kwargs.items())
            params_repr = []
            for k, v in sorted_items:
                params_repr.append(
                    f"{k}:{ConfigBasedMessageProvider._canonicalize(v)}"
                )
            params_str = "|".join(params_repr)
            parts.append(
                hashlib.blake2b(
                    params_str.encode("utf-8"), digest_size=8
                ).hexdigest()
            )
        return ":".join(parts)

    @staticmethod
    def _canonicalize(value: Any) -> str:
        if isinstance(value, (str, int, float, bool, type(None))):
            return str(value)
        try:
            if isinstance(value, (list, tuple)):
                return json.dumps(
                    list(value), sort_keys=True, ensure_ascii=False
                )
            if isinstance(value, dict):
                return json.dumps(value, sort_keys=True, ensure_ascii=False)
            return str(value)
        except (TypeError, ValueError):
            return str(value)


BUILTIN_MESSAGES: dict[str, str] = {
    # dispatch (prompt / welcome / app_quit carry the app name and live
    # in the app config, see CLI._build_default_config)
    "unknown_command": "Unknown command. Type 'help' for available commands.",
    "available_commands": "Available commands:",
    "command_not_found": "Command '{command}' not found.",
    "execution_error": "Error executing command: {error}",
    "did_you_mean": "Did you mean: {suggestions}?",
    # command list (`help`)
    "help_no_description": "No description",
    "help_list_usage": "Usage:",
    "help_list_aliases": "aliases",
    "help_commands_under": "Commands under '{prefix}':",
    "help_detail_hint": "Use 'help <command>' for detailed help on a specific command.",
    "help_command_groups": "Command groups:",
    "help_group_line": "({count} commands) - use 'help {prefix}' for details",
    # per-command help
    "help_usage": "usage: ",
    "help_positionals": "positional arguments",
    "help_options": "options",
    "help_show_help": "Show this help message",
    "help_flag_on": "{help} (enabled by default, use --no-{name} to disable)",
    "help_flag_on_bare": "Disable {name} (enabled by default)",
    "help_flag_off": "{help} (disabled by default)",
    "help_flag_off_bare": "Enable {name}",
    "help_value_for": "Value for {name} {examples}",
    "help_choices": "{help} (choices: {values})",
    "help_choices_bare": "Choices: {values}",
    "help_notes": "Notes:",
    "help_note_no_flags": "Flags marked as 'enabled by default' use --no-<name> to disable",
    "help_type_conversion": "Type Conversion:",
    "help_enum_options": "Enum Options:",
    "help_examples": "Examples:",
    "unknown_command_help": "Unknown command: {command}",
    "invalid_arguments": (
        "Invalid arguments for command '{command}': {error}.\n"
        "Use '{command} --help' for detailed help."
    ),
    # built-in commands
    "cmd_help": "Show help information",
    "cmd_help_arg": "Command to show help for",
    "cmd_version": "Show application version",
    "cmd_version_line": "{name} version {version}",
    "cmd_exit": "Exit the application",
}

BUILTIN_MESSAGES_RU: dict[str, str] = {
    "unknown_command": "Неизвестная команда. Введите 'help', чтобы увидеть команды.",
    "available_commands": "Команды:",
    "command_not_found": "Команда '{command}' не найдена.",
    "execution_error": "Ошибка выполнения команды: {error}",
    "did_you_mean": "Возможно, вы имели в виду: {suggestions}?",
    "help_no_description": "Без описания",
    "help_list_usage": "Вызов:",
    "help_list_aliases": "синонимы",
    "help_commands_under": "Команды группы '{prefix}':",
    "help_detail_hint": "Подробнее о команде: help <команда>.",
    "help_command_groups": "Группы команд:",
    "help_group_line": "(команд: {count}) — подробнее: help {prefix}",
    "help_usage": "вызов: ",
    "help_positionals": "аргументы",
    "help_options": "опции",
    "help_show_help": "Показать эту справку",
    "help_flag_on": "{help} (включено по умолчанию, выключить: --no-{name})",
    "help_flag_on_bare": "Выключить {name} (включено по умолчанию)",
    "help_flag_off": "{help}",
    "help_flag_off_bare": "Включить {name}",
    "help_value_for": "Значение {name} {examples}",
    "help_choices": "{help} (варианты: {values})",
    "help_choices_bare": "Варианты: {values}",
    "help_notes": "Примечания:",
    "help_note_no_flags": "Флаги, включённые по умолчанию, выключаются через --no-<имя>",
    "help_type_conversion": "Форматы значений:",
    "help_enum_options": "Допустимые значения:",
    "help_examples": "Примеры:",
    "unknown_command_help": "Неизвестная команда: {command}",
    "invalid_arguments": (
        "Неверные аргументы команды '{command}': {error}.\n"
        "Справка: {command} --help"
    ),
    "cmd_help": "Показать справку",
    "cmd_help_arg": "Команда, по которой нужна справка",
    "cmd_version": "Показать версию",
    "cmd_version_line": "{name} версии {version}",
    "cmd_exit": "Выйти",
}

BUILTIN_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": BUILTIN_MESSAGES,
    "ru": BUILTIN_MESSAGES_RU,
}


def builtin_message(
    provider: MessageProvider | None, key: str, **kwargs: Any
) -> str:
    """Text of a framework string: the provider's translation if it has one,
    else the built-in English default from ``BUILTIN_MESSAGES``."""
    default = BUILTIN_MESSAGES[key]
    if provider is not None:
        return provider.get_message(key, default=default, **kwargs)
    try:
        return _safe_formatter.format(default, **kwargs)
    except (KeyError, MessageError):
        return default


__all__ = [
    "MessageError",
    "ConfigBasedMessageProvider",
    "BUILTIN_MESSAGES",
    "BUILTIN_MESSAGES_RU",
    "BUILTIN_TRANSLATIONS",
    "builtin_message",
]

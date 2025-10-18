"""
Localized message management for CLI applications

Provides multi-language support with message caching and parameter formatting.
"""

import json
import logging
import threading
import hashlib
from typing import Any, Dict, Optional, Set, List
from collections import OrderedDict
from .interfaces import MessageProvider, ConfigProvider


class MessageError(Exception):
    """Base exception for message-related errors"""
    pass


class ConfigBasedMessageProvider(MessageProvider):
    """Configuration-based message provider with LRU caching"""

    def __init__(self,
                 config: ConfigProvider,
                 default_language: str = 'en',
                 cache_size: int = 100):
        """Initialize message provider"""
        if cache_size < 1:
            raise ValueError(f"cache_size must be >= 1, got {cache_size}")

        self._config: ConfigProvider = config
        self._logger: logging.Logger = logging.getLogger('cliframework.messages')
        self._cache_size: int = cache_size
        self._message_cache: OrderedDict[str, str] = OrderedDict()
        self._cache_lock = threading.Lock()
        self._config_lock = threading.Lock()

        self._default_language: str = config.get('default_language', default_language)
        self._current_language: str = config.get('current_language', self._default_language)

        config_langs: List = config.get('languages', [])
        self._available_languages: Set[str] = set(config_langs) if config_langs else {self._default_language}

        self._available_languages.add(self._default_language)
        self._available_languages.add(self._current_language)

        self._logger.debug(
            f"MessageProvider initialized: current={self._current_language}, "
            f"default={self._default_language}, "
            f"available={self._available_languages}"
        )

    @staticmethod
    def _canonicalize_value(value: Any) -> str:
        """Convert value to stable string representation"""
        if isinstance(value, (str, int, float, bool, type(None))):
            return str(value)

        try:
            if isinstance(value, (list, tuple)):
                return json.dumps(list(value), sort_keys=True, ensure_ascii=False)
            if isinstance(value, dict):
                return json.dumps(value, sort_keys=True, ensure_ascii=False)
            return str(value)
        except (TypeError, ValueError):
            return str(value)

    def get_message(self,
                    key: str,
                    default: Optional[str] = None,
                    **kwargs: Any) -> str:
        """Get localized message with parameter substitution"""
        cache_key_parts = [self._current_language, key]

        if default is not None:
            default_hash = hashlib.sha256(default.encode('utf-8')).hexdigest()[:8]
            cache_key_parts.append(default_hash)

        if kwargs:
            sorted_kwargs = sorted(kwargs.items())
            params_repr = []
            for k, v in sorted_kwargs:
                canonical = self._canonicalize_value(v)
                params_repr.append(f"{k}:{canonical}")
            params_str = '|'.join(params_repr)
            params_hash = hashlib.sha256(params_str.encode('utf-8')).hexdigest()[:16]
            cache_key_parts.append(params_hash)

        cache_key = ':'.join(cache_key_parts)

        with self._cache_lock:
            if cache_key in self._message_cache:
                self._message_cache.move_to_end(cache_key)
                return self._message_cache[cache_key]

        message: Optional[str] = self._config.get(
            f'messages.{self._current_language}.{key}'
        )

        if message is None and self._current_language != self._default_language:
            message = self._config.get(
                f'messages.{self._default_language}.{key}'
            )

            if message:
                self._logger.debug(
                    f"Message '{key}' not found in '{self._current_language}', "
                    f"using '{self._default_language}'"
                )

        if message is None:
            message = default if default is not None else key
            self._logger.warning(
                f"Message '{key}' not found in any language, "
                f"using fallback: {message}"
            )

        if kwargs:
            try:
                message = message.format(**kwargs)
            except KeyError as e:
                self._logger.warning(
                    f"Missing parameter {e} for message '{key}', "
                    f"using unformatted message"
                )
            except Exception as e:
                self._logger.error(
                    f"Error formatting message '{key}': {e}, "
                    f"using unformatted message"
                )

        with self._cache_lock:
            if len(self._message_cache) >= self._cache_size:
                self._message_cache.popitem(last=False)
            self._message_cache[cache_key] = message

        return message

    def set_language(self, language: str) -> None:
        """Set current language for messages"""
        with self._config_lock:
            if language not in self._available_languages:
                available_str = ', '.join(sorted(self._available_languages))
                raise MessageError(
                    f"Language '{language}' not available. "
                    f"Available languages: {available_str}"
                )

            self._current_language = language
            self._config.set('current_language', language)

            try:
                self._config.save()
            except Exception as e:
                self._logger.error(f"Failed to save language change: {e}")

            with self._cache_lock:
                self._message_cache.clear()

            self._logger.info(f"Language set to '{language}'")

    def get_current_language(self) -> str:
        """Get current language code"""
        return self._current_language

    def get_available_languages(self) -> Set[str]:
        """Get set of available language codes"""
        return self._available_languages.copy()

    def add_language(self,
                     language: str,
                     messages: Dict[str, str]) -> None:
        """Add new language with messages"""
        with self._config_lock:
            try:
                existing_messages: Dict[str, str] = self._config.get(
                    f'messages.{language}',
                    {}
                )

                existing_messages.update(messages)
                self._config.set(f'messages.{language}', existing_messages)

                self._available_languages.add(language)
                self._config.set('languages', sorted(self._available_languages))

                self._config.save()

                with self._cache_lock:
                    self._message_cache.clear()

                self._logger.info(
                    f"Added/updated language '{language}' with {len(messages)} messages"
                )

            except Exception as e:
                self._logger.error(f"Error adding language '{language}': {e}")
                raise MessageError(f"Failed to add language '{language}': {e}")

    def remove_language(self, language: str, purge: bool = False) -> None:
        """
        Remove language and optionally purge its messages

        Args:
            language: Language code to remove
            purge: If True, delete messages from config; if False, only remove from available list
        """
        with self._config_lock:
            if language == self._default_language:
                raise MessageError(
                    f"Cannot remove default language '{language}'"
                )

            if language == self._current_language:
                raise MessageError(
                    f"Cannot remove currently active language '{language}'. "
                    f"Switch to another language first."
                )

            if language not in self._available_languages:
                raise MessageError(
                    f"Language '{language}' not found"
                )

            try:
                self._available_languages.discard(language)
                self._config.set('languages', sorted(self._available_languages))

                if purge:
                    all_config = self._config.get_all()
                    if 'messages' in all_config and language in all_config['messages']:
                        messages_dict = dict(all_config['messages'])
                        del messages_dict[language]
                        self._config.set('messages', messages_dict)
                        self._logger.info(f"Purged all messages for language '{language}'")

                self._config.save()

                with self._cache_lock:
                    self._message_cache.clear()

                action = "removed and purged" if purge else "removed from available languages"
                self._logger.info(f"Language '{language}' {action}")

            except Exception as e:
                self._logger.error(f"Error removing language '{language}': {e}")
                raise MessageError(f"Failed to remove language '{language}': {e}")

    def clear_cache(self) -> None:
        """Clear message cache"""
        with self._cache_lock:
            self._message_cache.clear()
            self._logger.debug("Message cache cleared")
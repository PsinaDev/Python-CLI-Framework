"""
Terminal output formatting with ANSI colors and styles.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import platform
import re
import shutil
import sys
import textwrap
import threading
import time
from typing import Any, Callable, TextIO

from .interfaces import OutputFormatter


class OutputError(Exception):
    """Output formatting error."""


_ANSI_REGEX: re.Pattern[str] = re.compile(
    r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\][0-9;]*(?:\x07|\x1b\\))"
)

_ANSI_PREFIX_REGEX: re.Pattern[str] = re.compile(r"^(\033\[[0-9;]+m)+")

_COLORAMA_INIT_LOCK = threading.Lock()
_COLORAMA_INITIALIZED = False


def _ensure_colorama_initialized() -> None:
    """Lazily initialize colorama on Windows; safe to call repeatedly."""
    global _COLORAMA_INITIALIZED
    if _COLORAMA_INITIALIZED or platform.system() != "Windows":
        return
    with _COLORAMA_INIT_LOCK:
        if _COLORAMA_INITIALIZED:
            return
        try:
            import colorama

            colorama.just_fix_windows_console()
        except (ImportError, Exception):
            pass
        _COLORAMA_INITIALIZED = True


COLORS: dict[str, str] = {
    "reset": "\033[0m",
    "black": "\033[30m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
    "bright_black": "\033[90m",
    "bright_red": "\033[91m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
    "bright_blue": "\033[94m",
    "bright_magenta": "\033[95m",
    "bright_cyan": "\033[96m",
    "bright_white": "\033[97m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "italic": "\033[3m",
    "underline": "\033[4m",
    "blink": "\033[5m",
    "reverse": "\033[7m",
    "hidden": "\033[8m",
    "strikethrough": "\033[9m",
}

STYLES: dict[str, str] = {
    "success": COLORS["green"],
    "error": COLORS["red"],
    "warning": COLORS["yellow"],
    "info": COLORS["blue"],
    "header": COLORS["bold"] + COLORS["bright_white"],
    "debug": COLORS["bright_black"],
    "emphasis": COLORS["bold"],
    "code": COLORS["bright_black"],
    "highlight": COLORS["reverse"],
}

_BG_COLOR_MAP: dict[str, str] = {
    "black": "\033[40m",
    "red": "\033[41m",
    "green": "\033[42m",
    "yellow": "\033[43m",
    "blue": "\033[44m",
    "magenta": "\033[45m",
    "cyan": "\033[46m",
    "white": "\033[47m",
    "bright_black": "\033[100m",
    "bright_red": "\033[101m",
    "bright_green": "\033[102m",
    "bright_yellow": "\033[103m",
    "bright_blue": "\033[104m",
    "bright_magenta": "\033[105m",
    "bright_cyan": "\033[106m",
    "bright_white": "\033[107m",
}

_KNOWN_TERMS: frozenset[str] = frozenset(
    {
        "xterm",
        "xterm-color",
        "xterm-256color",
        "linux",
        "screen",
        "screen-256color",
        "vt100",
        "rxvt",
        "cygwin",
        "tmux",
        "tmux-256color",
        "alacritty",
        "kitty",
        "wezterm",
        "ansi",
    }
)


def _enable_windows_vt_mode_for_handle(win_handle_const: int) -> bool:
    if platform.system() != "Windows":
        return True
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(win_handle_const)
        if handle in (-1, 0, None):
            return False
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def _enable_windows_vt_mode() -> bool:
    if platform.system() != "Windows":
        return True
    try:
        ok_out = _enable_windows_vt_mode_for_handle(-11)
        ok_err = _enable_windows_vt_mode_for_handle(-12)
        return ok_out or ok_err
    except Exception:
        return False


def _supports_color() -> bool:
    if "NO_COLOR" in os.environ:
        return False
    if os.environ.get("FORCE_COLOR") or os.environ.get("CLICOLOR_FORCE") == "1":
        return True
    if os.environ.get("PYCHARM_HOSTED") == "1":
        return True

    plat = platform.system()
    if plat == "Windows":
        win_term = bool(
            os.environ.get("WT_SESSION")
            or os.environ.get("TERM_PROGRAM") == "vscode"
            or os.environ.get("ConEmuANSI") == "ON"
            or "ANSICON" in os.environ
        )
        if win_term:
            return True
        return _enable_windows_vt_mode()

    term = (os.environ.get("TERM") or "").lower()
    if term in _KNOWN_TERMS:
        return True
    if term == "dumb":
        return False
    if (
        os.environ.get("CI") == "true"
        or os.environ.get("GITHUB_ACTIONS") == "true"
    ):
        return True
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _supports_ansi_sequences(file: TextIO = sys.stdout) -> bool:
    if platform.system() == "Windows":
        return _enable_windows_vt_mode()
    return hasattr(file, "isatty") and file.isatty()


def _strip_ansi(text: str) -> str:
    return _ANSI_REGEX.sub("", text)


class TerminalOutputFormatter(OutputFormatter):
    """Terminal output formatter with ANSI color support."""

    def __init__(self, use_colors: bool | None = None) -> None:
        _ensure_colorama_initialized()
        if use_colors is None:
            use_colors = _supports_color()
        self.use_colors: bool = use_colors
        self._logger: logging.Logger = logging.getLogger("cliframework.output")
        self._update_terminal_size()

    def format(self, text: str, style: str | None = None) -> str:
        if not self.use_colors or not style:
            return text
        style_code = STYLES.get(style, COLORS.get(style, ""))
        if not style_code:
            self._logger.warning(f"Unknown style: {style}")
            return text
        return f"{style_code}{text}{COLORS['reset']}"

    def style_text(
        self,
        text: str,
        fg: str | None = None,
        bg: str | None = None,
        bold: bool = False,
        underline: bool = False,
        blink: bool = False,
    ) -> str:
        if not self.use_colors:
            return text
        codes: list[str] = []
        if fg:
            code = STYLES.get(fg) or COLORS.get(fg)
            if code:
                codes.append(code)
        if bg and bg in _BG_COLOR_MAP:
            codes.append(_BG_COLOR_MAP[bg])
        if bold:
            codes.append(COLORS["bold"])
        if underline:
            codes.append(COLORS["underline"])
        if blink:
            codes.append(COLORS["blink"])
        if not codes:
            return text
        return f"{''.join(codes)}{text}{COLORS['reset']}"

    def render_table(
        self,
        headers: list[str],
        rows: list[list[str]],
        max_col_width: int | None = None,
        file: TextIO = sys.stdout,
        output_format: str = "text",
    ) -> None:
        if output_format == "json":
            self._render_table_json(headers, rows, file)
            return
        if output_format == "csv":
            self._render_table_csv(headers, rows, file)
            return
        if output_format != "text":
            raise OutputError(
                f"Unknown output_format '{output_format}' "
                f"(supported: text, json, csv)"
            )

        if not headers:
            return

        num_cols = len(headers)
        separator_overhead = 3 * num_cols + 1
        available_width = self.terminal_width - separator_overhead

        if max_col_width is None:
            max_col_width = max(20, available_width // num_cols)

        col_widths: list[int] = [
            min(len(_strip_ansi(h)), max_col_width) for h in headers
        ]

        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    clean_cell = _strip_ansi(str(cell))
                    col_widths[i] = min(
                        max(col_widths[i], len(clean_cell)),
                        max_col_width,
                    )

        separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"

        print(separator, file=file)

        header_cells = [
            self._pad_cell(h, col_widths[i], truncate=True)
            for i, h in enumerate(headers)
            if i < len(col_widths)
        ]
        print(
            self.format("| " + " | ".join(header_cells) + " |", "header"),
            file=file,
        )
        print(separator, file=file)

        for row in rows:
            cells = [
                self._pad_cell(str(cell), col_widths[i], truncate=True)
                for i, cell in enumerate(row)
                if i < len(col_widths)
            ]
            print("| " + " | ".join(cells) + " |", file=file)

        print(separator, file=file)

    def _render_table_json(
        self,
        headers: list[str],
        rows: list[list[str]],
        file: TextIO,
    ) -> None:
        records: list[dict[str, Any]] = []
        for row in rows:
            record: dict[str, Any] = {}
            for i, header in enumerate(headers):
                value = row[i] if i < len(row) else None
                record[_strip_ansi(header)] = (
                    _strip_ansi(str(value)) if value is not None else None
                )
            records.append(record)
        json.dump(records, file, ensure_ascii=False, indent=2)
        print(file=file)

    def _render_table_csv(
        self,
        headers: list[str],
        rows: list[list[str]],
        file: TextIO,
    ) -> None:
        writer = csv.writer(file, quoting=csv.QUOTE_MINIMAL)
        writer.writerow([_strip_ansi(h) for h in headers])
        for row in rows:
            writer.writerow([_strip_ansi(str(c)) for c in row])

    def progress_bar(
        self,
        total: int,
        width: int | None = None,
        char: str = "█",
        empty_char: str = "·",
        show_percent: bool = True,
        show_count: bool = True,
        prefix: str = "",
        suffix: str = "",
        color_low: str = "yellow",
        color_mid: str = "blue",
        color_high: str = "green",
        color_threshold_low: float = 0.33,
        color_threshold_high: float = 0.66,
        brackets: tuple[str, str] = ("[", "]"),
        file: TextIO = sys.stdout,
        force_inline: bool | None = None,
        min_render_interval: float = 0.05,
    ) -> Callable[[int], None]:
        if width is None:
            width = max(1, min(50, self.terminal_width - 30))

        use_unicode = True
        if hasattr(file, "encoding"):
            try:
                encoding = file.encoding or "utf-8"
                char.encode(encoding)
                empty_char.encode(encoding)
                brackets[0].encode(encoding)
                brackets[1].encode(encoding)
            except (UnicodeEncodeError, AttributeError, LookupError):
                use_unicode = False
                char = "#"
                empty_char = "-"
                brackets = ("[", "]")

        if force_inline is None:
            is_tty = hasattr(file, "isatty") and file.isatty()
            is_ide = bool(
                os.environ.get("PYCHARM_HOSTED")
                or os.environ.get("TERM_PROGRAM") == "vscode"
                or os.environ.get("PYTEST_CURRENT_TEST")
            )
            use_carriage_return = is_tty or is_ide
        else:
            use_carriage_return = bool(force_inline)

        supports_erase = (
            _supports_ansi_sequences(file) and use_carriage_return
        )
        left_bracket, right_bracket = brackets
        if prefix and not prefix.endswith(" "):
            prefix += " "
        if suffix and not suffix.startswith(" "):
            suffix = " " + suffix

        last_visible_len = 0
        last_render_time = 0.0

        def update(current: int) -> None:
            nonlocal last_visible_len, last_render_time
            if total <= 0:
                return

            now = time.monotonic()
            is_terminal_update = current >= total or current <= 0
            if (
                not is_terminal_update
                and now - last_render_time < min_render_interval
            ):
                return
            last_render_time = now

            progress = max(0.0, min(1.0, current / total))
            filled = int(width * progress)

            percent_str = f" {progress * 100:5.1f}%" if show_percent else ""
            count_str = f" {max(0, current)}/{total}" if show_count else ""

            if self.use_colors:
                if progress < color_threshold_low:
                    color = color_low
                elif progress < color_threshold_high:
                    color = color_mid
                else:
                    color = color_high
                bar_visible = (
                    self.format(char * filled, color)
                    + empty_char * (width - filled)
                )
            else:
                bar_visible = char * filled + empty_char * (width - filled)

            line = (
                f"{prefix}{left_bracket}{bar_visible}{right_bracket}"
                f"{percent_str}{count_str}{suffix}"
            )

            try:
                if use_carriage_return:
                    if supports_erase:
                        print(
                            f"\r{line}\033[K",
                            end="",
                            flush=True,
                            file=file,
                        )
                    else:
                        current_len = len(_strip_ansi(line))
                        pad_spaces = max(0, last_visible_len - current_len)
                        print(
                            f"\r{line}{' ' * pad_spaces}",
                            end="",
                            flush=True,
                            file=file,
                        )
                        last_visible_len = current_len
                    if current >= total:
                        print(file=file, flush=True)
                else:
                    print(line, file=file, flush=True)
            except UnicodeEncodeError:
                simple_bar = "#" * filled + "-" * (width - filled)
                simple_line = (
                    f"{prefix}[{simple_bar}]{percent_str}{count_str}{suffix}"
                )
                if use_carriage_return:
                    print(
                        f"\r{simple_line}",
                        end="",
                        flush=True,
                        file=file,
                    )
                    if current >= total:
                        print(file=file, flush=True)
                else:
                    print(simple_line, file=file, flush=True)

        return update

    def clear_line(self, file: TextIO = sys.stdout) -> None:
        if _supports_ansi_sequences(file):
            print("\r\033[K", end="", flush=True, file=file)
        else:
            print(
                "\r" + " " * self.terminal_width,
                end="\r",
                flush=True,
                file=file,
            )

    def wrap_text(
        self,
        text: str,
        width: int | None = None,
        indent: str = "",
        subsequent_indent: str = "",
    ) -> str:
        if width is None:
            width = self.terminal_width
        clean_text = _strip_ansi(text)
        wrapper = textwrap.TextWrapper(
            width=width,
            initial_indent=indent,
            subsequent_indent=subsequent_indent,
            break_long_words=False,
            break_on_hyphens=False,
        )
        return wrapper.fill(clean_text)

    def get_terminal_size(self) -> tuple[int, int]:
        self._update_terminal_size()
        return self.terminal_width, self.terminal_height

    def _update_terminal_size(self) -> None:
        try:
            size = shutil.get_terminal_size(fallback=(80, 24))
            self.terminal_width: int = size.columns
            self.terminal_height: int = size.lines
        except Exception:
            self.terminal_width = 80
            self.terminal_height = 24

    def _pad_cell(self, text: str, width: int, truncate: bool = True) -> str:
        clean_text = _strip_ansi(text)
        clean_len = len(clean_text)

        if truncate and clean_len > width:
            match = _ANSI_PREFIX_REGEX.match(text)
            ansi_prefix = match.group(0) if match else ""
            truncated = clean_text[: width - 3] + "..."
            if ansi_prefix:
                return ansi_prefix + truncated + COLORS["reset"]
            return truncated

        if clean_len < width:
            return text + " " * (width - clean_len)
        return text

    def _strip_ansi(self, text: str) -> str:
        return _strip_ansi(text)


_default_formatter: TerminalOutputFormatter | None = None
_formatter_lock = threading.Lock()


def _get_default_formatter() -> TerminalOutputFormatter:
    global _default_formatter
    if _default_formatter is not None:
        return _default_formatter
    with _formatter_lock:
        if _default_formatter is None:
            _default_formatter = TerminalOutputFormatter()
        return _default_formatter


def echo(
    text: str,
    style: str | None = None,
    file: TextIO = sys.stdout,
    formatter: TerminalOutputFormatter | None = None,
) -> None:
    if formatter is None:
        formatter = _get_default_formatter()
    print(formatter.format(text, style), file=file)


def style(
    text: str,
    fg: str | None = None,
    bg: str | None = None,
    bold: bool = False,
    underline: bool = False,
    blink: bool = False,
    formatter: TerminalOutputFormatter | None = None,
) -> str:
    if formatter is None:
        formatter = _get_default_formatter()
    return formatter.style_text(text, fg, bg, bold, underline, blink)


def progress_bar(
    total: int,
    width: int | None = None,
    char: str = "█",
    empty_char: str = "·",
    show_percent: bool = True,
    show_count: bool = True,
    prefix: str = "",
    suffix: str = "",
    color_low: str = "yellow",
    color_mid: str = "blue",
    color_high: str = "green",
    color_threshold_low: float = 0.33,
    color_threshold_high: float = 0.66,
    brackets: tuple[str, str] = ("[", "]"),
    file: TextIO = sys.stdout,
    force_inline: bool | None = None,
    min_render_interval: float = 0.05,
    formatter: TerminalOutputFormatter | None = None,
) -> Callable[[int], None]:
    if formatter is None:
        formatter = _get_default_formatter()
    return formatter.progress_bar(
        total=total,
        width=width,
        char=char,
        empty_char=empty_char,
        show_percent=show_percent,
        show_count=show_count,
        prefix=prefix,
        suffix=suffix,
        color_low=color_low,
        color_mid=color_mid,
        color_high=color_high,
        color_threshold_low=color_threshold_low,
        color_threshold_high=color_threshold_high,
        brackets=brackets,
        file=file,
        force_inline=force_inline,
        min_render_interval=min_render_interval,
    )


def table(
    headers: list[str],
    rows: list[list[str]],
    max_col_width: int | None = None,
    file: TextIO = sys.stdout,
    output_format: str = "text",
    formatter: TerminalOutputFormatter | None = None,
) -> None:
    if formatter is None:
        formatter = _get_default_formatter()
    formatter.render_table(headers, rows, max_col_width, file, output_format)


__all__ = [
    "OutputError",
    "TerminalOutputFormatter",
    "echo",
    "style",
    "progress_bar",
    "table",
    "COLORS",
    "STYLES",
]

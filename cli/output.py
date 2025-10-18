"""
Terminal output formatting with ANSI colors and styles

Provides colored output, tables, progress bars, and text wrapping
with automatic terminal capability detection.
"""

import sys
import os
import platform
import re
import shutil
import logging
import threading
from typing import Dict, List, Optional, TextIO, Any, Callable, Tuple
from .interfaces import OutputFormatter


class OutputError(Exception):
    """Output formatting error"""
    pass


if platform.system() == 'Windows':
    try:
        import colorama
        colorama.just_fix_windows_console()
    except (ImportError, Exception):
        pass


COLORS: Dict[str, str] = {
    'reset': '\033[0m',
    'black': '\033[30m',
    'red': '\033[31m',
    'green': '\033[32m',
    'yellow': '\033[33m',
    'blue': '\033[34m',
    'magenta': '\033[35m',
    'cyan': '\033[36m',
    'white': '\033[37m',
    'bright_black': '\033[90m',
    'bright_red': '\033[91m',
    'bright_green': '\033[92m',
    'bright_yellow': '\033[93m',
    'bright_blue': '\033[94m',
    'bright_magenta': '\033[95m',
    'bright_cyan': '\033[96m',
    'bright_white': '\033[97m',
    'bold': '\033[1m',
    'dim': '\033[2m',
    'italic': '\033[3m',
    'underline': '\033[4m',
    'blink': '\033[5m',
    'reverse': '\033[7m',
    'hidden': '\033[8m',
    'strikethrough': '\033[9m',
}

STYLES: Dict[str, str] = {
    'success': COLORS['green'],
    'error': COLORS['red'],
    'warning': COLORS['yellow'],
    'info': COLORS['blue'],
    'header': COLORS['bold'] + COLORS['bright_white'],
    'debug': COLORS['bright_black'],
    'emphasis': COLORS['bold'],
    'code': COLORS['bright_black'],
    'highlight': COLORS['reverse'],
}


def _enable_windows_vt_mode_for_handle(win_handle_const: int) -> bool:
    """Enable VT100 mode for specific Windows console handle"""
    if platform.system() != 'Windows':
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

        ENABLE_VTP = 0x0004
        new_mode = mode.value | ENABLE_VTP

        return bool(kernel32.SetConsoleMode(handle, new_mode))

    except Exception:
        return False


def _enable_windows_vt_mode() -> bool:
    """Try to enable VT100 escape sequences on Windows 10+ for stdout and stderr"""
    if platform.system() != 'Windows':
        return True

    try:
        STD_OUTPUT_HANDLE = -11
        STD_ERROR_HANDLE = -12

        ok_out = _enable_windows_vt_mode_for_handle(STD_OUTPUT_HANDLE)
        ok_err = _enable_windows_vt_mode_for_handle(STD_ERROR_HANDLE)

        return ok_out or ok_err

    except Exception:
        return False


def _supports_color() -> bool:
    """Detect if current terminal supports ANSI colors"""
    if 'NO_COLOR' in os.environ:
        return False

    if os.environ.get('FORCE_COLOR') or os.environ.get('CLICOLOR_FORCE') == '1':
        return True

    plat: str = platform.system()

    if os.environ.get('PYCHARM_HOSTED') == '1':
        return True

    if plat == 'Windows':
        win_term: bool = bool(
            os.environ.get('WT_SESSION') or
            os.environ.get('TERM_PROGRAM') == 'vscode' or
            os.environ.get('ConEmuANSI') == 'ON' or
            'ANSICON' in os.environ
        )
        if win_term:
            return True

        if _enable_windows_vt_mode():
            return True

        return False

    term: str = (os.environ.get('TERM') or '').lower()
    if term in ('xterm', 'xterm-color', 'xterm-256color', 'linux',
                'screen', 'screen-256color', 'vt100', 'rxvt', 'cygwin'):
        return True
    if term == 'dumb':
        return False

    if os.environ.get('CI') == 'true' or os.environ.get('GITHUB_ACTIONS') == 'true':
        return True

    return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


def _supports_ansi_sequences(file: TextIO = sys.stdout) -> bool:
    """Check if given stream supports ANSI escape sequences"""
    if platform.system() == 'Windows':
        return _enable_windows_vt_mode()

    return hasattr(file, 'isatty') and file.isatty()


class TerminalOutputFormatter(OutputFormatter):
    """
    Terminal output formatter with ANSI color support

    Features:
    - Automatic color support detection
    - Styled text output
    - Table rendering with stream support
    - Progress bars with inline updates
    - Terminal size detection
    - Text wrapping
    """

    def __init__(self, use_colors: Optional[bool] = None):
        """
        Initialize output formatter

        Args:
            use_colors: Force colors on/off (None = auto-detect)
        """
        if use_colors is None:
            use_colors = _supports_color()

        self.use_colors: bool = use_colors
        self._logger: logging.Logger = logging.getLogger('cliframework.output')

        self._update_terminal_size()

        self._logger.debug(
            f"OutputFormatter initialized: colors={'enabled' if use_colors else 'disabled'}, "
            f"size={self.terminal_width}x{self.terminal_height}"
        )

    def _update_terminal_size(self) -> None:
        """Update terminal size information"""
        try:
            size: os.terminal_size = shutil.get_terminal_size(fallback=(80, 24))
            self.terminal_width: int = size.columns
            self.terminal_height: int = size.lines
        except Exception:
            self.terminal_width = 80
            self.terminal_height = 24

    def format(self, text: str, style: Optional[str] = None) -> str:
        """
        Format text with specified style

        Args:
            text: Text to format
            style: Style name or color code

        Returns:
            Formatted text (with ANSI codes if colors enabled)
        """
        if not self.use_colors or not style:
            return text

        style_code: str = STYLES.get(style, COLORS.get(style, ''))

        if not style_code:
            self._logger.warning(f"Unknown style: {style}")
            return text

        return f"{style_code}{text}{COLORS['reset']}"

    def style_text(self,
                   text: str,
                   fg: Optional[str] = None,
                   bg: Optional[str] = None,
                   bold: bool = False,
                   underline: bool = False,
                   blink: bool = False) -> str:
        """
        Apply multiple style attributes to text

        Args:
            text: Text to style
            fg: Foreground color name or style name
            bg: Background color name
            bold: Apply bold
            underline: Apply underline
            blink: Apply blink

        Returns:
            Styled text
        """
        if not self.use_colors:
            return text

        codes: List[str] = []

        if fg:
            style_code = STYLES.get(fg) or COLORS.get(fg)
            if style_code:
                codes.append(style_code)

        if bg:
            bg_color_map = {
                'black': '\033[40m',
                'red': '\033[41m',
                'green': '\033[42m',
                'yellow': '\033[43m',
                'blue': '\033[44m',
                'magenta': '\033[45m',
                'cyan': '\033[46m',
                'white': '\033[47m',
                'bright_black': '\033[100m',
                'bright_red': '\033[101m',
                'bright_green': '\033[102m',
                'bright_yellow': '\033[103m',
                'bright_blue': '\033[104m',
                'bright_magenta': '\033[105m',
                'bright_cyan': '\033[106m',
                'bright_white': '\033[107m',
            }
            if bg in bg_color_map:
                codes.append(bg_color_map[bg])

        if bold:
            codes.append(COLORS['bold'])
        if underline:
            codes.append(COLORS['underline'])
        if blink:
            codes.append(COLORS['blink'])

        if not codes:
            return text

        start: str = ''.join(codes)
        return f"{start}{text}{COLORS['reset']}"

    def render_table(self,
                    headers: List[str],
                    rows: List[List[str]],
                    max_col_width: Optional[int] = None,
                    file: TextIO = sys.stdout) -> None:
        """
        Render formatted table to output stream

        Args:
            headers: Column headers
            rows: Table data rows
            max_col_width: Maximum column width (None = auto-calculate based on terminal)
            file: Output stream (default: stdout)
        """
        if not headers:
            return

        num_cols = len(headers)
        separator_overhead = 3 * num_cols + 1
        available_width = self.terminal_width - separator_overhead

        if max_col_width is None:
            max_col_width = max(20, available_width // num_cols)

        col_widths: List[int] = [min(len(self._strip_ansi(h)), max_col_width) for h in headers]

        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    clean_cell: str = self._strip_ansi(str(cell))
                    col_widths[i] = min(
                        max(col_widths[i], len(clean_cell)),
                        max_col_width
                    )

        separator: str = '+' + '+'.join('-' * (w + 2) for w in col_widths) + '+'

        print(separator, file=file)

        header_cells = []
        for i, h in enumerate(headers):
            if i < len(col_widths):
                header_cells.append(self._pad_cell(h, col_widths[i], truncate=True))

        header_row: str = '| ' + ' | '.join(header_cells) + ' |'
        print(self.format(header_row, 'header'), file=file)
        print(separator, file=file)

        for row in rows:
            cells: List[str] = []
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    cells.append(self._pad_cell(str(cell), col_widths[i], truncate=True))
            print('| ' + ' | '.join(cells) + ' |', file=file)

        print(separator, file=file)

    def _extract_ansi_codes(self, text: str) -> Tuple[str, str]:
        """Extract leading ANSI codes and clean text"""
        ansi_pattern = re.compile(r'^(\033\[[0-9;]+m)+')
        match = ansi_pattern.match(text)
        if match:
            prefix = match.group(0)
            clean = text[len(prefix):]
            return prefix, clean
        return '', text

    def _pad_cell(self, text: str, width: int, truncate: bool = True) -> str:
        """
        Pad cell to specified width, handling ANSI codes correctly

        Args:
            text: Text to pad (may contain ANSI codes)
            width: Target display width (visible characters)
            truncate: Whether to truncate if text is too long

        Returns:
            Padded text with ANSI codes preserved
        """
        clean_text = self._strip_ansi(text)
        clean_len = len(clean_text)

        if truncate and clean_len > width:
            ansi_prefix, _ = self._extract_ansi_codes(text)
            truncated = clean_text[:width - 3] + '...'

            if ansi_prefix:
                return ansi_prefix + truncated + COLORS['reset']
            return truncated

        elif clean_len < width:
            padding_needed = width - clean_len
            return text + ' ' * padding_needed

        else:
            return text

    def progress_bar(self,
                     total: int,
                     width: Optional[int] = None,
                     char: str = '█',
                     empty_char: str = '·',
                     show_percent: bool = True,
                     show_count: bool = True,
                     prefix: str = '',
                     suffix: str = '',
                     color_low: str = 'yellow',
                     color_mid: str = 'blue',
                     color_high: str = 'green',
                     color_threshold_low: float = 0.33,
                     color_threshold_high: float = 0.66,
                     brackets: tuple = ('[', ']'),
                     file: TextIO = sys.stdout,
                     force_inline: Optional[bool] = None) -> Callable[[int], None]:
        """
        Create progress bar update function

        Args:
            total: Total number of iterations
            width: Progress bar width (None = auto)
            char: Character for filled portion
            empty_char: Character for empty portion
            show_percent: Show percentage
            show_count: Show count (current/total)
            prefix: Text before progress bar
            suffix: Text after progress bar
            color_low: Color for 0-33% progress
            color_mid: Color for 33-66% progress
            color_high: Color for 66-100% progress
            color_threshold_low: Threshold for low->mid color (0.0-1.0)
            color_threshold_high: Threshold for mid->high color (0.0-1.0)
            brackets: Tuple of (left_bracket, right_bracket)
            file: Output stream (default: stdout)
            force_inline: Force inline updates (True for IDE consoles, None = auto-detect)

        Returns:
            Function to update progress bar with current value
        """
        if width is None:
            width = max(1, min(50, self.terminal_width - 30))

        use_unicode = True
        if hasattr(file, 'encoding'):
            try:
                encoding = file.encoding or 'utf-8'
                char.encode(encoding)
                empty_char.encode(encoding)
                brackets[0].encode(encoding)
                brackets[1].encode(encoding)
            except (UnicodeEncodeError, AttributeError, LookupError):
                use_unicode = False
                char = '#'
                empty_char = '-'
                brackets = ('[', ']')
                self._logger.debug("Using ASCII characters for progress bar")

        if force_inline is None:
            is_tty = hasattr(file, 'isatty') and file.isatty()
            is_ide = bool(
                os.environ.get('PYCHARM_HOSTED') or
                os.environ.get('TERM_PROGRAM') == 'vscode' or
                os.environ.get('PYTEST_CURRENT_TEST')
            )
            use_carriage_return = is_tty or is_ide
        else:
            use_carriage_return = bool(force_inline)

        supports_erase = _supports_ansi_sequences(file) and use_carriage_return

        left_bracket, right_bracket = brackets

        if prefix and not prefix.endswith(' '):
            prefix += ' '
        if suffix and not suffix.startswith(' '):
            suffix = ' ' + suffix

        last_visible_len = 0

        def visible_len(s: str) -> int:
            """Get visible length of string (without ANSI codes)"""
            return len(self._strip_ansi(s))

        def update(current: int) -> None:
            """Update progress bar to current value"""
            nonlocal last_visible_len

            if total <= 0:
                return

            progress: float = max(0.0, min(1.0, current / total))
            filled: int = int(width * progress)

            percent_str: str = f" {progress * 100:5.1f}%" if show_percent else ""
            count_str: str = f" {max(0, current)}/{total}" if show_count else ""

            if self.use_colors:
                if progress < color_threshold_low:
                    color = color_low
                elif progress < color_threshold_high:
                    color = color_mid
                else:
                    color = color_high
                bar_visible: str = self.format(char * filled, color) + empty_char * (width - filled)
            else:
                bar_visible: str = char * filled + empty_char * (width - filled)

            line: str = f"{prefix}{left_bracket}{bar_visible}{right_bracket}{percent_str}{count_str}{suffix}"

            try:
                if use_carriage_return:
                    if supports_erase:
                        print(f"\r{line}\033[K", end='', flush=True, file=file)
                    else:
                        current_len = visible_len(line)
                        pad_spaces = max(0, last_visible_len - current_len)
                        print(f"\r{line}{' ' * pad_spaces}", end='', flush=True, file=file)
                        last_visible_len = current_len

                    if current >= total:
                        print(file=file, flush=True)
                else:
                    print(line, file=file, flush=True)

            except UnicodeEncodeError:
                simple_bar = '#' * filled + '-' * (width - filled)
                simple_line = f"{prefix}[{simple_bar}]{percent_str}{count_str}{suffix}"

                if use_carriage_return:
                    if supports_erase:
                        print(f"\r{simple_line}\033[K", end='', flush=True, file=file)
                    else:
                        current_len = len(simple_line)
                        pad_spaces = max(0, last_visible_len - current_len)
                        print(f"\r{simple_line}{' ' * pad_spaces}", end='', flush=True, file=file)
                        last_visible_len = current_len

                    if current >= total:
                        print(file=file, flush=True)
                else:
                    print(simple_line, file=file, flush=True)

        return update

    def clear_line(self, file: TextIO = sys.stdout) -> None:
        """Clear current terminal line"""
        if _supports_ansi_sequences(file):
            print('\r\033[K', end='', flush=True, file=file)
        else:
            print('\r' + ' ' * self.terminal_width, end='\r', flush=True, file=file)

    def wrap_text(self,
                  text: str,
                  width: Optional[int] = None,
                  indent: str = '',
                  subsequent_indent: str = '') -> str:
        """
        Wrap long text to fit terminal width

        Args:
            text: Text to wrap
            width: Maximum line width (None = terminal width)
            indent: Indent for first line
            subsequent_indent: Indent for subsequent lines

        Returns:
            Wrapped text with newlines
        """
        import textwrap

        if width is None:
            width = self.terminal_width

        clean_text: str = self._strip_ansi(text)

        wrapper = textwrap.TextWrapper(
            width=width,
            initial_indent=indent,
            subsequent_indent=subsequent_indent,
            break_long_words=False,
            break_on_hyphens=False
        )

        return wrapper.fill(clean_text)

    def _strip_ansi(self, text: str) -> str:
        """Remove ANSI escape codes from text"""
        ansi_escape = re.compile(
            r'\x1B(?:'
            r'[@-Z\\-_]|'
            r'\[[0-?]*[ -/]*[@-~]|'
            r'\][0-9;]*(?:\x07|\x1b\\)'
            r')'
        )
        return ansi_escape.sub('', text)

    def get_terminal_size(self) -> Tuple[int, int]:
        """Get current terminal size"""
        self._update_terminal_size()
        return self.terminal_width, self.terminal_height


_default_formatter: Optional[TerminalOutputFormatter] = None
_formatter_lock = threading.Lock()


def _get_default_formatter() -> TerminalOutputFormatter:
    """Get or create cached default formatter"""
    global _default_formatter

    if _default_formatter is not None:
        return _default_formatter

    with _formatter_lock:
        if _default_formatter is None:
            _default_formatter = TerminalOutputFormatter()
        return _default_formatter


def echo(text: str, style: Optional[str] = None, file: TextIO = sys.stdout,
         formatter: Optional[TerminalOutputFormatter] = None) -> None:
    """
    Print styled text to output stream

    Args:
        text: Text to print
        style: Style name (success, error, warning, info, etc.)
        file: Output stream (default: stdout)
        formatter: Custom formatter instance (uses cached default if None)
    """
    if formatter is None:
        formatter = _get_default_formatter()
    print(formatter.format(text, style), file=file)


def style(text: str,
          fg: Optional[str] = None,
          bg: Optional[str] = None,
          bold: bool = False,
          underline: bool = False,
          blink: bool = False,
          formatter: Optional[TerminalOutputFormatter] = None) -> str:
    """
    Apply style attributes to text

    Args:
        text: Text to style
        fg: Foreground color or style name
        bg: Background color
        bold: Bold text
        underline: Underlined text
        blink: Blinking text
        formatter: Custom formatter instance (uses cached default if None)

    Returns:
        Styled text string
    """
    if formatter is None:
        formatter = _get_default_formatter()
    return formatter.style_text(text, fg, bg, bold, underline, blink)


def progress_bar(total: int,
                 width: Optional[int] = None,
                 char: str = '█',
                 empty_char: str = '·',
                 show_percent: bool = True,
                 show_count: bool = True,
                 prefix: str = '',
                 suffix: str = '',
                 color_low: str = 'yellow',
                 color_mid: str = 'blue',
                 color_high: str = 'green',
                 color_threshold_low: float = 0.33,
                 color_threshold_high: float = 0.66,
                 brackets: tuple = ('[', ']'),
                 file: TextIO = sys.stdout,
                 force_inline: Optional[bool] = None,
                 formatter: Optional[TerminalOutputFormatter] = None) -> Callable[[int], None]:
    """
    Create progress bar update function

    Args:
        total: Total number of iterations
        width: Progress bar width (None = auto-calculate based on terminal)
        char: Character for filled portion (default: '█')
        empty_char: Character for empty portion (default: '·')
        show_percent: Show percentage indicator
        show_count: Show count as "current/total"
        prefix: Text to display before progress bar
        suffix: Text to display after progress bar
        color_low: Color for 0-33% progress (default: 'yellow')
        color_mid: Color for 33-66% progress (default: 'blue')
        color_high: Color for 66-100% progress (default: 'green')
        color_threshold_low: Threshold for low->mid color transition (0.0-1.0)
        color_threshold_high: Threshold for mid->high color transition (0.0-1.0)
        brackets: Tuple of (left_bracket, right_bracket) characters
        file: Output stream (default: stdout)
        force_inline: Force inline updates (True for IDE consoles, None = auto-detect)
        formatter: Custom formatter instance (uses cached default if None)

    Returns:
        Update function that takes current progress value as argument

    Example:
        >>> update = progress_bar(100, prefix="Processing")
        >>> for i in range(100):
        ...     do_work(i)
        ...     update(i + 1)
    """
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
        force_inline=force_inline
    )


def table(headers: List[str],
         rows: List[List[str]],
         max_col_width: Optional[int] = None,
         file: TextIO = sys.stdout,
         formatter: Optional[TerminalOutputFormatter] = None) -> None:
    """
    Render table to output stream

    Args:
        headers: Column headers
        rows: Table data rows
        max_col_width: Maximum column width (None = auto-calculate)
        file: Output stream (default: stdout)
        formatter: Custom formatter instance (uses cached default if None)
    """
    if formatter is None:
        formatter = _get_default_formatter()
    formatter.render_table(headers, rows, max_col_width, file)
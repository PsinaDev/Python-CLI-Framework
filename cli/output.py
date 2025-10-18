"""
Terminal output formatting with ANSI colors and styles

Provides colored output, tables, progress bars, and text wrapping
with automatic terminal capability detection.
"""

import os
import platform
import re
import shutil
import logging
import sys
from typing import Dict, List, Optional, TextIO, Any, Callable, Tuple
from .interfaces import OutputFormatter


class OutputError(Exception):
    """Output formatting error"""
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


def _enable_windows_vt_mode() -> bool:
    """
    Try to enable VT100 escape sequences on Windows 10+

    Returns:
        True if VT mode enabled or already supported, False otherwise
    """
    if platform.system() != 'Windows':
        return True

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32

        # Get stdout handle
        STD_OUTPUT_HANDLE = -11
        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
        if handle == -1 or handle is None:
            return False

        # Get current console mode
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False

        # Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004)
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        new_mode = mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING

        if kernel32.SetConsoleMode(handle, new_mode):
            return True

        return False

    except Exception:
        return False


def _supports_color() -> bool:
    """
    Detect if current terminal supports ANSI colors

    Checks various environment variables and platform settings.

    Returns:
        True if colors supported, False otherwise
    """
    if 'NO_COLOR' in os.environ:
        return False

    if 'FORCE_COLOR' in os.environ:
        return True

    plat: str = platform.system()
    supported_platform: bool = plat != 'Windows' or 'ANSICON' in os.environ

    is_a_tty: bool = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()

    if plat == 'Windows':
        win_term: bool = bool(
            os.environ.get('WT_SESSION') or
            os.environ.get('TERM_PROGRAM') == 'vscode' or
            os.environ.get('ConEmuANSI') == 'ON'
        )
        if win_term:
            return True

        # Try to enable VT processing on Windows 10+
        if _enable_windows_vt_mode():
            return True

        try:
            if sys.getwindowsversion().major >= 10:
                return True
        except AttributeError:
            pass

    if 'TERM' in os.environ:
        term: str = os.environ['TERM'].lower()
        if term in ('xterm', 'xterm-color', 'xterm-256color', 'linux',
                    'screen', 'screen-256color', 'vt100', 'rxvt', 'cygwin'):
            return True

    if os.environ.get('CI') == 'true' or os.environ.get('GITHUB_ACTIONS') == 'true':
        return True

    return supported_platform and is_a_tty


class TerminalOutputFormatter(OutputFormatter):
    """
    Terminal output formatter with ANSI color support

    Features:
    - Automatic color support detection
    - Styled text output
    - Table rendering
    - Progress bars
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
            fg: Foreground color name
            bg: Background color name
            bold: Apply bold
            underline: Apply underline
            blink: Apply blink (may not work in all terminals)

        Returns:
            Styled text
        """
        if not self.use_colors:
            return text

        codes: List[str] = []

        if fg and fg in COLORS:
            codes.append(COLORS[fg])

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

    def render_table(self, headers: List[str], rows: List[List[str]],
                    max_col_width: Optional[int] = None) -> None:
        """
        Render formatted table to stdout
        Args:
            headers: Column headers
            rows: Table data rows
            max_col_width: Maximum column width (None = unlimited, but respects terminal width)
        """
        if not headers:
            return

        if max_col_width is None:
            max_col_width = max(20, (self.terminal_width - len(headers) * 3) // len(headers))

        # Calculate column widths based on clean text (without ANSI codes)
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

        print(separator)

        # Process headers
        header_cells = []
        for i, h in enumerate(headers):
            if i < len(col_widths):
                header_cells.append(self._pad_cell(h, col_widths[i], truncate=True))

        header_row: str = '| ' + ' | '.join(header_cells) + ' |'
        print(self.format(header_row, 'header'))
        print(separator)

        # Process data rows
        for row in rows:
            cells: List[str] = []
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    cells.append(self._pad_cell(str(cell), col_widths[i], truncate=True))
            print('| ' + ' | '.join(cells) + ' |')

        print(separator)

    def _extract_ansi_codes(self, text: str) -> Tuple[List[str], str]:
        """
        Extract ANSI codes from text

        Returns:
            Tuple of (list of ANSI codes, clean text)
        """
        ansi_pattern = re.compile(r'(\033\[[0-9;]+m)')
        codes = ansi_pattern.findall(text)
        clean = ansi_pattern.sub('', text)
        return codes, clean

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
        # Extract ANSI codes and get clean text
        ansi_codes, clean_text = self._extract_ansi_codes(text)
        clean_len = len(clean_text)

        if truncate and clean_len > width:
            # Truncate clean text
            truncated = clean_text[:width - 3] + '...'

            # Re-apply ANSI codes if present
            if ansi_codes and self.use_colors:
                # Apply all codes found in original, then add reset at end
                style_prefix = ''.join(ansi_codes)
                return style_prefix + truncated + COLORS['reset']

            return truncated

        elif clean_len < width:
            # Need padding
            padding_needed = width - clean_len

            # If text has ANSI codes, we need to add padding after the text
            # but before the reset code if it exists
            if ansi_codes and self.use_colors:
                # Check if text ends with reset code
                if text.endswith(COLORS['reset']):
                    # Insert padding before reset
                    text_without_reset = text[:-len(COLORS['reset'])]
                    return text_without_reset + ' ' * padding_needed + COLORS['reset']
                else:
                    # Just add padding at the end
                    return text + ' ' * padding_needed
            else:
                # Plain text, just add padding
                return text + ' ' * padding_needed

        else:
            # Exactly right width
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
                     file: TextIO = sys.stdout) -> Callable[[int], None]:
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

        Returns:
            Function to update progress bar with current value
        """
        if width is None:
            width = min(50, self.terminal_width - 30)

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
                self._logger.debug("Using ASCII characters for progress bar (Unicode not supported)")

        use_carriage_return = hasattr(file, 'isatty') and file.isatty()

        left_bracket, right_bracket = brackets

        if prefix and not prefix.endswith(' '):
            prefix += ' '
        if suffix and not suffix.startswith(' '):
            suffix = ' ' + suffix

        def update(current: int) -> None:
            """Update progress bar to current value"""
            if total <= 0:
                return

            progress: float = min(1.0, current / total)
            filled: int = int(width * progress)

            bar: str = char * filled + empty_char * (width - filled)

            percent_str: str = f" {progress * 100:5.1f}%" if show_percent else ""
            count_str: str = f" {current}/{total}" if show_count else ""

            line: str = f"{prefix}{left_bracket}{bar}{right_bracket}{percent_str}{count_str}{suffix}"

            if self.use_colors:
                if progress < color_threshold_low:
                    color = color_low
                elif progress < color_threshold_high:
                    color = color_mid
                else:
                    color = color_high

                colored_bar: str = self.format(char * filled, color) + empty_char * (width - filled)
                line = f"{prefix}{left_bracket}{colored_bar}{right_bracket}{percent_str}{count_str}{suffix}"

            try:
                if use_carriage_return:
                    print(f"\r{line}", end='', flush=True, file=file)
                else:
                    print(line, file=file, flush=True)

                if current >= total and use_carriage_return:
                    print(file=file)
            except UnicodeEncodeError:
                simple_bar = '#' * filled + '-' * (width - filled)
                simple_line = f"{prefix}[{simple_bar}]{percent_str}{count_str}{suffix}"
                if use_carriage_return:
                    print(f"\r{simple_line}", end='', flush=True, file=file)
                else:
                    print(simple_line, file=file, flush=True)
                if current >= total and use_carriage_return:
                    print(file=file)

        return update

    def clear_line(self) -> None:
        """Clear current terminal line"""
        if self.use_colors:
            print('\r\033[K', end='', flush=True)
        else:
            print('\r' + ' ' * self.terminal_width, end='\r', flush=True)

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
        """
        Remove ANSI escape codes from text

        Args:
            text: Text with ANSI codes

        Returns:
            Clean text without ANSI codes
        """
        ansi_escape = re.compile(
            r'\x1B(?:'
            r'[@-Z\\-_]|'
            r'\[[0-?]*[ -/]*[@-~]|'
            r'\][0-9;]*(?:\x07|\x1b\\)'
            r')'
        )
        return ansi_escape.sub('', text)

    def get_terminal_size(self) -> Tuple[int, int]:
        """
        Get current terminal size

        Returns:
            Tuple of (width, height)
        """
        self._update_terminal_size()
        return self.terminal_width, self.terminal_height


# Helper functions
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
        fg: Foreground color
        bg: Background color
        bold: Bold text
        underline: Underlined text
        blink: Blinking text
        formatter: Custom formatter instance (creates new if None)

    Returns:
        Styled text string
    """
    if formatter is None:
        formatter = TerminalOutputFormatter()
    return formatter.style_text(text, fg, bg, bold, underline, blink)


def progress_bar(total: int, formatter: Optional[TerminalOutputFormatter] = None,
                **kwargs: Any) -> Callable[[int], None]:
    """
    Create progress bar update function

    Args:
        total: Total iterations
        formatter: Custom formatter instance (creates new if None)
        **kwargs: Additional options (see TerminalOutputFormatter.progress_bar)

    Returns:
        Update function that takes current value
    """
    if formatter is None:
        formatter = TerminalOutputFormatter()
    return formatter.progress_bar(total, **kwargs)


def table(headers: List[str], rows: List[List[str]],
         formatter: Optional[TerminalOutputFormatter] = None) -> None:
    """
    Render table to stdout

    Args:
        headers: Column headers
        rows: Table data rows
        formatter: Custom formatter instance (creates new if None)
    """
    if formatter is None:
        formatter = TerminalOutputFormatter()
    formatter.render_table(headers, rows)
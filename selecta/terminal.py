"""Terminal handling related classes and functions."""

import codecs
import os
import re
import sys

from contextlib import contextmanager
from selecta.errors import NotSupportedError, TerminalInitError
from string import Template

__all__ = ["Keycodes", "Terminal", "getch", "reopened_terminal"]


def _find_getch():
    """Returns a cross-platform function that can be used to read a single
    character from the terminal without echoing it to the user, either in
    blocking or nonblocking mode."""

    try:
        import termios
    except ImportError:
        # Non-POSIX system, so let's try msvcrt.getch
        try:
            import msvcrt

            def _getch(block=True):
                """Reads a single character from the terminal without echoing it
                to the user.

                Args:
                    block (bool): whether to wait for a keypress if there are
                        no characters in the terminal buffer.

                Returns:
                    the character read from the terminal or ``None`` if there
                    was no character waiting to be read and ``block`` was
                    set to ``False``. May also return a full ANSI escape
                    sequence for cursor keys.
                """
                if not block and not msvcrt.kbhit():
                    return None
                else:
                    # TODO: ensure that msvcrt.getch() returns escape sequences
                    # corresponding to cursor keys in a single sequence
                    return msvcrt.getch()
        except ImportError:
            def _getch(block=True):
                raise NotImplementedError
            return _getch

    from select import select
    from tty import setraw

    def _kbhit(fd):
        rlist, _, _ = select([fd], [], [], 0)
        return bool(rlist)

    def _getch(block=True):
        """Reads a single character from the terminal without echoing it
        to the user."""
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            setraw(fd)

            # If we are in nonblocking mode and there is no input available
            # on fd, just return
            if not block and not _kbhit(fd):
                return None

            # Escape sequences should be read in a single chunk so that's
            # why we have to loop below
            result = [os.read(fd, 1)]
            while _kbhit(fd):
                result.append(os.read(fd, 1))
            return b"".join(result)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    return _getch

getch = _find_getch()


class Keycodes(object):
    """Class holding symbolic names for common keycodes that the user may
    see when using getch_."""

    BREAK = '\x03'
    EOF = '\x04'
    ENTER = '\r'
    ESCAPE = '\x1b'
    DELETE = '\x7f'

    CTRL_H = '\x08'
    CTRL_J = '\x0a'
    CTRL_U = '\x15'
    CTRL_M = '\x0d'
    CTRL_N = '\x0e'
    CTRL_P = '\x10'
    CTRL_R = '\x12'
    CTRL_W = '\x17'

    UP = object()
    LEFT = object()
    RIGHT = object()
    DOWN = object()

    @classmethod
    def is_backspace_like(cls, char):
        """Checks whether the given character is 'Backspace-like', i.e. it may
        appear in response to the user pressing the Backspace key."""
        return char in (cls.DELETE, cls.CTRL_H)

    @classmethod
    def is_enter_like(cls, char):
        """Checks whether the given character is 'Enter-like', i.e. it may
        appear in response to the user pressing the Enter key."""
        return char in (cls.ENTER, cls.CTRL_M, cls.CTRL_J)


class Terminal(object):
    """Abstract superclass for classes that provide methods and helper
    variables for colored output and cursor movement.

    The ``init()`` method of the class must be called before using its
    functionality, and the ``deinit()`` method must be called when we are
    done with the terminal. The class can also act as a context manager
    that calls ``init()`` and ``deinit()`` automatically so it is probably
    easier to use the class like this::

        with Terminal.factory() as term:
            do_something_with(term)

    The only exception to the rule above is the ``supported`` getter: it may
    be called even if the terminal was not initialized. The ``factory()``
    factory method takes care of selecting a Terminal implementation that is
    supported on the current platform with the available set of Python modules.
    """

    _COLORS = "BLACK BLUE GREEN CYAN RED MAGENTA YELLOW WHITE".split()

    @classmethod
    def create(self, stream=None, is_tty=None):
        """Creates an appropriate ``Terminal`` subclass by evaluating the
        platform, the availability of the various helper modules and the
        given output stream.

        When the ``curses`` module is available, the function will create
        a class that queries the terminfo database for the escape sequences that
        are required for coloring and cursor movement. When the ``curses``
        module is not available, but the ``colorama`` module is installed, the
        function will create a class that assumes that the terminal understands
        ANSI escape sequences (leaving it up to ``colorama`` to wrap
        ``sys.stdout`` properly to ensure that ANSI escape sequences are
        understood). If everything else fails, the function creates a class that
        represents a dumb terminal without capabilities.

        In all platforms, the class also checks whether the stream that the
        class will operate on (typically ``sys.stdout``) is attached to a TTY.
        If not, the terminal is assumed to be a dumb terminal with no coloring and
        cursor movement capabilities. If you want to override this behaviour,
        set ``is_tty`` to ``True`` or ``False`` instead of ``None``.

        Args:
            stream (file-like or None): the stream that will be used for
                terminal output. ``None`` means to use ``sys.stdout``,
                evaluated at construction time.
            is_tty (bool or None): whether the stream is known to be a TTY or
                not. See the constructor of the Terminal_ class for more info.
        """
        subclasses = [CursesTerminal, ANSITerminal, DumbTerminal]
        for subclass in subclasses:
            term = subclass(stream=stream, is_tty=is_tty)
            if term.supported:
                return term
        raise NotSupportedError("no terminal class is supported on the "
                                "current platform")

    def __init__(self, stream=None, is_tty=None):
        """Constructor.

        Args:
            stream (file-like or None): the stream that will be used for
                terminal output. ``None`` means to use ``sys.stdout``,
                evaluated at construction time.
            is_tty (bool or None): whether the stream is known to be a TTY.
                ``True`` means that we know that the stream is connected to a
                TTY (even if it claims otherwise); ``False`` means that we know
                that the stream is *not* connected to a TTY (even if it claims
                that it is). ``None`` means to decide based on the ``isatty()``
                method of the stream; in the absence of such a method, the
                stream is assumed not to be connected to a TTY.
        """
        self.stream = stream or sys.stdout
        self._initialized = False
        self._control_sequences = None
        self._deinit_hook = None
        self._input_encoding = None
        if is_tty is not None:
            self._is_tty = bool(is_tty)
        else:
            self._is_tty = hasattr(self.stream, "isatty") and self.stream.isatty()

    def init(self):
        """Initializes the terminal. This function must be called before
        using any other functionality of this class.

        Raises:
            RuntimeError: when the terminal is already initialized
        """
        if self._initialized:
            raise TerminalInitError("terminal is already initialized")

        self._control_sequences = self._create_empty_control_sequences()
        self._deinit_hook = None
        self._input_encoding = self._detect_input_encoding()

        self._initialized = True

    def deinit(self):
        """Deinitializes the terminal. This function should be called when
        we are done with the terminal.

        Raises:
            RuntimeError: when the terminal has not been initialized
        """
        if not self._initialized:
            raise TerminalInitError("the terminal has not been initialized")

        if self._deinit_hook is not None:
            self._deinit_hook()

        self._is_tty = False
        self._control_sequences = None
        self._deinit_hook = None
        self._input_encoding = None

        self._initialized = False

    def clear_to_eol(self):
        """Clears the contents of the current line from the cursor position
        to the end of the line."""
        self.write("${CLEAR_EOL}")

    def clear_to_eos(self):
        """Clears the contents of the current line from the cursor position
        to the end of the screen."""
        self.write("${CLEAR_EOS}")

    def getch(self):
        """Reads a single character from the terminal without echoing it
        to the user. Handles Ctrl-C and EOF properly by raising
        KeyboardInterrupt or EOFError when needed. Also remaps some cursor
        movement escape sequences to the appropriate constants in
        ``Keycodes``. If you don't need this behaviour, use the raw getch()_
        function.

        Returns:
            the raw character from the terminal or one of the constants from
            the ``Keycodes`` class for some special keys.

        Raises:
            KeyboardInterrupt: when the user pressed Ctrl-C
            EOFError: when the user typed an end-of-file character
        """
        char = getch()
        if char == Keycodes.BREAK:
            raise KeyboardInterrupt
        elif char == Keycodes.EOF:
            raise EOFError
        elif char == b"\n":
            # Special treatment for \n: sometimes it is the same as the
            # DOWN control sequence, and we don't want to report
            # Keycodes.DOWN instead
            pass
        elif char == b"\x1b[B" and self._control_sequences.get("DOWN") == b"\n":
            # ANSI escape sequence for the 'down' key. We treat this as
            # DOWN when the DOWN sequence is equal to '\n'; this is an
            # educated guess in such cases.
            return Keycodes.DOWN
        elif char == self._control_sequences.get("UP"):
            return Keycodes.UP
        elif char == self._control_sequences.get("LEFT"):
            return Keycodes.LEFT
        elif char == self._control_sequences.get("RIGHT"):
            return Keycodes.RIGHT

        # Time to try and decode the input if we know the input encoding
        if self._input_encoding:
            try:
                return char.decode(self._input_encoding)
            except UnicodeError:
                return char
        else:
            return char

    @contextmanager
    def hidden_cursor(self):
        """Context manager that hides the cursor temporarily while the
        execution is in the context."""
        self.write("${HIDE_CURSOR}")
        try:
            yield
        finally:
            self.write("${SHOW_CURSOR}")

    @property
    def input_encoding(self):
        """The input encoding of the terminal."""
        return self._input_encoding

    def move_cursor(self, x=None, y=None, dx=0, dy=0):
        """Moves the cursor to an absolute location or to a location relative
        to the current position. Absolute positions take precedence over
        relative ones.

        Args:
            x (int or None): the horizontal index of the cell to move the
                cursor to
            y (int or None): the vertical index of the cell to move the
                cursor to
            dx (int): the number of cells to move the cursor to the right,
                relative to the current location (negative numbers mean left)
            dy (int): the number of cells to move the cursor down,
                relative to the current location (negative numbers mean up)
        """
        if y is not None:
            raise NotImplementedError("move() not implemented yet for absolute "
                                      "values in the Y direction")
        else:
            if dy > 0:
                self.write("$DOWN" * dy)
            elif dy < 0:
                self.write("$UP" * -dy)

        if x is not None:
            self.write("$BOL")
            if x > 0:
                self.write("$RIGHT" * x)
        else:
            if dx > 0:
                self.write("$RIGHT" * dx)
            elif dx < 0:
                self.write("$LEFT" * -dx)

    def render(self, template):
        """Replaces tokens of the form ``$TOKEN`` and ``${TOKEN}`` in the given
        template string with the corresponding terminal control sequences and
        returns the generated string.

        Supported tokens are::

            - ``BLACK``, ``RED``, ``GREEN``, ``BLUE``, ``CYAN``, ``MAGENTA``,
              ``YELLOW`` and ``WHITE`` are replaced by control sequences that
              set the foreground color to these colors. They *may* be prefixed
              with ``FG_`` to make it explicit that they refer to the
              foreground color. Adding ``BG_`` as a prefix makes them change
              the background color instead.

            - ``BLINK`` switches to blinking text

            - ``BOLD`` switches to bold text

            - ``DIM`` switches to dim text

            - ``REVERSE`` reverses the foreground and background colors

            - ``UNDERLINE`` switches to underlined text

            - ``NORMAL`` resets the foreground and background color of the
              terminal to the default.

            - ``UP``, ``DOWN``, ``LEFT`` and ``RIGHT`` move the cursor by
              one cell in the given direction.

            - ``BOL`` moves the cursor to the beginning of the current line

            - ``CLEAR_BOL`` clears everything up to the beginning of the
              current line while keeping the cursor in the same place

            - ``CLEAR_EOL`` clears everything up to the end of the current line
              while keeping the cursor in the same place

            - ``CLEAR_EOS`` clears everything up to the end of the screen
              while keeping the cursor in the same place

            - ``CLEAR_SCREEN`` clears the entire screen

            - ``HIDE_CURSOR`` hides the cursor

            - ``SHOW_CURSOR`` shows the cursor
        """
        return Template(template).safe_substitute(self._control_sequences)

    @property
    def supported(self):
        """Method that returns whether this terminal type is supported
        on the current platform with the current set of Python modules.

        Args:
            stream (file-like): the stream that will be used for terminal
                output.
        """
        raise NotImplementedError

    def supports(self, *tokens):
        """Returns whether the terminal supports all the given control
        tokens. See the render_ method for the list of tokens that you may
        pass here."""
        return all(self._control_sequences.get(token) for token in tokens)

    def write(self, template, raw=False):
        """Writes the given template to the attached stream of the terminal,
        replacing any tokens handled by the ``render()`` function before
        actually printing it.

        Args:
            template (str): the template to write
            raw (bool): when True, no replacements are performed on the
                template
        """
        self.stream.write(self.render(template) if not raw else template)
        self.stream.flush()

    def __enter__(self):
        self.init()
        return self

    def __exit__(self, type, value, traceback):
        self.deinit()

    def _create_empty_control_sequences(self):
        """Creates a default set of control sequences that simply map all
        the tokens handled by the ``render()`` method to empty strings."""
        keys = "BLINK BOLD DIM NORMAL REVERSE UNDERLINE UP DOWN LEFT RIGHT "\
            "BOL EOL CLEAR_BOL CLEAR_EOL CLEAR_EOS CLEAR_SCREEN "\
            "HIDE_CURSOR SHOW_CURSOR".split()
        keys.extend(self._COLORS)
        keys.extend("FG_{0}".format(color) for color in self._COLORS)
        keys.extend("BG_{0}".format(color) for color in self._COLORS)
        return dict((key, '') for key in keys)

    def _detect_input_encoding(self):
        """Detects the input encoding of the terminal."""
        encoding = sys.stdin.encoding
        if encoding is None:
            # hmmm, input encoding not known. Let's assume that it is the
            # same as the stream's encoding.
            encoding = getattr(self.stream, "encoding", None)
        return encoding or sys.getdefaultencoding()


class CursesTerminal(Terminal):
    """Terminal class that uses the ``curses`` module to retrieve the escape
    sequences needed for controlling the cursor and the colors."""

    _ANSI_COLORS = "BLACK RED GREEN YELLOW BLUE MAGENTA CYAN WHITE".split()

    def __init__(self, stream=None, is_tty=None):
        super(CursesTerminal, self).__init__(stream, is_tty)
        self._curses = None

    @Terminal.supported.getter
    def supported(self):
        if not self._is_tty:
            return False
        try:
            import curses
            return True
        except ImportError:
            return False

    def init(self):
        super(CursesTerminal, self).init()

        import curses
        self._curses = curses
        curses.setupterm(fd=self.stream.fileno())

        self._parse_background_control_sequences()
        self._parse_foreground_control_sequences()
        self._parse_styling_control_sequences()
        self._parse_cursor_control_sequences()
        self._parse_erasing_control_sequences()

    def _get_string_capability(self, capability_name, strip_delays=True):
        """Returns a string capability with the given name from terminfo.

        Args:
            capability_name (str): the name of the capability to retrieve
            strip_delays (bool): whether to strip delays (substrings of the
                form ``$<2>``) from the capability string.

        Returns:
            the string corresponding to the capability name in terminfo
        """
        capability = self._curses.tigetstr(capability_name) or ''
        if strip_delays:
            capability = re.sub(r'\$<\d+>[/*]?', '', capability)
        return capability

    def _parse_background_control_sequences(self):
        """Parses the control sequences from terminfo that set the background
        color of the terminal."""

        capability = self._get_string_capability("setb")
        for index, color in enumerate(self._COLORS):
            key = "BG_{0}".format(color)
            value = self._tparm(capability, index)
            if value:
                self._control_sequences[key] = value

        capability = self._get_string_capability("setab")
        for index, color in enumerate(self._ANSI_COLORS):
            key = "BG_{0}".format(color)
            value = self._tparm(capability, index)
            if value:
                self._control_sequences[key] = value

    def _parse_cursor_control_sequences(self):
        """Parses the control sequences from terminfo that control the location
        and appearance of the cursor."""
        self._parse_capabilities(BOL="cr", UP="cuu1", DOWN="cud1",
                                 LEFT="cub1", RIGHT="cuf1",
                                 HIDE_CURSOR="cinvis", SHOW_CURSOR="cnorm")

    def _parse_erasing_control_sequences(self):
        """Parses the control sequences from terminfo that erase content from
        the terminal."""
        self._parse_capabilities(CLEAR_BOL="el1", CLEAR_EOL="el",
                                 CLEAR_EOS="ed", CLEAR_SCREEN="clear")

    def _parse_capabilities(self, **kwds):
        """Parses the given terminal capabilities and stores them as
        control sequences. This method accepts keyword arguments only; the
        name of the keyword argument is the control sequence and the
        value of the keyword argument is the corresponding capability name."""
        self._control_sequences.update((
            (name, self._get_string_capability(capability_name))
            for name, capability_name in kwds.items()
        ))

    def _parse_foreground_control_sequences(self):
        """Parses the control sequences from terminfo that set the foreground
        color of the terminal."""

        capability = self._get_string_capability("setf")
        for index, color in enumerate(self._COLORS):
            key = "FG_{0}".format(color)
            value = self._tparm(capability, index)
            if value:
                self._control_sequences[color] = self._control_sequences[key] = value

        capability = self._get_string_capability("setaf")
        for index, color in enumerate(self._ANSI_COLORS):
            key = "FG_{0}".format(color)
            value = self._tparm(capability, index)
            if value:
                self._control_sequences[color] = self._control_sequences[key] = value

    def _parse_styling_control_sequences(self):
        """Parses the control sequences from terminfo that perform styling of
        the output."""
        self._parse_capabilities(BLINK="blink", BOLD="bold", DIM="dim",
                                 NORMAL="sgr0", REVERSE="rev",
                                 UNDERLINE="smul")

    def _tparm(self, capability, index):
        """Wrapper around ``curses.tparm`` that returns an empty string in
        case of an error."""
        try:
            return self._curses.tparm(capability, index) or ''
        except self._curses.error:
            return ''


class ANSITerminal(Terminal):
    """Terminal class that assumes that the terminal understands standard ANSI
    escape sequences."""

    @Terminal.supported.getter
    def supported(self):
        if not self._is_tty:
            return False
        try:
            import colorama
            return True
        except ImportError:
            return False

    def init(self):
        super(ANSITerminal, self).init()

        import colorama
        colorama.init()
        self._deinit_hook = colorama.deinit

        self._control_sequences.update(
            UP="\x1b[1A",
            DOWN="\x1b[1B",
            RIGHT="\x1b[1C",
            LEFT="\x1b[1D",
            BOL="\r",
            CLEAR_BOL="\x1b[1K",
            CLEAR_EOL="\x1b[K",
            CLEAR_EOS="\x1b[J",
            CLEAR_SCREEN="\x1b[2J",
            HIDE_CURSOR="\x1b[?25l",
            SHOW_CURSOR="\x1b[?25h",

            NORMAL="\x1b[0m",
            BOLD="\x1b[1m",
            DIM="\x1b[2m",
            UNDERLINE="\x1b[4m",
            BLINK="\x1b[5m",
            REVERSE="\x1b[7m",

            FG_BLACK="\x1b[30m",
            FG_RED="\x1b[31m",
            FG_GREEN="\x1b[32m",
            FG_YELLOW="\x1b[33m",
            FG_BLUE="\x1b[34m",
            FG_MAGENTA="\x1b[35m",
            FG_CYAN="\x1b[36m",
            FG_WHITE="\x1b[37m",

            BG_BLACK="\x1b[40m",
            BG_RED="\x1b[41m",
            BG_GREEN="\x1b[42m",
            BG_YELLOW="\x1b[43m",
            BG_BLUE="\x1b[44m",
            BG_MAGENTA="\x1b[45m",
            BG_CYAN="\x1b[46m",
            BG_WHITE="\x1b[47m"
        )


class DumbTerminal(Terminal):
    """Terminal class that assumes that the terminal itself has no capabilities
    for controlling the cursor or the output colors."""

    @Terminal.supported.getter
    def supported(self):
        return True


@contextmanager
def reopened_terminal():
    """Context manager that reopens the current terminal device (``/dev/tty``
    on Linux and Mac OS X, ``con`` on Windows) and reassigns ``sys.stdin`` and
    ``sys.stdout`` to the reopened device. Restores the original ``sys.stdin``
    and ``sys.stdout`` upon leaving the context."""
    tty = os.ctermid()
    saved_stdin, saved_stdout = sys.stdin, sys.stdout
    try:
        if saved_stdin.encoding is not None:
            sys.stdin = codecs.open(tty, "r", encoding=saved_stdin.encoding)
        else:
            sys.stdin = open(tty, "r")
        if saved_stdout.encoding is not None:
            sys.stdout = codecs.open(tty, "w", encoding=saved_stdout.encoding)
        else:
            sys.stdout = open(tty, "w")
        yield
    finally:
        sys.stdin, sys.stdout = saved_stdin, saved_stdout

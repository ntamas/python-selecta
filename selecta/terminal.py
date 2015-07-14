"""Terminal handling related classes and functions."""

import os
import re
import sys

from contextlib import contextmanager
from string import Template

__all__ = ["Terminal", "reopened_terminal"]


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

        When the ``curses`` module is available, this class queries the terminfo
        database for the escape sequences that are required for coloring and
        cursor movement. When the ``curses`` module is not available, this class
        assumes that the terminal understands ANSI escape sequences. On Windows,
        the ``colorama`` module is used to silently convert ANSI escape sequences
        into the appropriate Windows API calls.

        In all platforms, the class also checks whether the stream that the
        class will operate on (typically ``sys.stdout``) is attached to a TTY.
        If not, the terminal is assumed to be a dumb terminal with no coloring and
        cursor movement capabilities.

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
        raise RuntimeError("no terminal class is supported on the "
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
            raise RuntimeError("terminal is already initialized")

        self._control_sequences = self._create_empty_control_sequences()
        self._deinit_hook = None

        self._initialized = True

    def deinit(self):
        """Deinitializes the terminal. This function should be called when
        we are done with the terminal.

        Raises:
            RuntimeError: when the terminal has not been initialized
        """
        if not self._initialized:
            raise RuntimeError("the terminal has not been initialized")

        if self._deinit_hook is not None:
            self._deinit_hook()

        self._is_tty = False
        self._control_sequences = None
        self._deinit_hook = None
        self._initialized = False

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

            - ``DIM`` switches to dim text

            - ``REVERSE`` reverses the foreground and background colors

            - ``BOLD`` switches to bold text

            - ``NORMAL`` resets the foreground and background color of the
              terminal to the default.
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

    def write(self, template):
        """Writes the given template to the attached stream of the terminal,
        replacing any tokens handled by the ``render()`` function before
        actually printing it."""
        self.stream.write(self.render(template))
        self.stream.flush()

    def __enter__(self):
        self.init()
        return self

    def __exit__(self, type, value, traceback):
        self.deinit()

    def _create_empty_control_sequences(self):
        """Creates a default set of control sequences that simply map all
        the tokens handled by the ``render()`` method to empty strings."""
        keys = "BLINK BOLD DIM NORMAL REVERSE".split()
        keys.extend(self._COLORS)
        keys.extend("FG_{0}".format(color) for color in self._COLORS)
        keys.extend("BG_{0}".format(color) for color in self._COLORS)
        return dict((key, '') for key in keys)


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

        capability_pairs = {
            "BLINK": "blink",
            "BOLD": "bold",
            "DIM": "dim",
            "NORMAL": "sgr0",
            "REVERSE": "rev"
        }
        self._control_sequences.update((
            (name, self._get_string_capability(capability_name))
            for name, capability_name in capability_pairs.items()
        ))

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
        sys.stdin = open(tty, "r")
        sys.stdout = open(tty, "w")
        yield
    finally:
        sys.stdin, sys.stdout = saved_stdin, saved_stdout

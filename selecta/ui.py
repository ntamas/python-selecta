from __future__ import print_function

from contextlib import contextmanager
from selecta.errors import NotSupportedError
from selecta.terminal import Keycodes
from selecta.renderers import MatchRenderer
from selecta.utils import is_printable, safeint

import re
import unicodedata

__all__ = ["UI", "DumbTerminalUI", "SmartTerminalUI"]


class UI(object):
    """Abstract superclass for the different variants of the user interface
    that we offer to the user."""

    def __init__(self):
        self.index = None

    def dispose(self):
        """Notifies the user interface that it will not be needed any more."""
        pass

    def setup(self, index):
        """Prepares the user interface to be used with the given search index.

        Args:
            index (selecta.indexing.Index): the search index to be used by the
                UI to search for hits matching a given query string
        """
        self.index = index

    def choose_item(self, initial_query=None):
        """Shows the user interface and lets the user choose an item.

        Args:
            initial_query (str or None): the initial search query to submit
                automatically, or ``None`` if no such query should be
                submitted

        Returns:
            Match: a match representing the item that the user has chosen,
                or ``None`` if the user cancelled the selection.
        """
        raise NotImplementedError

    @contextmanager
    def use(self, *args, **kwds):
        try:
            self.setup(*args, **kwds)
            yield
        finally:
            self.dispose()


class TerminalUI(UI):
    """Abstract superclass for terminal-based UIs."""

    def __init__(self, terminal, prompt="> ", renderer=None):
        """Constructor.

        Args:
            terminal (Terminal): the terminal that the UI will be created on
            prompt (str): prompt to use before lines that require user input
            renderer (Renderer or None): renderer to use for showing matches
                on the UI. ``None`` means to use a default renderer created
                by ``create_default_renderer()``..
        """
        super(TerminalUI, self).__init__()

        # If you are thinking about importing readline to add support for
        # fancy editing, don't. Doing so might add extra ANSI escape
        # sequences on some terminals with some versions of readline, which
        # will screw up the output of selecta. This is apparently a readline
        # bug:
        #
        # https://bugs.python.org/issue19884

        self.hit_list_limit = 9
        self.prompt = prompt
        self.renderer = renderer or self.create_default_renderer()
        self.terminal = terminal

    def create_default_renderer(self):
        """Creates a default MatchRenderer_ that is used to show matches on
        the console."""
        return MatchRenderer()


class DumbTerminalUI(TerminalUI):
    """Dumb terminal-based UI class for ``selecta``. This UI class does not
    require any special capabilities from the terminal (e.g., raw terminal
    access)."""

    def choose_item(self, initial_query=None):
        matches = self.index.search(initial_query) if initial_query else None
        while True:
            self.show_matches(matches)
            query = self.read_query()
            if query is None:
                return None

            match_index = safeint(query, 0)
            if match_index > 0 and match_index <= len(matches):
                return matches[match_index-1]

            matches = self.index.search(query)

    def read_query(self):
        """Reads the query string or the index of the match chosen by the
        user from the standard input.

        Returns:
            the query string or the index of the match chosen by the user,
            or ``None`` if the user cancelled the selection by submitting EOF
        """
        try:
            return raw_input(self.prompt)
        except KeyboardInterrupt:
            return None
        except EOFError:
            return None

    def show_matches(self, matches):
        """Shows the given list of matches on the standard output."""
        matches = matches or []
        limit = self.hit_list_limit

        self.renderer.attach_to_terminal(self.terminal)
        for index, match in enumerate(matches[:limit], 1):
            print("{index}: {rendered_match}".format(
                index=index,
                rendered_match=self.renderer.render(match)
            ))
        if len(matches) > limit:
            print("...and {0} more".format(len(matches) - limit))


class SmartTerminalUI(TerminalUI):
    """Smart terminal-based UI class for ``selecta`` that provides a snappier
    user experience but requires raw access to the terminal (which might not
    be available on all platforms)."""

    def __init__(self, terminal, prompt="> ", renderer=None):
        super(SmartTerminalUI, self).__init__(terminal, prompt, renderer)
        if not terminal.supports("LEFT", "RIGHT", "UP", "DOWN"):
            raise NotSupportedError("SmartTerminalUI requires a terminal that "
                                    "supports cursor movement")
        self._query = None
        self._ui_shown = False
        self.reset()

    def choose_item(self, initial_query=None):
        self.query = initial_query or ''
        while True:
            try:
                # TODO: Unicode handling
                char = self.terminal.getch()
            except KeyboardInterrupt:
                return None
            except EOFError:
                return None

            if Keycodes.is_enter_like(char):
                return self.selected_item
            elif Keycodes.is_backspace_like(char):
                self.query = self.query[:-1]
            elif char == Keycodes.CTRL_N:    # TODO: handle arrow key
                self.adjust_selected_index_by(1)
            elif char == Keycodes.CTRL_P:    # TODO: handle arrow key
                self.adjust_selected_index_by(-1)
            elif char == Keycodes.CTRL_U:
                self.query = ''
            elif char == Keycodes.CTRL_W:
                self.query = re.sub("[^ ]* *$", "", self.query)
            elif is_printable(char):
                self.query += char
            else:
                print("Unhandled char: {0!r}".format(char))

    def dispose(self):
        self.hide()

    def hide(self):
        """Hides the UI. This function assumes that the cursor is currently
        in the first row of the UI."""
        if not self._ui_shown:
            return

        self._hide()
        self._ui_shown = False

    def _hide(self):
        self.terminal.move_cursor(x=0)
        self.terminal.clear_to_eos()

    def adjust_selected_index_by(self, offset, wrap=True):
        """Adjusts the selected index with the given offset, wrapping around
        the result list.

        Args:
            offset (int): the offset to add to the selected index
            wrap (bool): whether to wrap around the result list
        """
        new_index = int(self.selected_index) + offset
        if wrap:
            new_index = new_index % self.num_visible_matches
        self.selected_index = new_index

    @property
    def num_visible_matches(self):
        """The number of matches currently visible on the UI."""
        return min(len(self._best_matches), self.hit_list_limit)

    @property
    def query(self):
        """The current query string shown on the UI."""
        return self._query

    @query.setter
    def query(self, value):
        """Sets the current query string shown on the UI."""
        # TODO: optimize if the new query string has the old as a prefix
        if value == self._query:
            return
        self._query = value
        self.refresh()

    def refresh(self):
        """Redraws the UI. Assumes that the cursor is in the row where the
        drawing should start."""

        num_lines = self.hit_list_limit + 1
        if not self._ui_shown:
            # Ensure that there are enough empty lines at the bottom of the
            # terminal to show the UI
            self.terminal.write("\n" * num_lines)
            self.terminal.move_cursor(dy=-num_lines)
            self._ui_shown = True

        query = self.query

        self._best_matches = self.index.search(query) if self.index else []
        if self._best_matches and self._selected_index is None:
            self._selected_index = 0
        self._fix_selected_index()

        with self.terminal.hidden_cursor():
            # Draw the matches first
            self.terminal.move_cursor(x=0, dy=1)
            num_lines_printed = self._show_matches(self._best_matches)
            self.terminal.clear_to_eos()

            # Now draw the prompt and the query
            self.terminal.move_cursor(x=0, dy=-num_lines_printed-1)
            self.terminal.write(self.prompt, raw=True)
            # TODO: truncate the query from the front if too wide
            self.terminal.write(query, raw=True)
            self.terminal.clear_to_eol()


    def reset(self):
        """Resets the UI to the initial state (no query, no matches, no
        selection)."""
        self._best_matches = []
        self._selected_index = None
        self.query = ''

    @property
    def selected_index(self):
        """Returns the index of the currently selected item on the UI."""
        return self._selected_index

    @selected_index.setter
    def selected_index(self, value):
        if self._selected_index == value:
            return

        self._selected_index = value
        self._fix_selected_index()
        self.refresh()

    @property
    def selected_item(self):
        """The currently selected item on the UI."""
        if self._selected_index is None or self._selected_index < 0:
            return None
        else:
            return self._best_matches[self._selected_index]

    def _fix_selected_index(self):
        """Ensures that the index of the selected item is within valid
        bounds."""
        if not self._best_matches:
            self._selected_index = None
        elif self._selected_index is not None:
            self._selected_index = max(
                0, min(self._selected_index, self.num_visible_matches)
            )

    def _show_matches(self, matches):
        """Shows the given list of matches on the terminal.

        Returns:
            int: the number of lines printed on the terminal
        """
        matches = matches or []
        limit = self.hit_list_limit

        self.renderer.attach_to_terminal(self.terminal)
        for index, match in enumerate(matches[:limit]):
            selected = (index == self._selected_index)
            rendered_match = self.renderer.render(match, selected=selected)
            self.terminal.write(rendered_match, raw=True)
            self.terminal.write("\n")

        return min(len(matches), limit)

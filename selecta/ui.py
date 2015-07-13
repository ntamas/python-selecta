from __future__ import print_function

from selecta.renderers import MatchRenderer
from selecta.utils import safeint

__all__ = ["UI", "DumbUI"]


class UI(object):
    """Abstract superclass for the different variants of the user interface
    that we offer to the user."""

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
            the item that the user has chosen.
        """
        raise NotImplementedError


class DumbUI(UI):
    def __init__(self, terminal, prompt="> ", renderer=None):
        """Constructor.

        Args:
            terminal (Terminal): the terminal that the UI will be created on
            prompt (str): prompt to use before lines that require user input
            renderer (Renderer or None): renderer to use for showing matches
                on the UI. ``None`` means to use a default renderer created
                by ``create_default_renderer()``..
        """
        super(DumbUI, self).__init__()

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

    def choose_item(self, initial_query=None):
        matches = self.index.search(initial_query) if initial_query else None
        while True:
            self.show_matches(matches)
            query = self.read_query()
            if query is None:
                return None

            match_index = safeint(query, 0)
            if match_index > 0 and match_index <= len(matches):
                return matches[match_index-1].matched_object

            matches = self.index.search(query)

    def create_default_renderer(self):
        """Creates a default MatchRenderer_ that is used to show matches on
        the console."""
        return MatchRenderer()

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

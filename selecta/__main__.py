from __future__ import print_function

import argparse
import sys

from selecta.indexing import FuzzyIndex
from selecta.ui import DumbTerminalUI, SmartTerminalUI
from selecta.utils import identity
from selecta.terminal import reopened_terminal, Terminal

__version__ = "0.0.1"

KNOWN_UI_CLASSES = dict(
    dumb=DumbTerminalUI,
    smart=SmartTerminalUI
)

def main(args=None):
    """The main entry point of the command line application.

    Args:
        args (list of str): the command line arguments

    Returns:
        int: the exit code of the application
    """
    if args is None:
        args = sys.argv[1:]

    parser = create_command_line_parser()
    options = parser.parse_args(args)

    if options.show_version:
        print(__version__)
        return

    index = prepare_index()

    with reopened_terminal():
        ui_factory = KNOWN_UI_CLASSES[options.ui]
        selection = process_input(index, options.initial_query,
                                  ui_factory=ui_factory)

    if selection is not None:
        print(selection)

    return selection is None


def create_command_line_parser():
    """Creates and returns the command line argument parser."""
    ui_names = sorted(KNOWN_UI_CLASSES.keys())

    parser = argparse.ArgumentParser(prog="selecta")
    parser.add_argument("--version", help="show the version number",
                        action="store_true", default=False,
                        dest="show_version")
    parser.add_argument("-s", "--search", dest="initial_query",
                        metavar="SEARCH", default=None,
                        help="specify an initial search string")
    parser.add_argument("--ui", dest="ui", metavar="UI", default="smart",
                        choices=ui_names,
                        help="use the given user interface; valid choices "
                        "are: {0!r}".format(ui_names))
    return parser


def prepare_index(strings=sys.stdin, transform=unicode.strip, encoding=None):
    """Prepares the index to be used by the application from strings coming
    from the given input stream or iterable.

    Args:
        strings (iterable of str): the strings to be included in the index
        transform (callable or None): a callable to call on each of the strings
            from the iterable before they are fed into the index
        encoding (str or None): the encoding of the strings in the iterable
            if they are not Unicode. ``None`` means to fall back to the
            ``encoding`` attribute of the ``strings`` iterable if there is
            such an attribute, or to ``sys.getdefaultencoding()``.

    Returns:
        selecta.indexing.Index: the prepared index
    """
    transform = transform or identity
    encoding = encoding or getattr(strings, "encoding", None) or \
        sys.getdefaultencoding()
    index = FuzzyIndex()
    for string in strings:
        if not isinstance(string, unicode):
            string = string.decode(encoding)
        index.add(transform(string))
    return index


def process_input(index, initial_query=None, ui_factory=SmartTerminalUI):
    # Note that we force the Terminal factory to assume that we are connected
    # to a TTY. This is intentional; we know that because we have reopened
    # /dev/tty (on Linux and Mac) or CON (on Windows) before.
    with Terminal.create(is_tty=True) as terminal:
        ui = ui_factory(terminal)
        with ui.use(index):
            match = ui.choose_item(initial_query)
            return match.matched_object if match else None


if __name__ == "__main__":
    sys.exit(main())

"""Renderers convert model objects into a visual representation that
can be shown on the UI."""


class Renderer(object):
    def attach_to_terminal(self, terminal):
        """Attaches the renderer to the given terminal."""
        pass

    def render(self, obj, selected=False):
        """Renders the given object into a string that can be printed to
        the terminal.

        Args:
            obj (object): the object to render
            selected (bool): whether the object should have a "selected"
                appearance

        Returns:
            str: the string representation of the object, suitable for printing
                to the terminal
        """
        raise NotImplementedError


class MatchRenderer(Renderer):
    """Converts a ``selecta.matches.Match`` object into a textual
    representation that can be printed on the console."""

    def attach_to_terminal(self, terminal):
        escape_braces = lambda s: s.replace("{", "{{").replace("}", "}}")
        self._unselected_templates = {
            "match_start": terminal.render("${BG_YELLOW}${FG_BLACK}"),
            "match_end": terminal.render("${NORMAL}"),
            "start": terminal.render("${NORMAL}"),
            "end": terminal.render("${CLEAR_EOL}${NORMAL}")
        }
        self._selected_templates = {
            "match_start": terminal.render("${BG_YELLOW}"),
            "match_end": terminal.render("${BG_WHITE}"),
            "start": terminal.render("${NORMAL}${BG_WHITE}${FG_BLACK}"),
            "end": terminal.render("${CLEAR_EOL}${NORMAL}")
        }

    def render(self, match, selected=False):
        match.canonicalize()
        result = list(match.matched_string)

        templates = self._selected_templates if selected \
            else self._unselected_templates
        for start, end in reversed(match.substrings):
            result[end:end] = templates["match_end"]
            result[start:start] = templates["match_start"]
        result[0:0] = templates["start"]
        result.extend(templates["end"])
        return "".join(result)

"""Renderers convert model objects into a visual representation that
can be shown on the UI."""


class Renderer(object):
    def attach_to_terminal(self, terminal):
        """Attaches the renderer to the given terminal."""
        pass

    def render(self, obj):
        """Renders the given object into a string that can be printed to
        the terminal.

        Args:
            obj (object): the object to render

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
        self._template = "".join([
            escape_braces(terminal.render("${BG_YELLOW}${FG_BLACK}")),
            "{0}",
            escape_braces(terminal.render("${NORMAL}"))
        ])

    def render(self, match):
        match.canonicalize()
        result = list(match.matched_string)
        for start, end in reversed(match.substrings):
            substring = match.matched_string[start:end]
            result[start:end] = [self._template.format(substring)]
        return "".join(result)

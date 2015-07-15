class Error(RuntimeError):
    """Superclass for all selecta-related exceptions."""
    pass


class NotSupportedError(Error):
    """Exception thrown when something is not supported; for instance, the
    combination of a terminal and a given UI class."""
    pass


class TerminalInitError(Error):
    """Exception thrown when a terminal is already initialized and we try
    to initialize it once again, or when a terminal is not initialized and
    we try to deinitialize it once again."""
    pass

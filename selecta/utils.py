def all_occurrences_of_string(string, corpus):
    """Finds all occurrences of a given string in a corpus.

    Args:
        string (str): the string to search
        corpus (str): the string to search in

    Yields:
        a start index for each occurrence of the string within the corpus,
        in ascending order
    """
    start = -1
    while True:
        start = corpus.find(string, start+1)
        if start < 0:
            return
        yield start


def identity(arg):
    """An identity function that simply returns its argument."""
    return arg


def list_packer(*args):
    """An identity function that creates a list from its arguments."""
    return args


def _safe_conversion(value, converter, default=None):
    """Pipes a value through a converter function and returns the converted
    value or the default value if there was an exception during the conversion.

    Args:
        value: the value to convert
        converter (callable): a callable that converts the value to the result.
            Must accept a single argument only.
        default: the default value to return in case of an unsuccessful
            conversion.

    Returns: the converted value if the conversion was successful or the default
        value otherwise.
    """
    try:
        return converter(value)
    except:
        return default


def safeint(value, default=None):
    """Tries to convert a value given as a string to an integer. Returns the
    default value if the value cannot be converted.

    Args:
        value (str): the value to turn into an integer
        default (object): the default value to return if the given value cannot
            be converted into an integer

    Returns (int or object): the integer value converted from the given value,
        or the default value if the conversion was unsuccessful.
    """
    return _safe_conversion(value, int, default)

from functools import total_ordering


@total_ordering
class Match(object):
    """Object representing a match in a search index.

    Attributes:
        matched_object (object): the object that was matched
        matched_string (string): the string representation of the object
        score (float): the score of the match. Higher scores indicate a better
            match.
        substrings (list of tuples): optional list of substrings to mark in
            the string representation of the object. Each tuple in the list
            is a pair of the start and end indices of the substring.
    """

    def __init__(self):
        self.matched_object = None
        self.matched_string = None
        self.score = 0.0
        self.substrings = []

    def __lt__(self, other):
        return self.score < other.score or \
            self.matched_string < other.matched_string

    def canonicalize(self):
        """Canonicalizes the match by ensuring that the ranges in the map
        do not overlap with each other and are sorted by the start index."""
        self.substrings = canonical_ranges(self.substrings)


def canonical_ranges(ranges):
    """Given a list of ranges of the form ``(start, end)``, returns
    another list that ensures that:

    - For any number *x*, *x* will be included in at most one of the returned
      ranges.

    - For any number *x*, *x* will be included in one of the returned ranges
      if and only if *x* was included in at least one of the input ranges.

    - The returned ranges are sorted by the start index.

    - There exist no pairs of ranges in the returned list such that the end
      of one of the ranges is the start of the other.

    Args:
        ranges (list of tuples): list of ranges of the form ``(start, end)``

    Returns:
        list of tuples: the canonical representation of the input list, as
            defined by the rules above.
    """
    if len(ranges) < 2:
        return ranges

    result = sorted(ranges)
    changed = True
    while changed:
        if len(result) < 2:
            return result

        next_result, changed = [], False
        prev_start, prev_end = result.pop(0)
        for curr in result:
            curr_start, curr_end = curr
            if prev_end >= curr_start:
                # prev and curr have an overlap, so merge them
                prev_end = curr_end
                changed = True
            else:
                # No overlap, prev_start and prev_end can be saved
                next_result.append((prev_start, prev_end))
                prev_start, prev_end = curr
        next_result.append((prev_start, prev_end))
        result = next_result

    return result

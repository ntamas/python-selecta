from collections import defaultdict
from operator import itemgetter
from selecta.matches import Match
from selecta.utils import all_occurrences_of_string, list_packer


class Index(object):
    """Interface specification for the different types of search indexes."""

    def add(self, item):
        """Adds the given item to the index.

        Args:
            item (object): the item to add
        """
        raise NotImplementedError

    def search(query):
        """Returns a list of matches given a search query.

        Args:
            query (str): the search query

        Returns:
            list of selecta.matches.Match: the list of matches
        """
        raise NotImplementedError


class IndexBase(Index):
    """Abstract superclass for the different types of search indexes.

    Attributes:
        displayer (callable): a callable that takes an item in the
            index and returns a suitable string representation that can be
            shown on the UI.
        match_factory (callable): a callable that creates subclasses of Match
            objects
        tokenizer (callable): a callable that takes an item to be
            added to the index and returns a list of extracted tokens that are
            added to the index. ``None`` means to add the string representation
            of the item as is.
    """

    def __init__(self, displayer=str, tokenizer=list_packer,
                 match_factory=Match):
        self.displayer = displayer
        self.match_factory = match_factory
        self.tokenizer = tokenizer

    def add(self, item, tokenizer=None):
        """Adds the given item to the index.

        Args:
            item (object): the item to add
            tokenizer (callable or None): a tokenizer function that can be
                called with the item to extract a list of tokens for the item.
                ``None`` means to use the default tokenizer.
        """
        tokenizer = tokenizer or self.tokenizer
        for token in tokenizer(item):
            self._add_token_for_item(token, item)

    def _add_token_for_item(self, token, item):
        """Registers a token corresponding to the given item in the search
        index."""
        raise NotImplementedError

    def _construct_match_for_item(self, item, score=0.0):
        """Constructs a match that corresponds to the given item.

        Args:
            item (object): the item to construct the match for
            score (float): the score of the item, if known
        """
        result = self.match_factory()
        result.matched_object = item
        result.matched_string = self.displayer(item)
        result.score = score
        return result


class SubstringIndex(IndexBase):
    """Index that finds all objects in the index that are associated to at
    least one token that contains the query string as a substring. Matches are
    scored based on the index of the first character of the match; lower scores
    are better."""

    def __init__(self, case_sensitive=True):
        super(SubstringIndex, self).__init__()
        self._case_sensitive = bool(case_sensitive)
        self._tokens_to_items = defaultdict(list)

    def _add_token_for_item(self, token, item):
        if not self._case_sensitive:
            token = token.lower()
        self._tokens_to_items[token].append(item)

    def search(self, query):
        if not self._case_sensitive:
            query = query.lower()

        items_and_scores = defaultdict(int)
        for token, items in self._tokens_to_items.iteritems():
            index = token.find(query)
            if index >= 0:
                for item in items:
                    items_and_scores[item] = min(items_and_scores[item], -index)

        query_length = len(query)
        result = []
        for item, score in sorted(items_and_scores.items(), key=itemgetter(1)):
            match = self._construct_match_for_item(item, -score)
            matched_string = match.matched_string
            if not self._case_sensitive:
                matched_string = matched_string.lower()
            match.substrings = [
                (index, index + query_length)
                for index in all_occurrences_of_string(query, matched_string)
            ]
            result.append(match)

        return result


class FuzzyIndex(IndexBase):
    """TODO: document"""

    def __init__(self):
        super(FuzzyIndex, self).__init__()
        self._tokens_to_items = defaultdict(list)

    def _add_token_for_item(self, token, item):
        self._tokens_to_items[token].append(item)

    def search(self, query):
        raise NotImplementedError

from collections import defaultdict
from operator import itemgetter
from selecta.matches import Match
from selecta.utils import each_index_of_string, list_packer


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
        self._tokens_to_items = defaultdict(list)

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
        self._tokens_to_items[token].append(item)

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

    def _add_token_for_item(self, token, item):
        if not self._case_sensitive:
            token = token.lower()
        super(SubstringIndex, self)._add_token_for_item(token, item)

    def search(self, query):
        if not self._case_sensitive:
            query = query.lower()

        items_and_scores = self._score_items(query)
        return self._create_matches_from(query, items_and_scores)

    def _create_matches_from(self, query, items_and_scores):
        """Given a query string and a dictionary mapping matched items to their
        scores, returns an appropriate list of highlighted matches, sorted by
        score."""
        query_length = len(query)
        result = []
        for item, score in sorted(items_and_scores.items(), key=itemgetter(1)):
            match = self._construct_match_for_item(item, -score)
            matched_string = match.matched_string
            if not self._case_sensitive:
                matched_string = matched_string.lower()
            match.substrings = [
                (index, index + query_length)
                for index in each_index_of_string(query, matched_string)
            ]
            result.append(match)
        return result

    def _score_items(self, query):
        """Given a query, returns a dictionary that contains all the items
        where at least one token of the item matches the query, along with
        the scores of the matches.
        """
        result = defaultdict(int)
        for token, items in self._tokens_to_items.iteritems():
            index = token.find(query)
            if index >= 0:
                for item in items:
                    result[item] = min(result[item], -index)
        return result


class FuzzyIndex(IndexBase):
    """TODO: document"""

    def __init__(self):
        super(FuzzyIndex, self).__init__()
        self._tokens_to_items = defaultdict(list)

    def _add_token_for_item(self, token, item):
        super(FuzzyIndex, self)._add_token_for_item(token.lower(), item)

    def _create_matches_from(self, prepared_query, items_and_scores):
        """Given a prepared query string and a dictionary mapping matched items
        to their scores and the matched ranges, returns an appropriate list of
        highlighted matches, sorted by score."""
        result = []
        for item, score in sorted(items_and_scores.items(), key=itemgetter(1)):
            match = self._construct_match_for_item(item, score)
            matched_string = match.matched_string.lower()
            _, matched_range = self._score_token(matched_string, prepared_query)
            if matched_range is not None:
                match.substrings = [matched_range]
            result.append(match)
        return result

    def _find_end_of_match(self, rest, token, start):
        """Finds the end of a potential match in the given token.

        Args:
            rest (str): the remaining characters in the query string that have
                not been processed yet
            token (str): the token being matched
            start (int): the index of the character in the token that matches
                the first character of the query string

        Returns:
            tuple: the score of the match and the end of the matched substring,
                or ``(None, None)`` if the token does not match the remaining
                characters of the query.
        """
        score = 1
        last_match_type = None

        for char in rest:
            end = token.find(char, start+1)
            if end < 0:
                return None, None

            if end == start+1:
                # This is a sequential match. These matches are worth 2
                # points only.
                if last_match_type != "sequential":
                    last_match_type = "sequential"
                    score += 1
            else:
                last_match_type = "normal"
                score += (end - start)

            start = end
        return score, end

    def _prepare_query(self, query):
        """Given a query string, returns some pre-computed information that
        is used by the searching and scoring routines in this index.

        Args:
            query (str): the query to prepare

        Returns:
            tuple: a tuple containing the first character of the query and
                a list with the remaining characters of the query
        """
        if query:
            query_chars = list(query.lower())
            return query_chars[0], query_chars[1:]
        else:
            return None, []

    def _score_items(self, prepared_query):
        """Given a prepared query, returns a dictionary that contains all the
        items where at least one token of the item matches the query, along
        with the scores of the matches and the corresponding matched ranges.
        """
        result = {}
        for token, items in self._tokens_to_items.iteritems():
            score, matched_range = self._score_token(token, prepared_query)
            if matched_range is not None:
                for item in items:
                    if item not in result or result[item][0] < score:
                        result[item] = score, matched_range
        return result

    def _score_token(self, token, prepared_query):
        """Returns the score assigned to the given token for the given
        prepared query string.

        Args:
            token (str): the token to score
            prepared_query (tuple): the prepared query string returned by
                ``_prepare_query()``

        Returns:
            tuple: a tuple containing the score of the token and the matching
                range, or ``(None, None)`` if the token does not match the
                query
        """
        best_score, best_match = None, None

        first_char, rest = prepared_query
        if first_char:
            for match_start in each_index_of_string(first_char, token):
                score, match_end = self._find_end_of_match(rest, token, match_start)
                if match_end and (best_score is None or score < best_score):
                    best_score = score
                    best_match = match_start, match_end+1

        return best_score, best_match

    def search(self, query):
        prepared_query = self._prepare_query(query)
        items_and_scores = self._score_items(prepared_query)
        return self._create_matches_from(prepared_query, items_and_scores)

    def score_token(self, token, query):
        """Returns the score assigned to the given token for the given query
        string.

        Args:
            token (str): the token to score
            query (str): the query string

        Returns:
            tuple: a tuple containing the score of the token and the matching
                range, or ``(None, None)`` if the token does not match the
                query
        """
        return self._score_token(token, self._prepare_query(query))

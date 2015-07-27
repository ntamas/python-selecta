import unittest

from selecta.utils import each_index_of_string


class EachIndexOfStringTestCase(unittest.TestCase):
    def test_empty_corpus(self):
        self.assertEquals([], list(each_index_of_string("foo", "")))
        self.assertEquals([0], list(each_index_of_string("", "")))

    def test_empty_string(self):
        self.assertEquals([0], list(each_index_of_string("", "")))
        self.assertEquals([0, 1], list(each_index_of_string("", " ")))
        self.assertEquals([0, 1, 2, 3, 4], list(each_index_of_string("", " abc")))

    def test_nonempty_corpus_and_string(self):
        corpus = "spam ham bacon"
        self.assertEquals([5], list(each_index_of_string("ham", corpus)))
        self.assertEquals([2, 6], list(each_index_of_string("am", corpus)))
        self.assertEquals([2, 6, 10], list(each_index_of_string("a", corpus)))


if __name__ == "__main__":
    unittest.main()

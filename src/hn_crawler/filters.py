"""Pure title filters that preserve entries and their original ranks."""

from collections.abc import Iterable

from hn_crawler.models import Entry


def count_words(title: str) -> int:
    """Count whitespace-separated tokens containing a Unicode letter or digit.

    Punctuation does not split tokens: self-explained counts once, while
    a standalone hyphen does not count.
    """
    return sum(any(char.isalnum() for char in token) for token in title.split())


def filter_long_titles(entries: Iterable[Entry]) -> list[Entry]:
    """Return titles over five words, by comments descending then rank ascending."""
    return sorted(
        (entry for entry in entries if count_words(entry.title) > 5),
        key=lambda entry: (-entry.comments, entry.number),
    )


def filter_short_titles(entries: Iterable[Entry]) -> list[Entry]:
    """Return titles of at most five words, by points descending then rank ascending."""
    return sorted(
        (entry for entry in entries if count_words(entry.title) <= 5),
        key=lambda entry: (-entry.points, entry.number),
    )

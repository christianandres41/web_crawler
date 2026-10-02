"""Contract tests for title length, ordering, and input preservation."""

import pytest

from hn_crawler.filters import count_words, filter_long_titles, filter_short_titles
from hn_crawler.models import Entry


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("", 0),
        (" \t\n ", 0),
        ("- + & ... 🚀", 0),
        ("This is - a self-explained example", 5),
        ("one two three four five", 5),
        ("one two three four five six", 6),
        ("  one\ttwo\nthree\u00a0four  ", 4),
        ("Hello, (world)!", 2),
        ("don't self-explained C++ foo/bar", 4),
        ("café 日本語 naïve", 3),
        ("Python 3.12 in 2026", 4),
        ("🚀launch 🚀 +", 1),
    ],
)
def test_count_words(title, expected):
    assert count_words(title) == expected


@pytest.fixture
def entries():
    # Input order and the other metric deliberately disagree with expected sorting.
    return [
        Entry(8, "one two three four five six", 1000, 9),
        Entry(6, "This is - a self-explained example", 20, 1000),
        Entry(4, "six words belong in this title", 1, 30),
        Entry(2, "one two three four five", 20, 1),
        Entry(1, "another title that contains six words", 500, 9),
        Entry(9, "short title", 80, 0),
    ]


def test_long_titles_order_by_comments_then_original_rank(entries):
    assert filter_long_titles(entries) == [entries[2], entries[4], entries[0]]


def test_short_titles_order_by_points_then_original_rank(entries):
    assert filter_short_titles(entries) == [entries[5], entries[3], entries[1]]


@pytest.mark.parametrize("operation", [filter_long_titles, filter_short_titles])
def test_filters_preserve_input_and_entry_objects(operation, entries):
    original = entries.copy()

    result = operation(entries)

    assert entries == original
    assert result is not entries
    assert all(any(item is entry for entry in entries) for item in result)


@pytest.mark.parametrize("operation", [filter_long_titles, filter_short_titles])
def test_filters_accept_generators(operation, entries):
    assert operation(entry for entry in entries) == operation(entries)


@pytest.mark.parametrize("operation", [filter_long_titles, filter_short_titles])
def test_empty_input(operation):
    assert operation([]) == []


def test_filters_partition_entries_including_zero_word_titles(entries):
    entries += [Entry(10, "", 0, 0), Entry(11, "- 🚀", 0, 0)]

    long_titles = filter_long_titles(entries)
    short_titles = filter_short_titles(entries)

    assert set(long_titles).isdisjoint(short_titles)
    assert set(long_titles) | set(short_titles) == set(entries)
    assert short_titles[-2:] == entries[-2:]


def test_no_matching_titles():
    assert filter_long_titles([Entry(1, "short", 0, 0)]) == []
    assert filter_short_titles([Entry(1, "one two three four five six", 0, 0)]) == []

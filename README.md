# Hacker News crawler

A Python tool that can scrape the first 30 entries from
<https://news.ycombinator.com/>, filter them by title length, and record usage.

## Development setup

Requires Python 3.10 or newer. From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
```

On Windows, activate with `.venv\Scripts\activate` instead.

Verify the installed package with:

```sh
python -c "import hn_crawler"
```

## Expected behavior

- Extract original rank (`number`), title, points, and comment count.
- Return all entries, or filter titles with more than five words and sort by
  comments, or filter titles with at most five words and sort by points.
- Sort descending, breaking ties by original rank.
- Count whitespace-separated tokens containing at least one letter or digit.
  Standalone symbols do not count; hyphenated words count once. For example,
  `This is - a self-explained example` contains five words.
- Store a UTC request timestamp, filter identifier, outcome, duration, entry
  counts, and an optional error category in SQLite for each invocation.

Commands:

```sh
hn-crawler --filter all
hn-crawler --filter long-titles
hn-crawler --filter short-titles --database usage.sqlite3
```

The CLI will emit JSON on stdout and diagnostics on stderr.

## Using the title filters

The functions accept an iterable of entries and return a new sorted list without
changing the input or renumbering entries:

```python
from hn_crawler.models import Entry
from hn_crawler.filters import count_words, filter_long_titles, filter_short_titles

entries = [
    Entry(number=1, title="This is - a self-explained example", points=12, comments=3),
    Entry(number=2, title="A longer title with six words", points=8, comments=10),
]

assert count_words(entries[0].title) == 5
assert filter_short_titles(entries) == [entries[0]]
assert filter_long_titles(entries) == [entries[1]]
```

Letters and digits from Unicode are supported. Tabs, newlines, and nonbreaking
spaces also separate words. Empty or symbol-only titles have zero words and
therefore fall into the short-title filter.

## Design decisions

The `src/` layout keeps package code separate from tests and ensures tests use
the installed package.

Entries use a frozen dataclass to prevent accidental changes to scraped values.
Filtering uses pure functions so it can be tested without network or storage.
Each filter sorts by its metric descending and original rank ascending for ties.
HTTP fetching, HTML parsing, and SQLite persistence will have separate boundaries.
The intended stack is requests, Beautiful Soup, and standard-library sqlite3 and
argparse. One front-page fetch per invocation is sufficient for this scope.

Automated tests will use local fixtures rather than depend on changing live data.
Legitimately absent scores or comment counts will be treated as zero. Invalid
required fields, fewer than 30 parsed entries, and storage failures will produce
explicit errors instead of silently returning an incomplete result.

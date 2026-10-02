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

## Design decisions

The `src/` layout keeps package code separate from tests and ensures tests use
the installed package.

Filtering will use pure functions so it can be tested without network or storage.
HTTP fetching, HTML parsing, and SQLite persistence will have separate boundaries.
The intended stack is requests, Beautiful Soup, and standard-library sqlite3 and
argparse. One front-page fetch per invocation is sufficient for this scope.

Automated tests will use local fixtures rather than depend on changing live data.
Legitimately absent scores or comment counts will be treated as zero. Invalid
required fields, fewer than 30 parsed entries, and storage failures will produce
explicit errors instead of silently returning an incomplete result.

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

## Scraping the front page


```python
from hn_crawler.scraper import crawl_front_page
from hn_crawler.filters import filter_long_titles

entries = crawl_front_page()
filtered = filter_long_titles(entries)
```

`fetch_front_page()` retrieves HTML, `parse_front_page(html)` parses an existing
snapshot without network access, and `crawl_front_page()` combines the two.
The scraper returns exactly 30 entries, retaining ranks 1 through 30. It ignores
extra entries and never follows story links or pagination.

HTTP requests use a descriptive User-Agent, a 5-second connection timeout, and a
15-second read timeout, with no automatic retries. A read timeout measures socket
inactivity, not total elapsed time. Network and unsuccessful HTTP responses raise
`FetchError`; incomplete pages or malformed entry data raise `ParseError`. Both
inherit from `ScraperError`.

Parsing pairs each story row with its immediately following metadata row. Missing
scores or comment links and `discuss` become zero, including job listings. A
missing metadata row, blank title, invalid rank, or malformed present count raises
an error. Entries are never skipped to fill the result with later stories.

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

## Recording usage

SQLite storage is implemented. No additional database service or dependency is required.

```python
from datetime import datetime, timezone
from time import perf_counter

from hn_crawler.storage import UsageRecord, UsageStore

requested_at = datetime.now(timezone.utc)
started = perf_counter()
# Perform the crawl and selected filter here.
UsageStore("usage.sqlite3").record(UsageRecord(
    request_timestamp=requested_at,
    filter_id="all",
    outcome="success",
    duration_ms=int((perf_counter() - started) * 1000),
    fetched_count=30,
    result_count=30,
))
```

The counts above illustrate a successful unfiltered request; callers must supply
actual counts. For a failed fetch, record `outcome="failure"`, zero counts, and
`error_category="FetchError"`. A failed operation after fetching can retain its
fetched count. Duration uses a monotonic clock, independently of the wall-clock
request timestamp.

The `usage_records` table contains:

| Column | Meaning |
| --- | --- |
| `id` | Integer primary key identifying a stored invocation |
| `request_timestamp` | Request start as ISO 8601 text, normalized to UTC |
| `filter_id` | `all`, `long-titles`, or `short-titles` |
| `outcome` | `success` or `failure` |
| `duration_ms` | Nonnegative integer elapsed milliseconds |
| `fetched_count` | Number of entries successfully fetched and parsed |
| `result_count` | Number of resulting entries, at most the fetched count |
| `error_category` | Optional error classification; null by default |

`UsageRecord` is immutable and rejects naive timestamps, unknown filters/outcomes,
and invalid counts or durations with `ValueError`. Each `UsageStore.record()`
call creates the database/table if needed, commits one parameterized insert, and
closes its connection. Reopening the same file preserves earlier records.
The parent directory must exist; empty paths and `:memory:` are rejected because
usage must survive closed connections. SQLite waits up to five seconds for locks.
Database failures raise `StorageError` with the original SQLite exception attached;
they are never silently ignored. An unavailable database cannot record its own
failure, so the CLI will need to report that error to the user.

Local `.sqlite3` files and their sidecars are ignored by Git. Tests use temporary
SQLite files to check persisted fields, UTC conversion, multiple connections,
success/failure records, parameterized values, and write failures.

## Design decisions

The `src/` layout keeps package code separate from tests and ensures tests use
the installed package.

Entries use a frozen dataclass to prevent accidental changes to scraped values.
Filtering uses pure functions so it can be tested without network or storage.
Each filter sorts by its metric descending and original rank ascending for ties.
HTTP fetching, HTML parsing, and SQLite persistence have separate boundaries.
The scraper uses requests and Beautiful Soup with Python’s built-in HTML parser.
Storage uses standard-library sqlite3; the CLI will use argparse. One front-page fetch per invocation is sufficient for this scope.

Automated tests use a synthetic HTML fixture and mocked HTTP rather than depend
on changing live data. The fixture includes 31 entries, a job listing, singular
and plural counts, HTML entities, and absent optional metadata.
Legitimately absent scores or comment counts will be treated as zero. Invalid
required fields, fewer than 30 parsed entries, and storage failures will produce
explicit errors instead of silently returning an incomplete result.

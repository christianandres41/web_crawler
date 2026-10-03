"""Command-line orchestration for scraping, filtering, and usage recording."""

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from time import perf_counter

from hn_crawler.filters import filter_long_titles, filter_short_titles
from hn_crawler.scraper import ScraperError, crawl_front_page
from hn_crawler.storage import StorageError, UsageRecord, UsageStore


def main(argv: list[str] | None = None) -> int:
    """Run a request; return 0 on success, 1 on crawl failure, or 3 on storage failure."""
    parser = argparse.ArgumentParser(
        prog="hn-crawler", description="Scrape and filter the first 30 Hacker News entries."
    )
    parser.add_argument(
        "--filter", choices=("all", "long-titles", "short-titles"), default="all",
        help="all (default), long titles by comments, or short titles by points",
    )
    parser.add_argument(
        "--database", default="usage.sqlite3",
        help="SQLite file for usage records (default: usage.sqlite3)",
    )
    args = parser.parse_args(argv)
    try:
        store = UsageStore(args.database)
    except ValueError as exc:
        parser.error(str(exc))

    requested_at = datetime.now(timezone.utc)
    started = perf_counter()
    entries = []
    results = []
    error = None
    try:
        entries = crawl_front_page()
        if args.filter == "long-titles":
            results = filter_long_titles(entries)
        elif args.filter == "short-titles":
            results = filter_short_titles(entries)
        else:
            results = entries
    except ScraperError as exc:
        error = exc
        print(f"hn-crawler: {exc}", file=sys.stderr)

    usage = UsageRecord(
        request_timestamp=requested_at,
        filter_id=args.filter,
        outcome="failure" if error else "success",
        duration_ms=int((perf_counter() - started) * 1000),
        fetched_count=len(entries),
        result_count=len(results),
        error_category=type(error).__name__ if error else None,
    )
    try:
        store.record(usage)
    except StorageError as exc:
        print(f"hn-crawler: {exc}", file=sys.stderr)
        return 3

    if error:
        return 1
    print(json.dumps([asdict(entry) for entry in results], ensure_ascii=False, indent=2))
    return 0

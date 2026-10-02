"""Fetch one Hacker News front page and parse its first 30 entries."""

import re

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from hn_crawler.models import Entry

FRONT_PAGE_URL = "https://news.ycombinator.com/"
ENTRY_COUNT = 30


class ScraperError(Exception):
    """Base error for fetching or parsing the front page."""


class FetchError(ScraperError):
    """The HTTP request failed."""


class ParseError(ScraperError):
    """The page cannot supply 30 valid entries."""


def fetch_front_page() -> str:
    """Fetch HTML with 5-second connect and 15-second read timeouts.

    Read timeouts limit socket inactivity, not total request duration.
    No pagination or automatic retries are performed.
    """
    try:
        with requests.get(
            FRONT_PAGE_URL,
            timeout=(5, 15),
            headers={"User-Agent": "hn-crawler/0.1.0"},
        ) as response:
            response.raise_for_status()
            response.encoding = "utf-8"
            return response.text
    except requests.RequestException as exc:
        raise FetchError(f"Could not fetch the Hacker News front page: {exc}") from exc


def _parse_count(text: str, label: str) -> int:
    match = re.fullmatch(rf"([0-9]+)\s+{label}s?", text.strip())
    if match is None:
        raise ParseError(f"Invalid {label} count: {text!r}")
    return int(match[1])


def _parse_entry(row: Tag, expected_rank: int) -> Entry:
    rank = row.select_one(".rank")
    title_link = row.select_one(".titleline > a")
    if rank is None or rank.get_text(strip=True) != f"{expected_rank}.":
        raise ParseError(f"Missing or invalid rank for entry {expected_rank}")
    title = title_link.get_text(strip=True) if title_link is not None else ""
    if not title:
        raise ParseError(f"Missing title for entry {expected_rank}")

    # Never search past the adjacent row: doing so can steal the next story's data.
    metadata_row = row.find_next_sibling("tr")
    metadata = (
        metadata_row.select_one("td.subtext")
        if metadata_row is not None and "athing" not in metadata_row.get("class", [])
        else None
    )
    if metadata is None:
        raise ParseError(f"Missing metadata row for entry {expected_rank}")

    score = metadata.select_one(".score")
    points = _parse_count(score.get_text(" ", strip=True), "point") if score else 0
    comments = 0
    for link in metadata.select('a[href^="item?id="]'):
        text = link.get_text(" ", strip=True)
        if text == "discuss":
            break
        if "comment" in text.lower():
            comments = _parse_count(text, "comment")
            break

    return Entry(expected_rank, title, points, comments)


def parse_front_page(html: str) -> list[Entry]:
    """Parse exactly the first 30 story rows, failing instead of skipping bad rows."""
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tr.athing")[:ENTRY_COUNT]
    if len(rows) < ENTRY_COUNT:
        raise ParseError(f"Expected {ENTRY_COUNT} entries, found {len(rows)}")
    return [_parse_entry(row, rank) for rank, row in enumerate(rows, start=1)]


def crawl_front_page() -> list[Entry]:
    """Fetch once and return the first 30 entries in original rank order."""
    return parse_front_page(fetch_front_page())

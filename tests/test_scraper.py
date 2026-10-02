"""Offline parser fixtures and mocked transport tests."""

from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from bs4 import BeautifulSoup

from hn_crawler.models import Entry
from hn_crawler.scraper import (
    FRONT_PAGE_URL,
    FetchError,
    ParseError,
    crawl_front_page,
    fetch_front_page,
    parse_front_page,
)


@pytest.fixture
def html():
    return (Path(__file__).parent / "fixtures" / "front_page.html").read_text(
        encoding="utf-8"
    )


@pytest.fixture
def soup(html):
    return BeautifulSoup(html, "html.parser")


@pytest.fixture
def http_get(monkeypatch):
    get = Mock()
    monkeypatch.setattr("hn_crawler.scraper.requests.get", get)
    return get


def respond(http_get, html, status=200):
    response = requests.Response()
    response.status_code = status
    response._content = html.encode("utf-8")
    response._content_consumed = True
    response.url = FRONT_PAGE_URL
    http_get.return_value = response
    return response


def test_first_30_entries_and_metadata_pairing(html):
    entries = parse_front_page(html)

    assert len(entries) == 30
    assert entries[0] == Entry(1, "Café & Python <3", 101, 7)
    assert entries[1] == Entry(2, "Story 2", 1, 1)
    assert entries[2] == Entry(3, "Story 3", 103, 0)
    assert entries[3] == Entry(4, "Hiring a Python developer", 0, 0)
    assert entries[4] == Entry(5, "Story 5", 0, 35)
    assert entries[5:] == [
        Entry(i, f"Story {i}", 100 + i, i * 7) for i in range(6, 31)
    ]


def test_extra_malformed_entry_is_not_parsed(soup):
    soup.select("tr.athing")[30].clear()
    assert len(parse_front_page(str(soup))) == 30


@pytest.mark.parametrize("html", ["", "<html>Maintenance</html>", "<table></table>"])
def test_non_front_pages_fail(html):
    with pytest.raises(ParseError, match="Expected 30 entries, found 0"):
        parse_front_page(html)


def test_fewer_than_30_entries_fail(soup):
    for row in soup.select("tr.athing")[29:]:
        row.decompose()
    with pytest.raises(ParseError, match="Expected 30 entries, found 29"):
        parse_front_page(str(soup))


@pytest.mark.parametrize("selector", [".rank", ".titleline > a"])
def test_missing_required_fields_fail(soup, selector):
    soup.select_one(selector).decompose()
    with pytest.raises(ParseError, match="entry 1"):
        parse_front_page(str(soup))


@pytest.mark.parametrize("rank", ["bad", "0.", "2.", "-1."])
def test_invalid_rank_fails(soup, rank):
    soup.select_one(".rank").string = rank
    with pytest.raises(ParseError, match="rank"):
        parse_front_page(str(soup))


def test_blank_title_fails(soup):
    soup.select_one(".titleline > a").string = "  "
    with pytest.raises(ParseError, match="Missing title"):
        parse_front_page(str(soup))


@pytest.mark.parametrize("remove_spacer", [False, True])
def test_missing_metadata_does_not_borrow_next_story(soup, remove_spacer):
    row = soup.select_one("tr.athing")
    row.find_next_sibling("tr").decompose()
    if remove_spacer:
        row.find_next_sibling("tr").decompose()
    with pytest.raises(ParseError, match="Missing metadata row for entry 1"):
        parse_front_page(str(soup))


@pytest.mark.parametrize("score", ["many points", "-1 points", "1.5 points"])
def test_invalid_present_score_fails(soup, score):
    soup.select_one(".score").string = score
    with pytest.raises(ParseError, match="Invalid point count"):
        parse_front_page(str(soup))


def test_invalid_present_comments_fail(soup):
    soup.select_one("a.comments").string = "many comments"
    with pytest.raises(ParseError, match="Invalid comment count"):
        parse_front_page(str(soup))


def test_fetch_uses_timeouts_user_agent_and_utf8(http_get, html):
    response = respond(http_get, html)
    response.encoding = "iso-8859-1"

    assert fetch_front_page() == html
    http_get.assert_called_once_with(
        FRONT_PAGE_URL, timeout=(5, 15), headers={"User-Agent": "hn-crawler/0.1.0"}
    )


@pytest.mark.parametrize("status", [403, 429, 500])
def test_http_failure(http_get, status):
    respond(http_get, "Unavailable", status)
    with pytest.raises(FetchError) as error:
        fetch_front_page()
    assert isinstance(error.value.__cause__, requests.HTTPError)
    assert http_get.call_count == 1


@pytest.mark.parametrize("error_type", [requests.Timeout, requests.ConnectionError])
def test_transport_failure(http_get, error_type):
    http_get.side_effect = error_type("network failure")
    with pytest.raises(FetchError) as error:
        fetch_front_page()
    assert isinstance(error.value.__cause__, error_type)
    assert http_get.call_count == 1


def test_crawl_fetches_once_and_parses(http_get, html):
    respond(http_get, html)
    assert crawl_front_page() == parse_front_page(html)
    assert http_get.call_count == 1


def test_crawl_propagates_parse_errors(http_get):
    respond(http_get, "<html>Maintenance</html>")
    with pytest.raises(ParseError):
        crawl_front_page()


def test_author_name_is_not_a_comment_count(soup):
    soup.select_one('a[href="user?id=author"]').string = "commentator"
    assert parse_front_page(str(soup))[0].comments == 7

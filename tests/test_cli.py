"""Exercise real parsing, filtering, and SQLite storage with mocked HTTP."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from hn_crawler.cli import main


@pytest.fixture
def http_get(monkeypatch):
    html = (Path(__file__).parent / "fixtures/front_page.html").read_text(
        encoding="utf-8"
    )
    # Put multiple long titles into the fixture to exercise comment sorting.
    html = html.replace("Story 2<", "one two three four five six<")
    html = html.replace("Story 6<", "another title that has six words<")
    response = requests.Response()
    response.status_code = 200
    response._content = html.encode("utf-8")
    response._content_consumed = True
    get = Mock(return_value=response)
    monkeypatch.setattr("hn_crawler.scraper.requests.get", get)
    return get


def records(database):
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(
            "SELECT * FROM usage_records ORDER BY id"
        )]


@pytest.mark.parametrize(
    ("filter_id", "expected"),
    [
        ("all", list(range(1, 31))),
        ("long-titles", [6, 2]),
        ("short-titles", list(range(30, 6, -1)) + [3, 1, 4, 5]),
    ],
)
def test_filter_output_and_usage(tmp_path, capsys, http_get, filter_id, expected):
    database = tmp_path / "usage.sqlite3"
    before = datetime.now(timezone.utc)
    assert main(["--filter", filter_id, "--database", str(database)]) == 0
    after = datetime.now(timezone.utc)
    output = capsys.readouterr()
    data = json.loads(output.out)
    assert output.err == ""
    assert [entry["number"] for entry in data] == expected
    assert all(set(entry) == {"number", "title", "points", "comments"} for entry in data)
    if filter_id == "all":
        assert data[0] == {
            "number": 1, "title": "Café & Python <3", "points": 101, "comments": 7
        }
    row, = records(database)
    assert row["filter_id"] == filter_id
    assert row["outcome"] == "success"
    assert row["fetched_count"] == 30
    assert row["result_count"] == len(expected)
    assert row["error_category"] is None
    assert before <= datetime.fromisoformat(row["request_timestamp"]) <= after
    assert row["duration_ms"] >= 0
    http_get.assert_called_once()


def test_defaults_and_repeated_invocations(tmp_path, monkeypatch, capsys, http_get):
    monkeypatch.chdir(tmp_path)
    assert main([]) == 0
    assert main([]) == 0
    rows = records(tmp_path / "usage.sqlite3")
    assert [row["filter_id"] for row in rows] == ["all", "all"]
    assert http_get.call_count == 2


def test_empty_filter_is_success(tmp_path, capsys, http_get):
    response = http_get.return_value
    response._content = response.content.replace(
        b"one two three four five six", b"short"
    ).replace(b"another title that has six words", b"short")
    database = tmp_path / "usage.sqlite3"
    assert main(["--filter", "long-titles", "--database", str(database)]) == 0
    assert json.loads(capsys.readouterr().out) == []
    row, = records(database)
    assert row["outcome"] == "success"
    assert row["fetched_count"] == 30
    assert row["result_count"] == 0


@pytest.mark.parametrize("failure", ["timeout", "http", "parse"])
def test_failed_requests_are_recorded(tmp_path, capsys, http_get, failure):
    if failure == "timeout":
        http_get.side_effect = requests.Timeout("timed out")
    elif failure == "http":
        http_get.return_value.status_code = 503
    else:
        http_get.return_value._content = b"<html>Maintenance</html>"
    database = tmp_path / "usage.sqlite3"
    assert main(["--filter", "short-titles", "--database", str(database)]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "hn-crawler:" in output.err
    row, = records(database)
    assert row["outcome"] == "failure"
    assert row["filter_id"] == "short-titles"
    assert row["error_category"] == ("ParseError" if failure == "parse" else "FetchError")
    assert row["fetched_count"] == row["result_count"] == 0


@pytest.mark.parametrize("crawl_fails", [False, True])
def test_storage_failure_suppresses_output(tmp_path, capsys, http_get, crawl_fails):
    if crawl_fails:
        http_get.side_effect = requests.ConnectionError("offline")
    database = tmp_path / "missing" / "usage.sqlite3"
    assert main(["--database", str(database)]) == 3
    output = capsys.readouterr()
    assert output.out == ""
    assert "Could not record usage" in output.err
    if crawl_fails:
        assert "Could not fetch" in output.err


@pytest.mark.parametrize(
    ("arguments", "exit_code"),
    [
        (["--help"], 0),
        (["--filter", "invalid"], 2),
        (["--database", ":memory:"], 2),
        (["--database", ""], 2),
        (["--unknown"], 2),
    ],
)
def test_argument_handling_has_no_side_effects(
    tmp_path, monkeypatch, capsys, http_get, arguments, exit_code
):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == exit_code
    http_get.assert_not_called()
    assert not list(tmp_path.iterdir())
    output = capsys.readouterr()
    assert output.out if exit_code == 0 else output.err


def test_duration_uses_monotonic_clock(tmp_path, monkeypatch, capsys, http_get):
    ticks = iter([10.0, 10.125])
    monkeypatch.setattr("hn_crawler.cli.perf_counter", lambda: next(ticks))
    database = tmp_path / "usage.sqlite3"
    assert main(["--database", str(database)]) == 0
    assert records(database)[0]["duration_ms"] == 125

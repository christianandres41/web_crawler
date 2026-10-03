"""Persistence tests use real SQLite files in pytest's temporary directory."""

import sqlite3
from contextlib import closing
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from hn_crawler.storage import StorageError, UsageRecord, UsageStore


@pytest.fixture
def usage():
    return UsageRecord(
        request_timestamp=datetime(2026, 10, 2, 9, 30, tzinfo=timezone(timedelta(hours=-5))),
        filter_id="long-titles",
        outcome="success",
        duration_ms=125,
        fetched_count=30,
        result_count=12,
    )


def read_records(database):
    with closing(sqlite3.connect(database)) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(
            "SELECT * FROM usage_records ORDER BY id"
        )]


def test_creates_database_and_persists_all_fields(tmp_path, usage):
    database = tmp_path / "usage.sqlite3"
    UsageStore(database).record(usage)

    assert read_records(database) == [{
        "id": 1,
        "request_timestamp": "2026-10-02T14:30:00.000000+00:00",
        "filter_id": "long-titles",
        "outcome": "success",
        "duration_ms": 125,
        "fetched_count": 30,
        "result_count": 12,
        "error_category": None,
    }]


def test_reopening_appends_success_and_failure_records(tmp_path, usage):
    database = tmp_path / "usage.sqlite3"
    UsageStore(database).record(usage)
    failure = replace(
        usage, filter_id="all", outcome="failure",
        fetched_count=0, result_count=0, error_category="FetchError",
    )
    UsageStore(str(database)).record(failure)
    UsageStore(database).record(replace(usage, filter_id="short-titles", result_count=0))

    rows = read_records(database)
    assert [row["id"] for row in rows] == [1, 2, 3]
    assert [row["filter_id"] for row in rows] == ["long-titles", "all", "short-titles"]
    assert rows[1]["outcome"] == "failure"
    assert rows[1]["error_category"] == "FetchError"
    assert rows[1]["fetched_count"] == rows[1]["result_count"] == 0
    assert rows[2]["outcome"] == "success"
    assert rows[2]["result_count"] == 0


def test_error_category_is_stored_as_data(tmp_path, usage):
    database = tmp_path / "usage.sqlite3"
    category = "error'); DROP TABLE usage_records; --"
    store = UsageStore(database)
    store.record(replace(usage, outcome="failure", error_category=category))
    store.record(usage)
    assert read_records(database)[0]["error_category"] == category
    assert len(read_records(database)) == 2


@pytest.mark.parametrize("target", ["directory", "missing-parent", "invalid-database"])
def test_storage_errors_are_explicit(tmp_path, usage, target):
    database = tmp_path / "usage.sqlite3"
    if target == "directory":
        database.mkdir()
    elif target == "missing-parent":
        database = tmp_path / "missing" / "usage.sqlite3"
    else:
        database.write_text("This is not a SQLite database.")

    with pytest.raises(StorageError) as error:
        UsageStore(database).record(usage)
    assert isinstance(error.value.__cause__, sqlite3.Error)


def test_failed_insert_does_not_change_existing_records(tmp_path, usage):
    database = tmp_path / "usage.sqlite3"
    store = UsageStore(database)
    store.record(usage)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("""
            CREATE TRIGGER reject_usage BEFORE INSERT ON usage_records
            BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END
        """)

    with pytest.raises(StorageError, match="simulated write failure"):
        store.record(usage)
    assert len(read_records(database)) == 1

    with closing(sqlite3.connect(database)) as connection:
        connection.execute("DROP TRIGGER reject_usage")
    store.record(usage)
    assert len(read_records(database)) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("request_timestamp", datetime(2026, 10, 2)),
        ("filter_id", "unknown"),
        ("outcome", "unknown"),
        ("duration_ms", -1),
        ("duration_ms", 1.5),
        ("fetched_count", -1),
        ("result_count", -1),
        ("result_count", 31),
        ("result_count", True),
    ],
)
def test_invalid_usage_is_rejected(usage, field, value):
    with pytest.raises(ValueError):
        replace(usage, **{field: value})


def test_usage_is_immutable(usage):
    with pytest.raises(FrozenInstanceError):
        usage.result_count = 5


@pytest.mark.parametrize("database", ["", ":memory:"])
def test_ephemeral_database_is_rejected(database):
    with pytest.raises(ValueError, match="file database"):
        UsageStore(database)

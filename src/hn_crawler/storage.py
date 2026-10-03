"""SQLite persistence for crawler usage, independent of scraping and filtering."""

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

FilterId = Literal["all", "long-titles", "short-titles"]
Outcome = Literal["success", "failure"]


@dataclass(frozen=True)
class UsageRecord:
    """One invocation, with a timezone-aware request start and elapsed milliseconds."""

    request_timestamp: datetime
    filter_id: FilterId
    outcome: Outcome
    duration_ms: int
    fetched_count: int
    result_count: int
    error_category: str | None = None

    def __post_init__(self) -> None:
        if self.request_timestamp.utcoffset() is None:
            raise ValueError("request_timestamp must be timezone-aware")
        if self.filter_id not in ("all", "long-titles", "short-titles"):
            raise ValueError("Unknown filter_id")
        if self.outcome not in ("success", "failure"):
            raise ValueError("Unknown outcome")
        for name in ("duration_ms", "fetched_count", "result_count"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.result_count > self.fetched_count:
            raise ValueError("result_count cannot exceed fetched_count")


class StorageError(Exception):
    """A usage record could not be persisted."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_records (
    id INTEGER PRIMARY KEY,
    request_timestamp TEXT NOT NULL,
    filter_id TEXT NOT NULL,
    outcome TEXT NOT NULL,
    duration_ms INTEGER NOT NULL,
    fetched_count INTEGER NOT NULL,
    result_count INTEGER NOT NULL,
    error_category TEXT
)
"""


class UsageStore:
    """Append usage records to a local SQLite file.

    Each call opens and closes its own connection. The database and table are
    created on first write; the parent directory must already exist.
    """

    def __init__(self, database: str | Path) -> None:
        self.database = str(database)
        if self.database in ("", ":memory:"):
            raise ValueError("Use a file database so usage survives closed connections")

    def record(self, usage: UsageRecord) -> None:
        """Commit one record, or raise StorageError without hiding the cause."""
        timestamp = usage.request_timestamp.astimezone(timezone.utc).isoformat(
            timespec="microseconds"
        )
        try:
            # The connection transaction context does not close the connection.
            with closing(sqlite3.connect(self.database, timeout=5)) as connection:
                with connection:
                    connection.execute(_SCHEMA)
                    connection.execute(
                        """
                        INSERT INTO usage_records (
                            request_timestamp, filter_id, outcome, duration_ms,
                            fetched_count, result_count, error_category
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            timestamp, usage.filter_id, usage.outcome,
                            usage.duration_ms, usage.fetched_count,
                            usage.result_count, usage.error_category,
                        ),
                    )
        except sqlite3.Error as exc:
            raise StorageError(f"Could not record usage in {self.database}: {exc}") from exc

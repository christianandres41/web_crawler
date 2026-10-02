"""Data shared by scraping and filtering operations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    """A front-page entry; number is its original rank, not its story ID."""

    number: int
    title: str
    points: int
    comments: int

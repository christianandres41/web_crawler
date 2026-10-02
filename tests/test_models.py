"""Contract tests for the shared entry model."""

from dataclasses import FrozenInstanceError

import pytest

from hn_crawler.models import Entry


def test_entry_is_immutable():
    entry = Entry(number=3, title="Example", points=10, comments=2)

    with pytest.raises(FrozenInstanceError):
        entry.points = 20

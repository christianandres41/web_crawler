"""Smoke check for the installed package scaffold."""

from importlib import import_module


def test_package_is_importable():
    assert import_module("hn_crawler").__name__ == "hn_crawler"

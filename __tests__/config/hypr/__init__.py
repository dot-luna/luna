"""Discover tests that mirror Hyprland's hidden configuration directory."""

from pathlib import Path
import unittest


def load_tests(loader, tests, pattern):
    directory = Path(__file__).parent / ".config/hypr"
    return unittest.TestLoader().discover(str(directory), pattern=pattern or "test*.py")

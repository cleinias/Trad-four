"""
conftest.py — Trad-Four shared test fixtures.

Provides a session-scoped BrickLibrary fixture and a has_vocab flag
for skipping tests that require the vocab data files.
"""

import warnings
import pytest

from python.config import DICT_PATH, SUB_PATH

has_vocab = DICT_PATH.exists() and SUB_PATH.exists()


@pytest.fixture(scope='session')
def lib():
    """Session-scoped BrickLibrary loaded from the local vocab files."""
    if not has_vocab:
        pytest.skip("Vocab data not found")
    from python.roadmap.brick_library import BrickLibrary
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        library = BrickLibrary()
        library.load(str(DICT_PATH), str(SUB_PATH))
    return library

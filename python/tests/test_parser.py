"""
test_parser.py — Trad-Four Phase 1a
Corpus-wide stress test for the .ls parser.
"""

import warnings
import os
import pytest
from python.leadsheet.parser import parse
from python.config import LEADSHEETS_DIR

LS_DIR = str(LEADSHEETS_DIR)
LS_FILES = [
    os.path.join(LS_DIR, f)
    for f in sorted(os.listdir(LS_DIR))
    if f.endswith('.ls')
]


@pytest.mark.parametrize('path', LS_FILES, ids=lambda p: os.path.basename(p))
def test_parse_no_exception(path):
    """Every .ls file in the corpus should parse without raising an exception."""
    ls = parse(path)
    assert ls is not None


@pytest.mark.parametrize('path', LS_FILES, ids=lambda p: os.path.basename(p))
def test_parse_has_chords(path):
    """Every parsed leadsheet should have at least one chord event."""
    ls = parse(path)
    assert len(ls.chord_timeline) > 0, f"No chords parsed in {os.path.basename(path)}"


@pytest.mark.parametrize('path', LS_FILES, ids=lambda p: os.path.basename(p))
def test_parse_no_warnings(path):
    """No unrecognized chord tokens should appear in any file."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        parse(path)
    unrecognized = [str(x.message) for x in w if 'Unrecognized' in str(x.message)]
    assert not unrecognized, f"Unrecognized tokens in {os.path.basename(path)}: {unrecognized}"


# --- Specific known-good files ---

def test_bye_bye_blackbird():
    ls = parse(os.path.join(LS_DIR, 'ByeByeBlackbird.ls'))
    assert ls.title == 'Bye Bye Blackbird'
    assert ls.composer == 'Ray Henderson'
    assert ls.beats_per_bar == 4
    assert ls.tempo == 160.0
    assert ls.total_bars == 32
    assert len(ls.chord_timeline) == 44


def test_take_five():
    ls = parse(os.path.join(LS_DIR, 'TakeFive.ls'))
    assert ls.title == 'Take Five'
    assert ls.beats_per_bar == 5
    assert ls.total_bars == 24
    # First bar: Ebm for 3 beats, Bbm7 for 2 beats
    bar1 = ls.chords_in_bar(1)
    assert len(bar1) == 2
    assert bar1[0].symbol == 'Ebm'
    assert float(bar1[0].duration) == 3.0
    assert bar1[1].symbol == 'Bbm7'
    assert float(bar1[1].duration) == 2.0


def test_autumn_leaves_gm():
    ls = parse(os.path.join(LS_DIR, 'AutumnLeavesGm.ls'))
    assert ls.title == 'Autumn Leaves'
    assert ls.raw_key == '-3'
    assert ls.total_bars == 32
    # Check maj7 normalization
    symbols = [c.symbol for c in ls.chord_timeline]
    assert 'Bbmaj7' in symbols
    assert 'Ebmaj7' in symbols


def test_chord_at_query():
    ls = parse(os.path.join(LS_DIR, 'ByeByeBlackbird.ls'))
    # Bar 2 beat 1 should be Gm7
    chord = ls.chord_at(2, 1.0)
    assert chord is not None
    assert chord.symbol == 'Gm7'
    # Bar 2 beat 3 should be C7
    chord = ls.chord_at(2, 3.0)
    assert chord is not None
    assert chord.symbol == 'C7'
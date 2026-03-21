"""
test_simple_parser.py — Tests for the .tls (Trad-four Lead Sheet) parser.
"""

import pytest
from python.leadsheet.parser import parse, parse_simple, LeadSheet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_tls(tmp_path, content, name="test.tls"):
    """Write a .tls file and return its path."""
    p = tmp_path / name
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Basic parsing
# ---------------------------------------------------------------------------

def test_minimal_chords_only(tmp_path):
    """Parse a .tls with just a chord grid (no header)."""
    p = _write_tls(tmp_path, "FM6 | Gm7 C7 | F6 |\n")
    ls = parse_simple(p)
    assert ls.total_bars == 3
    assert ls.chord_timeline[0].symbol == 'FM6'
    assert ls.chord_timeline[1].symbol == 'Gm7'
    assert ls.chord_timeline[2].symbol == 'C7'
    assert ls.chord_timeline[3].symbol == 'F6'


def test_full_header(tmp_path):
    """Parse with all header fields populated."""
    content = """\
title: Bye Bye Blackbird
composer: Ray Henderson
tempo: 160
meter: 4/4

FM6 | Gm7 C7 | F6 |
"""
    p = _write_tls(tmp_path, content)
    ls = parse_simple(p)
    assert ls.title == 'Bye Bye Blackbird'
    assert ls.composer == 'Ray Henderson'
    assert ls.tempo == 160.0
    assert ls.beats_per_bar == 4
    assert ls.beat_unit == 4
    assert ls.total_bars == 3


def test_comments_and_blank_lines(tmp_path):
    """Comments and extra blank lines are ignored."""
    content = """\
# This is a comment
title: Test

# Another comment
FM6 | Gm7 C7 |

F6 | Dm7 |
"""
    p = _write_tls(tmp_path, content)
    ls = parse_simple(p)
    assert ls.title == 'Test'
    assert ls.total_bars == 4


def test_continuation_slash(tmp_path):
    """The / token continues the previous chord."""
    content = """\
FM6 | / | Gm7 | / |
"""
    p = _write_tls(tmp_path, content)
    ls = parse_simple(p)
    # Bars 1-2: FM6 sustained over 2 bars
    assert ls.total_bars == 4
    bar1 = ls.chords_in_bar(1)
    assert len(bar1) == 1
    assert bar1[0].symbol == 'FM6'
    bar2 = ls.chords_in_bar(2)
    assert len(bar2) == 1
    assert bar2[0].symbol == 'FM6'
    # Bars 3-4: Gm7 sustained over 2 bars
    bar3 = ls.chords_in_bar(3)
    assert bar3[0].symbol == 'Gm7'
    bar4 = ls.chords_in_bar(4)
    assert bar4[0].symbol == 'Gm7'


def test_nc_chord(tmp_path):
    """NC (no-chord) markers are preserved."""
    content = "NC | Dm7 G7 | Cmaj7 |\n"
    p = _write_tls(tmp_path, content)
    ls = parse_simple(p)
    bar1 = ls.chords_in_bar(1)
    assert len(bar1) == 1
    assert bar1[0].symbol == 'NC'


def test_melody_section_ignored(tmp_path):
    """Everything after 'melody:' is ignored."""
    content = """\
title: Test

FM6 | Gm7 C7 |
melody:
c4 d4 e4 f4
this is not parsed
"""
    p = _write_tls(tmp_path, content)
    ls = parse_simple(p)
    assert ls.total_bars == 2
    assert len(ls.chord_timeline) == 3


def test_slash_chords(tmp_path):
    """Slash chords are parsed with bass_note."""
    content = "Gm7/F | C7/E | F6 |\n"
    p = _write_tls(tmp_path, content)
    ls = parse_simple(p)
    assert ls.chord_timeline[0].symbol == 'Gm7'
    assert ls.chord_timeline[0].bass_note == 'F'
    assert ls.chord_timeline[1].symbol == 'C7'
    assert ls.chord_timeline[1].bass_note == 'E'
    assert ls.chord_timeline[2].bass_note is None


def test_waltz_meter(tmp_path):
    """Non-4/4 meter is parsed correctly."""
    content = """\
meter: 3/4

Dm7 | G7 | Cmaj7 |
"""
    p = _write_tls(tmp_path, content)
    ls = parse_simple(p)
    assert ls.beats_per_bar == 3
    assert ls.beat_unit == 4
    assert float(ls.chord_timeline[0].duration) == 3.0


def test_defaults(tmp_path):
    """Default values are used when header is absent."""
    p = _write_tls(tmp_path, "Dm7 | G7 |\n")
    ls = parse_simple(p)
    assert ls.title == ''
    assert ls.composer == ''
    assert ls.tempo == 120.0
    assert ls.beats_per_bar == 4


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def test_parse_dispatches_tls(tmp_path):
    """parse() auto-dispatches on .tls extension."""
    content = """\
title: Dispatch Test

Dm7 | G7 | Cmaj7 |
"""
    p = _write_tls(tmp_path, content)
    ls = parse(p)
    assert ls.title == 'Dispatch Test'
    assert ls.total_bars == 3


def test_parse_dispatches_ls():
    """parse() still works for .ls files."""
    from python.config import LEADSHEETS_DIR
    ls_path = LEADSHEETS_DIR / 'ByeByeBlackbird.ls'
    if not ls_path.exists():
        pytest.skip("Lead sheet corpus not available")
    ls = parse(str(ls_path))
    assert ls.title == 'Bye Bye Blackbird'


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_file_not_found():
    """FileNotFoundError for missing file."""
    with pytest.raises(FileNotFoundError):
        parse('/nonexistent/path/test.tls')


def test_file_not_found_simple():
    """FileNotFoundError from parse_simple for missing file."""
    with pytest.raises(FileNotFoundError):
        parse_simple('/nonexistent/path/test.tls')


# ---------------------------------------------------------------------------
# End-to-end: .tls → CYK → KeySpans
# ---------------------------------------------------------------------------

def test_end_to_end_pipeline(tmp_path):
    """Parse a .tls file through the full roadmap pipeline."""
    import warnings
    from python.config import DICT_PATH as _DICT_PATH, SUB_PATH as _SUB_PATH
    from python.roadmap.brick_library import BrickLibrary
    from python.roadmap.cyk_parser import CYKParser
    from python.roadmap.post_processor import find_keys

    if not _DICT_PATH.exists():
        pytest.skip("Vocab data not available")

    # Bye Bye Blackbird chord changes (first 16 bars, simplified)
    content = """\
title: Bye Bye Blackbird
composer: Ray Henderson
tempo: 160
meter: 4/4

FM6 | Gm7 C7 | F6 | / |
F6 | Abdim7 | Gm7 | C7 |
Gm7 | Gm7/F | Gm7/F | C7 |
Gm7 | C7 | F6 | / |
"""
    p = _write_tls(tmp_path, content)
    ls = parse(p)

    assert ls.title == 'Bye Bye Blackbird'
    assert ls.total_bars == 16
    assert len(ls.chord_timeline) > 0

    # Load brick library and CYK parser
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        lib = BrickLibrary()
        lib.load(str(_DICT_PATH), str(_SUB_PATH))
    parser = CYKParser(lib)

    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        roadmap = parser.parse_leadsheet(ls.chord_timeline)
    assert len(roadmap) > 0

    # Run key detection
    key_spans = find_keys(roadmap, ls.total_bars)
    assert len(key_spans) > 0
    # The tune is in F major (pitch class 5), so we expect at least one F key span
    keys = [ks.key for ks in key_spans]
    assert 5 in keys

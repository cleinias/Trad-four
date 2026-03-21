"""
test_note_function.py — Trad-Four
Tests for note_function() classification: C / L / S / A / X / NC.

Run:
    pytest python/tests/test_note_function.py -v
"""

import pytest
from fractions import Fraction

from python.leadsheet.parser import ChordEvent
from python.leadsheet.annotator import annotate_chord, note_function


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(symbol: str, next_symbol: str | None = None) -> ChordEvent:
    """Create an annotated ChordEvent (and optional next event for context)."""
    event = ChordEvent(bar=1, beat=Fraction(1), symbol=symbol, duration=Fraction(4))
    next_ev = None
    if next_symbol:
        next_ev = ChordEvent(bar=2, beat=Fraction(1), symbol=next_symbol, duration=Fraction(4))
        annotate_chord(next_ev)
    annotate_chord(event, next_ev)
    return event


# ---------------------------------------------------------------------------
# Tests for Cmaj7 (chord tones: C=0, E=4, G=7, B=11)
# ---------------------------------------------------------------------------

class TestCmaj7:
    @pytest.fixture
    def cmaj7(self):
        return _make_event('Cmaj7')

    def test_chord_tone_c(self, cmaj7):
        """C (MIDI 60) over Cmaj7 → chord tone."""
        assert note_function(60, cmaj7) == 'C'

    def test_chord_tone_e(self, cmaj7):
        """E (MIDI 64) over Cmaj7 → chord tone."""
        assert note_function(64, cmaj7) == 'C'

    def test_chord_tone_g(self, cmaj7):
        """G (MIDI 67) over Cmaj7 → chord tone."""
        assert note_function(67, cmaj7) == 'C'

    def test_chord_tone_b(self, cmaj7):
        """B (MIDI 71) over Cmaj7 → chord tone."""
        assert note_function(71, cmaj7) == 'C'

    def test_scale_tone_d(self, cmaj7):
        """D (MIDI 62) over Cmaj7 → scale tone (ionian)."""
        assert note_function(62, cmaj7) == 'S'

    def test_scale_tone_a(self, cmaj7):
        """A (MIDI 69) over Cmaj7 → scale tone."""
        assert note_function(69, cmaj7) == 'S'

    def test_approach_fsharp(self, cmaj7):
        """F# (MIDI 66) over Cmaj7 → approach (half-step below G)."""
        assert note_function(66, cmaj7) == 'A'

    def test_approach_bb(self, cmaj7):
        """Bb (MIDI 70) over Cmaj7 → approach (half-step below B)."""
        assert note_function(70, cmaj7) == 'A'

    def test_approach_db(self, cmaj7):
        """Db (MIDI 61) over Cmaj7 → approach (half-step above C)."""
        assert note_function(61, cmaj7) == 'A'

    def test_approach_ab(self, cmaj7):
        """Ab (MIDI 68) over Cmaj7 → approach (half-step above G)."""
        assert note_function(68, cmaj7) == 'A'

    def test_outside_eb(self, cmaj7):
        """Eb (MIDI 63) over Cmaj7 → outside.
        Eb is a half-step below E (chord tone) but also a half-step above D.
        Wait — Eb is pc=3, E is pc=4: (3-4)%12 = 11, (4-3)%12 = 1 → half-step!
        So Eb IS an approach tone to E."""
        assert note_function(63, cmaj7) == 'A'


# ---------------------------------------------------------------------------
# Tests for Dm7 (chord tones: D=2, F=5, A=9, C=0)
# ---------------------------------------------------------------------------

class TestDm7:
    @pytest.fixture
    def dm7(self):
        return _make_event('Dm7')

    def test_chord_tone_d(self, dm7):
        assert note_function(62, dm7) == 'C'

    def test_chord_tone_f(self, dm7):
        assert note_function(65, dm7) == 'C'

    def test_chord_tone_a(self, dm7):
        assert note_function(69, dm7) == 'C'

    def test_chord_tone_c(self, dm7):
        assert note_function(60, dm7) == 'C'

    def test_approach_csharp(self, dm7):
        """C# (MIDI 61) → approach (half-step below D)."""
        assert note_function(61, dm7) == 'A'

    def test_approach_ab(self, dm7):
        """Ab (MIDI 68) → approach (half-step below A, pc=9)."""
        assert note_function(68, dm7) == 'A'


# ---------------------------------------------------------------------------
# NC (no chord) handling
# ---------------------------------------------------------------------------

class TestNoChord:
    def test_nc_returns_nc(self):
        event = _make_event('NC')
        assert note_function(60, event) == 'NC'


# ---------------------------------------------------------------------------
# Tests for G7 with approach tones
# ---------------------------------------------------------------------------

class TestG7:
    @pytest.fixture
    def g7(self):
        return _make_event('G7')

    def test_chord_tone_g(self, g7):
        assert note_function(67, g7) == 'C'

    def test_chord_tone_b(self, g7):
        assert note_function(71, g7) == 'C'

    def test_chord_tone_d(self, g7):
        assert note_function(62, g7) == 'C'

    def test_chord_tone_f(self, g7):
        assert note_function(65, g7) == 'C'

    def test_scale_tone_a(self, g7):
        """A (MIDI 69) over G7 → scale tone (mixolydian)."""
        assert note_function(69, g7) == 'S'


# ---------------------------------------------------------------------------
# Verify that approach tones are NOT scale tones
# ---------------------------------------------------------------------------

class TestApproachVsScale:
    def test_fsharp_not_scale_for_cmaj7(self):
        """F# is NOT in C ionian, so it's classified as approach, not scale."""
        event = _make_event('Cmaj7')
        result = note_function(66, event)
        assert result == 'A'
        assert result != 'S'

    def test_octave_equivalence(self):
        """Approach tones work across octaves."""
        event = _make_event('Cmaj7')
        # F# in different octaves
        assert note_function(42, event) == 'A'   # F#2
        assert note_function(54, event) == 'A'   # F#3
        assert note_function(66, event) == 'A'   # F#4
        assert note_function(78, event) == 'A'   # F#5

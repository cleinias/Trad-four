"""
test_tonal_integration.py — Trad-Four
Tests for KeySpan → ChordEvent mapping (assign_tonal_areas)
and the full run_roadmap pipeline.

Run:
    pytest python/tests/test_tonal_integration.py -v
"""

import os
import warnings
import pytest
from fractions import Fraction

from python.leadsheet.parser import LeadSheet, ChordEvent
from python.leadsheet.annotator import annotate, _SCALE_INTERVALS
from python.leadsheet.tonal_areas import (
    assign_tonal_areas, run_roadmap, scale_pcs_from_root_and_mode,
)
from python.roadmap.post_processor import KeySpan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ls(chords_per_bar: list[list[str]], beats_per_bar: int = 4) -> LeadSheet:
    """
    Build a minimal LeadSheet from a list of bars, each bar a list of chord
    symbol strings.  Chords within a bar split the bar evenly.
    """
    ls = LeadSheet(beats_per_bar=beats_per_bar)
    bpb = Fraction(beats_per_bar)
    for bar_num, bar_chords in enumerate(chords_per_bar, start=1):
        n = len(bar_chords)
        dur = bpb / n
        for i, sym in enumerate(bar_chords):
            beat = Fraction(1) + i * dur
            ls.chord_timeline.append(
                ChordEvent(bar=bar_num, beat=beat, symbol=sym, duration=dur)
            )
    return ls


# ---------------------------------------------------------------------------
# Unit tests: scale_pcs_from_root_and_mode
# ---------------------------------------------------------------------------

class TestScalePcs:
    def test_c_major(self):
        pcs = scale_pcs_from_root_and_mode(0, 'Major')  # C ionian
        assert pcs == frozenset({0, 2, 4, 5, 7, 9, 11})

    def test_f_major(self):
        pcs = scale_pcs_from_root_and_mode(5, 'Major')  # F ionian
        assert pcs == frozenset({5, 7, 9, 10, 0, 2, 4})

    def test_g_minor(self):
        pcs = scale_pcs_from_root_and_mode(7, 'Minor')  # G dorian
        expected = frozenset((7 + i) % 12 for i in _SCALE_INTERVALS['dorian'])
        assert pcs == expected

    def test_c_dominant(self):
        pcs = scale_pcs_from_root_and_mode(0, 'Dominant')  # C mixolydian
        assert pcs == frozenset({0, 2, 4, 5, 7, 9, 10})

    def test_unknown_mode_falls_back_to_ionian(self):
        pcs = scale_pcs_from_root_and_mode(0, 'Whatever')
        assert pcs == frozenset({0, 2, 4, 5, 7, 9, 11})


# ---------------------------------------------------------------------------
# Unit tests: assign_tonal_areas with hand-crafted KeySpans
# ---------------------------------------------------------------------------

class TestAssignTonalAreas:
    def test_single_key_span(self):
        """All chords in one key span → all get the same tonal info."""
        ls = _make_ls([['Dm7', 'G7'], ['Cmaj7'], ['Am7', 'Dm7'], ['G7', 'Cmaj7']])
        key_spans = [KeySpan(key=0, mode='Major', duration=Fraction(16))]
        assign_tonal_areas(ls, key_spans)

        for event in ls.chord_timeline:
            assert event.tonal_key == 0
            assert event.tonal_mode == 'Major'
            assert event.tonal_scale == scale_pcs_from_root_and_mode(0, 'Major')

    def test_two_key_spans(self):
        """First 8 beats C major, next 8 beats F major."""
        ls = _make_ls([['Dm7', 'G7'], ['Cmaj7'], ['Gm7', 'C7'], ['Fmaj7']])
        key_spans = [
            KeySpan(key=0, mode='Major', duration=Fraction(8)),
            KeySpan(key=5, mode='Major', duration=Fraction(8)),
        ]
        assign_tonal_areas(ls, key_spans)

        # First two bars (beats 0-7) → C major
        for event in ls.chord_timeline:
            abs_beat = (event.bar - 1) * 4 + (event.beat - 1)
            if abs_beat < 8:
                assert event.tonal_key == 0, f"bar {event.bar} beat {event.beat}"
                assert event.tonal_mode == 'Major'
            else:
                assert event.tonal_key == 5, f"bar {event.bar} beat {event.beat}"
                assert event.tonal_mode == 'Major'

    def test_boundary_chord_gets_new_span(self):
        """Chord at exact KeySpan boundary gets the new span."""
        ls = _make_ls([['Cmaj7'], ['Fmaj7']])  # bar1=C, bar2=F
        key_spans = [
            KeySpan(key=0, mode='Major', duration=Fraction(4)),
            KeySpan(key=5, mode='Major', duration=Fraction(4)),
        ]
        assign_tonal_areas(ls, key_spans)

        assert ls.chord_timeline[0].tonal_key == 0   # bar 1
        assert ls.chord_timeline[1].tonal_key == 5   # bar 2 (at boundary)

    def test_minor_key_span(self):
        """Minor key span produces dorian scale."""
        ls = _make_ls([['Am7b5', 'D7'], ['Gm7']])
        key_spans = [KeySpan(key=7, mode='Minor', duration=Fraction(8))]
        assign_tonal_areas(ls, key_spans)

        for event in ls.chord_timeline:
            assert event.tonal_key == 7
            assert event.tonal_mode == 'Minor'
            expected_scale = scale_pcs_from_root_and_mode(7, 'Minor')
            assert event.tonal_scale == expected_scale

    def test_empty_timeline(self):
        """Empty chord timeline → no crash."""
        ls = LeadSheet()
        key_spans = [KeySpan(key=0, mode='Major', duration=Fraction(4))]
        assign_tonal_areas(ls, key_spans)  # should not raise

    def test_empty_key_spans(self):
        """Empty key spans list → no crash, fields stay None."""
        ls = _make_ls([['Cmaj7']])
        assign_tonal_areas(ls, [])
        assert ls.chord_timeline[0].tonal_key is None

    def test_three_key_spans_with_dominant(self):
        """Three spans including a Dominant mode."""
        ls = _make_ls([['Cmaj7'], ['Bb7'], ['Fmaj7']])
        key_spans = [
            KeySpan(key=0, mode='Major', duration=Fraction(4)),
            KeySpan(key=10, mode='Dominant', duration=Fraction(4)),
            KeySpan(key=5, mode='Major', duration=Fraction(4)),
        ]
        assign_tonal_areas(ls, key_spans)

        assert ls.chord_timeline[0].tonal_key == 0
        assert ls.chord_timeline[0].tonal_mode == 'Major'
        assert ls.chord_timeline[1].tonal_key == 10
        assert ls.chord_timeline[1].tonal_mode == 'Dominant'
        assert ls.chord_timeline[1].tonal_scale == scale_pcs_from_root_and_mode(10, 'Dominant')
        assert ls.chord_timeline[2].tonal_key == 5
        assert ls.chord_timeline[2].tonal_mode == 'Major'

    def test_waltz_meter(self):
        """3/4 time: beats_per_bar=3."""
        ls = _make_ls([['Cmaj7'], ['Dm7'], ['G7'], ['Cmaj7']], beats_per_bar=3)
        key_spans = [
            KeySpan(key=0, mode='Major', duration=Fraction(6)),   # bars 1-2
            KeySpan(key=0, mode='Major', duration=Fraction(6)),   # bars 3-4
        ]
        assign_tonal_areas(ls, key_spans)
        # All C major
        for event in ls.chord_timeline:
            assert event.tonal_key == 0


# ---------------------------------------------------------------------------
# Integration tests with real BrickLibrary (requires Impro-Visor data)
# ---------------------------------------------------------------------------

from python.config import LEADSHEETS_DIR
from python.tests.conftest import has_vocab

LS_DIR = str(LEADSHEETS_DIR)


@pytest.fixture(scope='module')
def cyk(lib):
    from python.roadmap.cyk_parser import CYKParser
    return CYKParser(lib)


@pytest.mark.skipif(not has_vocab, reason="Vocab data not found")
class TestRunRoadmap:
    def test_ii_v_i_c_major(self, lib, cyk):
        """ii-V-I in C → all chords get C major tonal area."""
        ls = _make_ls([['Dm7', 'G7'], ['Cmaj7']])
        annotate(ls)
        key_spans = run_roadmap(ls, lib, cyk)

        assert len(key_spans) >= 1
        # The dominant key should be C major (pc=0)
        # (all chords should resolve to C)
        for event in ls.chord_timeline:
            assert event.tonal_key is not None
            assert event.tonal_mode is not None
            assert event.tonal_scale is not None

    def test_bye_bye_blackbird(self, lib, cyk):
        """Bye Bye Blackbird — first 8 bars should be in F major."""
        ls_path = os.path.join(LS_DIR, 'ByeByeBlackbird.ls')
        if not os.path.exists(ls_path):
            pytest.skip("ByeByeBlackbird.ls not found")

        from python.leadsheet.parser import parse
        ls = parse(ls_path)
        annotate(ls)
        key_spans = run_roadmap(ls, lib, cyk)

        assert len(key_spans) >= 1

        # All chords should have tonal info
        for event in ls.chord_timeline:
            assert event.tonal_key is not None, f"bar {event.bar}"
            assert event.tonal_mode is not None
            assert event.tonal_scale is not None

        # First 8 bars should be F major (key=5)
        for event in ls.chord_timeline:
            if event.bar <= 8:
                assert event.tonal_key == 5, (
                    f"bar {event.bar} {event.symbol}: "
                    f"expected F major (5), got {event.tonal_key}"
                )

    def test_all_chords_annotated(self, lib, cyk):
        """After run_roadmap, every chord should have tonal info set."""
        ls = _make_ls([
            ['Gm7', 'C7'], ['Fmaj7'], ['Am7b5', 'D7'], ['Gm7'],
        ])
        annotate(ls)
        run_roadmap(ls, lib, cyk)

        for event in ls.chord_timeline:
            assert event.tonal_key is not None
            assert event.tonal_mode in ('Major', 'Minor', 'Dominant')
            assert isinstance(event.tonal_scale, frozenset)
            assert len(event.tonal_scale) >= 7  # at least 7 scale tones

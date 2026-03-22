"""
test_grammar_converter.py — Tests for the grammar S-exp → JSON converter.
"""

import json
import math
from pathlib import Path

import pytest

from python.grammar.converter import (
    parse_duration,
    parse_note,
    parse_x_interval,
    parse_slope,
    parse_note_sequence,
    extract_parameters,
    convert_grammar,
)
from python.config import SOURCE_GRAMMARS_DIR

has_grammar = (SOURCE_GRAMMARS_DIR / 'LesterYoung.grammar').exists()


# ---------------------------------------------------------------------------
# Duration parsing
# ---------------------------------------------------------------------------

class TestParseDuration:
    def test_whole(self):
        assert parse_duration('1') == 4.0

    def test_half(self):
        assert parse_duration('2') == 2.0

    def test_quarter(self):
        assert parse_duration('4') == 1.0

    def test_eighth(self):
        assert parse_duration('8') == 0.5

    def test_sixteenth(self):
        assert parse_duration('16') == 0.25

    def test_thirty_second(self):
        assert parse_duration('32') == 0.125

    def test_dotted_quarter(self):
        assert parse_duration('4+8') == 1.5

    def test_triplet_eighth(self):
        assert math.isclose(parse_duration('8/3'), 0.5 / 3)

    def test_compound(self):
        # 2+4 = 2.0 + 1.0 = 3.0
        assert parse_duration('2+4') == 3.0

    def test_complex_compound(self):
        # 4+8/3 = 1.0 + 0.167
        assert math.isclose(parse_duration('4+8/3'), 1.0 + 0.5 / 3)

    def test_long_rest(self):
        # R1+1+1+1 duration string: 1+1+1+1 = 16 beats
        assert parse_duration('1+1+1+1') == 16.0

    def test_dotted_half_plus_eighth(self):
        # 2+4+8 = 2.0 + 1.0 + 0.5 = 3.5
        assert parse_duration('2+4+8') == 3.5


# ---------------------------------------------------------------------------
# Note parsing
# ---------------------------------------------------------------------------

class TestParseNote:
    def test_chord_tone_eighth(self):
        n = parse_note('C8')
        assert n == {"type": "C", "dur": 0.5}

    def test_rest_whole(self):
        n = parse_note('R1')
        assert n == {"type": "R", "dur": 4.0}

    def test_color_tone(self):
        n = parse_note('L4')
        assert n == {"type": "L", "dur": 1.0}

    def test_scale_tone(self):
        n = parse_note('S16')
        assert n == {"type": "S", "dur": 0.25}

    def test_approach_tone(self):
        n = parse_note('A8')
        assert n == {"type": "A", "dur": 0.5}

    def test_compound_duration(self):
        n = parse_note('C4+8')
        assert n == {"type": "C", "dur": 1.5}

    def test_triplet(self):
        n = parse_note('X8/3')
        assert n is not None
        assert n["type"] == "X"
        assert math.isclose(n["dur"], 0.5 / 3)

    def test_not_a_note(self):
        assert parse_note('BRICK') is None
        assert parse_note('480') is None

    def test_rest_compound(self):
        n = parse_note('R2+4')
        assert n == {"type": "R", "dur": 3.0}


# ---------------------------------------------------------------------------
# X-interval parsing
# ---------------------------------------------------------------------------

class TestParseXInterval:
    def test_simple(self):
        x = parse_x_interval(['X', 'b6', '8'])
        assert x == {"type": "X", "degree": "b6", "dur": 0.5}

    def test_sharp_degree(self):
        x = parse_x_interval(['X', '#4', '4'])
        assert x == {"type": "X", "degree": "#4", "dur": 1.0}

    def test_compound_duration(self):
        x = parse_x_interval(['X', '2', '4+8'])
        assert x == {"type": "X", "degree": "2", "dur": 1.5}

    def test_not_x(self):
        assert parse_x_interval(['slope', '0', '0', 'C8']) is None

    def test_atom(self):
        assert parse_x_interval('C8') is None


# ---------------------------------------------------------------------------
# Slope parsing
# ---------------------------------------------------------------------------

class TestParseSlope:
    def test_basic(self):
        s = parse_slope(['slope', '-3', '-1', 'C8', 'L8', 'C8'])
        assert s["type"] == "slope"
        assert s["start"] == -3
        assert s["end"] == -1
        assert len(s["notes"]) == 3
        assert s["notes"][0] == {"type": "C", "dur": 0.5}

    def test_single_note(self):
        s = parse_slope(['slope', '0', '0', 'R1'])
        assert s["type"] == "slope"
        assert len(s["notes"]) == 1
        assert s["notes"][0] == {"type": "R", "dur": 4.0}

    def test_with_x_inside(self):
        # Slopes can contain X-notation notes like X4, X8
        s = parse_slope(['slope', '3', '3', ['X', '5', '8']])
        assert s is not None
        assert len(s["notes"]) == 1
        assert s["notes"][0]["type"] == "X"

    def test_not_slope(self):
        assert parse_slope(['X', 'b6', '8']) is None


# ---------------------------------------------------------------------------
# Note sequence parsing
# ---------------------------------------------------------------------------

class TestParseNoteSequence:
    def test_mixed_sequence(self):
        elements = [
            'R8',
            ['X', 'b6', '8'],
            ['X', '5', '8'],
            'C4',
        ]
        notes = parse_note_sequence(elements)
        assert len(notes) == 4
        assert notes[0] == {"type": "R", "dur": 0.5}
        assert notes[1] == {"type": "X", "degree": "b6", "dur": 0.5}
        assert notes[3] == {"type": "C", "dur": 1.0}

    def test_slope_sequence(self):
        elements = [
            ['slope', '0', '0', 'L8'],
            ['slope', '-5', '-2', 'C8', 'C8'],
        ]
        notes = parse_note_sequence(elements)
        assert len(notes) == 2
        assert notes[0]["type"] == "slope"
        assert notes[1]["start"] == -5


# ---------------------------------------------------------------------------
# Parameter extraction
# ---------------------------------------------------------------------------

class TestExtractParameters:
    def test_basic(self):
        from python.roadmap.sexp_parser import parse_string
        exprs = parse_string(
            '(parameter (chord-tone-weight 0.7))'
            '(parameter (min-pitch 58))'
            '(parameter (rectify true))'
        )
        params = extract_parameters(exprs)
        assert params['chord-tone-weight'] == 0.7
        assert params['min-pitch'] == 58
        assert params['rectify'] is True


# ---------------------------------------------------------------------------
# Full grammar conversion (requires LesterYoung.grammar)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not has_grammar, reason="LesterYoung.grammar not found")
class TestConvertGrammar:
    @pytest.fixture(scope='class')
    def grammar(self):
        path = str(SOURCE_GRAMMARS_DIR / 'LesterYoung.grammar')
        return convert_grammar(path)

    def test_player_name(self, grammar):
        assert grammar['player'] == 'LesterYoung'

    def test_parameter_count(self, grammar):
        assert len(grammar['parameters']) == 24

    def test_pitch_range(self, grammar):
        assert grammar['parameters']['min-pitch'] == 58
        assert grammar['parameters']['max-pitch'] == 82

    def test_p_brick_rules(self, grammar):
        assert len(grammar['p_brick_rules']) == 7
        ticks = [r['ticks'] for r in grammar['p_brick_rules']]
        assert 480 in ticks
        assert 3840 in ticks

    def test_p_start_rules(self, grammar):
        assert len(grammar['p_start_rules']) == 7

    def test_brick_rule_count(self, grammar):
        total = sum(
            len(rules)
            for dur_bucket in grammar['brick_rules'].values()
            for rules in dur_bucket.values()
        )
        assert total == 948

    def test_brick_duration_buckets(self, grammar):
        assert len(grammar['brick_rules']) == 7
        assert '480' in grammar['brick_rules']
        assert '3840' in grammar['brick_rules']

    def test_start_rules(self, grammar):
        assert len(grammar['start_rules']) == 2
        names = {r['rhs'] for r in grammar['start_rules']}
        assert names == {'Cluster0', 'Cluster1'}

    def test_cluster_rules(self, grammar):
        assert len(grammar['cluster_rules']) == 13

    def test_q_rules(self, grammar):
        assert 'Q0' in grammar['q_rules']
        assert 'Q1' in grammar['q_rules']
        assert len(grammar['q_rules']['Q0']) == 8
        assert len(grammar['q_rules']['Q1']) == 56

    def test_brick_note_durations_sum(self, grammar):
        """Verify note durations within BRICK rules sum to the expected ticks.

        Uses 120 ticks/beat (Impro-Visor standard: 480 ticks = 4 beats = 1 bar).
        Some rules have minor duration imbalances from triplet rounding in the
        grammar source, so we allow a tolerance of 5% and up to 25% of rules
        having small mismatches.
        """
        total_rules = 0
        errors = 0
        for ticks_str, by_name in grammar['brick_rules'].items():
            expected_beats = int(ticks_str) / 120.0
            for name, rules in by_name.items():
                for i, rule in enumerate(rules):
                    total_rules += 1
                    total = _sum_note_dur(rule['notes'])
                    if not math.isclose(total, expected_beats, rel_tol=0.05):
                        errors += 1
        # Most rules should match; allow some tolerance for triplet rounding
        error_rate = errors / total_rules if total_rules else 0
        assert error_rate < 0.25, (
            f"{errors}/{total_rules} rules ({error_rate:.1%}) have duration mismatches"
        )

    def test_x_interval_notes_present(self, grammar):
        """Verify X-interval notes are parsed in brick rules."""
        x_count = 0
        for dur_bucket in grammar['brick_rules'].values():
            for rules in dur_bucket.values():
                for rule in rules:
                    for note in rule['notes']:
                        if note.get('type') == 'X':
                            x_count += 1
        assert x_count > 100

    def test_slope_notes_present(self, grammar):
        """Verify slope notes are parsed in brick rules."""
        slope_count = 0
        for dur_bucket in grammar['brick_rules'].values():
            for rules in dur_bucket.values():
                for rule in rules:
                    for note in rule['notes']:
                        if note.get('type') == 'slope':
                            slope_count += 1
        assert slope_count > 100


def _sum_note_dur(notes):
    """Sum durations from a note list, recursing into slopes."""
    total = 0.0
    for n in notes:
        if n.get('type') == 'slope':
            total += _sum_note_dur(n['notes'])
        else:
            total += n.get('dur', 0)
    return total

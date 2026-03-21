"""
test_osc_bridge.py — Trad-Four
Tests for the OSC broadcaster (Phase 1d).

All tests use a mocked SimpleUDPClient — no live SuperCollider needed.

Run:
    pytest python/tests/test_osc_bridge.py -v
"""

import os
import warnings
import pytest
from fractions import Fraction
from unittest.mock import MagicMock

from python.leadsheet.parser import LeadSheet, ChordEvent
from python.leadsheet.osc_bridge import (
    _pcs_to_csv, _send_metadata, _send_chord, _send_done,
    broadcast_leadsheet, prepare_and_broadcast,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_annotated_event(bar=1, beat=Fraction(1), symbol='Cm7',
                          duration=Fraction(4)) -> ChordEvent:
    """Build a ChordEvent with annotation attributes set."""
    event = ChordEvent(bar=bar, beat=beat, symbol=symbol, duration=duration)
    event.chord_tones = frozenset({0, 3, 7, 10})
    event.color_tones = frozenset({2})
    event.scale_tones = frozenset({5, 8})
    event.scale_pcs = frozenset({0, 2, 3, 5, 7, 8, 10})
    event.scale_name = 'dorian'
    event.tonal_key = 0
    event.tonal_mode = 'Major'
    event.tonal_scale = frozenset({0, 2, 4, 5, 7, 9, 11})
    return event


def _make_ls(events: list[ChordEvent] = None, **kwargs) -> LeadSheet:
    """Build a minimal LeadSheet."""
    ls = LeadSheet(title='Test Tune', composer='Test Composer',
                   tempo=140.0, beats_per_bar=4, beat_unit=4, **kwargs)
    ls.chord_timeline = events or []
    return ls


# ---------------------------------------------------------------------------
# _pcs_to_csv
# ---------------------------------------------------------------------------

class TestPcsToCsv:
    def test_normal_frozenset(self):
        assert _pcs_to_csv(frozenset({0, 4, 7, 11})) == '0,4,7,11'

    def test_sorted_output(self):
        result = _pcs_to_csv(frozenset({11, 0, 7, 4}))
        assert result == '0,4,7,11'

    def test_empty_frozenset(self):
        assert _pcs_to_csv(frozenset()) == ''

    def test_none(self):
        assert _pcs_to_csv(None) == ''

    def test_single_element(self):
        assert _pcs_to_csv(frozenset({5})) == '5'

    def test_roundtrip(self):
        """csv string → back to set of ints matches original."""
        original = frozenset({0, 3, 7, 10})
        csv = _pcs_to_csv(original)
        restored = frozenset(int(x) for x in csv.split(','))
        assert restored == original


# ---------------------------------------------------------------------------
# _send_metadata
# ---------------------------------------------------------------------------

class TestSendMetadata:
    def test_message_address_and_args(self):
        ls = _make_ls()
        ls.inferred_key = 'F major'
        client = MagicMock()

        _send_metadata(client, ls)

        client.send_message.assert_called_once()
        addr, args = client.send_message.call_args[0]
        assert addr == '/trad4/meta'
        assert args[0] == 'Test Tune'
        assert args[1] == 'Test Composer'
        assert args[2] == 140.0
        assert args[3] == 4       # beats_per_bar
        assert args[4] == 4       # beat_unit
        assert args[5] == 0       # total_bars (empty timeline)
        assert args[6] == 'F major'

    def test_none_inferred_key(self):
        ls = _make_ls()
        ls.inferred_key = None
        client = MagicMock()

        _send_metadata(client, ls)

        _, args = client.send_message.call_args[0]
        assert args[6] == ''  # None → empty string


# ---------------------------------------------------------------------------
# _send_chord
# ---------------------------------------------------------------------------

class TestSendChord:
    def test_message_fields(self):
        event = _make_annotated_event()
        client = MagicMock()

        _send_chord(client, 0, event)

        client.send_message.assert_called_once()
        addr, args = client.send_message.call_args[0]
        assert addr == '/trad4/chord'
        assert args[0] == 0                    # index
        assert args[1] == 1                    # bar
        assert args[2] == 1.0                  # beat
        assert args[3] == 'Cm7'               # symbol
        assert args[4] == 4.0                  # duration
        assert args[5] == '0,3,7,10'          # chord_tones
        assert args[6] == '2'                  # color_tones
        assert args[7] == '5,8'               # scale_tones
        assert args[8] == '0,2,3,5,7,8,10'   # scale_pcs
        assert args[9] == 'dorian'            # scale_name
        assert args[10] == 0                   # tonal_key
        assert args[11] == 'Major'            # tonal_mode
        assert args[12] == '0,2,4,5,7,9,11'  # tonal_scale

    def test_none_tonal_fields(self):
        """ChordEvent with no tonal info → -1 for key, '' for mode."""
        event = ChordEvent(bar=1, beat=Fraction(1), symbol='C7',
                           duration=Fraction(4))
        event.chord_tones = frozenset({0, 4, 7, 10})
        event.color_tones = frozenset()
        event.scale_tones = frozenset({2, 5, 9})
        event.scale_pcs = frozenset({0, 2, 4, 5, 7, 9, 10})
        event.scale_name = 'mixolydian'
        # tonal fields left as None (not set by roadmap)
        client = MagicMock()

        _send_chord(client, 0, event)

        _, args = client.send_message.call_args[0]
        assert args[10] == -1   # tonal_key None → -1
        assert args[11] == ''   # tonal_mode None → ''
        assert args[12] == ''   # tonal_scale None → ''

    def test_unannotated_event(self):
        """ChordEvent that hasn't been through annotator → empty strings."""
        event = ChordEvent(bar=3, beat=Fraction(3), symbol='G7',
                           duration=Fraction(2))
        client = MagicMock()

        _send_chord(client, 5, event)

        _, args = client.send_message.call_args[0]
        assert args[0] == 5      # index
        assert args[3] == 'G7'   # symbol preserved
        assert args[5] == ''     # chord_tones (not set)
        assert args[9] == ''     # scale_name (not set)


# ---------------------------------------------------------------------------
# _send_done
# ---------------------------------------------------------------------------

class TestSendDone:
    def test_done_message(self):
        client = MagicMock()
        _send_done(client, 42)
        client.send_message.assert_called_once_with('/trad4/done', [42])


# ---------------------------------------------------------------------------
# broadcast_leadsheet
# ---------------------------------------------------------------------------

class TestBroadcastLeadsheet:
    def test_message_count(self):
        """1 meta + N chords + 1 done."""
        events = [_make_annotated_event(bar=i) for i in range(1, 4)]
        ls = _make_ls(events)
        client = MagicMock()

        count = broadcast_leadsheet(ls, client=client)

        assert count == 3
        assert client.send_message.call_count == 5  # 1 meta + 3 chords + 1 done

    def test_message_order(self):
        """Messages are sent in order: meta, chords, done."""
        events = [_make_annotated_event(bar=1), _make_annotated_event(bar=2)]
        ls = _make_ls(events)
        client = MagicMock()

        broadcast_leadsheet(ls, client=client)

        calls = client.send_message.call_args_list
        assert calls[0][0][0] == '/trad4/meta'
        assert calls[1][0][0] == '/trad4/chord'
        assert calls[2][0][0] == '/trad4/chord'
        assert calls[3][0][0] == '/trad4/done'

    def test_empty_timeline(self):
        """Empty timeline → 1 meta + 0 chords + 1 done."""
        ls = _make_ls([])
        client = MagicMock()

        count = broadcast_leadsheet(ls, client=client)

        assert count == 0
        assert client.send_message.call_count == 2  # meta + done

    def test_chord_indices_sequential(self):
        """Chord messages have sequential indices starting at 0."""
        events = [_make_annotated_event(bar=i) for i in range(1, 6)]
        ls = _make_ls(events)
        client = MagicMock()

        broadcast_leadsheet(ls, client=client)

        chord_calls = [c for c in client.send_message.call_args_list
                       if c[0][0] == '/trad4/chord']
        indices = [c[0][1][0] for c in chord_calls]
        assert indices == [0, 1, 2, 3, 4]

    def test_done_count_matches(self):
        """Done message count matches actual timeline length."""
        events = [_make_annotated_event(bar=i) for i in range(1, 8)]
        ls = _make_ls(events)
        client = MagicMock()

        broadcast_leadsheet(ls, client=client)

        done_call = [c for c in client.send_message.call_args_list
                     if c[0][0] == '/trad4/done']
        assert done_call[0][0][1] == [7]


# ---------------------------------------------------------------------------
# Integration: prepare_and_broadcast (requires Impro-Visor data)
# ---------------------------------------------------------------------------

DICT_PATH = '/usr/share/impro-visor/vocab/My.dictionary'
LS_DIR = '/usr/share/impro-visor/leadsheets/imaginary-book'
_has_improvisor = os.path.exists(DICT_PATH)


@pytest.mark.skipif(not _has_improvisor, reason="Impro-Visor data not found")
class TestPrepareAndBroadcast:
    def test_bye_bye_blackbird(self):
        """Full pipeline on a real .ls file with mocked OSC client."""
        ls_path = os.path.join(LS_DIR, 'ByeByeBlackbird.ls')
        if not os.path.exists(ls_path):
            pytest.skip("ByeByeBlackbird.ls not found")

        from unittest.mock import patch

        with patch('python.leadsheet.osc_bridge.SimpleUDPClient') as MockClient:
            mock_instance = MagicMock()
            MockClient.return_value = mock_instance

            ls = prepare_and_broadcast(ls_path)

        assert ls.title  # should have a title
        assert len(ls.chord_timeline) > 0

        # Verify message pattern: meta, N chords, done
        calls = mock_instance.send_message.call_args_list
        assert calls[0][0][0] == '/trad4/meta'
        assert calls[-1][0][0] == '/trad4/done'

        chord_calls = [c for c in calls if c[0][0] == '/trad4/chord']
        assert len(chord_calls) == len(ls.chord_timeline)

        # Done message count matches
        done_args = calls[-1][0][1]
        assert done_args == [len(ls.chord_timeline)]

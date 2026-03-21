"""
osc_bridge.py — Trad-Four Phase 1d
OSC broadcaster: sends the fully annotated chord timeline to SuperCollider.

Protocol:
    /trad4/meta     s:title  s:composer  f:tempo  i:beats_per_bar  i:beat_unit
                    i:total_bars  s:inferred_key
    /trad4/chord    i:index  i:bar  f:beat  s:symbol  f:duration
                    s:chord_tones  s:color_tones  s:scale_tones  s:scale_pcs
                    s:scale_name  i:tonal_key  s:tonal_mode  s:tonal_scale
    /trad4/done     i:total_chords

Pitch class sets are sent as comma-separated strings (e.g. "0,4,7,11").
Empty sets → "".  None tonal_key → -1.  None tonal_mode → "".

Usage:
    from python.leadsheet.osc_bridge import broadcast_leadsheet, prepare_and_broadcast

    # If you already have an annotated LeadSheet:
    count = broadcast_leadsheet(ls)

    # Full pipeline from file:
    ls = prepare_and_broadcast('path/to/tune.ls')

CLI:
    python -m python.leadsheet.osc_bridge path/to/tune.ls [--host 127.0.0.1] [--port 57120]
"""

import warnings
from fractions import Fraction

from pythonosc.udp_client import SimpleUDPClient

from python.leadsheet.parser import LeadSheet, ChordEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pcs_to_csv(pcs) -> str:
    """
    Convert a pitch class set to a comma-separated string.

    frozenset({0, 4, 7, 11}) → '0,4,7,11'
    frozenset()               → ''
    None                      → ''
    """
    if not pcs:
        return ''
    return ','.join(str(pc) for pc in sorted(pcs))


def _send_metadata(client: SimpleUDPClient, ls: LeadSheet) -> None:
    """Send /trad4/meta message with tune metadata."""
    inferred = ''
    if ls.inferred_key is not None:
        inferred = str(ls.inferred_key)

    client.send_message('/trad4/meta', [
        ls.title,
        ls.composer,
        float(ls.tempo),
        ls.beats_per_bar,
        ls.beat_unit,
        ls.total_bars,
        inferred,
    ])


def _send_chord(client: SimpleUDPClient, index: int, event: ChordEvent) -> None:
    """Send /trad4/chord message for one ChordEvent."""
    chord_tones = _pcs_to_csv(getattr(event, 'chord_tones', None))
    color_tones = _pcs_to_csv(getattr(event, 'color_tones', None))
    scale_tones = _pcs_to_csv(getattr(event, 'scale_tones', None))
    scale_pcs = _pcs_to_csv(getattr(event, 'scale_pcs', None))
    scale_name = getattr(event, 'scale_name', '') or ''

    tonal_key = event.tonal_key if event.tonal_key is not None else -1
    tonal_mode = event.tonal_mode or ''
    tonal_scale = _pcs_to_csv(event.tonal_scale)

    client.send_message('/trad4/chord', [
        index,
        event.bar,
        float(event.beat),
        event.symbol,
        float(event.duration),
        chord_tones,
        color_tones,
        scale_tones,
        scale_pcs,
        scale_name,
        tonal_key,
        tonal_mode,
        tonal_scale,
    ])


def _send_done(client: SimpleUDPClient, count: int) -> None:
    """Send /trad4/done message."""
    client.send_message('/trad4/done', [count])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def broadcast_leadsheet(ls: LeadSheet, host: str = '127.0.0.1',
                        port: int = 57120, client: SimpleUDPClient = None) -> int:
    """
    Send a fully annotated LeadSheet to SuperCollider via OSC.

    Returns the number of chord events sent.

    Sends:
      1. /trad4/meta   — tune metadata
      2. /trad4/chord  — one per ChordEvent (indexed)
      3. /trad4/done   — completion signal with count

    Args:
        ls     : annotated LeadSheet (from parse → annotate → run_roadmap)
        host   : OSC target host
        port   : OSC target port
        client : optional pre-built SimpleUDPClient (for testing)
    """
    if client is None:
        client = SimpleUDPClient(host, port)

    _send_metadata(client, ls)

    for i, event in enumerate(ls.chord_timeline):
        _send_chord(client, i, event)

    count = len(ls.chord_timeline)
    _send_done(client, count)

    return count


def prepare_and_broadcast(path: str, host: str = '127.0.0.1',
                          port: int = 57120) -> LeadSheet:
    """
    Full pipeline: parse → annotate → roadmap → broadcast.

    Returns the annotated LeadSheet for inspection.
    """
    from python.leadsheet.parser import parse
    from python.leadsheet.annotator import annotate
    from python.leadsheet.tonal_areas import run_roadmap
    from python.roadmap.brick_library import BrickLibrary
    from python.roadmap.cyk_parser import CYKParser

    ls = parse(path)
    annotate(ls)

    from python.config import DICT_PATH, SUB_PATH

    # Load brick library and run roadmap
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        lib = BrickLibrary()
        lib.load(str(DICT_PATH), str(SUB_PATH))
    cyk = CYKParser(lib)
    run_roadmap(ls, lib, cyk)

    count = broadcast_leadsheet(ls, host, port)
    print(f"Broadcast {count} chords from '{ls.title}' to {host}:{port}")

    return ls


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Broadcast an annotated lead sheet to SuperCollider via OSC.',
    )
    parser.add_argument('path', help='Path to a lead sheet file (.ls or .tls)')
    parser.add_argument('--host', default='127.0.0.1',
                        help='OSC target host (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=57120,
                        help='OSC target port (default: 57120)')
    args = parser.parse_args()

    ls = prepare_and_broadcast(args.path, args.host, args.port)

    print(f"\n--- Summary ---")
    print(f"  Title:    {ls.title}")
    print(f"  Composer: {ls.composer}")
    print(f"  Tempo:    {ls.tempo}")
    print(f"  Meter:    {ls.beats_per_bar}/{ls.beat_unit}")
    print(f"  Bars:     {ls.total_bars}")
    print(f"  Chords:   {len(ls.chord_timeline)}")
    print(f"  Key:      {ls.inferred_key}")

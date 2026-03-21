"""
tonal_areas.py — Trad-Four Phase 1b
Maps roadmap KeySpans onto individual ChordEvents so every chord
carries its tonal center, mode, and scale.

Each ChordEvent is assigned:
    .tonal_key   — pitch class 0-11 of tonal center
    .tonal_mode  — 'Major', 'Minor', or 'Dominant'
    .tonal_scale — frozenset of pitch classes for the active scale

Usage:
    from python.leadsheet.parser import parse
    from python.leadsheet.annotator import annotate
    from python.leadsheet.tonal_areas import run_roadmap

    ls = parse('path/to/tune.ls')
    annotate(ls)
    run_roadmap(ls, lib, parser)

    for event in ls.chord_timeline:
        print(event.bar, event.symbol, event.tonal_key, event.tonal_mode)
"""

from fractions import Fraction

from python.leadsheet.parser import LeadSheet
from python.leadsheet.annotator import _SCALE_INTERVALS
from python.roadmap.post_processor import KeySpan


# ---------------------------------------------------------------------------
# Scale computation
# ---------------------------------------------------------------------------

_MODE_TO_SCALE = {
    'Major':    'ionian',
    'Minor':    'dorian',
    'Dominant': 'mixolydian',
}


def scale_pcs_from_root_and_mode(root_pc: int, mode: str) -> frozenset:
    """Return pitch class set given root pc (0-11) and KeySpan mode string."""
    scale_name = _MODE_TO_SCALE.get(mode, 'ionian')
    intervals = _SCALE_INTERVALS.get(scale_name, _SCALE_INTERVALS['ionian'])
    return frozenset((root_pc + i) % 12 for i in intervals)


# ---------------------------------------------------------------------------
# assign_tonal_areas
# ---------------------------------------------------------------------------

def assign_tonal_areas(ls: LeadSheet, key_spans: list[KeySpan]) -> None:
    """
    Map KeySpans onto ChordEvents by walking both lists in beat order.

    Each KeySpan has a duration in beats.  ChordEvents have bar/beat
    positions.  We build intervals from the sequential KeySpan durations,
    then for each ChordEvent find which interval contains it.

    Sets event.tonal_key, event.tonal_mode, event.tonal_scale on every
    ChordEvent in ls.chord_timeline.
    """
    if not key_spans or not ls.chord_timeline:
        return

    # Build (start_beat, end_beat, KeySpan) intervals
    intervals: list[tuple[Fraction, Fraction, KeySpan]] = []
    cursor = Fraction(0)
    for ks in key_spans:
        end = cursor + ks.duration
        intervals.append((cursor, end, ks))
        cursor = end

    bpb = Fraction(ls.beats_per_bar)

    # Index for walking intervals in order alongside events
    span_idx = 0

    for event in ls.chord_timeline:
        # Absolute beat position (0-indexed)
        abs_beat = (event.bar - 1) * bpb + (event.beat - 1)

        # Advance span_idx to the interval containing abs_beat
        while (span_idx < len(intervals) - 1 and
               abs_beat >= intervals[span_idx][1]):
            span_idx += 1

        start, end, ks = intervals[span_idx]
        event.tonal_key = ks.key
        event.tonal_mode = ks.mode
        event.tonal_scale = scale_pcs_from_root_and_mode(ks.key, ks.mode)


# ---------------------------------------------------------------------------
# run_roadmap — convenience pipeline
# ---------------------------------------------------------------------------

def run_roadmap(ls: LeadSheet, lib, parser) -> list[KeySpan]:
    """
    Run the full roadmap pipeline and annotate ChordEvents in place.

    1. parser.parse_leadsheet(ls.chord_timeline) → roadmap blocks
    2. find_keys(blocks, lib) → key spans
    3. assign_tonal_areas(ls, key_spans) → annotates ChordEvents

    Args:
        ls     : parsed (and annotated) LeadSheet
        lib    : BrickLibrary instance
        parser : CYKParser instance

    Returns:
        The list of KeySpan objects produced (for inspection/debugging).
    """
    from python.roadmap.post_processor import find_keys

    blocks = parser.parse_leadsheet(ls.chord_timeline)
    key_spans = find_keys(blocks, lib)
    assign_tonal_areas(ls, key_spans)
    return key_spans


# ---------------------------------------------------------------------------
# CLI — quick test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    import warnings
    from python.leadsheet.parser import parse
    from python.leadsheet.annotator import annotate
    from python.roadmap.brick_library import BrickLibrary
    from python.roadmap.cyk_parser import CYKParser
    from python.roadmap.chord_block import pc_to_name

    path = sys.argv[1] if len(sys.argv) > 1 else \
        '/usr/share/impro-visor/leadsheets/imaginary-book/ByeByeBlackbird.ls'

    print(f"Parsing: {path}\n")
    ls = parse(path)
    annotate(ls)

    print("Loading BrickLibrary...")
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        lib = BrickLibrary()
        lib.load('/usr/share/impro-visor/vocab/My.dictionary',
                 '/usr/share/impro-visor/vocab/My.substitutions')
    cyk = CYKParser(lib)

    key_spans = run_roadmap(ls, lib, cyk)

    print(f"\nKeySpans: {key_spans}\n")

    print(f"{'Bar':>4} {'Beat':>5} {'Chord':>12} {'Key':>6} {'Mode':>10} "
          f"{'Scale PCs':>30}")
    print('-' * 75)

    for event in ls.chord_timeline:
        key_str = pc_to_name(event.tonal_key) if event.tonal_key is not None else '—'
        mode_str = event.tonal_mode or '—'
        scale_str = str(sorted(event.tonal_scale)) if event.tonal_scale else '—'
        print(f"{event.bar:>4} {float(event.beat):>5.1f} "
              f"{event.symbol:>12} {key_str:>6} {mode_str:>10} "
              f"{scale_str:>30}")

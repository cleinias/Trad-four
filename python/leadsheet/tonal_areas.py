"""
tonal_areas.py — Trad-Four Phase 1b
Detects tonal areas in a parsed LeadSheet by identifying cadential
patterns (ii-V-I, iiø-V-i, V-I) using music21 Roman numeral analysis.

Each ChordEvent is assigned:
    .tonal_area       — music21 Key object or None
    .tonal_area_type  — 'diatonic' | 'sequential' | 'passing'
    .tonal_area_scale — frozenset of pitch classes for the active scale

The three area types:
    diatonic   — chord falls within a detected key area (e.g. F major bars 1-8)
    sequential — chord is part of a chromatic ii-V sequence with an implied
                 but unresolved tonic (e.g. B section of Bye Bye Blackbird)
    passing    — chord outside any detected area; uses per-chord scale

Usage:
    from python.leadsheet.parser import parse
    from python.leadsheet.tonal_areas import detect_tonal_areas

    ls = parse('path/to/tune.ls')
    detect_tonal_areas(ls)

    for event in ls.chord_timeline:
        print(event.bar, event.symbol,
              event.tonal_area, event.tonal_area_type)
"""

import re
import warnings
from typing import Optional

from music21 import harmony, key as m21key, roman

from python.leadsheet.parser import LeadSheet, ChordEvent
from python.leadsheet.chord_preprocessor import to_music21_figure, _ROOT_SPLIT, _FLAT_ROOTS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Simplified Roman numeral patterns for cadence detection
# We match against the output of simplify_rn()

# Patterns that establish a MAJOR key area, listed by strength
_MAJOR_CADENCES = [
    ('vi', 'ii', 'V', 'I'),   # vi-ii-V-I  (strongest)
    ('ii', 'V',  'I'),         # ii-V-I
    ('V',  'I'),                # V-I        (weakest)
    ('I',  'ii', 'V', 'I'),   # I-ii-V-I
]

# Patterns that establish a MINOR key area
_MINOR_CADENCES = [
    ('vi', 'ii', 'V', 'i'),   # vi-iiø-V-i (rare but valid)
    ('ii', 'V',  'i'),         # iiø-V-i
    ('V',  'i'),                # V-i
    ('iv', 'V',  'i'),         # iv-V-i
    ('i',  'iv', 'i'),         # i-iv-i  (tonic confirmation in minor)
    ('i',  'IV', 'i'),         # i-IV-i  (i-subdominant-i, e.g. Gm-C7-Gm)
]

# Roman numerals that qualify as 'ii' in major (includes iiø)
_II_MAJOR = {'ii'}
# Roman numerals that qualify as 'ii' in minor
_II_MINOR = {'ii'}   # iiø simplifies to 'ii'
# Roman numerals that qualify as 'V'
_V_DEGREES = {'V'}
# Roman numerals that qualify as 'I' / 'i'
_I_MAJOR = {'I'}
_I_MINOR = {'i'}
# Roman numerals that qualify as 'vi'
_VI_DEGREES = {'vi', 'VI'}

# Diatonic scales as semitone intervals from root
_MAJOR_INTERVALS = [0, 2, 4, 5, 7, 9, 11]
_MINOR_INTERVALS = [0, 2, 3, 5, 7, 8, 10]   # natural minor
_DORIAN_INTERVALS = [0, 2, 3, 5, 7, 9, 10]  # dorian (jazz minor default)

# Note name to pitch class
_NOTE_TO_PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def simplify_rn(figure: str) -> str:
    """
    Extract just the scale degree from a music21 Roman numeral figure,
    stripping inversion, figured bass, and quality suffixes.

    Examples:
        'I65'      → 'I'
        'ii7'      → 'ii'
        'bVII65'   → 'bVII'
        'iiø7b53'  → 'ii'
        'V7'       → 'V'
    """
    m = re.match(r'([#b]?[IiVv]+)', figure)
    return m.group(1) if m else figure


def root_pc_from_symbol(symbol: str) -> Optional[int]:
    """Extract root pitch class (0-11) from a chord symbol string."""
    if not symbol or symbol == 'NC':
        return None
    m = _ROOT_SPLIT.match(symbol)
    if not m:
        return None
    root_str = m.group(1)
    root_m21 = _FLAT_ROOTS.get(root_str, root_str)
    letter = root_m21[0]
    pc = _NOTE_TO_PC.get(letter, 0)
    if len(root_m21) > 1:
        if root_m21[1] == '-':
            pc = (pc - 1) % 12
        elif root_m21[1] == '#':
            pc = (pc + 1) % 12
    return pc


def scale_pcs_for_key(k: m21key.Key) -> frozenset:
    """Return the pitch class set for a music21 Key object."""
    root_pc = k.tonic.pitchClass
    if k.mode == 'major':
        intervals = _MAJOR_INTERVALS
    else:
        intervals = _DORIAN_INTERVALS   # use Dorian for minor jazz context
    return frozenset((root_pc + i) % 12 for i in intervals)


def scale_pcs_from_root_and_mode(root_pc: int, mode: str) -> frozenset:
    """Return pitch class set given root pc and mode string."""
    if mode == 'major':
        intervals = _MAJOR_INTERVALS
    elif mode == 'dorian':
        intervals = _DORIAN_INTERVALS
    else:
        intervals = _MINOR_INTERVALS
    return frozenset((root_pc + i) % 12 for i in intervals)


def implied_tonic_from_dominant(dom_event: ChordEvent) -> tuple[int, str]:
    """
    Given a dominant chord event, return (root_pc, mode) of the implied tonic.
    The implied tonic root is a perfect fourth above the dominant root (V→I).

    Mode is 'major' unless the dominant is preceded by a iiø (half-dim),
    in which case it's 'dorian' (minor jazz context).
    """
    dom_pc = root_pc_from_symbol(dom_event.symbol)
    if dom_pc is None:
        return 0, 'major'
    implied_root = (dom_pc + 5) % 12   # perfect fourth up
    return implied_root, 'major'        # mode refined by caller


# ---------------------------------------------------------------------------
# Roman numeral sequence builder
# ---------------------------------------------------------------------------

def build_rn_sequence(timeline: list[ChordEvent],
                       candidate_key: m21key.Key) -> list[tuple[ChordEvent, str]]:
    """
    Compute simplified Roman numerals for all ChordEvents in timeline
    relative to candidate_key.

    Returns list of (event, simplified_rn_string) pairs.
    NC events are included with rn='NC'.
    """
    result = []
    for event in timeline:
        if event.symbol == 'NC':
            result.append((event, 'NC'))
            continue
        figure = to_music21_figure(event.symbol)
        if figure is None:
            result.append((event, '?'))
            continue
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                cs = harmony.ChordSymbol(figure)
            rn = roman.romanNumeralFromChord(cs, candidate_key)
            result.append((event, simplify_rn(rn.figure)))
        except Exception:
            result.append((event, '?'))
    return result


# ---------------------------------------------------------------------------
# Cadence pattern detection
# ---------------------------------------------------------------------------

def _match_pattern(rn_seq: list[str],
                   pos: int,
                   pattern: tuple) -> bool:
    """
    Check if rn_seq starting at pos matches the given pattern.
    Matching is loose: 'ii' matches 'ii' regardless of ø or 7 suffix
    (already stripped by simplify_rn).
    """
    if pos + len(pattern) > len(rn_seq):
        return False
    for i, expected in enumerate(pattern):
        actual = rn_seq[pos + i]
        if expected in ('I', 'i') and actual not in (_I_MAJOR | _I_MINOR):
            if actual != expected:
                return False
        elif actual != expected:
            return False
    return True


def detect_cadences(rn_pairs: list[tuple[ChordEvent, str]],
                    candidate_key: m21key.Key) -> list[tuple[int, int, str]]:
    """
    Scan the Roman numeral sequence for cadential patterns.

    Returns list of (start_idx, end_idx, 'major'|'minor') tuples,
    where start_idx and end_idx are indices into rn_pairs,
    indicating the range of events belonging to this cadential unit.
    'end_idx' points to the resolution chord (I or i).
    """
    rns = [rn for _, rn in rn_pairs]
    cadences = []
    mode = candidate_key.mode

    patterns = _MAJOR_CADENCES if mode == 'major' else _MINOR_CADENCES

    i = 0
    while i < len(rns):
        matched = False
        for pattern in patterns:
            if _match_pattern(rns, i, pattern):
                start = i
                end = i + len(pattern) - 1
                cadences.append((start, end, mode))
                i = end + 1
                matched = True
                break
        if not matched:
            i += 1

    return cadences


# ---------------------------------------------------------------------------
# Sequential ii-V detection
# ---------------------------------------------------------------------------

def detect_sequential_iiv(timeline: list[ChordEvent]) -> list[tuple[int, int]]:
    """
    Detect chromatic sequences of ii-V pairs where the V does not resolve
    to a diatonic chord of any established key.

    A sequential ii-V pair is identified by:
    1. Event i has minor 7th quality (ii)
    2. Event i+1 has dominant 7th quality (V)
    3. Event i+1 does NOT resolve down a fifth to event i+2, OR
       event i+2 is another ii chord (continuing the sequence)

    Returns list of (start_idx, end_idx) index pairs into timeline,
    one per sequential ii-V unit.
    """
    from python.leadsheet.annotator import _is_dominant, _is_half_dim
    from python.leadsheet.chord_preprocessor import _ROOT_SPLIT

    _MINOR7_QUALITIES = {'m7', 'm9', 'm11', 'm', 'min7', 'm7b5'}

    def is_minor7(symbol):
        if not symbol or symbol == 'NC':
            return False
        m = _ROOT_SPLIT.match(symbol)
        q = m.group(2) if m else ''
        return q in _MINOR7_QUALITIES or q == 'm7b5'

    def resolves_diatonically(dom_idx, timeline, established_keys):
        """Check if dominant at dom_idx resolves to a chord in any established key."""
        if dom_idx + 1 >= len(timeline):
            return False
        next_event = timeline[dom_idx + 1]
        next_pc = root_pc_from_symbol(next_event.symbol)
        dom_pc = root_pc_from_symbol(timeline[dom_idx].symbol)
        if next_pc is None or dom_pc is None:
            return False
        interval = (next_pc - dom_pc) % 12
        # Perfect fourth up = fifth down (V→I), or tritone sub
        return interval in {5, 6}

    sequences = []
    i = 0
    while i < len(timeline) - 1:
        if is_minor7(timeline[i].symbol):
            m = _ROOT_SPLIT.match(timeline[i].symbol)
            ii_quality = m.group(2) if m else ''
            # Check if next is dominant
            if i + 1 < len(timeline) and _is_dominant(
                    _ROOT_SPLIT.match(timeline[i+1].symbol).group(2)
                    if _ROOT_SPLIT.match(timeline[i+1].symbol) else ''):
                # Check if this V resolves to another ii (continuing sequence)
                # or does not resolve diatonically
                is_seq = False
                if i + 2 < len(timeline):
                    next_next = timeline[i + 2]
                    if is_minor7(next_next.symbol):
                        is_seq = True   # V→ii = continuing sequence
                    elif not resolves_diatonically(i + 1, timeline, []):
                        is_seq = True

                if is_seq:
                    # Determine implied mode from ii quality
                    mode = 'dorian' if ii_quality == 'm7b5' else 'major'
                    sequences.append((i, i + 1, mode))
                    i += 2
                    continue
        i += 1

    return sequences


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def detect_tonal_areas(ls: LeadSheet,
                        candidate_keys: Optional[list] = None) -> None:
    """
    Detect tonal areas in a LeadSheet and annotate each ChordEvent with:
        .tonal_area       — music21 Key object or None
        .tonal_area_type  — 'diatonic' | 'sequential' | 'passing'
        .tonal_area_scale — frozenset of pitch classes

    Args:
        ls              — LeadSheet (should already be annotated by annotator.py)
        candidate_keys  — list of music21 Key objects to test; if None,
                          inferred automatically using 4-bar and 8-bar windows
    """
    timeline = ls.chord_timeline
    n = len(timeline)

    # Initialize all events as 'passing'
    for event in timeline:
        event.tonal_area       = None
        event.tonal_area_type  = 'passing'
        event.tonal_area_scale = frozenset()

    if not timeline:
        return

    # --- Step 1: determine candidate keys ---
    if candidate_keys is None:
        candidate_keys = _infer_candidate_keys(ls)

    # --- Step 2: for each candidate key, detect cadences ---
    # Build a mapping from event index → (key, type)
    area_map = {}   # idx → (m21key.Key, 'diatonic')

    for k in candidate_keys:
        rn_pairs = build_rn_sequence(timeline, k)
        cadences = detect_cadences(rn_pairs, k)

        # Debug output — remove after testing
        print(f"\nCadences detected for {k}:")
        for s, e, m in cadences:
            print(f"  idx {s}-{e}: {[rn_pairs[i][0].symbol for i in range(s, e+1)]}")

        for start_idx, end_idx, mode in cadences:
            coverage_start = _extend_backward(
                start_idx, rn_pairs, k, area_map)

            pattern_length = end_idx - start_idx + 1

            for idx in range(coverage_start, end_idx + 1):
                if idx not in area_map:
                    area_map[idx] = (k, 'diatonic', pattern_length)
                else:
                    # Keep the entry with the longer (stronger) pattern
                    existing_length = area_map[idx][2]
                    if pattern_length > existing_length:
                        area_map[idx] = (k, 'diatonic', pattern_length)

            # Extend forward: tonal area persists until next cadence
            # (handled by forward fill below)

    # --- Step 3: detect sequential ii-V pairs ---
    seq_pairs = detect_sequential_iiv(timeline)
    seq_map = {}   # idx → (implied_root_pc, mode)

    for start_idx, end_idx, mode in seq_pairs:
        # Only mark as sequential if not already assigned as diatonic
        dom_event = timeline[end_idx]
        implied_root, _ = implied_tonic_from_dominant(dom_event)
        for idx in range(start_idx, end_idx + 1):
            if idx not in area_map:
                seq_map[idx] = (implied_root, mode)

    # --- Step 4: assign tonal areas using nearest-cadence logic ---
    # For each unassigned event, find the nearest cadence by index distance.
    # We prefer the upcoming cadence over the past one (jazz is forward-looking),
    # but only if it's within a reasonable distance (max_lookahead bars).

    # Build sorted list of cadence anchor points: (idx, key)
    cadence_anchors = sorted(area_map.items())   # [(idx, (key, type, len)), ...]

    filled_map = {}

    # First pass: mark all directly detected cadence events
    for idx, (k, atype, _) in area_map.items():
        filled_map[idx] = (k, atype)

    # Second pass: assign unassigned non-sequential events
    cadence_indices = [idx for idx, _ in cadence_anchors]

    for idx in range(n):
        if idx in filled_map or idx in seq_map:
            continue

        # Find nearest past and future cadence
        past_cadences   = [(i, area_map[i][0]) for i in cadence_indices if i <= idx]
        future_cadences = [(i, area_map[i][0]) for i in cadence_indices if i > idx]

        past_key   = past_cadences[-1][1]   if past_cadences   else None
        future_key = future_cadences[0][1]  if future_cadences else None
        past_dist  = idx - past_cadences[-1][0]  if past_cadences  else float('inf')
        future_dist = future_cadences[0][0] - idx if future_cadences else float('inf')

        if past_key is None and future_key is None:
            continue  # No cadences at all — leave as passing

        if past_key is None:
            chosen_key = future_key
        elif future_key is None:
            chosen_key = past_key
        elif past_key == future_key:
            # Same key on both sides — unambiguous
            chosen_key = past_key
        else:
            # Different keys on either side — boundary zone
            # Use future key if close (within 2 events), past key otherwise
            # This captures the "preparation" feel of jazz harmony
            if future_dist <= 2:
                chosen_key = future_key
            else:
                chosen_key = past_key

        filled_map[idx] = (chosen_key, 'diatonic')

    # --- Step 5: write results back to events ---
    for idx, event in enumerate(timeline):
        if idx in filled_map:
            k, atype = filled_map[idx]
            event.tonal_area      = k
            event.tonal_area_type = atype
            event.tonal_area_scale = scale_pcs_for_key(k)

        elif idx in seq_map:
            root_pc, mode = seq_map[idx]
            event.tonal_area      = None
            event.tonal_area_type = 'sequential'
            event.tonal_area_scale = scale_pcs_from_root_and_mode(
                root_pc, mode)

        # else: remains 'passing' with empty scale — annotator's per-chord
        # scale_pcs is used as fallback


def _extend_backward(start_idx: int,
                      rn_pairs: list[tuple[ChordEvent, str]],
                      k: m21key.Key,
                      existing_map: dict) -> int:
    """
    Extend a cadential unit backward to include preparation chords
    that are diatonic to the same key (vi, IV, etc.).
    Stops at any chord already assigned to a different key.
    """
    diatonic_rns = {'I', 'i', 'ii', 'iii', 'IV', 'iv',
                    'V', 'vi', 'vii', 'bVII', 'VI'}
    pos = start_idx - 1
    while pos >= 0:
        if pos in existing_map and existing_map[pos][0] != k:
            break
        rn = rn_pairs[pos][1]
        if rn not in diatonic_rns:
            break
        pos -= 1
    return pos + 1


def _infer_candidate_keys(ls: LeadSheet) -> list:
    """
    Automatically infer candidate key areas by running music21 key analysis
    on 8-bar windows and collecting unique results.
    """
    from music21 import stream, chord as m21chord

    timeline = ls.chord_timeline
    if not timeline:
        return []

    total_bars = ls.total_bars
    window = 8
    candidates = {}   # key_str → Key object (deduplicated)

    for start_bar in range(1, total_bars + 1, window):
        end_bar = start_bar + window - 1
        s = stream.Stream()
        for event in timeline:
            if start_bar <= event.bar <= end_bar:
                if event.symbol == 'NC':
                    continue
                figure = to_music21_figure(event.symbol)
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter('ignore')
                        cs = harmony.ChordSymbol(figure)
                    c = m21chord.Chord(cs.pitches)
                    c.quarterLength = float(event.duration)
                    s.append(c)
                except Exception:
                    continue
        if len(s) > 0:
            try:
                k = s.analyze('key')
                key_str = f"{k.tonic.name} {k.mode}"
                if key_str not in candidates:
                    candidates[key_str] = k
                # Also add the parallel and relative keys as candidates
                rel = k.relative
                rel_str = f"{rel.tonic.name} {rel.mode}"
                if rel_str not in candidates:
                    candidates[rel_str] = rel
            except Exception:
                continue

    return list(candidates.values())


# ---------------------------------------------------------------------------
# CLI — quick test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    from python.leadsheet.parser import parse
    from python.leadsheet.annotator import annotate

    path = sys.argv[1] if len(sys.argv) > 1 else \
        '/usr/share/impro-visor/leadsheets/imaginary-book/ByeByeBlackbird.ls'

    print(f"Parsing: {path}\n")
    ls = parse(path)
    annotate(ls)
    detect_tonal_areas(ls)

    print(f"{'Bar':>4} {'Beat':>5} {'Chord':>12} {'Type':>12} "
          f"{'Key Area':>12} {'Scale PCs':>30}")
    print('-' * 85)

    for event in ls.chord_timeline:
        key_str = str(event.tonal_area) if event.tonal_area else '—'
        scale_str = str(sorted(event.tonal_area_scale))
        print(f"{event.bar:>4} {float(event.beat):>5.1f} "
              f"{event.symbol:>12} {event.tonal_area_type:>12} "
              f"{key_str:>12} {scale_str:>30}")

"""
annotator.py — Trad-Four Phase 1b
Harmonic annotator: enriches each ChordEvent in a LeadSheet with
music21 chord data, derived note pools, scale association, and
infers the overall key of the leadsheet.

Adds to each ChordEvent:
    .m21_chord      — music21 ChordSymbol object (None for NC)
    .chord_tones    — frozenset of pitch classes (root, 3rd, 5th, 7th)
    .color_tones    — frozenset of pitch classes (extensions: 9, 11, 13 etc.)
    .scale_tones    — frozenset of pitch classes (scale minus chord+color)
    .scale_name     — string e.g. 'dorian', 'mixolydian', 'lydian_dominant'
    .scale_pcs      — frozenset of all scale pitch classes

Adds to LeadSheet:
    .inferred_key   — music21 key.Key object

Usage:
    from python.leadsheet.parser import parse
    from python.leadsheet.annotator import annotate

    ls = parse('path/to/tune.ls')
    annotate(ls)

    # Query a chord event
    event = ls.chord_at(2, 1.0)
    print(event.chord_tones)    # frozenset of pitch classes
    print(event.scale_name)     # 'mixolydian'
"""

import warnings
from fractions import Fraction
from typing import Optional

from music21 import harmony, key, pitch, scale, stream, chord as m21chord

from python.leadsheet.parser import LeadSheet, ChordEvent
from python.leadsheet.chord_preprocessor import to_music21_figure

# ---------------------------------------------------------------------------
# Scale selection table
# Maps chord quality strings (as they appear in normalized chord symbols)
# to scale names and their pitch-class interval sets.
# Interval sets are semitone offsets from root (0=root, 2=M2, etc.)
# ---------------------------------------------------------------------------

# Scale interval sets (semitones from root)
_SCALE_INTERVALS = {
    'ionian':           [0, 2, 4, 5, 7, 9, 11],
    'dorian':           [0, 2, 3, 5, 7, 9, 10],
    'phrygian':         [0, 1, 3, 5, 7, 8, 10],
    'lydian':           [0, 2, 4, 6, 7, 9, 11],
    'mixolydian':       [0, 2, 4, 5, 7, 9, 10],
    'aeolian':          [0, 2, 3, 5, 7, 8, 10],
    'locrian':          [0, 1, 3, 5, 6, 8, 10],
    'lydian_dominant':  [0, 2, 4, 6, 7, 9, 10],   # Lydian b7
    'altered':          [0, 1, 3, 4, 6, 8, 10],   # Super-Locrian
    'hw_diminished':    [0, 1, 3, 4, 6, 7, 9, 10], # Half-whole diminished
    'wh_diminished':    [0, 2, 3, 5, 6, 8, 9, 11], # Whole-half diminished
    'whole_tone':       [0, 2, 4, 6, 8, 10],
    'melodic_minor':    [0, 2, 3, 5, 7, 9, 11],
    'lydian_augmented': [0, 2, 4, 6, 8, 9, 11],   # Melodic minor mode 3
    'locrian_sharp2':   [0, 2, 3, 5, 6, 8, 10],   # Melodic minor mode 6
    'diminished':       [0, 2, 3, 5, 6, 8, 9, 11], # Full diminished
    'augmented':        [0, 3, 4, 7, 8, 11],        # Augmented scale
}

# Quality → scale name mapping
# Keys are quality suffixes as they appear in normalized chord symbols
# (after chord_preprocessor normalization)
_QUALITY_TO_SCALE = {
    # Major family → Ionian / Lydian
    '':         'ionian',
    'maj7':     'ionian',
    'maj9':     'ionian',
    'M9':       'ionian',
    'maj13':    'ionian',
    'M13':      'ionian',
    '6':        'ionian',
    'M6':       'ionian',
    '69':       'ionian',
    'add9':     'ionian',
    'maj7#11':  'lydian',
    'maj9#11':  'lydian',
    'maj13#11': 'lydian',

    # Dominant family → Mixolydian (default) or variants
    '7':        'mixolydian',
    '9':        'mixolydian',
    '11':       'mixolydian',
    '13':       'mixolydian',
    '7sus':     'mixolydian',
    '7sus4':    'mixolydian',
    '9sus4':    'mixolydian',
    '13sus':    'mixolydian',
    '7#11':     'lydian_dominant',
    '9#11':     'lydian_dominant',
    '13#11':    'lydian_dominant',
    '7b9':      'hw_diminished',
    '7#9':      'hw_diminished',
    '7b9#9':    'hw_diminished',
    '7b9b13':   'hw_diminished',
    '7b9#11':   'hw_diminished',
    '7#9b13':   'hw_diminished',
    '7alt':     'altered',
    '7b9sus4':  'mixolydian',   # approximate
    '7b13':     'mixolydian',   # approximate

    # Minor family → Dorian (default)
    'm':        'dorian',
    'm7':       'dorian',
    'm9':       'dorian',
    'm11':      'dorian',
    'm13':      'dorian',
    'm6':       'dorian',
    'm69':      'dorian',
    'min7':     'dorian',
    'mM7':      'melodic_minor',
    'mM9':      'melodic_minor',

    # Half-diminished → Locrian #2
    'm7b5':     'locrian_sharp2',

    # Diminished → whole-half diminished
    'dim7':     'wh_diminished',
    'dim':      'wh_diminished',
    'o7':       'wh_diminished',
    'o':        'wh_diminished',

    # Augmented
    'aug':      'whole_tone',
    'aug7':     'whole_tone',
    'augmaj7':  'lydian_augmented',
    '+':        'whole_tone',
    '+7':       'whole_tone',

    # Suspended
    'sus4':     'mixolydian',
    'sus2':     'ionian',

    # Power / pedal
    'power':    'ionian',
    'pedal':    'ionian',
}

_DEFAULT_SCALE = 'ionian'

# Qualities that identify a chord as a dominant 7th family
_DOMINANT_QUALITIES = {
    '7', '9', '11', '13',
    '7b9', '7#9', '7alt', '7b13', '7#11', '7b9b13', '7#9b13',
    '7b9#9', '7b9#11', '7b9sus4', '7sus', '7sus4', '9sus4',
    '13sus', '13sus4', '9+', 'aug7', '+7',
}

# Qualities that identify a chord as half-diminished
_HALF_DIM_QUALITIES = {'m7b5'}

# Qualities that identify a chord as minor tonic
_MINOR_TONIC_QUALITIES = {
    'm', 'm7', 'm9', 'm11', 'm13', 'm6', 'm69', 'mM7', 'mM9', 'min7'
}

# Qualities that identify a chord as major tonic
_MAJOR_TONIC_QUALITIES = {
    '', 'maj7', 'maj9', 'M9', 'maj13', 'M13', '6', 'M6', '69',
    'add9', 'maj7#11', 'maj9#11', 'maj13#11'
}

def _get_scale_name(quality: str) -> str:
    """
    Return the scale name for a given chord quality string.
    Falls back to longest-prefix match, then to ionian.
    """
    if quality in _QUALITY_TO_SCALE:
        return _QUALITY_TO_SCALE[quality]
    # Try prefix match (longest first)
    for q in sorted(_QUALITY_TO_SCALE.keys(), key=len, reverse=True):
        if quality.startswith(q) and q:
            return _QUALITY_TO_SCALE[q]
    return _DEFAULT_SCALE

def _root_pc_from_symbol(symbol: str) -> Optional[int]:
    """Extract root pitch class (0-11) from a chord symbol string."""
    from python.leadsheet.chord_preprocessor import _ROOT_SPLIT, _FLAT_ROOTS
    _NOTE_TO_PC = {
        'C': 0, 'D': 2, 'E': 4, 'F': 5,
        'G': 7, 'A': 9, 'B': 11
    }
    if not symbol or symbol == 'NC':
        return None
    m = _ROOT_SPLIT.match(symbol)
    if not m:
        return None
    root_str = m.group(1)
    # Convert flat root notation
    root_m21 = _FLAT_ROOTS.get(root_str, root_str)
    # root_m21 is now e.g. 'B-', 'A-', 'G' etc.
    letter = root_m21[0]
    pc = _NOTE_TO_PC.get(letter, 0)
    if len(root_m21) > 1:
        if root_m21[1] == '-':
            pc = (pc - 1) % 12
        elif root_m21[1] == '#':
            pc = (pc + 1) % 12
    return pc


def _is_dominant(quality: str) -> bool:
    """Return True if quality string identifies a dominant 7th chord."""
    if quality in _DOMINANT_QUALITIES:
        return True
    # Prefix match for compound dominants like '7b9#11'
    for q in _DOMINANT_QUALITIES:
        if quality.startswith(q):
            return True
    return False


def _is_half_dim(quality: str) -> bool:
    return quality in _HALF_DIM_QUALITIES


def _resolves_to_minor(next_event: Optional[ChordEvent]) -> bool:
    """Return True if next_event is a minor tonic chord."""
    if next_event is None or next_event.symbol == 'NC':
        return False
    from python.leadsheet.chord_preprocessor import _ROOT_SPLIT
    m = _ROOT_SPLIT.match(next_event.symbol)
    quality = m.group(2) if m else ''
    return quality in _MINOR_TONIC_QUALITIES


def _resolves_to_major(next_event: Optional[ChordEvent]) -> bool:
    """Return True if next_event is a major tonic chord."""
    if next_event is None or next_event.symbol == 'NC':
        return False
    from python.leadsheet.chord_preprocessor import _ROOT_SPLIT
    m = _ROOT_SPLIT.match(next_event.symbol)
    quality = m.group(2) if m else ''
    return quality in _MAJOR_TONIC_QUALITIES


def _is_fifth_resolution(current_root_pc: int,
                          next_event: Optional[ChordEvent]) -> bool:
    """
    Return True if next_event's root is a perfect fourth above
    (= perfect fifth below) the current root — the canonical V→I motion.
    Also handles tritone substitutions (b2 above = augmented fourth).
    """
    if next_event is None or next_event.symbol == 'NC':
        return False
    next_pc = _root_pc_from_symbol(next_event.symbol)
    if next_pc is None:
        return False
    interval = (next_pc - current_root_pc) % 12
    return interval in {5,   # perfect fourth up (V→I)
                        6}   # tritone sub (bII→I)


def _get_scale_name_with_context(quality: str,
                                  root_pc: int,
                                  next_event: Optional[ChordEvent]) -> str:
    """
    Return scale name for a chord quality, sharpened by resolution context
    where musically relevant.

    For dominant 7th chords:
      - Altered dominant qualities (7alt, 7b9, 7#9 etc.) → always altered/hw_dim
      - Plain dominant resolving to minor via V→I → hw_diminished
      - Plain dominant resolving to major via V→I → mixolydian
      - With #11 → lydian_dominant
      - No clear resolution → mixolydian (safe default)

    For half-diminished chords:
      - Next chord is dominant resolving to minor → locrian_sharp2 (ii in minor)
      - Otherwise → locrian (passing usage)
    """
    # --- Altered dominants: quality already specifies the scale ---
    if quality in {'7alt'}:
        return 'altered'
    if quality in {'7b9', '7#9', '7b9#9', '7b9b13', '7#9b13', '7b9#11'}:
        return 'hw_diminished'

    # --- Plain dominant: use resolution context ---
    if _is_dominant(quality):
        # #11 variants → lydian dominant regardless of resolution
        if '#11' in quality:
            return 'lydian_dominant'

        if _is_fifth_resolution(root_pc, next_event):
            if _resolves_to_minor(next_event):
                return 'hw_diminished'
            if _resolves_to_major(next_event):
                return 'mixolydian'

        # No clear resolution or non-fifth motion → safe default
        return _QUALITY_TO_SCALE.get(quality, 'mixolydian')

    # --- Half-diminished: check if ii in minor ---
    if _is_half_dim(quality):
        # Look ahead: if next is a dominant that itself resolves to minor,
        # we're in a iim7b5–V7–im cadence
        if next_event is not None and next_event.symbol != 'NC':
            from python.leadsheet.chord_preprocessor import _ROOT_SPLIT
            m = _ROOT_SPLIT.match(next_event.symbol)
            next_quality = m.group(2) if m else ''
            if _is_dominant(next_quality):
                return 'locrian_sharp2'
        return 'locrian'

    # --- All other qualities: static lookup ---
    return _get_scale_name(quality)
    """
    Return the scale name for a given chord quality string.
    Falls back to longest-prefix match, then to ionian.
    """
    if quality in _QUALITY_TO_SCALE:
        return _QUALITY_TO_SCALE[quality]
    # Try prefix match (longest first)
    for q in sorted(_QUALITY_TO_SCALE.keys(), key=len, reverse=True):
        if quality.startswith(q) and q:
            return _QUALITY_TO_SCALE[q]
    return _DEFAULT_SCALE


def _pitch_class(p: pitch.Pitch) -> int:
    """Return the pitch class (0–11) of a music21 Pitch."""
    return p.pitchClass


def _scale_pitch_classes(root_pc: int, scale_name: str) -> frozenset:
    """
    Compute the set of pitch classes for a scale given root pitch class
    and scale name.
    """
    intervals = _SCALE_INTERVALS.get(scale_name, _SCALE_INTERVALS['ionian'])
    return frozenset((root_pc + i) % 12 for i in intervals)


# ---------------------------------------------------------------------------
# Core annotation function
# ---------------------------------------------------------------------------

def annotate_chord(event: ChordEvent,
                   next_event: Optional[ChordEvent] = None) -> None:
    """
    Annotate a single ChordEvent in place with music21 data and derived
    note pools. Modifies the event object directly.

    Args:
        event      — the ChordEvent to annotate
        next_event — the following ChordEvent (used for resolution-aware
                     scale selection on dominant and half-diminished chords)

    Sets:
        event.m21_chord     — music21 ChordSymbol or None
        event.chord_tones   — frozenset of pitch classes
        event.color_tones   — frozenset of pitch classes
        event.scale_tones   — frozenset of pitch classes
        event.scale_name    — string
        event.scale_pcs     — frozenset of all scale pitch classes
    """
    # Default empty pools
    event.m21_chord   = None
    event.chord_tones = frozenset()
    event.color_tones = frozenset()
    event.scale_tones = frozenset()
    event.scale_name  = 'ionian'
    event.scale_pcs   = frozenset()

    if event.symbol == 'NC':
        return

    # --- Build music21 ChordSymbol ---
    figure = to_music21_figure(event.symbol)
    if figure is None:
        return

    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            cs = harmony.ChordSymbol(figure)
        event.m21_chord = cs
    except Exception as e:
        warnings.warn(f"annotator: could not parse '{event.symbol}' "
                      f"(figure='{figure}'): {e}")
        return

    # --- Extract pitch classes from ChordSymbol ---
    try:
        pitches = cs.pitches
    except Exception:
        return

    if not pitches:
        return

    root_pc = _pitch_class(pitches[0])

    # Chord tones: root, 3rd, 5th, 7th (indices 0, 1, 2, 3)
    # Color tones: extensions beyond 7th (indices 4+)
    chord_pcs  = frozenset(_pitch_class(p) for p in pitches[:4])
    color_pcs  = frozenset(_pitch_class(p) for p in pitches[4:])

    # --- Scale selection with resolution context ---
    from python.leadsheet.chord_preprocessor import _ROOT_SPLIT
    m = _ROOT_SPLIT.match(event.symbol)
    quality = m.group(2) if m else ''

    scale_name = _get_scale_name_with_context(quality, root_pc, next_event)
    scale_pcs  = _scale_pitch_classes(root_pc, scale_name)

    # Scale tones = scale pitches not already in chord or color tones
    scale_only_pcs = scale_pcs - chord_pcs - color_pcs

    event.chord_tones = chord_pcs
    event.color_tones = color_pcs
    event.scale_tones = scale_only_pcs
    event.scale_name  = scale_name
    event.scale_pcs   = scale_pcs


def annotate(ls: LeadSheet,
             infer_key: bool = True,
             register: tuple = (48, 84)) -> None:
    """
    Annotate all ChordEvents in a LeadSheet in place.

    Args:
        ls          — LeadSheet object (from parser.parse())
        infer_key   — if True, infer the key from the chord progression
                      and store in ls.inferred_key
        register    — (low_midi, high_midi) range for MIDI note pools
                      (not used in current implementation — pools are
                      pitch-class-based; register expansion is Phase 3's job)

    After annotation, each ChordEvent has:
        .m21_chord, .chord_tones, .color_tones,
        .scale_tones, .scale_name, .scale_pcs
    """
    # Annotate each chord event with lookahead context
    timeline = ls.chord_timeline
    for i, event in enumerate(timeline):
        next_event = timeline[i + 1] if i + 1 < len(timeline) else None
        annotate_chord(event, next_event)

    # Infer key from chord progression
    if infer_key:
        ls.inferred_key = _infer_key(ls)


def _infer_key(ls: LeadSheet) -> Optional[key.Key]:
    """
    Infer the key of a leadsheet using music21's key analysis.
    Builds a stream of chords and runs the Krumhansl-Schmuckler
    key-finding algorithm.

    Returns a music21 Key object, or None if inference fails.
    """
    if not ls.chord_timeline:
        return None

    try:
        s = stream.Stream()
        for event in ls.chord_timeline:
            if event.m21_chord is None:
                continue
            # Use the chord's pitches as a Chord object for key analysis
            try:
                pitches = event.m21_chord.pitches
                if not pitches:
                    continue
                c = m21chord.Chord(pitches)
                c.quarterLength = float(event.duration)
                s.append(c)
            except Exception:
                continue

        if len(s) == 0:
            return None

        k = s.analyze('key')
        return k

    except Exception as e:
        warnings.warn(f"Key inference failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Convenience query functions
# ---------------------------------------------------------------------------

def note_function(midi_pitch: int, event: ChordEvent) -> str:
    """
    Classify a MIDI pitch against the annotation of a ChordEvent.

    Returns one of:
        'C'  — chord tone
        'L'  — color/tension tone
        'S'  — scale tone
        'A'  — approach tone (chromatic neighbor of a chord tone)
        'X'  — outside (chromatic)
        'NC' — no chord context
    """
    if event.symbol == 'NC':
        return 'NC'

    pc = midi_pitch % 12

    if pc in event.chord_tones:
        return 'C'
    if pc in event.color_tones:
        return 'L'
    if pc in event.scale_tones:
        return 'S'
    # Approach tone: half-step above or below any chord tone
    for ct in event.chord_tones:
        if (pc - ct) % 12 == 1 or (ct - pc) % 12 == 1:
            return 'A'
    return 'X'


def midi_note_pool(event: ChordEvent,
                   note_type: str,
                   low: int = 48,
                   high: int = 84) -> list[int]:
    """
    Return a list of MIDI pitches in the given register for a note type.

    Args:
        event     — annotated ChordEvent
        note_type — 'C', 'L', 'S', or 'A' (all scale tones)
        low, high — MIDI pitch range (inclusive)

    Returns:
        Sorted list of MIDI pitches.
    """
    if note_type == 'C':
        pcs = event.chord_tones
    elif note_type == 'L':
        pcs = event.color_tones
    elif note_type == 'S':
        pcs = event.scale_tones
    elif note_type == 'A':
        pcs = event.scale_pcs   # all scale tones including chord/color
    else:
        pcs = frozenset(range(12))  # X: chromatic

    return [m for m in range(low, high + 1) if m % 12 in pcs]


# ---------------------------------------------------------------------------
# CLI — quick test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    from python.leadsheet.parser import parse

    path = sys.argv[1] if len(sys.argv) > 1 else \
        '/usr/share/impro-visor/leadsheets/imaginary-book/ByeByeBlackbird.ls'

    print(f"Parsing: {path}")
    ls = parse(path)
    annotate(ls)

    print(f"\n{ls}")
    print(f"Inferred key: {ls.inferred_key}\n")

    print(f"{'Bar':>4} {'Beat':>5} {'Chord':>12} {'Scale':>18} "
          f"{'ChordTones':>30} {'ColorTones':>20} {'ScaleTones':>30}")
    print('-' * 120)

    for event in ls.chord_timeline:
        ct = sorted(event.chord_tones)
        col = sorted(event.color_tones)
        st = sorted(event.scale_tones)
        print(f"{event.bar:>4} {float(event.beat):>5.1f} "
              f"{event.symbol:>12} {event.scale_name:>18} "
              f"{str(ct):>30} {str(col):>20} {str(st):>30}")

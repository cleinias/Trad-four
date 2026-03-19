"""
chord_preprocessor.py — Trad-Four Phase 1b
Normalizes Impro-Visor chord symbols to music21-compatible figure strings.

The two main problems solved:
1. Flat root parsing: music21 misreads 'Bb' as root='B' + quality='b...'
   Fix: convert flat roots to music21's internal '-' notation (Bb → B-)
2. Unsupported quality abbreviations: music21's CHORD_TYPES doesn't cover
   all jazz vocabulary used in Impro-Visor.
   Fix: map to the closest supported equivalent.

Usage:
    from chord_preprocessor import to_music21_figure
    from music21 import harmony

    figure = to_music21_figure('Bbmaj9')   # → 'B- M9'
    cs = harmony.ChordSymbol(figure)
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Root handling
# ---------------------------------------------------------------------------

_ROOT_SPLIT = re.compile(r'^([A-G][b#]?)(.*)$')

# music21 uses '-' for flats internally
_FLAT_ROOTS = {
    'Ab': 'A-', 'Bb': 'B-', 'Cb': 'C-',
    'Db': 'D-', 'Eb': 'E-', 'Fb': 'F-', 'Gb': 'G-'
}

# ---------------------------------------------------------------------------
# Quality normalization map
# Maps Impro-Visor quality strings → music21 CHORD_TYPES abbreviations
# Ordered longest-first to ensure correct prefix matching
# ---------------------------------------------------------------------------

_QUALITY_MAP = {
    # --- maj9 variants (music21 uses M9/Maj9 not maj9) ---
    'maj13#11':  'M13',       # close enough — #11 lost but avoids crash
    'maj13':     'M13',
    'maj9#11':   'M9',        # #11 lost
    'maj9#5':    'augmaj9',
    'maj9':      'M9',
    'maj7+':     'augmaj7',
    'maj7#5':    'augmaj7',

    # --- M6 / M69 variants (music21 uses '6' not 'M6') ---
    'M69#11':    '6',         # approximate
    'M69':       '6',
    'M6':        '6',

    # --- m69 / 69 variants ---
    'm69':       'm6',        # approximate: drop the 9
    '69':        '6',         # approximate

    # --- minor-major seventh ---
    'mMaj7':     'mM7',
    'mMaj9':     'mM9',

    # --- augmented minor ---
    'm+':        '+',         # approximate: treat as augmented

    # --- altered dominant ---
    # 7alt = dominant with b9, #9, b5/#11, b13 — approximate with 7b9
    '7alt':      '7b9',

    # --- augmented ninth ---
    '9+':        'aug9',

    # --- suspended variants ---
    '13sus4':    '7sus4',     # approximate
    '13sus':     '7sus4',     # approximate
    '9sus4':     '7sus4',     # approximate
    '9sus':      '7sus',      # approximate
    '7b9sus4':   '7sus4',     # approximate
    'b9sus4':    '7sus4',     # approximate
    '7sus4b9':   '7sus4',     # approximate
    '7susb9':    '7sus',      # approximate
     'add9no3':   'sus2',    # no 3rd + 9 = suspended second, close enough

    # --- add chords ---
    'madd9':     'm9',        # approximate
    'add9':      'M9',        # approximate
    'addb9':     '7b9',       # approximate

    # --- oM7 / o7M7 — diminished with major seventh ---
    'o7M7':      'o7',        # drop the M7
    'oM7':       'o7',        # drop the M7

    # --- modal / other ---
    'phryg':     'sus4',      # very rough approximation
    'sus24':     'sus4',      # drop the sus2 component

    # --- Bass marker — treat as power chord (root only) ---
    'Bass':      'pedal',
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def normalize_quality(quality: str) -> str:
    """
    Map an unsupported Impro-Visor quality string to the closest
    music21-supported abbreviation. Returns the original if no mapping found.
    """
    # Try exact match first (longest-first ordering in dict handles prefixes)
    if quality in _QUALITY_MAP:
        return _QUALITY_MAP[quality]

    # Try prefix matches for compound qualities like '7alt#9' or 'maj9sus'
    # Sort by length descending to match longest prefix first
    for src, dst in sorted(_QUALITY_MAP.items(), key=lambda x: -len(x[0])):
        if quality.startswith(src):
            remainder = quality[len(src):]
            return dst + remainder  # append any trailing alterations

    return quality  # unknown — pass through and let music21 handle/fail


def to_music21_figure(symbol: str) -> Optional[str]:
    """
    Convert an Impro-Visor chord symbol to a music21-parseable figure string.

    Returns None for special tokens (NC) that should not be sent to music21.

    Steps:
      1. Handle special tokens
      2. Split root from quality
      3. Convert flat root to music21 '-' notation
      4. Normalize quality to music21-supported abbreviation
      5. Return as '<root> <quality>' figure string

    Examples:
        'Gm7'       → 'G m7'
        'Bbmaj7'    → 'B- maj7'
        'Abdim7'    → 'A- dim7'
        'C7alt'     → 'C 7b9'
        'Bbmaj9'    → 'B- M9'
        'FM6'       → 'F 6'
        'NC'        → None
    """
    if not symbol or symbol == 'NC':
        return None

    # Split root and quality
    m = _ROOT_SPLIT.match(symbol)
    if not m:
        return None

    root = m.group(1)
    quality = m.group(2)

    # Convert flat root to music21 internal notation
    root_m21 = _FLAT_ROOTS.get(root, root)

    # Normalize quality
    quality_m21 = normalize_quality(quality) if quality else ''

    return f"{root_m21} {quality_m21}".strip()


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------

def make_chord_symbol(symbol: str):
    """
    Parse an Impro-Visor chord symbol into a music21 ChordSymbol object.
    Returns None for NC and other non-chord tokens.
    Raises ValueError if music21 cannot parse the normalized figure.
    """
    from music21 import harmony

    figure = to_music21_figure(symbol)
    if figure is None:
        return None

    try:
        cs = harmony.ChordSymbol(figure)
        return cs
    except Exception as e:
        raise ValueError(f"Cannot parse chord symbol '{symbol}' "
                         f"(figure='{figure}'): {e}") from e


# ---------------------------------------------------------------------------
# CLI — quick test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    from music21 import harmony

    test_symbols = sys.argv[1:] or [
        'Gm7', 'Bbmaj7', 'Abdim7', 'C7alt', 'FM6', 'Ebm7',
        'Am7b5', 'C7b9', 'F9sus4', 'Bbm69', 'GmMaj7', 'NC',
        'Bbmaj9', 'D7alt', 'Cm+', 'Absus24',
    ]

    print(f"{'Symbol':20} {'Figure':20} {'Pitches'}")
    print('-' * 70)
    for sym in test_symbols:
        figure = to_music21_figure(sym)
        if figure is None:
            print(f"{sym:20} {'(special token)':20} —")
            continue
        try:
            cs = harmony.ChordSymbol(figure)
            pitches = [p.name for p in cs.pitches]
            print(f"{sym:20} {figure:20} {pitches}")
        except Exception as e:
            print(f"{sym:20} {figure:20} ERROR: {e}")
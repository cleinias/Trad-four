"""
chord_block.py — Trad-Four roadmap module
ChordBlock: a single chord, the terminal symbol of the brick grammar.

Mirrors imp.roadmap.brickdictionary.ChordBlock from Impro-Visor.

A ChordBlock carries:
  - root     : pitch class 0-11 (C=0, Db=1, ..., B=11)
  - quality  : quality string normalized to C-root form (e.g. 'm7', '7', 'maj7')
  - symbol   : full chord symbol string (e.g. 'Dm7', 'G7', 'FM7')
  - duration : duration in beats (Fraction), 0 for pattern-matching use

Chord family classification (matches Impro-Visor):
  - isTonic()         : major or minor tonic chord
  - isDominant()      : dominant 7th family
  - isMinor7()        : minor 7th (for join detection)
  - isDiminished()    : diminished family
  - isGeneralizedTonic(): tonic OR minor chord (for stability checks)
"""

from __future__ import annotations
from fractions import Fraction
from typing import Optional

# ---------------------------------------------------------------------------
# Pitch class utilities
# ---------------------------------------------------------------------------

_NOTE_TO_PC: dict[str, int] = {
    'C': 0, 'D': 2, 'E': 4, 'F': 5,
    'G': 7, 'A': 9, 'B': 11
}

_PC_TO_NAME: list[str] = [
    'C', 'Db', 'D', 'Eb', 'E', 'F',
    'Gb', 'G', 'Ab', 'A', 'Bb', 'B'
]

_PC_TO_NAME_SHARPS: list[str] = [
    'C', 'C#', 'D', 'D#', 'E', 'F',
    'F#', 'G', 'G#', 'A', 'A#', 'B'
]


def parse_root(symbol: str) -> tuple[int, str]:
    """
    Parse a chord symbol and return (root_pc, quality_string).
    Handles flat (b) and sharp (#) accidentals.

    Examples:
        'Dm7'    → (2, 'm7')
        'G7'     → (7, '7')
        'FM7'    → (5, 'M7')
        'Bbmaj7' → (10, 'maj7')
        'C'      → (0, '')
        'NC'     → (-1, 'NC')
    """
    if symbol == 'NC' or symbol == 'NOCHORD':
        return -1, 'NC'

    if not symbol or symbol[0] not in _NOTE_TO_PC:
        return -1, symbol

    letter = symbol[0]
    pc = _NOTE_TO_PC[letter]
    pos = 1

    # Accidental
    if pos < len(symbol):
        if symbol[pos] == 'b' and pos + 1 < len(symbol) and symbol[pos + 1].isalpha():
            # 'b' followed by a letter — it's a flat
            pc = (pc - 1) % 12
            pos += 1
        elif symbol[pos] == '#':
            pc = (pc + 1) % 12
            pos += 1
        # If 'b' is followed by a digit or end, it's part of the quality (e.g. 'Cb5')
        # but we still need to handle 'Cb' as C-flat
        elif symbol[pos] == 'b' and (pos + 1 >= len(symbol) or not symbol[pos + 1].isalpha()):
            # Could be 'Cb' (C-flat) — only if nothing follows or digit follows
            # Actually in jazz notation 'Cb' always means C-flat
            pc = (pc - 1) % 12
            pos += 1

    quality = symbol[pos:]
    return pc, quality


def pc_to_name(pc: int, sharps: bool = False) -> str:
    """Convert a pitch class (0-11) to a note name string."""
    if 0 <= pc < 12:
        return _PC_TO_NAME_SHARPS[pc] if sharps else _PC_TO_NAME[pc]
    return '?'


def transpose_symbol(symbol: str, semitones: int) -> str:
    """
    Transpose a chord symbol by a number of semitones.

    Example:
        transpose_symbol('Dm7', 5)  → 'Gm7'
        transpose_symbol('G7', 5)   → 'C7'
    """
    if symbol == 'NC':
        return 'NC'
    pc, quality = parse_root(symbol)
    if pc < 0:
        return symbol
    new_pc = (pc + semitones) % 12
    return pc_to_name(new_pc) + quality


# ---------------------------------------------------------------------------
# Chord family classification
# Mirrors ChordBlock.isDominant(), isMinor7(), isTonic() etc. in Java
# ---------------------------------------------------------------------------

# Quality prefixes/sets for family detection
# All comparisons are done on the quality string (root stripped)

_MAJOR_QUALITIES = {
    '', 'M', 'maj', 'M7', 'maj7', 'M9', 'maj9', 'M13', 'maj13',
    '6', 'M6', '69', 'M69', 'add9', 'add2', 'sus2',
    'M7#11', 'maj7#11', 'M9#11', 'maj9#11',
    '2', '5',   # power/sus chords treated as major family for tonic purposes
}

_MINOR_QUALITIES = {
    'm', 'min', 'm6', 'm69', 'mM7', 'mM9', 'm+', 'mb6', 'm#5',
    '-',   # alternate minor notation
}

_MINOR7_QUALITIES = {
    'm7', 'min7', 'm9', 'm11', 'm13',
}

_DOMINANT_QUALITIES = {
    '7', '9', '11', '13',
    '7b9', '7#9', '7alt', '7b13', '7#11', '7b9b13', '7#9b13',
    '7b9#9', '7b9#11', '7b9sus4', '7sus', '7sus4', '9sus4',
    '13sus', '13sus4', '9+', 'aug7', '+7', '7+',
    'dom7', 'dominant',
}

_HALF_DIM_QUALITIES = {
    'm7b5', 'min7b5', 'm9b5',
}

_DIM_QUALITIES = {
    'dim', 'dim7', 'o', 'o7', 'oM7', 'o7M7',
}

_AUG_QUALITIES = {
    'aug', '+', 'aug7', '+7', '7+', 'augmaj7', '+M7',
}


def _quality_in(quality: str, quality_set: set) -> bool:
    """Check if quality matches any entry in the set."""
    if quality in quality_set:
        return True
    # Prefix match only for multi-char qualities, not single-char ones
    # to avoid 'm' matching 'maj7', 'min7' etc.
    for q in quality_set:
        if len(q) > 1 and quality.startswith(q):
            return True
    return False
# ---------------------------------------------------------------------------
# ChordBlock
# ---------------------------------------------------------------------------

class ChordBlock:
    """
    A single chord — the terminal symbol of the brick grammar.

    Attributes:
        symbol   : full chord symbol string (e.g. 'Dm7')
        root     : pitch class 0-11, or -1 for NC
        quality  : quality string with root stripped (e.g. 'm7')
        duration : duration in beats (Fraction)
        is_section_end : True if this chord marks a phrase/section boundary
    """

    __slots__ = ('symbol', 'root', 'quality', 'duration', 'is_section_end')

    def __init__(self,
                 symbol: str,
                 duration: float | Fraction = Fraction(1),
                 is_section_end: bool = False):
        self.symbol = symbol
        self.root, self.quality = parse_root(symbol)
        self.duration = Fraction(duration).limit_denominator(64)
        self.is_section_end = is_section_end

    # --- Family classification ---

    def is_nochord(self) -> bool:
        return self.root == -1

    def is_major(self) -> bool:
        return _quality_in(self.quality, _MAJOR_QUALITIES)

    def is_minor(self) -> bool:
        return _quality_in(self.quality, _MINOR_QUALITIES)

    def is_minor7(self) -> bool:
        return _quality_in(self.quality, _MINOR7_QUALITIES)

    def is_dominant(self) -> bool:
        return _quality_in(self.quality, _DOMINANT_QUALITIES)

    def is_half_diminished(self) -> bool:
        return _quality_in(self.quality, _HALF_DIM_QUALITIES)

    def is_diminished(self) -> bool:
        return _quality_in(self.quality, _DIM_QUALITIES)

    def is_augmented(self) -> bool:
        return _quality_in(self.quality, _AUG_QUALITIES)

    def is_tonic(self) -> bool:
        """True for major or pure minor tonic chords (not minor7)."""
        return self.is_major() or (self.is_minor() and not self.is_minor7())

    def is_generalized_tonic(self) -> bool:
        """
        True for major, minor, or minor7 — used for 'first stability' check
        in join detection (Impro-Visor: isGeneralizedTonic).
        """
        return self.is_major() or self.is_minor() or self.is_minor7()

    def chord_family(self) -> str:
        """Return a coarse family label for display/debugging."""
        if self.is_nochord():    return 'NC'
        if self.is_dominant():   return 'dominant'
        if self.is_half_diminished(): return 'half_dim'
        if self.is_diminished(): return 'diminished'
        if self.is_augmented():  return 'augmented'
        if self.is_minor7():     return 'minor7'
        if self.is_minor():      return 'minor'
        if self.is_major():      return 'major'
        return 'unknown'

    # --- Transposition ---

    def transpose(self, semitones: int) -> 'ChordBlock':
        """Return a new ChordBlock transposed by semitones."""
        if self.is_nochord():
            return ChordBlock('NC', self.duration, self.is_section_end)
        new_root = (self.root + semitones) % 12
        new_symbol = pc_to_name(new_root) + self.quality
        return ChordBlock(new_symbol, self.duration, self.is_section_end)

    def transposed_to_c(self) -> 'ChordBlock':
        """Return a copy transposed so root is C (for equivalence checking)."""
        return self.transpose(-self.root)

    # --- Equivalence checking ---

    def quality_matches(self, other: 'ChordBlock',
                        edict: 'EquivalenceDict | None' = None) -> bool:
        """
        True if this chord's quality matches other's quality,
        optionally via an equivalence dictionary.
        Both chords must have the same root for this to be meaningful.
        """
        if self.quality == other.quality:
            return True
        if edict is not None:
            return edict.are_equivalent(self, other)
        return False

    def same(self, other: 'ChordBlock') -> bool:
        """True if root and quality are identical."""
        return self.root == other.root and self.quality == other.quality

    # --- Comparison helpers for join detection ---

    def resolves_to(self, other: 'ChordBlock') -> bool:
        """
        True if this chord (as a dominant) resolves to other via V→I motion
        (root of other is a perfect fourth above this root).
        Mirrors PostProcessor.doesResolve(ChordBlock, Block).
        """
        return (self.root + 5) % 12 == other.root

    # --- String representation ---

    def __repr__(self) -> str:
        dur = f"/{float(self.duration):.2f}" if self.duration != 1 else ""
        end = "||" if self.is_section_end else ""
        return f"ChordBlock({self.symbol}{dur}{end})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ChordBlock):
            return NotImplemented
        return self.root == other.root and self.quality == other.quality

    def __hash__(self) -> int:
        return hash((self.root, self.quality))


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    test_chords = [
        'C', 'Cmaj7', 'CM7', 'C6', 'Csus2',
        'Dm7', 'Gm7', 'Am7b5', 'D7', 'G7', 'G7b9', 'G7alt',
        'Bbmaj7', 'Ebm7', 'Abdim7', 'F#m7b5',
        'Bb7', 'Eb7', 'Ab7',
        'NC',
    ]

    print(f"{'Symbol':12} {'Root':>5} {'Quality':>12} {'Family':>12} "
          f"{'dom?':>6} {'min7?':>6} {'tonic?':>7}")
    print('-' * 65)
    for sym in test_chords:
        cb = ChordBlock(sym)
        print(f"{sym:12} {cb.root:>5} {cb.quality:>12} {cb.chord_family():>12} "
              f"{'Y' if cb.is_dominant() else '-':>6} "
              f"{'Y' if cb.is_minor7() else '-':>6} "
              f"{'Y' if cb.is_tonic() else '-':>7}")

    print("\nTransposition test:")
    cb = ChordBlock('Dm7', 4)
    print(f"  Dm7 + 5 semitones = {cb.transpose(5)}")
    print(f"  G7 resolves to C? {ChordBlock('G7').resolves_to(ChordBlock('C'))}")
    print(f"  G7 resolves to F? {ChordBlock('G7').resolves_to(ChordBlock('F'))}")
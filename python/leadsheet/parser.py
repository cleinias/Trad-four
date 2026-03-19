"""
parser.py — Trad-Four Phase 1a
Parses Impro-Visor .ls leadsheet files into a structured Python data model.

Produces a LeadSheet object containing:
  - metadata (title, composer, tempo, meter, raw key)
  - chord_timeline: list of ChordEvent(bar, beat, symbol, duration_beats)
  - section_markers: list of SectionMarker(bar, beat, style_name)

Usage:
    from parser import parse
    ls = parse('path/to/tune.ls')
"""

import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ChordEvent:
    """A single chord occurrence on the timeline."""
    bar: int                    # 1-indexed
    beat: Fraction              # 1-indexed, fractional beats allowed
    symbol: str                 # normalized chord symbol, e.g. 'Gm7', 'F7b9'
    duration: Fraction          # duration in beats
    bass_note: Optional[str] = None   # slash chord bass, e.g. 'F#' in 'Gm7/F#'

    def __repr__(self):
        base = f"{self.symbol}"
        if self.bass_note:
            base += f"/{self.bass_note}"
        return (f"ChordEvent(bar={self.bar}, beat={float(self.beat):.2f}, "
                f"chord={base}, dur={float(self.duration):.2f})")


@dataclass
class SectionMarker:
    """A style/section change marker."""
    bar: int
    beat: Fraction
    style_name: str


@dataclass
class LeadSheet:
    """Top-level result of parsing a .ls file."""
    title: str = ''
    composer: str = ''
    tempo: float = 120.0
    beats_per_bar: int = 4
    beat_unit: int = 4          # denominator of time signature
    raw_key: str = '0'          # raw value from (key ...), unreliable — use inferred_key
    inferred_key: Optional[str] = None   # set by annotator (Phase 1b)
    chord_timeline: list = field(default_factory=list)    # list of ChordEvent
    section_markers: list = field(default_factory=list)   # list of SectionMarker
    source_file: Optional[str] = None

    def chords_in_bar(self, bar: int) -> list:
        """Return all ChordEvents in a given bar (1-indexed)."""
        return [c for c in self.chord_timeline if c.bar == bar]

    def chord_at(self, bar: int, beat: float) -> Optional[ChordEvent]:
        """Return the ChordEvent active at a given bar and beat position."""
        beat_f = Fraction(beat).limit_denominator(64)
        candidates = [
            c for c in self.chord_timeline
            if c.bar == bar and c.beat <= beat_f < c.beat + c.duration
        ]
        return candidates[0] if candidates else None

    @property
    def total_bars(self) -> int:
        if not self.chord_timeline:
            return 0
        return max(c.bar for c in self.chord_timeline)

    def __repr__(self):
        return (f"LeadSheet(title={self.title!r},  composer={self.composer!r}, "
                f"meter={self.beats_per_bar}/{self.beat_unit}, "
                f"tempo={self.tempo}, bars={self.total_bars}, "
                f"chords={len(self.chord_timeline)})")


# ---------------------------------------------------------------------------
# Chord symbol normalizer
# ---------------------------------------------------------------------------

# Map Impro-Visor quality shorthands to normalized forms
_QUALITY_MAP = {
    'M7':    'maj7',
    'M9':    'maj9',
    'M13':   'maj13',
    'M':     'maj7',    # bare M treated as maj7
    '^':     'maj7',    # delta notation
    '^7':    'maj7',
    '^9':    'maj9',
    'h7':    'm7b5',    # half-diminished (Humdrum notation)
    'h':     'm7b5',
    'o7':    'dim7',
    'o':     'dim',
    '+':     'aug',
    'sus4':  'sus4',
    'sus2':  'sus2',
    'sus':   'sus4',    # bare sus = sus4
}

# Valid root note pattern: letter + optional accidental
_ROOT_RE = re.compile(r'^([A-G][b#]?)(.*)')

def normalize_chord(raw: str) -> tuple[str, Optional[str]]:
    """
    Parse a raw chord token into (normalized_symbol, bass_note).

    Returns:
        (symbol, bass_note) where bass_note is None if not a slash chord.
        Returns (None, None) if the token is not a valid chord symbol.

    Examples:
        'Gm7'       → ('Gm7', None)
        'BbM7'      → ('Bbmaj7', None)
        'Am7b5/C'   → ('Am7b5', 'C')
        'F^'        → ('Fmaj7', None)
        'Abo7'      → ('Abdim7', None)
        'C7#9b13'   → ('C7#9b13', None)
    """
    if not raw or raw == '/':
        return None, None

    # No-chord marker — treat as explicit silence
    if raw == 'NC':
        return 'NC', None

    # Split off slash bass note if present
    bass_note = None
    if '/' in raw:
        parts = raw.split('/', 1)
        raw = parts[0]
        bass_raw = parts[1]
        # Validate bass note is a real note name
        if re.match(r'^[A-G][b#]?$', bass_raw):
            bass_note = bass_raw

    # Match root
    m = _ROOT_RE.match(raw)
    if not m:
        return None, None

    root = m.group(1)
    quality_raw = m.group(2).strip()

    # Apply quality normalization map (longest match first)
    quality = quality_raw
    for src, dst in sorted(_QUALITY_MAP.items(), key=lambda x: -len(x[0])):
        if quality_raw == src:
            quality = dst
            break
        # Handle prefix matches for things like M7, ^7
        if quality_raw.startswith(src) and src in ('M7', 'M9', 'M13', '^7', '^9', 'h7'):
            quality = dst + quality_raw[len(src):]
            break

    # Reconstruct normalized symbol
    symbol = root + quality
    return symbol, bass_note


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

# Matches the (key ...) token
_KEY_RE    = re.compile(r'\(key\s+([^)]+)\)')
# Matches (meter N N)
_METER_RE  = re.compile(r'\(meter\s+(\d+)\s+(\d+)\)')
# Matches (tempo N)
_TEMPO_RE  = re.compile(r'\(tempo\s+([\d.]+)\)')
# Matches (title ...)
_TITLE_RE  = re.compile(r'^\(title\s+(.*?)\)\s*$')
# Matches (composer ...)
_COMP_RE   = re.compile(r'^\(composer\s+(.*?)\)\s*$')
# Matches (section (style name)) — captures style name
_SECTION_RE = re.compile(r'\(section\s+\(style\s*([^)]*)\)\s*\)')
# Matches (part (type ...))
_PART_RE   = re.compile(r'^\(part')
# Matches (type chords) or (type melody)
_TYPE_RE   = re.compile(r'\(type\s+(chords|melody)\)')


def _parse_metadata(lines: list[str], ls: LeadSheet) -> None:
    """Extract header metadata from the top-level s-expression lines."""
    for line in lines:
        stripped = line.strip()

        m = _TITLE_RE.search(stripped)
        if m and not ls.title:
            ls.title = m.group(1).strip()
            continue

        m = _COMP_RE.search(stripped)
        if m:
            #print(f"COMPOSER MATCH: {stripped!r} -> {m.group(1)!r}")
            val = m.group(1).strip()
            if val:  # only update if non-empty
                ls.composer = val
            continue

        m = _METER_RE.search(stripped)
        if m:
            ls.beats_per_bar = int(m.group(1))
            ls.beat_unit = int(m.group(2))
            continue

        m = _TEMPO_RE.search(stripped)
        if m:
            ls.tempo = float(m.group(1))
            continue

        m = _KEY_RE.search(stripped)
        if m and ls.raw_key == '0':
            ls.raw_key = m.group(1).strip()
            continue


def _tokenize_chord_line(line: str) -> list[str]:
    """
    Strip section markers from a line and return a list of bar strings.
    Each bar string is the space-separated content between | delimiters.

    Example:
        '(section (style swing)) FM6 | Gm7 C7 | F6 |'
        → ['FM6', 'Gm7 C7', 'F6']
    """
    # Strip section markers
    line = _SECTION_RE.sub('', line).strip()

    if not line:
        return []

    # Split on barlines, filter empty
    bars = [b.strip() for b in line.split('|')]
    # Last element after final | is usually empty
    bars = [b for b in bars if b]
    return bars


def _parse_chord_grid(chord_lines: list[str], ls: LeadSheet) -> None:
    """
    Parse the chord grid lines into ChordEvents and append to ls.chord_timeline.
    """
    beats_per_bar = Fraction(ls.beats_per_bar)
    bar_number = 1
    prev_chord_symbol = None
    prev_chord_bass = None

    for line in chord_lines:
        bar_strings = _tokenize_chord_line(line)

        for bar_str in bar_strings:
            tokens = bar_str.split()

            if not tokens:
                # Empty bar — carry previous chord for a full bar
                if prev_chord_symbol:
                    event = ChordEvent(
                        bar=bar_number,
                        beat=Fraction(1),
                        symbol=prev_chord_symbol,
                        duration=beats_per_bar,
                        bass_note=prev_chord_bass,
                    )
                    ls.chord_timeline.append(event)
                bar_number += 1
                continue

            # Check if this is a section marker line with no chord content
            if all(t.startswith('(') for t in tokens):
                # Pure section marker line, no chord content — extract style
                for token in tokens:
                    sm = _SECTION_RE.search(token)
                    if sm:
                        ls.section_markers.append(SectionMarker(
                            bar=bar_number,
                            beat=Fraction(1),
                            style_name=sm.group(1).strip(),
                        ))
                continue

            # n_slots determines beat duration per slot
            n_slots = len(tokens)
            slot_duration = beats_per_bar / n_slots
            current_beat = Fraction(1)  # 1-indexed beat position

            # Group consecutive slots into chord events
            # A '/' slot continues the previous chord
            i = 0
            while i < len(tokens):
                token = tokens[i]

                if token == '/':
                    # Continuation — extend previous chord's duration
                    if ls.chord_timeline and ls.chord_timeline[-1].bar == bar_number:
                        ls.chord_timeline[-1].duration += slot_duration
                    elif ls.chord_timeline:
                        # / at start of bar continuing from previous bar
                        event = ChordEvent(
                            bar=bar_number,
                            beat=current_beat,
                            symbol=prev_chord_symbol,
                            duration=slot_duration,
                            bass_note=prev_chord_bass,
                        )
                        ls.chord_timeline.append(event)
                    current_beat += slot_duration
                    i += 1
                    continue

                # Check for inline section marker token
                if token.startswith('('):
                    sm = _SECTION_RE.search(token)
                    if sm:
                        ls.section_markers.append(SectionMarker(
                            bar=bar_number,
                            beat=current_beat,
                            style_name=sm.group(1).strip(),
                        ))
                    i += 1
                    continue

                # Normal chord token
                symbol, bass = normalize_chord(token)
                if symbol is None:
                    # Unrecognized token — skip but warn
                    import warnings
                    warnings.warn(f"Unrecognized chord token: {token!r} in bar {bar_number}")
                    current_beat += slot_duration
                    i += 1
                    continue

                event = ChordEvent(
                    bar=bar_number,
                    beat=current_beat,
                    symbol=symbol,
                    duration=slot_duration,
                    bass_note=bass,
                )
                ls.chord_timeline.append(event)
                prev_chord_symbol = symbol
                prev_chord_bass = bass
                current_beat += slot_duration
                i += 1

            bar_number += 1


def parse(path: str | Path) -> LeadSheet:
    """
    Parse an Impro-Visor .ls file and return a LeadSheet object.

    Args:
        path: path to the .ls file

    Returns:
        LeadSheet with metadata and chord_timeline populated.

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if the file does not appear to be a valid .ls file.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Leadsheet not found: {path}")

    text = path.read_text(encoding='utf-8', errors='replace')
    lines = text.splitlines()

    ls = LeadSheet(source_file=str(path))

    # --- Pass 1: extract metadata from header lines ---
    _parse_metadata(lines, ls)

    # --- Pass 2: locate chord grid ---
    # The chord grid lives between (part (type chords)...) closing paren
    # and the next (part ...) block.
    # Strategy: find the line after the chords part header closes,
    # collect lines until the next (part ...) line.

    in_chords_part = False
    part_header_depth = 0
    chord_lines = []

    for line in lines:
        stripped = line.strip()

        if not in_chords_part:
            # Look for start of a chords part
            if _PART_RE.match(stripped):
                # Check if this part contains (type chords)
                # The part header may span multiple lines, but in practice
                # it's usually on one line or the type is on the next line
                if _TYPE_RE.search(stripped) and 'chords' in stripped:
                    in_chords_part = True
                    part_header_depth = stripped.count('(') - stripped.count(')')
                    if part_header_depth <= 0:
                        # Header closed on same line — next lines are chord content
                        part_header_depth = 0
                elif _PART_RE.match(stripped):
                    # Multi-line part header — peek ahead handled below
                    pass
            continue

        # We are inside a chords part
        if part_header_depth > 0:
            # Still consuming the part header
            part_header_depth += stripped.count('(') - stripped.count(')')
            if _TYPE_RE.search(stripped) and 'chords' not in stripped:
                # This is not a chords part after all
                in_chords_part = False
                part_header_depth = 0
            continue

        # Check if we've hit the next part block
        if _PART_RE.match(stripped):
            break

        # Skip pure comment or empty lines
        if not stripped or stripped.startswith(';'):
            continue

        chord_lines.append(stripped)

    # Fallback: if the above didn't find a (part (type chords)) block,
    # try parsing lines that look like chord grids directly
    if not chord_lines:
        chord_lines = _extract_chord_lines_fallback(lines)

    _parse_chord_grid(chord_lines, ls)

    return ls

def _extract_chord_lines_fallback(lines: list[str]) -> list[str]:
    """
    Fallback chord grid extraction for files without explicit (part (type chords))
    blocks. Identifies lines containing barlines (|) and chord-like tokens.
    """
    chord_lines = []
    in_melody_part = False

    for line in lines:
        stripped = line.strip()

        # Stop at melody part
        if _PART_RE.match(stripped) and 'melody' in stripped:
            in_melody_part = True
        if in_melody_part:
            continue

        # Skip pure s-expression lines (metadata)
        if stripped.startswith('(') and '|' not in stripped:
            continue

        # Include lines with barlines
        if '|' in stripped:
            chord_lines.append(stripped)

    return chord_lines


# ---------------------------------------------------------------------------
# CLI entry point for quick testing
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: python parser.py <path/to/file.ls>")
        sys.exit(1)

    ls = parse(sys.argv[1])
    print(f"\n{ls}\n")
    print(f"Key (raw): {ls.raw_key}")
    print(f"Section markers: {ls.section_markers}\n")
    print("Chord timeline:")
    for event in ls.chord_timeline:
        print(f"  {event}")
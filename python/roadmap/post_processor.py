"""
post_processor.py — Trad-Four roadmap module
Aggregates CYK parser brick keys into KeySpan tonal areas.

Mirrors imp.roadmap.cykparser.PostProcessor from Impro-Visor.

The PostProcessor takes the list of Blocks (Bricks + ChordBlocks) output
by the CYK parser and groups contiguous blocks sharing the same tonal
center into KeySpan objects.

Algorithm (right-to-left scan, mirroring Java findKeys()):
  1. Start with the last block's key/mode as the initial KeySpan
  2. Walk backwards through the block list
  3. For each block:
     - If same key/mode as current span → extend the span
     - If approach/launcher that resolves to next → absorb into span
     - If single-chord brick diatonic to current key → absorb
     - If bare chord diatonic to current key → absorb
     - Otherwise → start a new KeySpan
  4. Return the list of KeySpans (left-to-right order)

Usage:
    from python.roadmap.post_processor import find_keys
    from python.roadmap.cyk_parser import CYKParser
    from python.roadmap.brick_library import BrickLibrary

    lib = BrickLibrary()
    lib.load(dict_path, sub_path)
    parser = CYKParser(lib)

    blocks = parser.parse(chords)
    key_spans = find_keys(blocks, lib)
"""

from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
from typing import Optional

from python.roadmap.brick import Brick, Block
from python.roadmap.chord_block import ChordBlock, pc_to_name
from python.roadmap.brick_library import BrickLibrary


# ---------------------------------------------------------------------------
# KeySpan
# ---------------------------------------------------------------------------

@dataclass
class KeySpan:
    """
    A contiguous tonal area in the chord timeline.

    Attributes:
        key      : pitch class of tonal center (0-11)
        mode     : 'Major', 'Minor', or 'Dominant'
        duration : total duration in beats
    """
    key:      int
    mode:     str
    duration: Fraction

    def augment(self, delta: Fraction) -> None:
        """Extend this span's duration."""
        self.duration += delta

    def key_name(self) -> str:
        return pc_to_name(self.key)

    def __repr__(self) -> str:
        return (f"KeySpan({self.key_name()} {self.mode}, "
                f"dur={float(self.duration):.1f})")


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _block_duration(block: Block) -> Fraction:
    """Total duration of a block."""
    if isinstance(block, (ChordBlock, Brick)):
        return block.duration
    return Fraction(0)


def _block_key(block: Block) -> int:
    """Key of a block (pitch class 0-11)."""
    if isinstance(block, Brick):
        return block.key
    elif isinstance(block, ChordBlock):
        return block.root
    return 0


def _block_mode(block: Block) -> str:
    """Mode of a block."""
    if isinstance(block, Brick):
        return block.mode
    return 'Major'


def _first_chord(block: Block) -> Optional[ChordBlock]:
    """First chord of a block."""
    if isinstance(block, ChordBlock):
        return block
    elif isinstance(block, Brick):
        return block.first_chord()
    return None


def _is_approach_or_launcher(block: Block) -> bool:
    """True if block is an Approach or Launcher brick."""
    if isinstance(block, Brick):
        return block.type in ('Approach', 'Launcher')
    return False


# ---------------------------------------------------------------------------
# find_keys — main algorithm
# ---------------------------------------------------------------------------

def find_keys(blocks: list[Block], lib: BrickLibrary) -> list[KeySpan]:
    """
    Aggregate CYK parse blocks into contiguous KeySpan tonal areas.
    Mirrors PostProcessor.findKeys() in Java.

    Scans right-to-left, extending the current KeySpan as long as
    blocks share the same key/mode or resolve into it.

    Args:
        blocks: list of Blocks from CYKParser.parse()
        lib:    BrickLibrary (for diatonic rules and equivalence)

    Returns:
        List of KeySpan objects, ordered left-to-right
    """
    if not blocks:
        return []

    # Find the last non-NC block to seed the initial KeySpan
    last_idx = len(blocks) - 1
    while last_idx >= 0:
        b = blocks[last_idx]
        if isinstance(b, ChordBlock) and b.is_nochord():
            last_idx -= 1
        else:
            break

    if last_idx < 0:
        return []

    # Initialize current span from the last real block
    last = blocks[last_idx]
    current = KeySpan(
        key=_block_key(last),
        mode=_block_mode(last),
        duration=_block_duration(last),
    )

    # Accumulate any trailing NC duration
    for i in range(last_idx + 1, len(blocks)):
        current.augment(_block_duration(blocks[i]))

    result: list[KeySpan] = []
    nc_accum = Fraction(0)

    # Right-to-left scan (skip last_idx, already processed)
    for i in range(last_idx - 1, -1, -1):
        block = blocks[i]
        next_block = blocks[i + 1]

        # --- NOCHORD handling ---
        if isinstance(block, ChordBlock) and block.is_nochord():
            nc_accum += block.duration
            continue

        dur = _block_duration(block)

        # --- Brick handling ---
        if isinstance(block, Brick):
            # Same key and mode → extend current span
            if block.key == current.key and block.mode == current.mode:
                current.augment(dur + nc_accum)
                nc_accum = Fraction(0)
                continue

            # Single-chord brick diatonic to current key → absorb
            if block.is_single_chord():
                fc = block.first_chord()
                if fc and lib.diatonic.is_diatonic(
                        fc, current.key, current.mode, lib.dicts):
                    current.augment(dur + nc_accum)
                    nc_accum = Fraction(0)
                    continue

            # Approach/Launcher that resolves to the next block → absorb
            if _is_approach_or_launcher(block):
                lc = block.last_chord()
                if lc is not None:
                    fc_next = _first_chord(next_block)
                    if fc_next is not None and (lc.root + 5) % 12 == fc_next.root:
                        current.augment(dur + nc_accum)
                        nc_accum = Fraction(0)
                        continue

            # Key/mode change — push current span, start new one
            result.insert(0, current)
            current = KeySpan(
                key=block.key, mode=block.mode,
                duration=dur + nc_accum,
            )
            nc_accum = Fraction(0)
            continue

        # --- Bare ChordBlock handling ---
        if isinstance(block, ChordBlock):
            if lib.diatonic.is_diatonic(
                    block, current.key, current.mode, lib.dicts):
                current.augment(dur + nc_accum)
                nc_accum = Fraction(0)
            else:
                # Not diatonic → new span
                result.insert(0, current)
                current = KeySpan(
                    key=block.root,
                    mode='Major',
                    duration=dur + nc_accum,
                )
                nc_accum = Fraction(0)

    # Absorb any leading NC duration
    if nc_accum > 0:
        current.augment(nc_accum)

    # Push the final (leftmost) span
    result.insert(0, current)

    return result


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import warnings
    from python.roadmap.cyk_parser import CYKParser
    from python.roadmap.chord_block import ChordBlock as CB
    from python.config import DICT_PATH as _DICT_PATH, SUB_PATH as _SUB_PATH

    dict_path = str(_DICT_PATH)
    sub_path  = str(_SUB_PATH)

    print("Loading BrickLibrary...")
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        lib = BrickLibrary()
        lib.load(dict_path, sub_path)

    parser = CYKParser(lib)
    print(f"Parser ready.\n")

    test_cases = [
        ('ii-V-I in C major',
         [CB('Dm7', 2), CB('G7', 2), CB('CM7', 4)]),

        ('Perfect Cadence in C',
         [CB('G7', 2), CB('C', 2)]),

        ('ii-V-i in G minor',
         [CB('Am7b5', 2), CB('D7', 2), CB('Gm7', 4)]),

        ('ii-V-I in F major',
         [CB('Gm7', 2), CB('C7', 2), CB('FM7', 4)]),

        ('ii-V-I in C → ii-V-I in F (modulation)',
         [CB('Dm7', 2), CB('G7', 2), CB('CM7', 4),
          CB('Gm7', 2), CB('C7', 2), CB('FM7', 4)]),

        ('Bars 1-8 of Bye Bye Blackbird',
         [CB('FM6', 4),
          CB('Gm7', 2), CB('C7', 2),
          CB('F6', 4),
          CB('F6', 4),
          CB('F6', 4),
          CB('Abdim7', 4),
          CB('Gm7', 4),
          CB('C7', 4)]),
    ]

    for desc, chords in test_cases:
        print(f"--- {desc} ---")
        print(f"Input:  {[c.symbol for c in chords]}")

        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            blocks = parser.parse(chords)

        print(f"Bricks: {blocks}")

        key_spans = find_keys(blocks, lib)
        print(f"Keys:   {key_spans}")

        # Show beat-by-beat tonal areas
        total_dur = sum(c.duration for c in chords)
        span_dur  = sum(ks.duration for ks in key_spans)
        print(f"  Total chord duration: {float(total_dur):.1f} beats")
        print(f"  Total span duration:  {float(span_dur):.1f} beats")
        print()

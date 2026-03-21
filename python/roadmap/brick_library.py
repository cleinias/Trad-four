"""
brick_library.py — Trad-Four roadmap module
BrickLibrary: parses My.dictionary and builds the complete brick grammar.

Mirrors imp.roadmap.brickdictionary.BrickLibrary from Impro-Visor.

The library:
  1. Parses equiv/diatonic rules from My.dictionary
  2. Two-pass parse of defbrick definitions (collect all, then resolve
     sub-brick references to handle forward references)
  3. Auto-generates Overrun and Dropback bricks for each Cadence brick
  4. Stores bricks as {name: [Brick, ...]} with multiple variants per name

Usage:
    from python.roadmap.brick_library import BrickLibrary

    lib = BrickLibrary()
    lib.load('/usr/share/impro-visor/vocab/My.dictionary')
    print(lib)

    # Get a brick transposed to a specific key
    brick = lib.get_brick('Starlight Cadence', target_key=7)  # G major
    print(brick)
"""

from __future__ import annotations
from fractions import Fraction
from typing import Optional
from collections import defaultdict

from python.roadmap.chord_block import ChordBlock, pc_to_name
from python.roadmap.brick import Brick, IntermediateBrick, Block
from python.roadmap.equivalence import ChordDictionaries
from python.roadmap.sexp_parser import parse_file, SExp, is_list, is_atom, head, tail

# ---------------------------------------------------------------------------
# Key name / number conversion (mirrors BrickLibrary static methods)
# ---------------------------------------------------------------------------

_KEY_NAMES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']

_KEY_NAME_TO_NUM: dict[str, int] = {
    'C': 0, 'C#': 1, 'Db': 1,
    'D': 2, 'D#': 3, 'Eb': 3,
    'E': 4, 'Fb': 4,
    'F': 5, 'E#': 5, 'F#': 6, 'Gb': 6,
    'G': 7, 'G#': 8, 'Ab': 8,
    'A': 9, 'A#': 10, 'Bb': 10,
    'B': 11, 'Cb': 11,
}

# Default cost per brick type (mirrors BrickLibrary.DEFAULT_COST)
_DEFAULT_COST = 40
_TYPE_COSTS: dict[str, int] = {}


def key_name_to_num(name: str) -> int:
    """Convert a key name string to a pitch class number (0-11)."""
    return _KEY_NAME_TO_NUM.get(name, 0)


def dashless(name: str) -> str:
    """Convert hyphenated name to space-separated (mirrors BrickLibrary.dashless)."""
    return name.replace('-', ' ')


def _scale_brick_duration(brick: Brick, scale: Fraction) -> Brick:
    """
    Return a new Brick with all ChordBlock durations scaled by scale factor.
    Used when a brick sub-expression specifies an explicit duration.
    """
    new_blocks = []
    for block in brick.blocks:
        if isinstance(block, ChordBlock):
            new_blocks.append(ChordBlock(
                block.symbol,
                block.duration * scale,
                block.is_section_end,
            ))
        elif isinstance(block, Brick):
            new_blocks.append(_scale_brick_duration(block, scale))
    return Brick(
        name=brick.name,
        variant=brick.variant,
        key=brick.key,
        mode=brick.mode,
        brick_type=brick.type,
        blocks=new_blocks,
        is_section_end=brick.is_section_end,
    )


# ---------------------------------------------------------------------------
# Diatonic rules
# ---------------------------------------------------------------------------

class DiatonicRules:
    """
    Stores diatonic rules from My.dictionary.
    Used by PostProcessor to check whether a chord fits a key area.

    Format: (diatonic Major C Dm Dm7 Em Em7 F G7 Am Am7 Bo Bm7b5)
    """

    def __init__(self):
        # mode → list of (root_pc, quality) pairs for C-rooted diatonic chords
        self._rules: dict[str, list[tuple[int, str]]] = {}

    def add_rule(self, mode: str, chords: list[ChordBlock]) -> None:
        if mode not in self._rules:
            self._rules[mode] = []
        for cb in chords:
            self._rules[mode].append((cb.root, cb.quality))

    def is_diatonic(self, chord: ChordBlock, key: int, mode: str,
                    edict: Optional[ChordDictionaries] = None) -> bool:
        """
        True if chord is diatonic to the given key and mode.
        Mirrors PostProcessor.diatonicChordCheck().
        """
        if chord.is_diminished():
            return True   # diminished chords always treated as diatonic

        if mode not in self._rules:
            return False

        # Transpose chord to C for comparison
        offset = chord.root - key
        chord_in_c = chord.transpose(-key % 12)

        for (ref_root, ref_quality) in self._rules[mode]:
            if chord_in_c.root == ref_root:
                if chord_in_c.quality == ref_quality:
                    return True
                # Check equivalence
                if edict is not None:
                    ref_cb = ChordBlock(
                        pc_to_name(ref_root) + ref_quality)
                    if edict.are_equivalent(chord_in_c, ref_cb):
                        return True
        return False

    def modes(self) -> list[str]:
        return list(self._rules.keys())


# ---------------------------------------------------------------------------
# BrickLibrary
# ---------------------------------------------------------------------------

class BrickLibrary:
    """
    The complete brick grammar loaded from My.dictionary.

    Stores bricks as {name: [Brick, ...]} with multiple variants per name.
    Also holds the ChordDictionaries and DiatonicRules.
    """

    OVERRUN   = 'Overrun'
    DROPBACK  = 'Dropback'
    CONJUNCTION = ' + '
    INVISIBLE = 'Invisible'

    def __init__(self):
        # name → list of Brick variants
        self._bricks: dict[str, list[Brick]] = defaultdict(list)
        self.dicts   = ChordDictionaries()
        self.diatonic = DiatonicRules()
        self._loaded = False

    # --- Loading ---

    def load(self, dictionary_path: str,
             substitutions_path: Optional[str] = None) -> None:
        """
        Load bricks from My.dictionary and optionally My.substitutions.

        Args:
            dictionary_path:    path to My.dictionary
            substitutions_path: path to My.substitutions (optional)
        """
        if substitutions_path:
            self.dicts.load_substitutions_file(substitutions_path)

        exprs = parse_file(dictionary_path)
        self._process_dictionary(exprs)
        self._loaded = True

    def _process_dictionary(self, exprs: list[SExp]) -> None:
        """
        Two-pass parse of My.dictionary S-expressions.
        Pass 1: collect equiv, diatonic, brick-type, and raw defbrick polylists.
        Pass 2: construct Brick objects, resolving sub-brick references.
        """
        # Collect raw defbrick expressions keyed by name (for forward refs)
        raw_bricks: dict[str, list[list]] = defaultdict(list)

        for expr in exprs:
            if not is_list(expr) or not expr:
                continue
            tag = expr[0]

            if tag == 'equiv':
                # Pass to equivalence dictionary
                self.dicts.load_from_sexp([expr])

            elif tag == 'diatonic':
                # (diatonic Major C Dm Dm7 ...)
                if len(expr) < 3:
                    continue
                mode = expr[1]
                chords = []
                for sym in expr[2:]:
                    if isinstance(sym, str):
                        cb = ChordBlock(sym)
                        if not cb.is_nochord():
                            chords.append(cb)
                self.diatonic.add_rule(mode, chords)

            elif tag == 'brick-type':
                # (brick-type Cadence 40)
                if len(expr) >= 2:
                    btype = expr[1]
                    cost = int(expr[2]) if len(expr) >= 3 else _DEFAULT_COST
                    _TYPE_COSTS[btype] = cost

            elif tag == 'defbrick' and len(expr) > 4:
                # Collect raw for pass 2
                name = dashless(expr[1] if isinstance(expr[1], str)
                                else str(expr[1]))
                raw_bricks[name].append(expr)

        # Pass 2: construct Brick objects
        for name, raw_list in raw_bricks.items():
            for raw in raw_list:
                brick = self._parse_defbrick(raw, raw_bricks)
                if brick is not None:
                    self._add_brick(brick)

    def _parse_defbrick(self, expr: list,
                        raw_bricks: dict[str, list]) -> Optional[Brick]:
        """
        Parse a single defbrick S-expression into a Brick object.

        Format:
            (defbrick Name (qualifier) Mode Type Key
                (chord ChordSymbol duration)
                (brick BrickName KeyName duration)
                ...)
        """
        # expr[0] = 'defbrick'
        # expr[1] = name (possibly with qualifier)
        pos = 1

        # Name
        raw_name = expr[pos]
        if isinstance(raw_name, str):
            name = dashless(raw_name)
            pos += 1
        else:
            return None

        # Optional qualifier: (var 1), (var 2) etc.
        variant = ''
        if pos < len(expr) and isinstance(expr[pos], list):
            variant = ' '.join(str(x) for x in expr[pos])
            pos += 1

        # Mode
        if pos >= len(expr):
            return None
        mode = str(expr[pos])
        pos += 1

        # Type
        if pos >= len(expr):
            return None
        brick_type = str(expr[pos])
        pos += 1

        # Key
        if pos >= len(expr):
            return None
        key_str = str(expr[pos])
        key = key_name_to_num(key_str)
        pos += 1

        # Sub-blocks
        blocks: list[Block] = []
        while pos < len(expr):
            sub = expr[pos]
            pos += 1
            if not isinstance(sub, list) or len(sub) < 2:
                continue
            sub_tag = sub[0]

            if sub_tag == 'chord':
                # (chord ChordSymbol duration)
                # duration may be '*' meaning use natural duration (treat as 1)
                chord_sym = str(sub[1])
                dur_raw = str(sub[2]) if len(sub) > 2 else '1'
                duration = Fraction(1) if dur_raw == '*' else Fraction(int(dur_raw))
                blocks.append(ChordBlock(chord_sym, duration))

            elif sub_tag == 'brick':
                # Format without qualifier: (brick BrickName KeyName duration)
                # Format with qualifier:    (brick BrickName (qualifier) KeyName duration)
                sub_name = dashless(str(sub[1]))
                pos2 = 2

                # Check for qualifier as nested list in position 2
                sub_variant = ''
                if pos2 < len(sub) and isinstance(sub[pos2], list):
                    sub_variant = ' '.join(str(x) for x in sub[pos2])
                    pos2 += 1

                sub_key_str = str(sub[pos2]) if pos2 < len(sub) else key_str
                sub_key = key_name_to_num(sub_key_str)
                pos2 += 1

                # Duration: '*' means use natural duration of sub-brick
                sub_dur_raw = str(sub[pos2]) if pos2 < len(sub) else '*'
                sub_dur = None if sub_dur_raw == '*' else int(sub_dur_raw)

                # Look up the sub-brick — prefer matching variant if specified
                sub_brick = None
                if sub_variant:
                    variants = self._bricks.get(sub_name, [])
                    for b in variants:
                        if b.variant == sub_variant:
                            sub_brick = b
                            break
                if sub_brick is None:
                    sub_brick = self._get_any_brick(sub_name)

                if sub_brick is None:
                    # Try to parse it from raw (forward reference resolution)
                    if sub_name in raw_bricks:
                        for raw in raw_bricks[sub_name]:
                            parsed = self._parse_defbrick(raw, raw_bricks)
                            if parsed is not None:
                                self._add_brick(parsed)
                                sub_brick = self._get_any_brick(sub_name)
                                break

                if sub_brick is not None:
                    transposed = sub_brick.transposed_to(sub_key)
                    if sub_dur is not None:
                        flat = transposed.flatten()
                        natural = sum(cb.duration for cb in flat)
                        if natural > 0:
                            scale = Fraction(sub_dur) / natural
                            transposed = _scale_brick_duration(transposed, scale)
                    blocks.append(transposed)
                else:
                    import warnings
                    warnings.warn(f"Sub-brick '{sub_name}' not found in "
                                  f"definition of '{name}'")

        if not blocks:
            return None

        return Brick(
            name=name,
            variant=variant,
            key=key,
            mode=mode,
            brick_type=brick_type,
            blocks=blocks,
        )

    def _add_brick(self, brick: Brick) -> None:
        """
        Add a brick to the library. Also auto-generates Overrun and Dropback
        for Cadence bricks, mirroring BrickLibrary.addBrick() in Java.
        """
        # Check for duplicate variant
        for existing in self._bricks[brick.name]:
            if existing.variant == brick.variant:
                return   # already present

        self._bricks[brick.name].append(brick)

        # Auto-generate Overrun and Dropback for Cadence bricks
        if brick.is_cadence():
            self._generate_overrun(brick)
            self._generate_dropback(brick)

    def _generate_overrun(self, cadence: Brick) -> None:
        """
        Generate an Overrun brick: the cadence followed by a chord
        a P4 above the resolution (the next ii chord implied).
        Mirrors BrickLibrary.addBrick() overrun generation.
        """
        flat = cadence.flatten()
        if not flat:
            return
        prev_chord = flat[-1]
        # Chord a P4 above = dominant a P4 above the tonic
        overrun_root = (cadence.key + 5) % 12
        overrun_sym = pc_to_name(overrun_root) + prev_chord.quality
        overrun_chord = ChordBlock(overrun_sym, prev_chord.duration)

        overrun_name = cadence.name + self.CONJUNCTION + self.OVERRUN
        overrun = Brick(
            name=overrun_name,
            variant=cadence.variant,
            key=cadence.key,
            mode=cadence.mode,
            brick_type=self.OVERRUN,
            blocks=[cadence, overrun_chord],
        )
        self._add_brick(overrun)

    def _generate_dropback(self, cadence: Brick) -> None:
        """
        Generate a Dropback brick: the cadence followed by a dominant 7th
        a minor 6th below the tonic (= dominant of the relative minor).
        Mirrors BrickLibrary.addBrick() dropback generation.
        """
        flat = cadence.flatten()
        if not flat:
            return
        prev_chord = flat[-1]
        # Dominant a minor 6th below = (key + 9) % 12 dominant
        dropback_root = (cadence.key + 9) % 12
        dropback_sym = pc_to_name(dropback_root) + '7'
        dropback_chord = ChordBlock(dropback_sym, prev_chord.duration)

        dropback_name = cadence.name + self.CONJUNCTION + self.DROPBACK
        dropback = Brick(
            name=dropback_name,
            variant=cadence.variant,
            key=cadence.key,
            mode=cadence.mode,
            brick_type=self.DROPBACK,
            blocks=[cadence, dropback_chord],
        )
        self._add_brick(dropback)

    # --- Retrieval ---

    def _get_any_brick(self, name: str) -> Optional[Brick]:
        """Return the first brick with the given name, or None."""
        variants = self._bricks.get(name)
        if not variants:
            return None
        return variants[0]

    def get_brick(self, name: str,
                  target_key: int,
                  variant: str = '') -> Optional[Brick]:
        """
        Return a brick transposed to target_key.
        If variant is specified, return that variant; otherwise return
        the first non-invisible variant.

        Args:
            name:       brick name (with spaces, not dashes)
            target_key: pitch class to transpose to (0-11)
            variant:    optional variant string

        Returns:
            Transposed Brick, or None if not found.
        """
        variants = self._bricks.get(name)
        if not variants:
            return None

        brick = None
        if variant:
            for b in variants:
                if b.variant == variant:
                    brick = b
                    break
        else:
            # First non-invisible
            for b in variants:
                if not b.is_invisible():
                    brick = b
                    break
            if brick is None:
                brick = variants[0]

        if brick is None:
            return None

        return brick.transposed_to(target_key)

    def all_bricks(self) -> list[Brick]:
        """Return all brick variants as a flat list."""
        result = []
        for variants in self._bricks.values():
            result.extend(variants)
        return result

    def brick_names(self) -> list[str]:
        """Return all unique brick names."""
        return list(self._bricks.keys())

    def visible_bricks(self) -> list[Brick]:
        """Return all non-invisible brick variants."""
        return [b for b in self.all_bricks() if not b.is_invisible()]

    def cadence_bricks(self) -> list[Brick]:
        """Return all Cadence bricks (before Overrun/Dropback generation)."""
        return [b for b in self.all_bricks() if b.is_cadence()]

    # --- Statistics ---

    def __len__(self) -> int:
        return sum(len(v) for v in self._bricks.values())

    def __repr__(self) -> str:
        return (f"BrickLibrary("
                f"{len(self._bricks)} names, "
                f"{len(self)} total variants)")


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import os

    dict_path = '/usr/share/impro-visor/vocab/My.dictionary'
    sub_path  = '/usr/share/impro-visor/vocab/My.substitutions'

    print(f"Loading {dict_path}...")
    lib = BrickLibrary()
    lib.load(dict_path, sub_path)
    print(f"Loaded: {lib}")
    print(f"  Visible bricks:  {len(lib.visible_bricks())}")
    print(f"  Cadence bricks:  {len(lib.cadence_bricks())}")
    print(f"  Diatonic modes:  {lib.diatonic.modes()}")
    print()

    # Show all cadence brick names
    print("Cadence bricks:")
    for b in sorted(lib.cadence_bricks(), key=lambda b: b.name):
        key_name = pc_to_name(b.key)
        var = f" ({b.variant})" if b.variant else ""
        print(f"  {b.name}{var}  [key={key_name}]  "
              f"chords={[str(cb) for cb in b.flatten()]}")
    print()

    # Test retrieval and transposition
    test_name = 'Starlight Cadence'
    for target_key in [0, 5, 7]:   # C, F, G
        brick = lib.get_brick(test_name, target_key)
        if brick:
            print(f"{test_name} in {pc_to_name(target_key)}: "
                  f"{[cb.symbol for cb in brick.flatten()]}")
        else:
            print(f"{test_name} not found")

    print()
    # Test diatonic check
    print("Diatonic checks (F major, key=5):")
    test_chords = ['Gm7', 'C7', 'FM7', 'Dm7', 'Am7b5', 'D7', 'Bbmaj7']
    for sym in test_chords:
        cb = ChordBlock(sym)
        result = lib.diatonic.is_diatonic(cb, key=5, mode='Major',
                                          edict=lib.dicts)
        print(f"  {sym:10} diatonic to F major? {result}")
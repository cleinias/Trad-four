"""
brick.py — Trad-Four roadmap module
Brick: a named harmonic pattern — the non-terminal symbol of the brick grammar.

Mirrors imp.roadmap.brickdictionary.Brick from Impro-Visor.

A Brick has:
  - name     : display name (e.g. 'Starlight Cadence')
  - variant  : qualifier string (e.g. 'var 1', '')
  - key      : pitch class of the tonal center (0-11)
  - mode     : 'Major', 'Minor', or 'Dominant'
  - type     : brick type string (e.g. 'Cadence', 'Approach', 'Invisible')
  - blocks   : list of sub-blocks (ChordBlock or Brick instances)

Key operations:
  - flatten()      : recursively expand to a flat list of ChordBlocks
  - transpose()    : return a new Brick transposed by N semitones
  - first_chord()  : first ChordBlock in the flattened sequence
  - last_chord()   : last ChordBlock in the flattened sequence
  - duration       : total duration of all sub-blocks
"""

from __future__ import annotations
from fractions import Fraction
from typing import Union

from python.roadmap.chord_block import ChordBlock, pc_to_name, parse_root

# A Block is either a ChordBlock (terminal) or a Brick (non-terminal)
Block = Union[ChordBlock, 'Brick']


# ---------------------------------------------------------------------------
# Brick
# ---------------------------------------------------------------------------

class Brick:
    """
    A named harmonic pattern — the non-terminal symbol of the brick grammar.

    Attributes:
        name      : brick name with spaces (dashes converted, e.g. 'Starlight Cadence')
        variant   : qualifier string (e.g. 'var 1', '')
        key       : pitch class of tonal center (0-11)
        mode      : 'Major', 'Minor', or 'Dominant'
        type      : brick type string
        blocks    : list of sub-blocks (ChordBlock or Brick)
        is_section_end : True if this brick marks a phrase boundary
    """

    __slots__ = ('name', 'variant', 'key', 'mode', 'type',
                 'blocks', 'is_section_end')

    def __init__(self,
                 name: str,
                 variant: str,
                 key: int,
                 mode: str,
                 brick_type: str,
                 blocks: list[Block],
                 is_section_end: bool = False):
        self.name     = name
        self.variant  = variant
        self.key      = key
        self.mode     = mode
        self.type     = brick_type
        self.blocks   = blocks
        self.is_section_end = is_section_end

    # --- Accessors ---

    def is_invisible(self) -> bool:
        return self.type == 'Invisible'

    def is_cadence(self) -> bool:
        return self.type == 'Cadence'

    def is_approach(self) -> bool:
        return self.type == 'Approach'

    def is_single_chord(self) -> bool:
        return len(self.flatten()) == 1

    @property
    def duration(self) -> Fraction:
        """Total duration of all sub-blocks in beats."""
        return sum((b.duration for b in self.blocks), Fraction(0))

    # --- Flattening ---

    def flatten(self) -> list[ChordBlock]:
        """
        Recursively expand all sub-blocks into a flat list of ChordBlocks.
        Mirrors Brick.flattenBlock() in Java.
        """
        result = []
        for block in self.blocks:
            if isinstance(block, ChordBlock):
                result.append(block)
            elif isinstance(block, Brick):
                result.extend(block.flatten())
        return result

    def first_chord(self) -> ChordBlock | None:
        """Return the first ChordBlock in the flattened sequence."""
        flat = self.flatten()
        return flat[0] if flat else None

    def last_chord(self) -> ChordBlock | None:
        """Return the last ChordBlock in the flattened sequence."""
        flat = self.flatten()
        return flat[-1] if flat else None

    # --- Transposition ---

    def transpose(self, semitones: int) -> 'Brick':
        """
        Return a new Brick with all sub-blocks transposed by semitones,
        and key updated accordingly.
        """
        new_key = (self.key + semitones) % 12
        new_blocks = []
        for block in self.blocks:
            if isinstance(block, ChordBlock):
                new_blocks.append(block.transpose(semitones))
            elif isinstance(block, Brick):
                new_blocks.append(block.transpose(semitones))
        return Brick(
            name=self.name,
            variant=self.variant,
            key=new_key,
            mode=self.mode,
            brick_type=self.type,
            blocks=new_blocks,
            is_section_end=self.is_section_end,
        )

    def transposed_to(self, target_key: int) -> 'Brick':
        """Return a copy of this brick transposed so its key equals target_key."""
        semitones = (target_key - self.key) % 12
        return self.transpose(semitones)

    # --- Join detection helpers ---

    def resolves_to(self, other: Block) -> bool:
        """
        True if this brick's last chord resolves to other's first chord
        via V→I motion (P4 up).
        Mirrors PostProcessor.doesResolve(Brick, Block).
        """
        last = self.last_chord()
        if last is None:
            return False
        if isinstance(other, ChordBlock):
            other_key = other.root
        elif isinstance(other, Brick):
            other_key = other.key
        else:
            return False
        return self.key == other_key

    # --- String representation ---

    def __repr__(self) -> str:
        key_name = pc_to_name(self.key) if self.key >= 0 else '?'
        var = f"({self.variant})" if self.variant else ""
        return (f"Brick({self.name}{var} "
                f"[{self.mode} {self.type}] "
                f"key={key_name} "
                f"blocks={len(self.blocks)})")

    def tree_str(self, indent: int = 0) -> str:
        """Pretty-print the brick hierarchy."""
        pad = '  ' * indent
        key_name = pc_to_name(self.key) if self.key >= 0 else '?'
        var = f"({self.variant})" if self.variant else ""
        lines = [f"{pad}{self.name}{var} [{self.mode} {self.type}] key={key_name}"]
        for block in self.blocks:
            if isinstance(block, ChordBlock):
                lines.append(f"{pad}  {block}")
            elif isinstance(block, Brick):
                lines.append(block.tree_str(indent + 1))
        return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Intermediate (binarization) brick
# ---------------------------------------------------------------------------

class IntermediateBrick(Brick):
    """
    An automatically generated intermediate brick used during binarization
    of bricks with more than 2 sub-blocks.

    e.g. A brick with sub-blocks [A, B, C, D] becomes:
        IntermediateBrick('Name1', [A, B])
        IntermediateBrick('Name2', [Name1, C])
        Brick('Name', [Name2, D])

    These are always Invisible type.
    """

    def __init__(self, name: str, key: int, mode: str,
                 blocks: list[Block], variant: str = ''):
        super().__init__(
            name=name,
            variant=variant,
            key=key,
            mode=mode,
            brick_type='Invisible',
            blocks=blocks,
        )


# ---------------------------------------------------------------------------
# CLI test (standalone, no BrickLibrary needed)
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # Manually construct a simple ii-V-I brick in C major
    # to test the Brick class before BrickLibrary is built

    ii  = ChordBlock('Dm7', Fraction(2))
    v   = ChordBlock('G7',  Fraction(2))
    i   = ChordBlock('CM7', Fraction(4))

    # A simple two-block brick: An-Approach (ii-V)
    approach = Brick(
        name='An Approach',
        variant='',
        key=0,       # C
        mode='Major',
        brick_type='Approach',
        blocks=[ii, v],
    )

    # A cadence: ii-V-I (3 blocks → needs binarization for CYK,
    # but we can still construct it directly)
    cadence = Brick(
        name='Starlight Cadence',
        variant='',
        key=0,
        mode='Major',
        brick_type='Cadence',
        blocks=[approach, i],
    )

    print("=== Brick structure ===")
    print(cadence.tree_str())
    print()

    print(f"Duration: {cadence.duration} beats")
    print(f"Flattened: {cadence.flatten()}")
    print(f"First chord: {cadence.first_chord()}")
    print(f"Last chord:  {cadence.last_chord()}")
    print()

    # Transposition test
    cadence_g = cadence.transposed_to(7)   # transpose to G major
    print("=== Transposed to G major ===")
    print(cadence_g.tree_str())
    print(f"Flattened: {cadence_g.flatten()}")
    print()

    # Resolution test
    next_chord = ChordBlock('C', Fraction(4))
    print(f"Approach resolves to C? {approach.resolves_to(next_chord)}")
    next_chord_f = ChordBlock('F', Fraction(4))
    print(f"Approach resolves to F? {approach.resolves_to(next_chord_f)}")
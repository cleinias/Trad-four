"""
productions.py — Trad-Four roadmap module
Grammar production rules for the CYK brick parser.

Mirrors imp.roadmap.cykparser.UnaryProduction,
imp.roadmap.cykparser.BinaryProduction, and
imp.roadmap.cykparser.AbstractProduction from Impro-Visor.

Productions are derived from Brick definitions in BrickLibrary:
  - UnaryProduction  : A → chord  (single-chord bricks)
  - BinaryProduction : A → B C    (two-subblock bricks, or binarized n-ary)

Bricks with more than 2 sub-blocks are binarized automatically:
  Brick [A, B, C, D] becomes:
    BinaryProduction('Name1', Invisible, [A, B])
    BinaryProduction('Name2', Invisible, [Name1, C])
    BinaryProduction('Name',  type,      [Name2, D])

MatchValue: the result of checking a production against tree nodes.
  chordDiff >= 0 means a match was found
  cost reflects match quality (0=exact, 5=equiv, 10=sub)
  familyMatch=True adds a small penalty
"""

from __future__ import annotations
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Optional, TYPE_CHECKING

from python.roadmap.chord_block import ChordBlock
from python.roadmap.brick import Brick, Block, IntermediateBrick

if TYPE_CHECKING:
    from python.roadmap.brick_library import BrickLibrary
    from python.roadmap.equivalence import ChordDictionaries


# ---------------------------------------------------------------------------
# MatchValue — result of production matching
# ---------------------------------------------------------------------------

@dataclass
class MatchValue:
    """
    Result of checking a production against one or two tree nodes.
    Mirrors AbstractProduction.MatchValue in Impro-Visor.

    Attributes:
        chordDiff  : >= 0 means match found; the key difference in semitones
        cost       : accumulated match cost (0=exact, 5=equiv, 10=sub)
        familyMatch: True if matched via family equivalence (adds penalty)
    """
    chordDiff:   int   = -1      # -1 = no match
    cost:        float = 0.0
    familyMatch: bool  = False

    @property
    def matched(self) -> bool:
        return self.chordDiff >= 0

    NO_MATCH: 'MatchValue' = None   # sentinel, set after class definition


MatchValue.NO_MATCH = MatchValue(chordDiff=-1, cost=0.0, familyMatch=False)


# ---------------------------------------------------------------------------
# TreeNode — a cell in the CYK table
# ---------------------------------------------------------------------------

@dataclass
class TreeNode:
    """
    A node in the CYK parse table.
    Each cell (row, col) holds a list of TreeNodes representing all possible
    parse trees for the chord sub-sequence [row..col].

    Mirrors imp.roadmap.cykparser.TreeNode.

    Leaf nodes wrap a single ChordBlock.
    Internal nodes wrap a production head with two child TreeNodes.
    """
    # For leaf nodes
    chord:    Optional[ChordBlock] = None

    # For internal nodes
    head:     str   = ''         # production head name
    ptype:    str   = ''         # brick type
    mode:     str   = ''         # 'Major', 'Minor', 'Dominant'
    variant:  str   = ''
    key:      int   = 0          # pitch class of tonal center
    left:     Optional['TreeNode'] = None
    right:    Optional['TreeNode'] = None

    # Cost and flags
    cost:     float = 0.0
    chord_diff: int = 0          # key transposition used in matching
    is_sub:   bool  = False      # matched via substitution
    is_overlap: bool = False     # overlap brick
    _show:    bool  = True       # whether to show in solution

    def is_leaf(self) -> bool:
        return self.chord is not None

    def is_section_end(self) -> bool:
        if self.chord is not None:
            return self.chord.is_section_end
        return False

    def is_overlap(self) -> bool:
        return self.is_overlap

    def to_show(self) -> bool:
        return self._show

    def less_than(self, other: 'TreeNode') -> bool:
        """True if this node has lower cost than other."""
        return self.cost < other.cost

    def overlap_copy(self) -> 'TreeNode':
        """Return a copy of this node marked as an overlap brick."""
        import copy
        c = copy.copy(self)
        c.is_overlap = True
        return c

    def get_duration(self) -> Fraction:
        """Total duration of chords covered by this node."""
        if self.chord is not None:
            return self.chord.duration
        dur = Fraction(0)
        if self.left:
            dur += self.left.get_duration()
        if self.right:
            dur += self.right.get_duration()
        return dur

    def to_blocks(self) -> list[Block]:
        """
        Convert this tree node to a list of Blocks (Brick or ChordBlock).
        Mirrors TreeNode.toBlocks() in Java.
        """
        if self.chord is not None:
            return [self.chord]

        if not self.head:
            # Unnamed node — just flatten children
            result = []
            if self.left:
                result.extend(self.left.to_blocks())
            if self.right:
                result.extend(self.right.to_blocks())
            return result

        if self.ptype == 'Invisible':
            # Invisible bricks are transparent — just return children's blocks
            result = []
            if self.left:
                result.extend(self.left.to_blocks())
            if self.right:
                result.extend(self.right.to_blocks())
            return result

        # Named visible brick — assemble sub-blocks
        sub_blocks: list[Block] = []
        if self.left:
            sub_blocks.extend(self.left.to_blocks())
        if self.right:
            sub_blocks.extend(self.right.to_blocks())

        brick = Brick(
            name=self.head,
            variant=self.variant,
            key=self.key,
            mode=self.mode,
            brick_type=self.ptype,
            blocks=sub_blocks,
        )
        return [brick]

    def __repr__(self) -> str:
        if self.chord is not None:
            return f"TreeNode(leaf={self.chord})"
        return (f"TreeNode(head={self.head!r}, type={self.ptype!r}, "
                f"cost={self.cost:.1f})")


# ---------------------------------------------------------------------------
# Production base helpers
# ---------------------------------------------------------------------------

def _match_chord_to_block(chord: ChordBlock,
                           target: Block,
                           dicts: 'ChordDictionaries') -> MatchValue:
    """
    Try to match a chord (from a brick definition, C-rooted and transposed)
    against a target block (from the chord sequence).

    Returns a MatchValue with the match result and cost.
    """
    if isinstance(target, TreeNode):
        target_chord = target.chord
        if target_chord is None:
            return MatchValue.NO_MATCH
    elif isinstance(target, ChordBlock):
        target_chord = target
    else:
        return MatchValue.NO_MATCH

    if target_chord.is_nochord():
        return MatchValue.NO_MATCH

    # Roots must match
    if chord.root != target_chord.root:
        return MatchValue.NO_MATCH

    # Exact match
    if chord.quality == target_chord.quality:
        return MatchValue(chordDiff=0, cost=0.0, familyMatch=False)

    # Equivalence match
    if dicts.equiv.are_equivalent(chord, target_chord):
        return MatchValue(chordDiff=0, cost=5.0, familyMatch=False)

    # Substitution match (target can substitute for chord definition)
    if dicts.sub.can_substitute(target_chord, chord):
        return MatchValue(chordDiff=0, cost=5.0, familyMatch=True)

    return MatchValue.NO_MATCH


# ---------------------------------------------------------------------------
# UnaryProduction — A → chord (single-chord brick)
# ---------------------------------------------------------------------------

class UnaryProduction:
    """
    A grammar rule of the form: BrickName → SingleChord

    Used for bricks that consist of a single chord (size == 1).
    Also used for bricks that are sub-bricks of other bricks.

    Mirrors imp.roadmap.cykparser.UnaryProduction.
    """

    __slots__ = ('head', 'ptype', 'key', 'mode', 'variant',
                 'chord', 'show', 'cost')

    def __init__(self,
                 head: str,
                 ptype: str,
                 key: int,
                 chord: ChordBlock,
                 show: bool,
                 mode: str,
                 variant: str,
                 cost: float = 0.0):
        self.head    = head
        self.ptype   = ptype
        self.key     = key
        self.chord   = chord
        self.show    = show
        self.mode    = mode
        self.variant = variant
        self.cost    = cost

    def check_production(self,
                          node: 'TreeNode',
                          dicts: 'ChordDictionaries') -> MatchValue:
        """
        Check if this production matches the given tree node.
        The node must be a leaf (single chord).

        Returns MatchValue — chordDiff >= 0 if matched.
        """
        if not node.is_leaf():
            return MatchValue.NO_MATCH

        return _match_chord_to_block(self.chord, node.chord, dicts)

    def get_head(self) -> str:
        return self.head

    def get_type(self) -> str:
        return self.ptype

    def get_mode(self) -> str:
        return self.mode

    def get_variant(self) -> str:
        return self.variant

    def get_key(self) -> int:
        return self.key

    def __repr__(self) -> str:
        return (f"UnaryProduction({self.head!r} → {self.chord}, "
                f"type={self.ptype!r})")


# ---------------------------------------------------------------------------
# BinaryProduction — A → B C (two-subblock brick)
# ---------------------------------------------------------------------------

class BinaryProduction:
    """
    A grammar rule of the form: BrickName → SubBlock1 SubBlock2

    Used for bricks that consist of exactly two sub-blocks, or for
    the intermediate rules generated during binarization of longer bricks.

    Sub-blocks can be ChordBlocks (terminals) or Brick references
    (non-terminals, identified by name).

    Mirrors imp.roadmap.cykparser.BinaryProduction.
    """

    __slots__ = ('head', 'ptype', 'key', 'mode', 'variant',
                 'left', 'right', 'show', 'cost')

    def __init__(self,
                 head: str,
                 ptype: str,
                 key: int,
                 left: Block,
                 right: Block,
                 show: bool,
                 mode: str,
                 variant: str,
                 cost: float = 0.0):
        self.head    = head
        self.ptype   = ptype
        self.key     = key
        self.left    = left
        self.right   = right
        self.show    = show
        self.mode    = mode
        self.variant = variant
        self.cost    = cost

    def check_production(self,
                          left_node: 'TreeNode',
                          right_node: 'TreeNode') -> MatchValue:
        """
        Check if this production matches two adjacent tree nodes.

        For each sub-block:
          - ChordBlock: the node must be a leaf with a matching chord
          - Brick: the node's head must match the brick's name

        Returns MatchValue — chordDiff >= 0 if matched.
        """
        # Match left sub-block
        left_match = self._match_subblock(self.left, left_node)
        if not left_match.matched:
            return MatchValue.NO_MATCH

        # Match right sub-block
        right_match = self._match_subblock(self.right, right_node)
        if not right_match.matched:
            return MatchValue.NO_MATCH

        # Combine costs
        total_cost = left_match.cost + right_match.cost
        family_match = left_match.familyMatch or right_match.familyMatch
        chord_diff = left_match.chordDiff

        return MatchValue(
            chordDiff=chord_diff,
            cost=total_cost,
            familyMatch=family_match,
        )

    def _match_subblock(self,
                         subblock: Block,
                         node: 'TreeNode') -> MatchValue:
        """
        Match a single sub-block definition against a tree node.
        """
        if isinstance(subblock, ChordBlock):
            # Terminal: node must be a leaf with matching chord
            if not node.is_leaf():
                return MatchValue.NO_MATCH
            if node.chord is None:
                return MatchValue.NO_MATCH
            chord = node.chord
            if subblock.root != chord.root:
                return MatchValue.NO_MATCH
            if subblock.quality == chord.quality:
                return MatchValue(chordDiff=0, cost=0.0)
            # No dicts available here — exact match only at binary level
            # Equivalence checking happens in UnaryProduction / findTerminal
            return MatchValue.NO_MATCH

        elif isinstance(subblock, Brick):
            # Non-terminal: node's head must match brick name
            if node.is_leaf():
                # A leaf can match a single-chord brick
                if subblock.is_single_chord():
                    flat = subblock.flatten()
                    if flat and node.chord:
                        if (flat[0].root == node.chord.root and
                                flat[0].quality == node.chord.quality):
                            return MatchValue(chordDiff=0, cost=0.0)
                return MatchValue.NO_MATCH

            # Check name match
            if node.head == subblock.name:
                return MatchValue(chordDiff=0, cost=0.0)

            # Also match invisible bricks with the same key/mode
            if (node.ptype == 'Invisible' and
                    node.key == subblock.key and
                    node.mode == subblock.mode):
                return MatchValue(chordDiff=0, cost=5.0, familyMatch=True)

            return MatchValue.NO_MATCH

        elif isinstance(subblock, IntermediateBrick):
            # Intermediate binarization node
            if node.head == subblock.name:
                return MatchValue(chordDiff=0, cost=0.0)
            return MatchValue.NO_MATCH

        return MatchValue.NO_MATCH

    def get_head(self) -> str:
        return self.head

    def get_type(self) -> str:
        return self.ptype

    def get_mode(self) -> str:
        return self.mode

    def get_variant(self) -> str:
        return self.variant

    def get_key(self) -> int:
        return self.key

    def __repr__(self) -> str:
        return (f"BinaryProduction({self.head!r} → "
                f"{self.left!r} + {self.right!r}, "
                f"type={self.ptype!r})")


# ---------------------------------------------------------------------------
# Rule factory — convert BrickLibrary to production lists
# ---------------------------------------------------------------------------

def create_rules(lib: 'BrickLibrary') -> tuple[
        list[UnaryProduction], list[BinaryProduction]]:
    """
    Convert a BrickLibrary into CYK grammar production rules.
    Mirrors CYKParser.createRules() in Java.

    Bricks with 1 sub-block  → UnaryProduction
    Bricks with 2 sub-blocks → BinaryProduction
    Bricks with N>2 blocks   → binarized into N-1 BinaryProductions

    Returns:
        (terminal_rules, nonterminal_rules)
    """
    terminal_rules:    list[UnaryProduction]  = []
    nonterminal_rules: list[BinaryProduction] = []

    for brick in lib.all_bricks():
        name    = brick.name
        ptype   = brick.type
        key     = brick.key
        mode    = brick.mode
        variant = brick.variant
        blocks  = brick.blocks

        n = len(blocks)
        if n == 0:
            continue

        elif n == 1:
            sb = blocks[0]
            if isinstance(sb, ChordBlock):
                u = UnaryProduction(
                    head=name, ptype=ptype, key=key,
                    chord=sb, show=True,
                    mode=mode, variant=variant,
                )
                terminal_rules.append(u)
            elif isinstance(sb, Brick):
                # Single-brick sub-block: wrap as unary via flattening
                flat = sb.flatten()
                if len(flat) == 1:
                    u = UnaryProduction(
                        head=name, ptype=ptype, key=key,
                        chord=flat[0], show=True,
                        mode=mode, variant=variant,
                    )
                    terminal_rules.append(u)
                else:
                    # Multi-chord sub-brick — treat as binary delegation
                    p = BinaryProduction(
                        head=name, ptype=ptype, key=key,
                        left=sb, right=ChordBlock('NC', 0),
                        show=True, mode=mode, variant=variant,
                    )
                    nonterminal_rules.append(p)

        elif n == 2:
            p = BinaryProduction(
                head=name, ptype=ptype, key=key,
                left=blocks[0], right=blocks[1],
                show=True, mode=mode, variant=variant,
            )
            nonterminal_rules.append(p)

        else:
            # Binarize: [A, B, C, D] → ((A,B), C), D
            # Generate intermediate invisible rules
            # Mirrors CYKParser.createRules() binarization in Java

            # First intermediate: name+variant+'1' → blocks[0], blocks[1]
            inter_name = name + variant + '1'
            inter_left = IntermediateBrick(
                name=inter_name, key=key, mode=mode,
                blocks=[blocks[0], blocks[1]], variant=variant,
            )
            p0 = BinaryProduction(
                head=inter_name, ptype='Invisible', key=key,
                left=blocks[0], right=blocks[1],
                show=False, mode=mode, variant=variant,
            )
            nonterminal_rules.append(p0)

            # Middle intermediates
            prev_inter = inter_left
            for i in range(2, n - 1):
                curr_name = name + variant + str(i)
                curr_inter = IntermediateBrick(
                    name=curr_name, key=key, mode=mode,
                    blocks=[prev_inter, blocks[i]], variant=variant,
                )
                pi = BinaryProduction(
                    head=curr_name, ptype='Invisible', key=key,
                    left=prev_inter, right=blocks[i],
                    show=False, mode=mode, variant=variant,
                )
                nonterminal_rules.append(pi)
                prev_inter = curr_inter

            # Final rule: original name → last_intermediate, last_block
            pn = BinaryProduction(
                head=name, ptype=ptype, key=key,
                left=prev_inter, right=blocks[n - 1],
                show=True, mode=mode, variant=variant,
            )
            nonterminal_rules.append(pn)

    return terminal_rules, nonterminal_rules


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    from python.roadmap.brick_library import BrickLibrary

    dict_path = '/usr/share/impro-visor/vocab/My.dictionary'
    sub_path  = '/usr/share/impro-visor/vocab/My.substitutions'

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        lib = BrickLibrary()
        lib.load(dict_path, sub_path)

    terminal_rules, nonterminal_rules = create_rules(lib)

    print(f"BrickLibrary: {lib}")
    print(f"Terminal rules   (unary):  {len(terminal_rules)}")
    print(f"Nonterminal rules (binary): {len(nonterminal_rules)}")
    print()

    # Show a sample of each
    print("Sample terminal rules:")
    for r in terminal_rules[:5]:
        print(f"  {r}")

    print("\nSample nonterminal rules:")
    for r in nonterminal_rules[:10]:
        print(f"  {r}")

    print()

    # Test MatchValue
    from python.roadmap.chord_block import ChordBlock as CB
    mv = MatchValue(chordDiff=0, cost=5.0, familyMatch=False)
    print(f"MatchValue: {mv}, matched={mv.matched}")
    print(f"NO_MATCH:   {MatchValue.NO_MATCH}, matched={MatchValue.NO_MATCH.matched}")
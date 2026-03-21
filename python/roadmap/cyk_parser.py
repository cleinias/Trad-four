"""
cyk_parser.py — Trad-Four roadmap module
CYK (Cocke-Younger-Kasami) parser for the brick grammar.

Mirrors imp.roadmap.cykparser.CYKParser from Impro-Visor.

The CYK algorithm fills an n×n triangular table where cell (i,j) holds
all possible parse trees for the chord sub-sequence [i..j].

Bottom-up fill:
  - Diagonal cells (i,i): try all UnaryProductions against single chords
  - Upper cells (i,j): try all BinaryProductions over all split points k
    where left = table[i][k] and right = table[k+1][j]

Solution extraction:
  A second pass finds the minimum-cost non-overlapping cover of the
  entire chord sequence [0..n-1].

Usage:
    from python.roadmap.cyk_parser import CYKParser
    from python.roadmap.brick_library import BrickLibrary
    from python.roadmap.chord_block import ChordBlock

    lib = BrickLibrary()
    lib.load('data/vocab/My.dictionary',
             'data/vocab/My.substitutions')

    parser = CYKParser(lib)

    chords = [ChordBlock('Dm7', 2), ChordBlock('G7', 2), ChordBlock('CM7', 4)]
    blocks = parser.parse(chords)
    for block in blocks:
        print(block)
"""

from __future__ import annotations
import warnings
from fractions import Fraction
from typing import Optional

from python.roadmap.chord_block import ChordBlock
from python.roadmap.brick import Brick, Block
from python.roadmap.brick_library import BrickLibrary, _TYPE_COSTS, _DEFAULT_COST
from python.roadmap.productions import (
    UnaryProduction, BinaryProduction, TreeNode,
    MatchValue, create_rules
)

# Cost constants (mirrors CYKParser in Java)
SUB_COST    = 5.0   # cost for substitution match
FAMILY_COST = 5.0   # cost for family match
OVERLAP_COST = 5.0  # cost for overlap bricks
INF_COST    = float('inf')


# ---------------------------------------------------------------------------
# CYKParser
# ---------------------------------------------------------------------------

class CYKParser:
    """
    CYK parser for the Impro-Visor brick grammar.

    Attributes:
        lib             : BrickLibrary with all brick definitions
        terminal_rules  : list of UnaryProduction
        nonterminal_rules: list of BinaryProduction
        dicts           : ChordDictionaries for equivalence/substitution
    """

    def __init__(self, lib: BrickLibrary):
        self.lib   = lib
        self.dicts = lib.dicts
        self.terminal_rules, self.nonterminal_rules = create_rules(lib)
        self._table: Optional[list[list[list[TreeNode]]]] = None
        self._chords: list[ChordBlock] = []

    def _init_table(self, chords: list[ChordBlock]) -> None:
        """Initialize the CYK table for a new chord sequence."""
        self._chords = chords
        n = len(chords)
        # table[i][j] = list of TreeNodes for span [i..j]
        self._table = [[[] for _ in range(n)] for _ in range(n)]

    def _find_terminal(self, i: int) -> None:
        """
        Fill table[i][i] — the diagonal cell for a single chord.
        Mirrors CYKParser.findTerminal() in Java.

        1. Create a leaf TreeNode for the chord itself
        2. Try all UnaryProductions against the leaf
        3. Add any matching nodes to the cell
        """
        chord = self._chords[i]
        leaf  = TreeNode(chord=chord, cost=0.0)
        self._table[i][i].append(leaf)

        unaries: list[TreeNode] = []
        for rule in self.terminal_rules:
            mv = rule.check_production(leaf, self.dicts)
            if mv.matched:
                type_cost = _TYPE_COSTS.get(rule.get_type(), _DEFAULT_COST)
                cost = mv.cost + SUB_COST + type_cost
                # Actual key = rule's C-rooted key + transposition
                actual_key = (rule.get_key() + mv.chordDiff) % 12
                node = TreeNode(
                    head=rule.get_head(),
                    ptype=rule.get_type(),
                    mode=rule.get_mode(),
                    variant=rule.get_variant(),
                    key=actual_key,
                    left=leaf,
                    cost=cost,
                    chord_diff=mv.chordDiff,
                    is_sub=mv.familyMatch,
                )
                unaries.append(node)

        self._table[i][i].extend(unaries)

    def _find_nonterminal(self, row: int, col: int) -> None:
        """
        Fill table[row][col] for span [row..col].
        Mirrors CYKParser.findNonterminal() in Java.

        For each split point k in [row..col-1]:
          For each (left_node, right_node) pair from table[row][k], table[k+1][col]:
            Try all BinaryProductions
        """
        self._table[row][col] = []
        overlaps: list[TreeNode] = []

        for k in range(row, col):
            for left_node in list(self._table[row][k]):
                if left_node.is_section_end() or left_node.overlap:
                    continue

                for right_node in list(self._table[k + 1][col]):
                    if right_node.overlap:
                        continue

                    for rule in self.nonterminal_rules:
                        mv = rule.check_production(left_node, right_node, self.dicts)
                        if not mv.matched:
                            continue

                        # Accumulate costs
                        cost = mv.cost
                        if left_node.is_sub:
                            cost += SUB_COST
                        if right_node.is_sub:
                            cost += SUB_COST
                        if mv.familyMatch:
                            cost += FAMILY_COST
                        type_cost = _TYPE_COSTS.get(rule.get_type(), _DEFAULT_COST)
                        cost += type_cost

                        node = TreeNode(
                            head=rule.get_head(),
                            ptype=rule.get_type(),
                            mode=rule.get_mode(),
                            variant=rule.get_variant(),
                            key=(rule.get_key() + mv.chordDiff) % 12,
                            left=left_node,
                            right=right_node,
                            cost=cost,
                            chord_diff=mv.chordDiff,
                            is_sub=mv.familyMatch,
                        )
                        self._table[row][col].append(node)

                        # Generate overlap copy unless this is an
                        # On-Off/Off-On type or section end
                        if (rule.get_type() not in ('On-Off', 'Off-On') and
                                not right_node.is_section_end() and
                                right_node.get_duration() > 0):
                            overlaps.append(node.overlap_copy())

        # Apply unary rules only to leaf nodes in the cell
        # (nonterminal nodes cannot match unary/terminal rules)
        unaries: list[TreeNode] = []
        for node in list(self._table[row][col]):
            if not node.is_leaf():
                continue
            for rule in self.terminal_rules:
                mv = rule.check_production(node, self.dicts)
                if mv.matched:
                    cost = mv.cost
                    if mv.familyMatch:
                        cost += FAMILY_COST
                    new_node = TreeNode(
                        head=rule.get_head(),
                        ptype=rule.get_type(),
                        mode=rule.get_mode(),
                        variant=rule.get_variant(),
                        key=(rule.get_key() + mv.chordDiff) % 12,
                        left=node,
                        cost=node.cost + cost,
                        chord_diff=mv.chordDiff,
                        is_sub=mv.familyMatch,
                    )
                    unaries.append(new_node)

        self._table[row][col].extend(unaries)

        # Add overlaps to the previous column
        if overlaps and col > 0:
            self._table[row][col - 1].extend(overlaps)

    def _fill_table(self) -> None:
        """
        Fill the entire CYK table bottom-up.
        Mirrors CYKParser.fillTable() in Java.
        """
        n = len(self._chords)

        # Fill diagonal (single chords)
        for i in range(n):
            self._find_terminal(i)

        # Fill upper triangle (spans of length 2..n)
        for length in range(2, n + 1):
            for row in range(n - length + 1):
                col = row + length - 1
                self._find_nonterminal(row, col)

    def _find_solution(self) -> list[Block]:
        """
        Find the minimum-cost parse covering all chords.
        Mirrors CYKParser.findSolution() in Java.

        Two-pass approach:
        1. For each cell, find the minimum-cost visible node
        2. Dynamic programming to find the minimum-cost non-overlapping cover
        """
        n = len(self._chords)
        if n == 0:
            return []

        # Pass 1: find minimum-cost visible node per cell
        min_vals: list[list[TreeNode]] = [
            [TreeNode(cost=INF_COST) for _ in range(n)]
            for _ in range(n)
        ]

        for row in range(n):
            for col in range(row, n):
                for node in self._table[row][col]:
                    if (node.to_show() and
                            node.ptype not in ('Invisible', '') and
                            node.less_than(min_vals[row][col])):
                        min_vals[row][col] = node

        # Fallback: ensure every diagonal cell has a finite cost.
        # Bare chords that don't match any unary production still need
        # to participate in the DP as valid (but expensive) leaf solutions.
        for i in range(n):
            if min_vals[i][i].cost == INF_COST:
                leaf = self._table[i][i][0]   # the original chord leaf
                min_vals[i][i] = TreeNode(
                    chord=leaf.chord,
                    cost=_DEFAULT_COST,
                )

        # Pass 2: dynamic programming for minimum-cost cover
        # min_vals[i][j] now gets updated to reflect the best
        # partition of [i..j] into sub-spans
        for i in range(n - 2, -1, -1):
            for j in range(i + 1, n):
                for k in range(i + 1, j + 1):
                    combined_cost = (min_vals[i][k - 1].cost +
                                     min_vals[k][j].cost)
                    if combined_cost < min_vals[i][j].cost:
                        min_vals[i][j] = TreeNode(
                            left=min_vals[i][k - 1],
                            right=min_vals[k][j],
                            cost=combined_cost,
                        )

        # Convert the optimal tree to a list of blocks
        return min_vals[0][n - 1].to_blocks()

    def parse(self, chords: list[ChordBlock]) -> list[Block]:
        """
        Parse a sequence of ChordBlocks into a list of Blocks (Bricks + ChordBlocks).

        Handles section boundaries by parsing each section independently,
        then concatenating results.

        Args:
            chords: list of ChordBlock objects

        Returns:
            list of Block objects (mix of recognized Bricks and bare ChordBlocks)
        """
        if not chords:
            return []

        # Split on section boundaries and parse each section
        result: list[Block] = []
        section: list[ChordBlock] = []

        for chord in chords:
            section.append(chord)
            if chord.is_section_end:
                result.extend(self._parse_section(section))
                section = []

        if section:
            result.extend(self._parse_section(section))

        return result

    def _parse_section(self, chords: list[ChordBlock]) -> list[Block]:
        """Parse a single section (no section boundaries within)."""
        # Filter out NC chords for parsing but preserve them in output
        non_nc = [c for c in chords if not c.is_nochord()]
        if not non_nc:
            return list(chords)

        self._init_table(non_nc)
        self._fill_table()
        blocks = self._find_solution()

        # If solution is empty or all bare chords, return as-is
        return blocks if blocks else list(chords)

    def parse_leadsheet(self, chord_timeline: list) -> list[Block]:
        """
        Parse a chord timeline from a parsed LeadSheet.

        Args:
            chord_timeline: list of ChordEvent objects (from parser.py)

        Returns:
            list of Block objects with tonal area information
        """
        from python.roadmap.chord_block import ChordBlock as CB

        chords = []
        for event in chord_timeline:
            cb = CB(event.symbol, event.duration)
            chords.append(cb)

        return self.parse(chords)


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import warnings
    from python.config import DICT_PATH as _DICT_PATH, SUB_PATH as _SUB_PATH

    dict_path = str(_DICT_PATH)
    sub_path  = str(_SUB_PATH)

    print("Loading BrickLibrary...")
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        lib = BrickLibrary()
        lib.load(dict_path, sub_path)

    parser = CYKParser(lib)
    print(f"Parser ready: {len(parser.terminal_rules)} terminal rules, "
          f"{len(parser.nonterminal_rules)} nonterminal rules\n")

    # Test cases
    test_cases = [
        # (description, chord list)
        ('ii-V-I in C major',
         [ChordBlock('Dm7', 2), ChordBlock('G7', 2), ChordBlock('CM7', 4)]),

        ('Perfect Cadence in C',
         [ChordBlock('G7', 2), ChordBlock('C', 2)]),

        ('iiø-V-i in G minor',
         [ChordBlock('Am7b5', 2), ChordBlock('D7', 2), ChordBlock('Gm7', 4)]),

        ('ii-V-I in F major',
         [ChordBlock('Gm7', 2), ChordBlock('C7', 2), ChordBlock('FM7', 4)]),

        ('Bars 1-8 of Bye Bye Blackbird',
         [ChordBlock('FM6', 4),
          ChordBlock('Gm7', 2), ChordBlock('C7', 2),
          ChordBlock('F6',  4),
          ChordBlock('F6',  4),
          ChordBlock('F6',  4),
          ChordBlock('Abdim7', 4),
          ChordBlock('Gm7', 4),
          ChordBlock('C7',  4)]),
    ]

    for desc, chords in test_cases:
        print(f"--- {desc} ---")
        print(f"Input:  {[c.symbol for c in chords]}")
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            blocks = parser.parse(chords)
        print(f"Output: {blocks}")
        for block in blocks:
            if isinstance(block, Brick):
                print(f"  Brick: {block.name!r} "
                      f"[{block.mode} {block.type}] "
                      f"key={block.key} "
                      f"chords={[c.symbol for c in block.flatten()]}")
            elif isinstance(block, ChordBlock):
                print(f"  Chord: {block}")
        print()
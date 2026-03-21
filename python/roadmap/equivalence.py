"""
equivalence.py — Trad-Four roadmap module
EquivalenceDictionary and SubstitutionDictionary for chord matching.

Mirrors imp.roadmap.cykparser.EquivalenceDictionary and
imp.roadmap.cykparser.SubstitutionDictionary from Impro-Visor.

These dictionaries allow the CYK parser to match chords that are
functionally equivalent or substitutable, even if their symbols differ.

Equivalence rules (bidirectional):
    (equiv C CM CMaj7 CM7 ...) means any of these can replace any other.

Substitution rules (unidirectional):
    (sub C7 C7alt C7b9 ...) means C7alt, C7b9 etc. can appear where
    C7 is expected, but C7 cannot appear where C7alt is expected.

Both are stored as normalized C-root qualities.
Transposition is handled by stripping the root before lookup.

Usage:
    from python.roadmap.equivalence import EquivalenceDictionary
    from python.roadmap.sexp_parser import parse_file

    exprs = parse_file('data/vocab/My.substitutions')
    edict = EquivalenceDictionary()
    edict.load_from_sexp(exprs)

    cb1 = ChordBlock('Dm7')
    cb2 = ChordBlock('Dm9')
    print(edict.are_equivalent(cb1, cb2))   # True
"""

from __future__ import annotations
from typing import Optional

from python.roadmap.chord_block import ChordBlock, parse_root
from python.roadmap.sexp_parser import parse_file, SExp


# ---------------------------------------------------------------------------
# EquivalenceDictionary
# ---------------------------------------------------------------------------

class EquivalenceDictionary:
    """
    Bidirectional chord equivalence classes.

    Stores equivalence as a mapping from normalized C-root quality string
    to a canonical quality (the first member of the equivalence class).
    Two chords are equivalent if they map to the same canonical quality.

    Example:
        'maj7', 'M7', 'Maj7' → all map to '' (bare major canonical)
        'm7', 'm9', 'm11'    → all map to 'm7'
        '7', '9', '13', '7b9' → all map to '7'
    """

    def __init__(self):
        # Maps quality_string → canonical_quality_string
        self._quality_to_canonical: dict[str, str] = {}
        # Maps canonical → frozenset of all equivalent qualities
        self._classes: dict[str, frozenset] = {}

    def add_rule(self, chords: list[ChordBlock]) -> None:
        """
        Add an equivalence rule from a list of ChordBlocks (all C-rooted).
        The first chord in the list becomes the canonical representative.
        """
        if len(chords) < 2:
            return
        qualities = [cb.quality for cb in chords]
        canonical = qualities[0]
        eq_class = frozenset(qualities)

        # Merge with any existing class that overlaps
        for q in qualities:
            if q in self._quality_to_canonical:
                existing_canonical = self._quality_to_canonical[q]
                existing_class = self._classes.get(existing_canonical, frozenset())
                # Merge the two classes
                merged = existing_class | eq_class
                # Re-canonicalize merged class
                merged_canonical = canonical
                for mc in merged:
                    self._quality_to_canonical[mc] = merged_canonical
                self._classes[merged_canonical] = merged
                # Remove old canonical if different
                if existing_canonical != merged_canonical:
                    self._classes.pop(existing_canonical, None)
                return

        # No overlap — add as new class
        self._classes[canonical] = eq_class
        for q in qualities:
            self._quality_to_canonical[q] = canonical

    def canonical(self, quality: str) -> Optional[str]:
        """Return the canonical quality for a given quality string, or None."""
        return self._quality_to_canonical.get(quality)

    def are_equivalent(self, a: ChordBlock, b: ChordBlock) -> bool:
        """
        True if chords a and b are equivalent — same root and
        qualities in the same equivalence class.
        """
        if a.root != b.root:
            return False
        if a.quality == b.quality:
            return True
        can_a = self._quality_to_canonical.get(a.quality)
        can_b = self._quality_to_canonical.get(b.quality)
        if can_a is None or can_b is None:
            return False
        return can_a == can_b

    def equivalence_class(self, chord: ChordBlock) -> frozenset:
        """Return all qualities equivalent to chord's quality."""
        can = self._quality_to_canonical.get(chord.quality)
        if can is None:
            return frozenset({chord.quality})
        return self._classes.get(can, frozenset({chord.quality}))

    def __len__(self) -> int:
        return len(self._classes)

    def __repr__(self) -> str:
        return f"EquivalenceDictionary({len(self._classes)} classes)"


# ---------------------------------------------------------------------------
# SubstitutionDictionary
# ---------------------------------------------------------------------------

class SubstitutionDictionary:
    """
    Unidirectional chord substitution rules.

    (sub C7 C7alt C7b9 ...) means:
      - C7alt, C7b9 etc. CAN appear where C7 is expected
      - C7 CANNOT appear where C7alt is expected

    Stored as: head_quality → set of substitute qualities
    """

    def __init__(self):
        # Maps head_quality → set of qualities that can substitute for it
        self._rules: dict[str, set[str]] = {}
        # Reverse map: sub_quality → set of head qualities it can substitute for
        self._reverse: dict[str, set[str]] = {}

    def add_rule(self, head: str, substitutes: list[str]) -> None:
        """
        Add a substitution rule.

        Args:
            head:        the quality being substituted (C-rooted, root stripped)
            substitutes: list of quality strings that can substitute for head
        """
        if head not in self._rules:
            self._rules[head] = set()
        self._rules[head].update(substitutes)

        for sub in substitutes:
            if sub not in self._reverse:
                self._reverse[sub] = set()
            self._reverse[sub].add(head)

    def can_substitute(self, candidate: ChordBlock,
                       target: ChordBlock) -> bool:
        """
        True if candidate can substitute for target.
        Both must have the same root.

        candidate can substitute for target if:
          - They are the same, OR
          - candidate.quality is in the substitution set for target.quality
        """
        if candidate.root != target.root:
            return False
        if candidate.quality == target.quality:
            return True
        return candidate.quality in self._rules.get(target.quality, set())

    def substitute_heads(self, chord: ChordBlock) -> set[str]:
        """
        Return all head qualities that chord.quality can substitute for.
        (i.e. what chords this chord can appear in place of)
        """
        return self._reverse.get(chord.quality, set())

    def __repr__(self) -> str:
        return f"SubstitutionDictionary({len(self._rules)} rules)"


# ---------------------------------------------------------------------------
# Combined loader
# ---------------------------------------------------------------------------

class ChordDictionaries:
    """
    Loads and holds both the EquivalenceDictionary and SubstitutionDictionary
    from My.substitutions (and optionally the equiv rules from My.dictionary).
    """

    def __init__(self):
        self.equiv = EquivalenceDictionary()
        self.sub   = SubstitutionDictionary()

    def load_from_sexp(self, exprs: list[SExp]) -> None:
        """
        Load equivalence and substitution rules from parsed S-expressions.
        Handles both My.substitutions and the equiv rules in My.dictionary.

        Args:
            exprs: list of top-level S-expressions from parse_file()
        """
        for expr in exprs:
            if not isinstance(expr, list) or len(expr) < 2:
                continue

            tag = expr[0]

            if tag == 'equiv':
                # (equiv C CM CMaj7 ...)
                # All symbols are C-rooted — strip root to get qualities
                chords = []
                for sym in expr[1:]:
                    if isinstance(sym, str):
                        cb = ChordBlock(sym)
                        if not cb.is_nochord():
                            chords.append(cb)
                if len(chords) >= 2:
                    self.equiv.add_rule(chords)

            elif tag == 'sub':
                # (sub C7 C7alt C7b9 ...)
                # First symbol is the head, rest are substitutes
                if len(expr) < 3:
                    continue
                head_sym = expr[1]
                if not isinstance(head_sym, str):
                    continue
                head_cb = ChordBlock(head_sym)
                if head_cb.is_nochord():
                    continue
                head_quality = head_cb.quality

                sub_qualities = []
                for sym in expr[2:]:
                    if isinstance(sym, str):
                        cb = ChordBlock(sym)
                        if not cb.is_nochord():
                            sub_qualities.append(cb.quality)
                if sub_qualities:
                    self.sub.add_rule(head_quality, sub_qualities)

    def load_substitutions_file(self, path: str) -> None:
        """Load from My.substitutions file."""
        exprs = parse_file(path)
        self.load_from_sexp(exprs)

    def load_dictionary_file(self, path: str) -> None:
        """Load equiv rules from My.dictionary (ignores defbrick etc.)."""
        exprs = parse_file(path)
        equiv_exprs = [e for e in exprs
                       if isinstance(e, list) and e and e[0] == 'equiv']
        self.load_from_sexp(equiv_exprs)

    def are_equivalent(self, a: ChordBlock, b: ChordBlock) -> bool:
        """True if a and b are equivalent (same root, same equiv class)."""
        return self.equiv.are_equivalent(a, b)

    def can_substitute(self, candidate: ChordBlock,
                       target: ChordBlock) -> bool:
        """True if candidate can substitute for target."""
        return self.sub.can_substitute(candidate, target)

    def match(self, candidate: ChordBlock, target: ChordBlock) -> tuple[bool, int]:
        """
        Check if candidate matches target for grammar matching purposes.

        Returns (matches, cost) where cost reflects match quality:
            0  = exact match
            5  = equivalence match
            10 = substitution match
            -1 = no match

        Mirrors AbstractProduction.MatchValue in Impro-Visor.
        """
        if candidate.root != target.root:
            return False, -1

        if candidate.quality == target.quality:
            return True, 0

        if self.equiv.are_equivalent(candidate, target):
            return True, 5

        if self.sub.can_substitute(candidate, target):
            return True, 10

        return False, -1

    def __repr__(self) -> str:
        return (f"ChordDictionaries("
                f"equiv={self.equiv}, sub={self.sub})")


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import os
    from python.config import DICT_PATH as _DICT_PATH, SUB_PATH as _SUB_PATH

    sub_path  = str(_SUB_PATH)
    dict_path = str(_DICT_PATH)

    dicts = ChordDictionaries()

    if os.path.exists(sub_path):
        dicts.load_substitutions_file(sub_path)
        print(f"Loaded substitutions: {dicts.sub}")
    if os.path.exists(dict_path):
        dicts.load_dictionary_file(dict_path)
        print(f"Loaded equivalences:  {dicts.equiv}")

    print()

    # Test equivalence
    test_pairs = [
        ('Dm7',  'Dm9',   True,  'minor7 family'),
        ('Dm7',  'Dm11',  True,  'minor7 family'),
        ('G7',   'G9',    True,  'dominant family'),
        ('G7',   'G7b9',  True,  'dominant family'),
        ('G7',   'G7alt', True,  'dominant family'),
        ('CM7',  'CMaj7', True,  'major family'),
        ('CM7',  'C6',    True,  'major family'),
        ('Dm7',  'G7',    False, 'different families'),
        ('Dm7',  'Fm7',   False, 'different roots'),
        ('Cdim', 'Co7',   True,  'diminished family'),
        ('C+',   'Caug',  True,  'augmented family'),
    ]

    print(f"{'Chord A':>8} {'Chord B':>8} {'Expected':>10} "
          f"{'Got':>5} {'OK?':>5}  Note")
    print('-' * 60)
    for sym_a, sym_b, expected, note in test_pairs:
        a = ChordBlock(sym_a)
        b = ChordBlock(sym_b)
        result = dicts.are_equivalent(a, b)
        ok = '✓' if result == expected else '✗'
        print(f"{sym_a:>8} {sym_b:>8} {str(expected):>10} "
              f"{str(result):>5} {ok:>5}  {note}")

    print()

    # Test substitution
    sub_tests = [
        ('G7alt', 'G7',   True,  'alt substitutes for dom7'),
        ('G7b9',  'G7',   True,  'b9 substitutes for dom7'),
        ('Gsus4', 'G',    True,  'sus substitutes for major'),
        ('G7',    'G7alt',False, 'dom7 does NOT sub for alt'),
        ('Dm9',   'Dm7',  True,  'min9 substitutes for min7'),
    ]

    print(f"{'Candidate':>10} {'Target':>8} {'Expected':>10} "
          f"{'Got':>5} {'OK?':>5}  Note")
    print('-' * 65)
    for sym_cand, sym_tgt, expected, note in sub_tests:
        cand = ChordBlock(sym_cand)
        tgt  = ChordBlock(sym_tgt)
        result = dicts.can_substitute(cand, tgt)
        ok = '✓' if result == expected else '✗'
        print(f"{sym_cand:>10} {sym_tgt:>8} {str(expected):>10} "
              f"{str(result):>5} {ok:>5}  {note}")

    print()

    # Test match() costs
    print("Match costs:")
    match_tests = [
        ('G7', 'G7',    0,  'exact'),
        ('G9', 'G7',    5,  'equiv'),
        ('G7b9', 'G7',  5,  'equiv (both dominant)'),
        ('Gsus4', 'G',  10, 'sub'),
        ('G7', 'Dm7',  -1,  'no match'),
    ]
    for sym_a, sym_b, expected_cost, note in match_tests:
        a = ChordBlock(sym_a)
        b = ChordBlock(sym_b)
        matches, cost = dicts.match(a, b)
        ok = '✓' if cost == expected_cost else '✗'
        print(f"  {sym_a:>8} vs {sym_b:<8} cost={cost:>3}  {ok}  {note}")
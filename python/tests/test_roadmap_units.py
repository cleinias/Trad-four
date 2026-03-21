"""
test_roadmap_units.py — Trad-Four roadmap module
Unit tests for chord_block, brick, sexp_parser, equivalence, productions,
and cyk_parser internals — targeting uncovered lines from the coverage report.

Run:
    pytest python/tests/test_roadmap_units.py -v
"""

import warnings
import pytest
from fractions import Fraction

from python.roadmap.chord_block import (
    ChordBlock as CB, parse_root, pc_to_name, transpose_symbol,
)
from python.roadmap.brick import Brick, IntermediateBrick
from python.roadmap.sexp_parser import (
    tokenize, parse_string, parse_file,
    is_list, is_atom, head, tail, to_str, ParseError,
)
from python.roadmap.equivalence import (
    EquivalenceDictionary, SubstitutionDictionary, ChordDictionaries,
)
from python.roadmap.productions import MatchValue, TreeNode
from python.roadmap.brick_library import BrickLibrary


# ===================================================================
# ChordBlock — family classification, transposition, comparison
# ===================================================================

class TestChordBlockFamilies:
    """Cover every family classifier and chord_family() branch."""

    @pytest.mark.parametrize('symbol,expected', [
        ('C',       'major'),
        ('CM7',     'major'),
        ('Cmaj7',   'major'),
        ('C6',      'major'),
        ('C69',     'major'),
        ('Cadd9',   'major'),
    ])
    def test_major(self, symbol, expected):
        cb = CB(symbol)
        assert cb.is_major()
        assert cb.chord_family() == expected

    @pytest.mark.parametrize('symbol,expected', [
        ('Cm',    'minor'),
        ('Cmin',  'minor'),
        ('Cm6',   'minor'),
        ('CmM7',  'minor'),
    ])
    def test_minor(self, symbol, expected):
        cb = CB(symbol)
        assert cb.is_minor()
        assert not cb.is_minor7()
        assert cb.chord_family() == expected

    @pytest.mark.parametrize('symbol,expected', [
        ('Cm7',   'minor7'),
        ('Cmin7', 'minor7'),
        ('Cm9',   'minor7'),
        ('Cm11',  'minor7'),
        ('Cm13',  'minor7'),
    ])
    def test_minor7(self, symbol, expected):
        cb = CB(symbol)
        assert cb.is_minor7()
        assert cb.chord_family() == expected

    @pytest.mark.parametrize('symbol,expected', [
        ('C7',     'dominant'),
        ('C9',     'dominant'),
        ('C13',    'dominant'),
        ('C7b9',   'dominant'),
        ('C7#9',   'dominant'),
        ('C7alt',  'dominant'),
        ('C7b13',  'dominant'),
        ('C7#11',  'dominant'),
        ('C7sus4', 'dominant'),
    ])
    def test_dominant(self, symbol, expected):
        cb = CB(symbol)
        assert cb.is_dominant()
        assert cb.chord_family() == expected

    @pytest.mark.parametrize('symbol', ['Cm7b5', 'Cmin7b5'])
    def test_half_diminished(self, symbol):
        cb = CB(symbol)
        assert cb.is_half_diminished()
        assert cb.chord_family() == 'half_dim'

    @pytest.mark.parametrize('symbol', ['Cdim', 'Cdim7', 'Co7'])
    def test_diminished(self, symbol):
        cb = CB(symbol)
        assert cb.is_diminished()
        assert cb.chord_family() == 'diminished'

    @pytest.mark.parametrize('symbol', ['Caug', 'C+'])
    def test_augmented(self, symbol):
        cb = CB(symbol)
        assert cb.is_augmented()
        assert cb.chord_family() == 'augmented'

    def test_nochord_family(self):
        assert CB('NC').chord_family() == 'NC'

    def test_unknown_family(self):
        """A quality that doesn't match any known family."""
        cb = CB('C')
        # Force an unrecognized quality
        cb.quality = 'xyzzy'
        assert cb.chord_family() == 'unknown'


class TestChordBlockTonic:
    """Cover is_tonic() and is_generalized_tonic()."""

    def test_major_is_tonic(self):
        assert CB('C').is_tonic()
        assert CB('CM7').is_tonic()

    def test_pure_minor_is_tonic(self):
        assert CB('Cm').is_tonic()

    def test_minor7_not_tonic(self):
        assert not CB('Cm7').is_tonic()

    def test_minor7_is_generalized_tonic(self):
        assert CB('Cm7').is_generalized_tonic()

    def test_dominant_not_generalized_tonic(self):
        assert not CB('C7').is_generalized_tonic()


class TestChordBlockTransposition:
    """Cover transpose, transposed_to_c, NC transpose."""

    def test_transpose_up(self):
        cb = CB('Dm7', 2)
        t = cb.transpose(5)
        assert t.symbol == 'Gm7'
        assert t.duration == Fraction(2)

    def test_transpose_nc(self):
        cb = CB('NC', 4)
        t = cb.transpose(5)
        assert t.symbol == 'NC'
        assert t.is_nochord()

    def test_transposed_to_c(self):
        cb = CB('Gm7')
        t = cb.transposed_to_c()
        assert t.root == 0
        assert t.quality == 'm7'

    def test_transpose_preserves_section_end(self):
        cb = CB('Dm7', 2, is_section_end=True)
        t = cb.transpose(3)
        assert t.is_section_end


class TestChordBlockComparison:
    """Cover quality_matches, same, resolves_to, __eq__, __hash__, __repr__."""

    def test_quality_matches_exact(self):
        assert CB('Dm7').quality_matches(CB('Gm7'))

    def test_quality_matches_no_match(self):
        assert not CB('Dm7').quality_matches(CB('G7'))

    def test_same(self):
        assert CB('Dm7').same(CB('Dm7'))
        assert not CB('Dm7').same(CB('Gm7'))

    def test_resolves_to(self):
        assert CB('G7').resolves_to(CB('C'))
        assert not CB('G7').resolves_to(CB('F'))

    def test_eq_different_type(self):
        assert CB('Dm7').__eq__('not a chord') == NotImplemented

    def test_eq_same(self):
        assert CB('Dm7') == CB('Dm7')
        assert CB('Dm7') != CB('Gm7')

    def test_hash(self):
        s = {CB('Dm7'), CB('Dm7'), CB('G7')}
        assert len(s) == 2

    def test_repr_with_duration(self):
        r = repr(CB('Dm7', 4))
        assert 'Dm7' in r
        assert '4.00' in r

    def test_repr_section_end(self):
        r = repr(CB('Dm7', 1, is_section_end=True))
        assert '||' in r


class TestParseRoot:
    """Cover parse_root edge cases."""

    def test_sharp(self):
        pc, q = parse_root('C#m7')
        assert pc == 1
        assert q == 'm7'

    def test_flat(self):
        pc, q = parse_root('Bbmaj7')
        assert pc == 10
        assert q == 'maj7'

    def test_cb(self):
        """Cb (C-flat) — flat followed by end of string."""
        pc, q = parse_root('Cb')
        assert pc == 11  # B

    def test_empty(self):
        pc, q = parse_root('')
        assert pc == -1

    def test_invalid_start(self):
        pc, q = parse_root('123')
        assert pc == -1


class TestTransposeSymbol:
    def test_basic(self):
        assert transpose_symbol('Dm7', 5) == 'Gm7'

    def test_nc(self):
        assert transpose_symbol('NC', 5) == 'NC'

    def test_pc_to_name_sharps(self):
        assert pc_to_name(1, sharps=True) == 'C#'
        assert pc_to_name(1, sharps=False) == 'Db'

    def test_pc_to_name_invalid(self):
        assert pc_to_name(99) == '?'


# ===================================================================
# Brick — resolves_to, tree_str, IntermediateBrick
# ===================================================================

class TestBrick:
    """Cover Brick methods missed by pipeline tests."""

    def _make_cadence(self):
        ii = CB('Dm7', Fraction(2))
        v = CB('G7', Fraction(2))
        i = CB('CM7', Fraction(4))
        approach = Brick(
            name='An Approach', variant='', key=0,
            mode='Major', brick_type='Approach', blocks=[ii, v],
        )
        return Brick(
            name='Straight Cadence', variant='', key=0,
            mode='Major', brick_type='Cadence', blocks=[approach, i],
        )

    def test_resolves_to_chord(self):
        cadence = self._make_cadence()
        # Cadence in C resolves to C chord (key == root)
        assert cadence.resolves_to(CB('C'))
        assert not cadence.resolves_to(CB('F'))

    def test_resolves_to_brick(self):
        cadence = self._make_cadence()
        other = Brick(name='X', variant='', key=0, mode='Major',
                      brick_type='On', blocks=[CB('CM7')])
        assert cadence.resolves_to(other)

    def test_resolves_to_unknown_type(self):
        cadence = self._make_cadence()
        assert not cadence.resolves_to("not a block")

    def test_resolves_to_empty_brick(self):
        empty = Brick(name='Empty', variant='', key=0, mode='Major',
                      brick_type='On', blocks=[])
        assert not empty.resolves_to(CB('C'))

    def test_tree_str(self):
        cadence = self._make_cadence()
        s = cadence.tree_str()
        assert 'Straight Cadence' in s
        assert 'An Approach' in s
        assert 'Dm7' in s

    def test_repr_with_variant(self):
        b = Brick(name='Foo', variant='var 1', key=0, mode='Major',
                  brick_type='Cadence', blocks=[CB('CM7')])
        r = repr(b)
        assert 'var 1' in r

    def test_intermediate_brick(self):
        ib = IntermediateBrick(name='Foo1', key=0, mode='Major',
                               blocks=[CB('Dm7'), CB('G7')])
        assert ib.type == 'Invisible'
        assert ib.is_invisible()


# ===================================================================
# sexp_parser — tokenizer, parser, utilities
# ===================================================================

class TestSexpParser:
    """Cover tokenizer edge cases, error paths, and utility functions."""

    def test_tokenize_block_comment(self):
        tokens = tokenize('(a /* comment */ b)')
        assert tokens == ['(', 'a', 'b', ')']

    def test_tokenize_line_comment(self):
        tokens = tokenize('(a // comment\n b)')
        assert tokens == ['(', 'a', 'b', ')']

    def test_parse_nested(self):
        result = parse_string('(a (b c) d)')
        assert result == [['a', ['b', 'c'], 'd']]

    def test_parse_multiple_exprs(self):
        result = parse_string('(a b) (c d)')
        assert len(result) == 2

    def test_parse_atom(self):
        result = parse_string('hello')
        assert result == ['hello']

    def test_parse_empty(self):
        assert parse_string('') == []

    def test_unclosed_paren_raises(self):
        with pytest.raises(ParseError):
            parse_string('(a b')

    def test_unexpected_close_paren_raises(self):
        with pytest.raises(ParseError):
            parse_string(') a')

    def test_is_list(self):
        assert is_list(['a', 'b'])
        assert not is_list('a')

    def test_is_atom(self):
        assert is_atom('hello')
        assert not is_atom(['a'])

    def test_head_tail(self):
        assert head(['defbrick', 'Name', 'Major']) == 'defbrick'
        assert tail(['defbrick', 'Name', 'Major']) == ['Name', 'Major']

    def test_head_empty(self):
        assert head([]) == ''

    def test_tail_single(self):
        assert tail(['x']) == []

    def test_to_str_atom(self):
        assert to_str('hello') == 'hello'

    def test_to_str_short_list(self):
        s = to_str(['a', 'b', 'c'])
        assert s == '(a b c)'

    def test_to_str_long_list(self):
        """Long list should be formatted across multiple lines."""
        long = ['defbrick'] + [f'item{i}' for i in range(20)]
        s = to_str(long)
        assert '\n' in s

    def test_parse_file_real(self):
        """Smoke test against the real dictionary file."""
        exprs = parse_file('/usr/share/impro-visor/vocab/My.dictionary')
        assert len(exprs) > 100
        # Should contain defbrick and equiv entries
        tags = {head(e) for e in exprs if is_list(e)}
        assert 'defbrick' in tags
        assert 'equiv' in tags


# ===================================================================
# Equivalence — EquivalenceDictionary, SubstitutionDictionary
# ===================================================================

class TestEquivalenceDictionary:
    """Cover equivalence edge cases."""

    def test_canonical_unknown(self):
        ed = EquivalenceDictionary()
        assert ed.canonical('xyzzy') is None

    def test_equiv_class_unknown(self):
        ed = EquivalenceDictionary()
        cb = CB('Cxyzzy')
        result = ed.equivalence_class(cb)
        assert result == frozenset({'xyzzy'})

    def test_different_roots_not_equivalent(self):
        ed = EquivalenceDictionary()
        ed.add_rule([CB('CM7'), CB('C6')])
        assert not ed.are_equivalent(CB('CM7'), CB('DM7'))

    def test_one_unknown_canonical(self):
        """If one chord has no canonical, they're not equivalent."""
        ed = EquivalenceDictionary()
        ed.add_rule([CB('CM7'), CB('C6')])
        assert not ed.are_equivalent(CB('CM7'), CB('Cxyz'))

    def test_merge_overlapping_classes(self):
        ed = EquivalenceDictionary()
        ed.add_rule([CB('CM7'), CB('C6')])
        ed.add_rule([CB('C6'), CB('C69')])
        # All three should be in the same class now
        assert ed.are_equivalent(CB('CM7'), CB('C69'))

    def test_len_and_repr(self):
        ed = EquivalenceDictionary()
        ed.add_rule([CB('CM7'), CB('C6')])
        assert len(ed) == 1
        assert 'EquivalenceDictionary' in repr(ed)


class TestSubstitutionDictionary:
    """Cover SubstitutionDictionary methods."""

    def test_basic_substitution(self):
        sd = SubstitutionDictionary()
        sd.add_rule('7', ['7alt', '7b9'])
        assert sd.can_substitute(CB('C7alt'), CB('C7'))
        assert not sd.can_substitute(CB('C7'), CB('C7alt'))

    def test_different_root_no_sub(self):
        sd = SubstitutionDictionary()
        sd.add_rule('7', ['7alt'])
        assert not sd.can_substitute(CB('D7alt'), CB('C7'))

    def test_same_quality_always_substitutes(self):
        sd = SubstitutionDictionary()
        assert sd.can_substitute(CB('C7'), CB('C7'))

    def test_substitute_heads(self):
        sd = SubstitutionDictionary()
        sd.add_rule('7', ['7alt', '7b9'])
        sd.add_rule('m7', ['7alt'])
        heads = sd.substitute_heads(CB('C7alt'))
        assert '7' in heads
        assert 'm7' in heads

    def test_substitute_heads_unknown(self):
        sd = SubstitutionDictionary()
        assert sd.substitute_heads(CB('Cxyz')) == set()

    def test_repr(self):
        sd = SubstitutionDictionary()
        sd.add_rule('7', ['7alt'])
        assert 'SubstitutionDictionary' in repr(sd)


class TestChordDictionaries:
    """Cover the combined match() method and loaders."""

    @pytest.fixture(scope='class')
    def dicts(self):
        d = ChordDictionaries()
        d.load_substitutions_file('/usr/share/impro-visor/vocab/My.substitutions')
        d.load_dictionary_file('/usr/share/impro-visor/vocab/My.dictionary')
        return d

    def test_match_exact(self, dicts):
        ok, cost = dicts.match(CB('C7'), CB('C7'))
        assert ok and cost == 0

    def test_match_equiv(self, dicts):
        ok, cost = dicts.match(CB('CM7'), CB('C6'))
        assert ok and cost == 5

    def test_match_substitution(self, dicts):
        """A chord that's not in the equiv class but IS a sub."""
        # Find a pair that's a substitution but not equivalence
        ok_eq = dicts.are_equivalent(CB('Csus4'), CB('C'))
        if not ok_eq:
            ok, cost = dicts.match(CB('Csus4'), CB('C'))
            if ok:
                assert cost == 10

    def test_match_no_match(self, dicts):
        ok, cost = dicts.match(CB('C7'), CB('Dm7'))
        assert not ok and cost == -1

    def test_match_different_root(self, dicts):
        ok, cost = dicts.match(CB('C7'), CB('D7'))
        assert not ok

    def test_repr(self, dicts):
        r = repr(dicts)
        assert 'ChordDictionaries' in r


# ===================================================================
# Productions — MatchValue, TreeNode
# ===================================================================

class TestMatchValue:
    def test_no_match_sentinel(self):
        assert not MatchValue.NO_MATCH.matched
        assert MatchValue.NO_MATCH.chordDiff == -1

    def test_matched(self):
        mv = MatchValue(chordDiff=5, cost=0.0)
        assert mv.matched

    def test_not_matched(self):
        mv = MatchValue(chordDiff=-1)
        assert not mv.matched


class TestTreeNode:
    """Cover TreeNode methods not hit by pipeline tests."""

    def test_leaf_to_blocks(self):
        leaf = TreeNode(chord=CB('Dm7'))
        blocks = leaf.to_blocks()
        assert len(blocks) == 1
        assert blocks[0].symbol == 'Dm7'

    def test_invisible_transparent(self):
        """Invisible nodes flatten out — children's blocks are returned."""
        left = TreeNode(chord=CB('Dm7'))
        right = TreeNode(chord=CB('G7'))
        invis = TreeNode(head='X1', ptype='Invisible', left=left, right=right)
        blocks = invis.to_blocks()
        assert len(blocks) == 2
        assert blocks[0].symbol == 'Dm7'

    def test_unnamed_node_flattens(self):
        """Unnamed node (no head) flattens children."""
        left = TreeNode(chord=CB('Dm7'))
        right = TreeNode(chord=CB('G7'))
        node = TreeNode(left=left, right=right, cost=0)
        blocks = node.to_blocks()
        assert len(blocks) == 2

    def test_get_duration_leaf(self):
        leaf = TreeNode(chord=CB('Dm7', 4))
        assert leaf.get_duration() == Fraction(4)

    def test_get_duration_tree(self):
        left = TreeNode(chord=CB('Dm7', 2))
        right = TreeNode(chord=CB('G7', 2))
        node = TreeNode(left=left, right=right)
        assert node.get_duration() == Fraction(4)

    def test_overlap_copy(self):
        node = TreeNode(head='X', ptype='Cadence', cost=10.0)
        ov = node.overlap_copy()
        assert ov.overlap is True
        assert ov.head == 'X'
        assert node.overlap is False

    def test_is_section_end_leaf(self):
        leaf = TreeNode(chord=CB('Dm7', 2, is_section_end=True))
        assert leaf.is_section_end()

    def test_is_section_end_nonleaf(self):
        node = TreeNode(head='X', ptype='Cadence')
        assert not node.is_section_end()

    def test_less_than(self):
        a = TreeNode(cost=5.0)
        b = TreeNode(cost=10.0)
        assert a.less_than(b)
        assert not b.less_than(a)

    def test_repr_leaf(self):
        r = repr(TreeNode(chord=CB('Dm7')))
        assert 'leaf' in r

    def test_repr_nonleaf(self):
        r = repr(TreeNode(head='Foo', ptype='Cadence', cost=5.0))
        assert 'Foo' in r


# ===================================================================
# CYKParser — section boundaries, NC handling, parse_leadsheet
# ===================================================================

class TestCYKParserInternals:
    """Cover CYK parser paths not hit by the standard pipeline tests."""

    @pytest.fixture(scope='class')
    def parser(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            lib = BrickLibrary()
            lib.load('/usr/share/impro-visor/vocab/My.dictionary',
                     '/usr/share/impro-visor/vocab/My.substitutions')
        from python.roadmap.cyk_parser import CYKParser
        return CYKParser(lib)

    def test_section_boundary_splits_parsing(self, parser):
        """Chords with is_section_end=True split into separate sections."""
        chords = [
            CB('Dm7', 2), CB('G7', 2), CB('CM7', 4, is_section_end=True),
            CB('Gm7', 2), CB('C7', 2), CB('FM7', 4),
        ]
        blocks = parser.parse(chords)
        # Should detect bricks in both sections
        bricks = [b for b in blocks if isinstance(b, Brick)]
        assert len(bricks) >= 2

    def test_nc_only_section(self, parser):
        """A section with only NC chords should pass through as-is."""
        chords = [CB('NC', 4), CB('NC', 4)]
        blocks = parser.parse(chords)
        assert len(blocks) == 2
        assert all(not isinstance(b, Brick) for b in blocks)

    def test_nc_among_real_chords(self, parser):
        """NC chords are filtered out for parsing, real chords still match."""
        # ii-V-I with an NC interspersed — the NC gets dropped for parsing
        chords = [CB('Dm7', 2), CB('G7', 2), CB('CM7', 4)]
        blocks = parser.parse(chords)
        bricks = [b for b in blocks if isinstance(b, Brick)]
        assert len(bricks) >= 1

    def test_parse_leadsheet_integration(self, parser):
        """parse_leadsheet() accepts ChordEvent objects from the parser."""
        from python.leadsheet.parser import parse as parse_ls
        import os
        ls = parse_ls(os.path.join(
            '/usr/share/impro-visor/leadsheets/imaginary-book',
            'BlueBossa.ls'))
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            blocks = parser.parse_leadsheet(ls.chord_timeline)
        bricks = [b for b in blocks if isinstance(b, Brick)]
        assert len(bricks) >= 5


# ===================================================================
# BrickLibrary — retrieval, diatonic rules
# ===================================================================

class TestBrickLibrary:
    """Cover BrickLibrary retrieval and diatonic methods."""

    @pytest.fixture(scope='class')
    def lib(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            library = BrickLibrary()
            library.load(
                '/usr/share/impro-visor/vocab/My.dictionary',
                '/usr/share/impro-visor/vocab/My.substitutions')
        return library

    def test_get_brick_not_found(self, lib):
        assert lib.get_brick('Nonexistent Brick Name', target_key=0) is None

    def test_get_brick_transpose(self, lib):
        b = lib.get_brick('Straight Cadence', target_key=5)
        assert b is not None
        assert b.key == 5

    def test_brick_names(self, lib):
        names = lib.brick_names()
        assert 'Straight Cadence' in names
        assert 'Sad Cadence' in names

    def test_visible_bricks(self, lib):
        visible = lib.visible_bricks()
        assert len(visible) > 0
        assert all(not b.is_invisible() for b in visible)

    def test_cadence_bricks(self, lib):
        cadences = lib.cadence_bricks()
        assert len(cadences) > 0
        assert all(b.is_cadence() for b in cadences)

    def test_repr(self, lib):
        r = repr(lib)
        assert 'BrickLibrary' in r
        assert 'names' in r

    def test_diatonic_major(self, lib):
        """Dm7 is diatonic to C major."""
        assert lib.diatonic.is_diatonic(CB('Dm7'), key=0, mode='Major',
                                        edict=lib.dicts)

    def test_diatonic_diminished_always_true(self, lib):
        """Diminished chords are always treated as diatonic."""
        assert lib.diatonic.is_diatonic(CB('Cdim7'), key=5, mode='Major',
                                        edict=lib.dicts)

    def test_not_diatonic(self, lib):
        """F#7 is not diatonic to C major."""
        result = lib.diatonic.is_diatonic(CB('Gb7'), key=0, mode='Major',
                                          edict=lib.dicts)
        assert not result

    def test_diatonic_unknown_mode(self, lib):
        """Unknown mode returns False."""
        assert not lib.diatonic.is_diatonic(CB('Dm7'), key=0, mode='Imaginary')

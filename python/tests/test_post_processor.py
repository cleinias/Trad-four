"""
test_post_processor.py — Trad-Four roadmap module
Tests for the CYK parser + post-processor pipeline using hand-crafted
chord sequences and a reduced sample of real Impro-Visor lead sheets.

Run:
    pytest python/tests/test_post_processor.py -v
"""

import os
import warnings
import pytest
from fractions import Fraction

from python.roadmap.chord_block import ChordBlock as CB
from python.roadmap.brick import Brick
from python.roadmap.brick_library import BrickLibrary
from python.roadmap.cyk_parser import CYKParser
from python.roadmap.post_processor import find_keys, KeySpan

# ---------------------------------------------------------------------------
# Fixtures — shared BrickLibrary + CYKParser (expensive to create)
# ---------------------------------------------------------------------------

DICT_PATH = '/usr/share/impro-visor/vocab/My.dictionary'
SUB_PATH  = '/usr/share/impro-visor/vocab/My.substitutions'
LS_DIR    = '/usr/share/impro-visor/leadsheets/imaginary-book'


@pytest.fixture(scope='module')
def lib():
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        library = BrickLibrary()
        library.load(DICT_PATH, SUB_PATH)
    return library


@pytest.fixture(scope='module')
def parser(lib):
    return CYKParser(lib)


def _parse(parser, chords):
    """Parse and suppress warnings."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return parser.parse(chords)


def _parse_ls(parser, path):
    """Parse a lead sheet file through the CYK parser."""
    from python.leadsheet.parser import parse as parse_leadsheet
    ls = parse_leadsheet(path)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        blocks = parser.parse_leadsheet(ls.chord_timeline)
    return ls, blocks


# ---------------------------------------------------------------------------
# Hand-crafted: CYK parser correctness
# ---------------------------------------------------------------------------

class TestCYKParserHandCrafted:
    """CYK parser brick detection on hand-crafted chord sequences."""

    def test_ii_v_i_in_c(self, parser):
        """ii-V-I in C → single Straight Cadence, key=C."""
        blocks = _parse(parser, [CB('Dm7', 2), CB('G7', 2), CB('CM7', 4)])
        assert len(blocks) == 1
        brick = blocks[0]
        assert isinstance(brick, Brick)
        assert 'Cadence' in brick.type
        assert brick.key == 0   # C

    def test_ii_v_i_in_f(self, parser):
        """ii-V-I in F → single Straight Cadence, key=F."""
        blocks = _parse(parser, [CB('Gm7', 2), CB('C7', 2), CB('FM7', 4)])
        assert len(blocks) == 1
        brick = blocks[0]
        assert isinstance(brick, Brick)
        assert 'Cadence' in brick.type
        assert brick.key == 5   # F

    def test_minor_ii_v_i_in_g(self, parser):
        """iiø-V-i in G minor → single Sad Cadence, key=G."""
        blocks = _parse(parser, [CB('Am7b5', 2), CB('D7', 2), CB('Gm7', 4)])
        assert len(blocks) == 1
        brick = blocks[0]
        assert isinstance(brick, Brick)
        assert brick.name == 'Sad Cadence'
        assert brick.mode == 'Minor'
        assert brick.key == 7   # G

    def test_perfect_cadence_in_c(self, parser):
        """V-I in C → Perfect Cadence, key=C."""
        blocks = _parse(parser, [CB('G7', 2), CB('C', 2)])
        assert len(blocks) == 1
        assert isinstance(blocks[0], Brick)
        assert blocks[0].key == 0   # C

    def test_modulation_c_to_f(self, parser):
        """ii-V-I in C followed by ii-V-I in F → two cadence bricks."""
        blocks = _parse(parser, [
            CB('Dm7', 2), CB('G7', 2), CB('CM7', 4),
            CB('Gm7', 2), CB('C7', 2), CB('FM7', 4),
        ])
        cadences = [b for b in blocks if isinstance(b, Brick)
                    and 'Cadence' in b.type]
        assert len(cadences) >= 2
        keys = {b.key for b in cadences}
        assert 0 in keys   # C
        assert 5 in keys   # F

    def test_empty_input(self, parser):
        """Empty chord list → empty result."""
        assert _parse(parser, []) == []

    def test_single_chord(self, parser):
        """Single chord → returned as-is (possibly with a unary brick)."""
        blocks = _parse(parser, [CB('CM7', 4)])
        assert len(blocks) >= 1


# ---------------------------------------------------------------------------
# Hand-crafted: post-processor KeySpan aggregation
# ---------------------------------------------------------------------------

class TestPostProcessorHandCrafted:
    """KeySpan aggregation on hand-crafted chord sequences."""

    def test_single_key(self, parser, lib):
        """ii-V-I in one key → single KeySpan."""
        blocks = _parse(parser, [CB('Dm7', 2), CB('G7', 2), CB('CM7', 4)])
        spans = find_keys(blocks, lib)
        assert len(spans) == 1
        assert spans[0].key == 0      # C
        assert spans[0].mode == 'Major'

    def test_minor_key(self, parser, lib):
        """iiø-V-i in G minor → single Minor KeySpan."""
        blocks = _parse(parser, [CB('Am7b5', 2), CB('D7', 2), CB('Gm7', 4)])
        spans = find_keys(blocks, lib)
        assert len(spans) == 1
        assert spans[0].key == 7      # G
        assert spans[0].mode == 'Minor'

    def test_modulation_two_spans(self, parser, lib):
        """ii-V-I in C → ii-V-I in F produces two KeySpans."""
        blocks = _parse(parser, [
            CB('Dm7', 2), CB('G7', 2), CB('CM7', 4),
            CB('Gm7', 2), CB('C7', 2), CB('FM7', 4),
        ])
        spans = find_keys(blocks, lib)
        assert len(spans) >= 2
        # First span should be C, second should be F
        assert spans[0].key == 0    # C
        assert spans[-1].key == 5   # F

    def test_empty_input(self, parser, lib):
        """Empty blocks → empty KeySpans."""
        assert find_keys([], lib) == []

    def test_duration_coverage(self, parser, lib):
        """Total KeySpan duration >= total chord duration."""
        chords = [CB('Dm7', 2), CB('G7', 2), CB('CM7', 4)]
        blocks = _parse(parser, chords)
        spans = find_keys(blocks, lib)
        chord_dur = sum(c.duration for c in chords)
        span_dur = sum(ks.duration for ks in spans)
        # Spans may be slightly larger due to overlap bricks, but never smaller
        assert span_dur >= chord_dur


# ---------------------------------------------------------------------------
# Lead sheet integration: Bye Bye Blackbird (F major, 32 bars)
# ---------------------------------------------------------------------------

class TestByeByeBlackbird:
    """Bye Bye Blackbird — standard in F major, simple form."""

    @pytest.fixture(scope='class')
    def parsed(self, parser, lib):
        ls, blocks = _parse_ls(parser, os.path.join(LS_DIR, 'ByeByeBlackbird.ls'))
        spans = find_keys(blocks, lib)
        return ls, blocks, spans

    def test_title(self, parsed):
        ls, _, _ = parsed
        assert ls.title == 'Bye Bye Blackbird'

    def test_bricks_detected(self, parsed):
        _, blocks, _ = parsed
        brick_count = sum(1 for b in blocks if isinstance(b, Brick))
        assert brick_count >= 10, f"expected >= 10 bricks, got {brick_count}"

    def test_primary_key_is_f(self, parsed):
        """First KeySpan should be F major."""
        _, _, spans = parsed
        assert spans[0].key == 5      # F
        assert spans[0].mode == 'Major'

    def test_contains_g_minor_spans(self, parsed):
        """Should detect G minor tonal areas (bars 9-14, bridge)."""
        _, _, spans = parsed
        gm_spans = [s for s in spans if s.key == 7 and s.mode == 'Minor']
        assert len(gm_spans) >= 1

    def test_returns_to_f(self, parsed):
        """Last KeySpan should be F major (final turnaround)."""
        _, _, spans = parsed
        assert spans[-1].key == 5     # F

    def test_keyspan_count(self, parsed):
        """Should have multiple tonal areas (F, Gm, chromatic bridge)."""
        _, _, spans = parsed
        assert len(spans) >= 5


# ---------------------------------------------------------------------------
# Lead sheet integration: Blue Bossa (Cm, modulation to Db)
# ---------------------------------------------------------------------------

class TestBlueBossa:
    """Blue Bossa — Cm with modulation to Db, clean 16-bar form."""

    @pytest.fixture(scope='class')
    def parsed(self, parser, lib):
        ls, blocks = _parse_ls(parser, os.path.join(LS_DIR, 'BlueBossa.ls'))
        spans = find_keys(blocks, lib)
        return ls, blocks, spans

    def test_all_bricks(self, parsed):
        """Every chord should be covered by a brick (no bare chords)."""
        _, blocks, _ = parsed
        bare = [b for b in blocks if not isinstance(b, Brick)]
        assert len(bare) == 0, f"unexpected bare chords: {bare}"

    def test_three_tonal_areas(self, parsed):
        """Should detect exactly 3 tonal areas: Cm → Db → Cm."""
        _, _, spans = parsed
        assert len(spans) == 3

    def test_cm_db_cm_sequence(self, parsed):
        """Tonal areas should follow Cm → Db → Cm."""
        _, _, spans = parsed
        assert spans[0].key == 0      # C
        assert spans[0].mode == 'Minor'
        assert spans[1].key == 1      # Db
        assert spans[1].mode == 'Major'
        assert spans[2].key == 0      # C
        assert spans[2].mode == 'Minor'


# ---------------------------------------------------------------------------
# Lead sheet integration: Autumn Leaves (Gm, Bb major relative)
# ---------------------------------------------------------------------------

class TestAutumnLeaves:
    """Autumn Leaves — alternates Bb major and G minor tonal areas."""

    @pytest.fixture(scope='class')
    def parsed(self, parser, lib):
        ls, blocks = _parse_ls(parser, os.path.join(LS_DIR, 'AutumnLeavesGm.ls'))
        spans = find_keys(blocks, lib)
        return ls, blocks, spans

    def test_bricks_detected(self, parsed):
        """Should find substantial brick coverage."""
        _, blocks, _ = parsed
        brick_count = sum(1 for b in blocks if isinstance(b, Brick))
        assert brick_count >= 8

    def test_contains_bb_major(self, parsed):
        """Should detect Bb major tonal areas (ii-V-I in Bb)."""
        _, _, spans = parsed
        bb_spans = [s for s in spans if s.key == 10 and s.mode == 'Major']
        assert len(bb_spans) >= 1

    def test_contains_g_minor(self, parsed):
        """Should detect G minor tonal areas (ii-V-i in Gm)."""
        _, _, spans = parsed
        gm_spans = [s for s in spans if s.key == 7 and s.mode == 'Minor']
        assert len(gm_spans) >= 1

    def test_starts_in_bb(self, parsed):
        """First tonal area should be Bb major (Cm7-F7-Bbmaj7 opening)."""
        _, _, spans = parsed
        assert spans[0].key == 10     # Bb
        assert spans[0].mode == 'Major'

    def test_autumn_leaves_opening_brick(self, parsed):
        """Should detect the 'Autumn Leaves Opening' brick."""
        _, blocks, _ = parsed
        names = [b.name for b in blocks if isinstance(b, Brick)]
        assert 'Autumn Leaves Opening' in names


# ---------------------------------------------------------------------------
# Lead sheet integration: Now's the Time (F blues)
# ---------------------------------------------------------------------------

class TestNowsTheTime:
    """Now's the Time — 12-bar blues in F."""

    @pytest.fixture(scope='class')
    def parsed(self, parser, lib):
        ls, blocks = _parse_ls(parser, os.path.join(LS_DIR, 'NowsTheTime.ls'))
        spans = find_keys(blocks, lib)
        return ls, blocks, spans

    def test_bricks_detected(self, parsed):
        _, blocks, _ = parsed
        brick_count = sum(1 for b in blocks if isinstance(b, Brick))
        assert brick_count >= 3

    def test_dominant_key_areas(self, parsed):
        """Blues should have dominant-mode tonal areas."""
        _, _, spans = parsed
        dom_spans = [s for s in spans if s.mode == 'Dominant']
        assert len(dom_spans) >= 1

    def test_f_dominant_present(self, parsed):
        """Should detect F dominant as a tonal area (blues tonic)."""
        _, _, spans = parsed
        f_dom = [s for s in spans if s.key == 5]
        assert len(f_dom) >= 1


# ---------------------------------------------------------------------------
# Lead sheet integration: Body and Soul (Db major, bridge modulates to D)
# ---------------------------------------------------------------------------

class TestBodyAndSoul:
    """Body and Soul — complex harmony, Db major with D major bridge."""

    @pytest.fixture(scope='class')
    def parsed(self, parser, lib):
        ls, blocks = _parse_ls(parser, os.path.join(LS_DIR, 'BodyAndSoul.ls'))
        spans = find_keys(blocks, lib)
        return ls, blocks, spans

    def test_all_bricks(self, parsed):
        """High-quality parse: no bare chords expected."""
        _, blocks, _ = parsed
        bare = [b for b in blocks if not isinstance(b, Brick)]
        assert len(bare) == 0, f"unexpected bare chords: {[b.symbol for b in bare]}"

    def test_primary_key_is_db(self, parsed):
        """First tonal area should be Db major."""
        _, _, spans = parsed
        assert spans[0].key == 1      # Db
        assert spans[0].mode == 'Major'

    def test_bridge_modulation_to_d(self, parsed):
        """Should detect D major tonal area in the bridge."""
        _, _, spans = parsed
        d_major = [s for s in spans if s.key == 2 and s.mode == 'Major']
        assert len(d_major) >= 1, "no D major span found for bridge"

    def test_returns_to_db(self, parsed):
        """Should return to Db major after the bridge."""
        _, _, spans = parsed
        db_spans = [i for i, s in enumerate(spans)
                    if s.key == 1 and s.mode == 'Major']
        d_spans = [i for i, s in enumerate(spans)
                   if s.key == 2 and s.mode == 'Major']
        # There should be Db spans both before and after the D span
        assert any(i < d_spans[0] for i in db_spans), "no Db before D"
        assert any(i > d_spans[-1] for i in db_spans), "no Db after D"

    def test_many_tonal_areas(self, parsed):
        """Body and Soul has rich harmonic motion — expect many spans."""
        _, _, spans = parsed
        assert len(spans) >= 8

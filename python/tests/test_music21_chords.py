"""
test_music21_chords.py — Trad-Four Phase 1b
Tests music21's ability to parse every chord symbol found in the
Impro-Visor corpus (extracted to data/chord_symbols.txt).

Run with:
    pytest python/tests/test_music21_chords.py -v

Or for a summary report without per-symbol verbosity:
    pytest python/tests/test_music21_chords.py -v --tb=no -q
"""

import re
import pytest
from pathlib import Path
from music21 import harmony
from python.leadsheet.chord_preprocessor import to_music21_figure

# ---------------------------------------------------------------------------
# Load symbol list
# ---------------------------------------------------------------------------

SYMBOLS_FILE = Path('data/chord_symbols.txt')

def load_symbols() -> list[str]:
    if not SYMBOLS_FILE.exists():
        pytest.skip(f"Symbol file not found: {SYMBOLS_FILE}. "
                    "Run the corpus extraction script first.")
    symbols = SYMBOLS_FILE.read_text().splitlines()
    return [s.strip() for s in symbols if s.strip()]

ALL_SYMBOLS = load_symbols()

# Symbols that should be skipped (not real chord symbols)
SKIP_SYMBOLS = {'NC'}

# ---------------------------------------------------------------------------
# Parametrized test — one test case per chord symbol
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('symbol', ALL_SYMBOLS, ids=ALL_SYMBOLS)
def test_music21_parses_symbol(symbol):
    """Every chord symbol in the corpus should be parseable by music21."""
    if symbol in SKIP_SYMBOLS:
        pytest.skip(f"'{symbol}' is a special token, not a chord symbol")

    try:
        cs = harmony.ChordSymbol(to_music21_figure(symbol))
        pitches = cs.pitches
        assert len(pitches) >= 2, (
            f"'{symbol}' parsed but produced fewer than 2 pitches: "
            f"{[p.name for p in pitches]}"
        )
    except Exception as e:
        pytest.fail(f"music21 failed to parse '{symbol}': {e}")


# ---------------------------------------------------------------------------
# Summary test — run all symbols and report failures as a group
# (useful for getting the full failure list in one shot)
# ---------------------------------------------------------------------------

def test_music21_corpus_summary():
    """
    Non-parametrized summary: parse all symbols and report all failures.
    Does not stop at first failure — collects all errors for inspection.
    """
    failures = []
    successes = []

    for symbol in ALL_SYMBOLS:
        if symbol in SKIP_SYMBOLS:
            continue
        try:
            cs = harmony.ChordSymbol(to_music21_figure(symbol))
            _ = cs.pitches
            successes.append(symbol)
        except Exception as e:
            failures.append((symbol, str(e)))

    total = len(ALL_SYMBOLS) - len(SKIP_SYMBOLS)
    print(f"\n{'='*60}")
    print(f"music21 chord symbol compatibility report")
    print(f"{'='*60}")
    print(f"Total symbols tested : {total}")
    print(f"Passed               : {len(successes)}")
    print(f"Failed               : {len(failures)}")
    if failures:
        print(f"\nFailing symbols:")
        for sym, msg in sorted(failures):
            # Truncate long error messages
            short_msg = msg[:80] if len(msg) > 80 else msg
            print(f"  {sym:25} → {short_msg}")

    assert not failures, (
        f"{len(failures)}/{total} chord symbols failed music21 parsing. "
        f"See printed report above for details."
    )
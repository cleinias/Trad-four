# Trad-Four — Project Plan

## Overall Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     INPUTS                              │
│   Lead sheet (chords + melody + metadata)               │
│   Player corpus (MIDI transcriptions + changes)         │
└───────────────┬─────────────────┬───────────────────────┘
                │                 │
                ▼                 ▼
┌──────────────────┐   ┌──────────────────────┐
│  PHASE 1         │   │  PHASE 2             │
│  Lead Sheet      │   │  Style Grammar       │
│  Interpretation  │   │  Induction           │
│  (Python)        │   │  (Python)            │
└──────────┬───────┘   └──────────┬───────────┘
           │                      │
           └──────────┬───────────┘
                      │ OSC
                      ▼
           ┌──────────────────────┐
           │  PHASE 3             │
           │  Improv Generation   │
           │  (SuperCollider)     │
           └──────────────────────┘
                      │ MIDI (via JACK)
                      ▼
           ┌──────────────────────────────────────┐
           │  REAPER                              │
           │  Track 1: generated improv (VSTi)   │
           │  Track 2: rhythm section (audio/MIDI)│
           └──────────────────────────────────────┘
```

The pipeline has four clearly separated concerns:

- **Phase 1 (Python):** interprets the lead sheet — chord symbols, melody, form, key/time/tempo — and exposes a queryable harmonic model.
- **Phase 2 (Python):** induces a player style grammar from a corpus of transcribed solos.
- **Phase 3 (SuperCollider):** executes the grammar in real time over the live chord stream to generate pitched, timed improv phrases, output as a MIDI stream.
- **Sound production (Reaper):** receives the MIDI stream from SC via JACK and plays it through a sampled instrument VSTi. A synchronized rhythm section track runs alongside.

Python and SuperCollider communicate via **OSC (Open Sound Control)**. Python broadcasts the chord timeline at startup and answers real-time note-function queries during playback. SuperCollider owns rhythm, pitch selection, and MIDI output. Reaper owns all audio and sound production.

---

## Functional Model

### Inputs
1. A **lead sheet**: a sequence of chord symbols plus an optional melody, plus metadata (tempo, key signature, time signature, form).
2. A **player corpus**: a set of transcribed solos by the target player, aligned against chord changes.

### Output
A **sequence of (pitch, duration, velocity) triples** — a musically coherent improvised phrase that respects:
- The harmonic structure of the lead sheet (chord tones, available tensions, scale)
- The stylistic tendencies of the target player (rhythmic patterns, note-type distributions)

### Internal pipeline
```
Lead sheet
  └─ chord symbol → note function classifier
       (which MIDI notes are chord tones / color tones / scale tones?)

Player grammar
  └─ grammar expander (probabilistic CFG)
       → typed rhythm skeleton
       e.g. [C♩, A♪, C♪, R♪, L♩, S♪, S♪, C♩]

Pitch filler
  └─ for each typed slot:
       sample from eligible pitch pool
       weighted by contour (prefer stepwise motion)

Output
  └─ (pitch_midi, duration_beats, velocity) sequence
```

### The two meanings of "style"
Impro-Visor distinguishes two unrelated uses of the word "style":

- **Rhythm section style** (`.style` files): bass patterns, chord voicings, drum patterns, swing feel. Not relevant to improv generation.
- **Soloist style** (`.grammar` files): how a particular improviser constructs melodic lines. This is what this project formalizes.

A soloist's style in this model = **rhythmic patterns** + **note-type distributions per rhythmic position**. Actual pitch selection is a separate probabilistic layer, intentionally generic, so the grammar generates fresh lines rather than replaying memorized licks.

---

## Phase 1 — Lead Sheet Interpretation

### Goal
Given a lead sheet as input, produce a structured runtime object that the improv engine can query: *"at beat 3 of bar 7, what chord is playing, what are its chord tones, what scale applies, what tonal area are we in, and what is the melodic note?"*

### Resources
- **`music21`** (MIT, actively maintained) — MusicXML parsing, chord symbol interpretation, scale selection, note function classification, key/time signature metadata. Can dynamically answer "is MIDI note 62 a chord tone over Gm7?" for any chord.
- **`pretty_midi`** — fallback for ingesting MIDI representations of lead sheets.
- **Impro-Visor imaginary-book** — 2600+ jazz standards in `.ls` format, copied locally to `data/leadsheets/`. Primary lead sheet source.
- **`My.dictionary` + `My.substitutions`** — Impro-Visor's brick grammar and chord equivalence rules, copied locally to `data/vocab/`. Used by the roadmap module.
- **`python/config.py`** — centralized path constants (`DICT_PATH`, `SUB_PATH`, `LEADSHEETS_DIR`, etc.) so all code resolves data paths relative to project root.

### Key deliverables

**1a. Lead sheet parser** ✓ DONE
Reads Impro-Visor `.ls` files and produces a Python `LeadSheet` object:
- Time signature, key signature (raw), tempo
- Chord timeline: list of `ChordEvent(bar, beat, symbol, duration_beats)`
- Handles `/` repeats, `NC` (no chord), slash chords, all meters
- 2600+ file corpus passes 100% with no warnings

**1b. Harmonic annotator** ✓ DONE
For each chord in the timeline, computes and caches:
- Root, quality (via `chord_preprocessor.py` — 832/832 corpus symbols passing music21)
- Chord tones (R, 3, 5, 7), color tones (extensions), scale tones
- Per-chord scale using resolution-aware lookahead (`annotator.py`)
- **Tonal area** — which key center is active at each bar (`tonal_areas.py` maps roadmap KeySpans onto ChordEvents)

**1b-roadmap. Tonal area detection** ✓ DONE
Identifies the key center (tonal area) active at each point in the lead sheet using Impro-Visor's brick grammar. This is architecturally separate from per-chord scale selection and operates at a higher level of musical abstraction.

**Strategy:** Reimplements Impro-Visor's roadmap analysis in Python. The Java system uses a CYK (Cocke-Younger-Kasami) parser over a recursive context-free grammar defined in `My.dictionary`. Each matched "brick" (harmonic idiom) carries a key center, and the `PostProcessor.findKeys()` method aggregates brick keys into contiguous `KeySpan` objects.

**Pipeline input/output:**
```
INPUT
  My.dictionary              — brick grammar definitions (818 brick variants)
  My.substitutions           — chord equivalence + substitution rules
  list[ChordEvent]           — chord timeline from the lead sheet parser (Phase 1a)

PIPELINE
  sexp_parser.py             — parse S-expression dictionary files
      → list[SExp]
  brick_library.py           — build recursive brick grammar from S-expressions
      → BrickLibrary            (equiv rules, diatonic rules, defbrick definitions,
                                 auto-generated Overrun + Dropback for Cadence bricks)
  productions.py             — convert BrickLibrary to CYK grammar rules
      → list[UnaryProduction]   (single-chord bricks)
      → list[BinaryProduction]  (multi-chord bricks, with binarization for N>2)
  cyk_parser.py              — CYK bottom-up table fill + DP min-cost solution
      → list[Block]             (mix of recognized Brick objects and bare ChordBlocks)
  post_processor.py          — right-to-left scan aggregating brick keys
      → list[KeySpan]           (contiguous tonal areas: key + mode + duration)

OUTPUT
  list[KeySpan]  — each KeySpan carries:
    key      : int (pitch class 0-11)
    mode     : str ('Major', 'Minor', or 'Dominant')
    duration : Fraction (total beats spanned)
```

Verified on Bye Bye Blackbird (F major), Autumn Leaves (Bb/Gm), Blue Bossa (Cm→Db→Cm), Now's the Time (F blues), and Body and Soul (Db with D major bridge). Test suite: 174 tests, 85% line coverage across the roadmap module.

**Roadmap module files (`python/roadmap/`):**
- `sexp_parser.py` ✓ — tokenizes and parses Impro-Visor S-expression files
- `chord_block.py` ✓ — terminal symbol with family classification and transposition
- `equivalence.py` ✓ — bidirectional equivalence classes + substitution rules
- `brick.py` ✓ — non-terminal with flatten/transpose/resolve operations
- `brick_library.py` ✓ — loads My.dictionary, 818 brick variants, auto Overrun/Dropback
- `productions.py` ✓ — UnaryProduction, BinaryProduction, binarization; chordDiff-based transposition-aware matching
- `cyk_parser.py` ✓ — CYK table fill + DP min-cost non-overlapping cover extraction
- `post_processor.py` ✓ — aggregates brick keys into KeySpan tonal areas (right-to-left scan with diatonic absorption and approach resolution)

**1c. Note function classifier** ✓ DONE
Given any MIDI pitch and the current chord + tonal area, returns its functional label:
`C` (chord tone), `L` (color tone), `S` (scale tone), `A` (approach tone — chromatic neighbor of chord tone), `X` (outside), `NC` (no chord).
Implemented in `annotator.py:note_function()`. Approach tones are detected as half-step above or below any chord tone.

**1d. OSC broadcaster** ✓ DONE
Sends the fully annotated chord timeline to SuperCollider via OSC at startup as a batch dump. Protocol: `/trad4/meta` (metadata), `/trad4/chord` (one per ChordEvent with all annotation fields), `/trad4/done` (completion signal). Pitch class sets sent as comma-separated strings for SC parsing. Full pipeline CLI: `python -m python.leadsheet.osc_bridge path/to/tune.ls`. Uses `python-osc` library. Real-time query server deferred to Phase 3.

### Open questions
- Do we treat the melody as a constraint on the improv (motivic development), or purely as reference material?
- Do we handle AABA form explicitly, or treat the changes as a flat sequence?

---

## Phase 2 — Style Grammar Induction

### Goal
Given a corpus of transcribed solos by a target player, produce a grammar — a set of weighted production rules — that captures their rhythmic tendencies and note-type preferences. This grammar is used in Phase 3 to generate a typed rhythm skeleton before pitches are filled in.

### Resources

**Corpus: Weimar Jazz Database**
456 jazz solos fully transcribed and annotated at the note level, including beat position, metric weight, and harmonic context for every note. Covers canonical players (Charlie Parker, Miles Davis, John Coltrane, Bill Evans, etc.). Available in SQLite format, directly queryable in Python.

**Grammar tools:**
- `nltk.grammar.PCFG` — probabilistic CFG representation, sampling, and induction
- `numpy` — Markov transition matrix construction as a simpler baseline
- Plain weighted dicts — for a transparent, SC-friendly representation

**Grammar alphabet — typed rhythmic events:**
```
C♩  = chord tone, quarter note
C♪  = chord tone, 8th note
L♩  = color tone, quarter note
L♪  = color tone, 8th note
S♩  = scale tone, quarter note
S♪  = scale tone, 8th note
A♪  = approach tone, 8th note
R♩  = rest, quarter note
R♪  = rest, 8th note
X♩  = any note, quarter note  (used for "outside" passages)
```

### Key deliverables

**2a. Corpus ingestion pipeline**
Reads the Weimar Jazz Database SQLite file, aligns each solo note against its chord context (via music21), and produces a labeled sequence of `(beat_position, note_type, duration_class)` tuples per phrase.

**2b. Phrase segmenter**
Divides solos into phrase units (typically 1–2 bars) based on rest positions and phrase-boundary heuristics. Defines the granularity at which the grammar operates.

**2c. Grammar inducer** — two options in increasing complexity:

*Baseline — Markov chain:*
Build a transition matrix over `(note_type, duration_class)` states from the labeled sequences. Fast to implement, easy to inspect, decent results with small corpora.

*Full — PCFG induction:*
Use MLE rule counting (or inside-outside for a more principled estimate) to produce a context-free grammar over phrase-level structures. More structured than Markov; captures hierarchical phrase shape; maps cleanly onto SC Patterns.

**2d. Grammar serializer**
Writes the induced grammar to a format SuperCollider can consume. Two options:
- JSON file of rules + weights — SC reads at startup and converts to nested `Pwrand`/`Pseq` patterns
- Directly emit SC Pattern code as a `.scd` file

**2e. Hand-crafted grammar library**
A small library of manually designed grammars for canonical styles (bebop, modal, post-bop), independent of corpus induction. Serves as:
- Baseline for comparison with induced grammars
- Fallback when corpus data is sparse
- Sanity check that the grammar executor works correctly

### Open questions
- How many solos constitute a usable corpus for a single player? Parker has ~50 solos in Weimar; a less-documented player might have 5.
- Single grammar per player, or a mixture (e.g. "Parker over rhythm changes" vs "Parker over ballads")?
- Should the grammar encode intervallic tendencies (specific interval patterns), or keep pitch selection entirely in Phase 3?

---

## Phase 3 — Improv Generation ✓ DONE

### Goal
Given a chord timeline (from Phase 1 via OSC) and a loaded player grammar, generate a musically coherent improvised solo as a sequence of `(pitch_midi, duration, velocity)` triples, output as MIDI to Reaper via JACK.

### Design decisions (resolved)
- **Grammar source:** Impro-Visor's hand-crafted `.grammar` files (probabilistic CFG, S-expression format). 85 files included in `data/grammars/`. Initial target: Lester Young (182KB, 1041 rules).
- **Pre-generation:** The entire solo is expanded before playback (offline within SC), matching Impro-Visor's behavior. Simpler, debuggable, and avoids latency at phrase boundaries.
- **Brick matching:** BRICK rules selected by duration only, not by harmonic type matching to roadmap. Note type annotations (C/L/S/A/X/R) already encode harmonic appropriateness.
- **Pipeline:** Python converts `.grammar` S-expressions to JSON → SC loads JSON → SC expands grammar → resolves pitches → plays MIDI.

### Architecture

```
Python side:                         SuperCollider side:
.grammar ──→ converter ──→ .json     .json ──→ GrammarLoader
                                                    ↓
osc_bridge ──→ OSC ──→ TradFourReceiver    GrammarExpander
                                                    ↓
                                            PitchResolver
                                                    ↓
                                          TradFourPlayer ──→ MIDI ──→ JACK ──→ Reaper
```

### Key deliverables

**3a. Python grammar converter** ✓ DONE (`python/grammar/converter.py`)
Converts Impro-Visor `.grammar` files to JSON for the SC engine. Reuses `sexp_parser.py` for S-expression parsing. Handles three note encoding types:
- **Simple terminals:** `C8` → `{"type": "C", "dur": 0.5}`
- **X intervals:** `(X b6 8)` → `{"type": "X", "degree": "b6", "dur": 0.5}`
- **Slope contours:** `(slope -3 -1 C8 L8 C8)` → `{"type": "slope", "start": -3, "end": -1, "notes": [...]}`

Duration parsing: subdivision-based (`beats = 4.0/N`), additive (`4+8` = 1.5 beats), divisive (`8/3` = triplet eighth). Grammar uses 120 ticks/beat (480 ticks = 1 bar in 4/4).

LesterYoung.grammar produces: 24 parameters, 7+7 P rules (BRICK + START paths), 948 BRICK rules across 50 brick types and 7 duration buckets, 2 START rules, 13 Cluster Markov transition rules, 64 Q terminal rules (8 Q0 + 56 Q1). CLI: `python -m python.grammar.converter <path>`. 46 pytest tests.

**3b. SC OSC receiver** ✓ DONE (`supercollider/TradFourReceiver.scd`)
Listens for `/trad4/meta`, `/trad4/chord`, `/trad4/done` (protocol from `osc_bridge.py`). Parses CSV pitch class strings back to SC arrays. Stores chord timeline in `~trad4` environment. Fires `~trad4[\onDone]` callback on completion.

**3c. SC grammar loader** ✓ DONE (`supercollider/GrammarLoader.scd`)
Loads JSON via SC's `String.parseYAML`. Parses all rule types into SC-native data structures stored in `~grammar`. Includes `~grammarLoader.weightedChoose(rules)` for probabilistic rule selection.

**3d. SC grammar expander** ✓ DONE (`supercollider/GrammarExpander.scd`)
Recursive expansion from start symbol P. Two expansion paths:
- **P → BRICK:** choose a BRICK rule by matching duration, emit its note sequence
- **P → START → Cluster → Q:** enter 2-state Markov chain (Cluster0/1 with transition states like Cluster0to1, Cluster1to1to0, etc.), each step emits a Q0 or Q1 terminal note sequence

Output: flat array of typed note events ready for pitch resolution.

**3e. SC pitch resolver** ✓ DONE (`supercollider/PitchResolver.scd`)
Maps typed note events to MIDI pitches using the current chord's pitch class sets:

| Type | Source pool | Strategy |
|------|------------|----------|
| C, H | `chord_tones` | Proximity to previous pitch |
| L | `color_tones` (fallback: `scale_tones`) | Proximity |
| S | `scale_tones` | Proximity |
| A | chromatic half-step to nearest chord tone | Direction-aware |
| X | scale degree → semitone offset from root | `degreeToSemitones` lookup |
| R | rest (nil) | — |

Slope events are flattened to their component notes before resolution. All pitches clamped to `min_pitch`..`max_pitch` from grammar parameters (58–82 for Lester Young = Bb3–Bb5).

**3f. SC playback engine** ✓ DONE (`supercollider/TradFourPlayer.scd`)
Uses `~tradFourClock` (from MIDISyncSetup) for tempo. MIDI output via `MIDIOut` → JACK virtual port → Reaper. Two playback modes: `play` (full solo) and `playTrading` (alternating computer/human phrases). Walks pre-generated note sequence, scheduling `noteOn`/`noteOff` pairs with 90% sustain / 10% gap for natural articulation. Velocity varies by note type (C=90, X=80, L=75, S=70, A=65). Fires `~tradFour[\onStatus]` callbacks for GUI status updates.

**3g. SC main launcher** ✓ DONE (`supercollider/main.scd`)
Loads all SC modules, initializes MIDI sync and output, loads grammar JSON, starts OSC listener, loads GUI. On `/trad4/done`, auto-generates and plays solo. Main controller `~tradFour` dispatches to full solo or trading mode based on `tradingMode` flag. Provides `~tradFour[\generate]` (replay with new random seed) and `~tradFour[\stop]`.

**3h. MIDI sync (Reaper as master)** ✓ DONE (`supercollider/MIDISyncSetup.scd`)
Uses ddwMIDI Quark's `MIDISyncClock` to receive MIDI clock from Reaper (F8 ticks, FA start, FC stop). Stores clock in `~tradFourClock` for use by TradFourPlayer. Fallback: `useMIDISync: false` creates a standalone `TempoClock`. Prerequisite: `Quarks.install("ddwMIDI")`.

**3i. Trading bars** ✓ DONE (in `main.scd` + `TradFourPlayer.scd`)
"Trading fours" mode: computer and human alternate N-bar turns (2, 4, or 8 bars). Each computer turn is an independently generated phrase with its own melodic arc — not a fragment of a longer solo. Configurable: `tradingBars` (default 4), `humanFirst` (who starts). Chord timeline is windowed per turn so the pitch resolver sees only the chords for that bar range.

**3j. GUI** ✓ DONE (`supercollider/TradFourGUI.scd`)
Minimalist Qt GUI: grammar dropdown (auto-populated from `grammars/*.json`), lead sheet file browser + Send button (runs Python pipeline via `unixCmd`), trading controls (bars: 2/4/8, human first, trading mode checkboxes), action buttons (Generate, Reseed, Stop), and live status display (current action, tune name + key, tempo from clock updated via `SkipJack`).

**Key detection fix** ✓ DONE (in `python/leadsheet/tonal_areas.py` + `osc_bridge.py`)
Replaced music21's Krumhansl-Schmuckler key inference with `majority_key()` — uses the KeySpan with the longest duration from the roadmap CYK analysis. Fixes relative minor confusion (e.g. Bye Bye Blackbird: was "g minor", now correctly "F Major").

### Open questions (deferred)
- Brick type matching: select BRICK rules not just by duration but by matching against the roadmap's detected brick type at that position
- Phrase shape: manage higher-level contour arc across the solo
- Active trading: listen to a human player and respond in real time (currently pre-generated turns)
- Form awareness: handle AABA repeats explicitly vs. flat sequence

---

## Summary Table

| Phase | What | Where | Key resource | Status |
|---|---|---|---|---|
| 1a | Lead sheet parsing | Python | Impro-Visor .ls format | ✓ Done |
| 1b prep | Chord symbol normalizer | Python | music21 | ✓ Done (832/832) |
| 1b | Harmonic annotator | Python | music21 | ✓ Done |
| 1b-roadmap | CYK brick parser + KeySpan aggregation | Python | My.dictionary | ✓ Done |
| 1c | Note function classifier | Python | music21 | ✓ Done |
| 1d | OSC broadcaster | Python | python-osc | ✓ Done |
| 2a–2b | Corpus ingestion + segmentation | Python | Weimar Jazz DB | TODO |
| 2c | Grammar induction | Python | nltk / numpy | TODO |
| 2d | Grammar serializer → SC | Python | JSON / .scd | TODO |
| 2e | Hand-crafted grammar library | SC | Patterns | TODO |
| 3a | Grammar converter (.grammar → JSON) | Python | sexp_parser | ✓ Done |
| 3b | OSC chord receiver | SC | OSCFunc | ✓ Done |
| 3c | Grammar loader (JSON → SC) | SC | parseYAML | ✓ Done |
| 3d | Grammar expander (P → notes) | SC | recursive expansion | ✓ Done |
| 3e | Pitch resolver (types → MIDI) | SC | proximity voice leading | ✓ Done |
| 3f | MIDI playback engine | SC → JACK → Reaper | MIDIOut + ~tradFourClock | ✓ Done |
| 3g | Main launcher + integration | SC | all modules | ✓ Done |
| 3h | MIDI sync (Reaper master) | SC | ddwMIDI MIDISyncClock | ✓ Done |
| 3i | Trading bars | SC | independent phrase generation | ✓ Done |
| 3j | GUI | SC | Qt (Window, PopUpMenu, etc.) | ✓ Done |

---

## Current State of the Project

### What is done

**Phase 1 — Lead Sheet Interpretation** (all sub-steps complete)
- `parser.py` — Impro-Visor `.ls` parser, 100% pass rate across 2600+ corpus files
- `chord_preprocessor.py` — music21 symbol normalizer, 832/832 corpus symbols
- `annotator.py` — harmonic annotation (chord/color/scale tones, scale name) + note function classifier (C/L/S/A/X/NC)
- `tonal_areas.py` — KeySpan→ChordEvent tonal area mapping via roadmap CYK analysis
- `osc_bridge.py` — OSC batch dump to SC (/trad4/meta, /trad4/chord, /trad4/done). 18 unit tests.
- `python/roadmap/` — full CYK brick parser (818 brick variants, DP min-cost extraction, KeySpan aggregation)

**Phase 3 — SuperCollider Improvisation Engine** (all sub-steps complete)
- `python/grammar/converter.py` — `.grammar` S-exp → JSON converter. Handles 3 note encodings (simple, X-interval, slope). 46 pytest tests. LesterYoung grammar: 24 params, 948 BRICK rules, 50 types, 7 duration buckets.
- `supercollider/TradFourReceiver.scd` — OSC chord timeline receiver, CSV→Array parsing
- `supercollider/GrammarLoader.scd` — JSON grammar loader with `weightedChoose` helper
- `supercollider/GrammarExpander.scd` — recursive grammar expansion (BRICK + START→Cluster→Q paths)
- `supercollider/PitchResolver.scd` — note type → MIDI pitch resolution with proximity voice leading
- `supercollider/TradFourPlayer.scd` — MIDIOut playback (full solo + trading bars), uses `~tradFourClock`
- `supercollider/MIDISyncSetup.scd` — MIDI clock sync (Reaper master) via ddwMIDI, standalone fallback
- `supercollider/TradFourGUI.scd` — Qt GUI: grammar selector, lead sheet loader, trading controls, status
- `supercollider/main.scd` — integration launcher with trading bars, MIDI sync, GUI, auto-generate
- Key detection fix: `majority_key()` in `tonal_areas.py` replaces music21's Krumhansl-Schmuckler

### What is next

**Phase 2 — Style grammar induction:** corpus ingestion from Weimar Jazz DB, phrase segmentation, grammar induction (Markov or PCFG), serialization to JSON. This will supplement or replace the hand-crafted Impro-Visor grammars used in Phase 3.

### What is not yet started

Phases 2a–2e (corpus ingestion, phrase segmenter, grammar inducer, serializer, hand-crafted grammar library).

---

## Repository Structure

```
trad-four/
├── README.md
├── python/
│   ├── config.py                      # centralized data path constants ✓
│   ├── leadsheet/
│   │   ├── parser.py                  # Phase 1a — Impro-Visor .ls parser ✓
│   │   ├── chord_preprocessor.py      # Phase 1b prep — music21 symbol normalizer ✓
│   │   ├── annotator.py               # Phase 1b/1c — harmonic annotation + note_function() ✓
│   │   ├── tonal_areas.py             # Phase 1b — KeySpan→ChordEvent tonal area mapping ✓
│   │   └── osc_bridge.py              # Phase 1d — OSC broadcaster ✓
│   ├── roadmap/                       # Phase 1b-roadmap — CYK brick parser ✓
│   │   ├── sexp_parser.py             # S-expression tokenizer/parser ✓
│   │   ├── chord_block.py             # terminal symbol ✓
│   │   ├── equivalence.py             # EquivalenceDictionary + SubstitutionDictionary ✓
│   │   ├── brick.py                   # non-terminal symbol ✓
│   │   ├── brick_library.py           # loads My.dictionary, 818 variants ✓
│   │   ├── productions.py             # UnaryProduction, BinaryProduction ✓
│   │   ├── cyk_parser.py              # CYK table fill + solution extraction ✓
│   │   └── post_processor.py          # KeySpan aggregation ✓
│   ├── grammar/
│   │   ├── converter.py               # Phase 3a — .grammar S-exp → JSON converter ✓
│   │   ├── ingestion.py               # Phase 2a — Weimar DB corpus reader (TODO)
│   │   ├── segmenter.py               # Phase 2b — phrase segmenter (TODO)
│   │   ├── inducer.py                 # Phase 2c — grammar induction (TODO)
│   │   └── serializer.py              # Phase 2d — JSON / .scd export (TODO)
│   ├── tests/
│   │   ├── conftest.py                # shared session-scoped fixtures (BrickLibrary) ✓
│   │   ├── test_parser.py             # corpus-wide parser tests ✓
│   │   ├── test_music21_chords.py     # music21 symbol compatibility tests ✓
│   │   ├── test_roadmap_units.py      # roadmap module unit tests ✓
│   │   ├── test_post_processor.py     # CYK + KeySpan integration tests ✓
│   │   ├── test_tonal_integration.py  # KeySpan→ChordEvent mapping tests ✓
│   │   ├── test_note_function.py      # C/L/S/A/X classification tests ✓
│   │   ├── test_osc_bridge.py         # OSC broadcaster tests ✓
│   │   └── test_grammar_converter.py  # grammar converter tests (46 tests) ✓
│   └── requirements.txt
├── supercollider/
│   ├── main.scd                       # Phase 3g — integration launcher ✓
│   ├── MIDISyncSetup.scd             # Phase 3h — MIDI clock sync (Reaper master) ✓
│   ├── TradFourReceiver.scd           # Phase 3b — OSC chord timeline receiver ✓
│   ├── GrammarLoader.scd              # Phase 3c — JSON grammar loader ✓
│   ├── GrammarExpander.scd            # Phase 3d — recursive grammar expansion ✓
│   ├── PitchResolver.scd              # Phase 3e — note type → MIDI pitch ✓
│   ├── TradFourPlayer.scd             # Phase 3f — MIDI playback (full + trading) ✓
│   ├── TradFourGUI.scd               # Phase 3j — Qt GUI ✓
│   └── grammars/
│       └── LesterYoung.json           # converted grammar (948 BRICK rules) ✓
├── data/
│   ├── grammars/                      # Impro-Visor .grammar files (85 players) ✓
│   ├── leadsheets/                    # Impro-Visor .ls files (2614 jazz standards) ✓
│   ├── vocab/                         # My.dictionary + My.substitutions ✓
│   ├── weimar/                        # Weimar Jazz Database SQLite (TODO)
│   └── chord_symbols.txt              # unique chord vocabulary extracted from corpus ✓
└── docs/
    └── Trad-four-plan.md              # this document
```

### Audio signal chain (Linux/Arch)

```
SuperCollider
  └─ MIDIOut → JACK virtual MIDI port
                    └─ Reaper MIDI input track
                              ├─ Track 1: improv melody → VSTi (sampled instrument)
                              └─ Track 2: rhythm section (pre-recorded audio or MIDI)
```

**Required tools:** JACK2, `a2jmidid` (ALSA↔JACK MIDI bridge if needed), Reaper, a sampled jazz instrument VSTi (e.g. Kontakt + a jazz piano library, or sforzando + a free jazz soundfont).
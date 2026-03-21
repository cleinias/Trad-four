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
- **Impro-Visor imaginary-book** — 2600+ jazz standards in `.ls` format, directly on disk at `/usr/share/impro-visor/leadsheets/imaginary-book/`. Primary lead sheet source.
- **`My.dictionary` + `My.substitutions`** — Impro-Visor's brick grammar and chord equivalence rules, used by the roadmap module.

### Key deliverables

**1a. Lead sheet parser** ✓ DONE
Reads Impro-Visor `.ls` files and produces a Python `LeadSheet` object:
- Time signature, key signature (raw), tempo
- Chord timeline: list of `ChordEvent(bar, beat, symbol, duration_beats)`
- Handles `/` repeats, `NC` (no chord), slash chords, all meters
- 2600+ file corpus passes 100% with no warnings

**1b. Harmonic annotator** — IN PROGRESS
For each chord in the timeline, computes and caches:
- Root, quality (via `chord_preprocessor.py` — 832/832 corpus symbols passing music21)
- Chord tones (R, 3, 5, 7), color tones (extensions), scale tones
- Per-chord scale using resolution-aware lookahead (`annotator.py`)
- **Tonal area** — which key center is active at each bar (`tonal_areas.py`, see below)

**1b-roadmap. Tonal area detection** — IN PROGRESS
Identifies the key center (tonal area) active at each point in the lead sheet using Impro-Visor's brick grammar. This is architecturally separate from per-chord scale selection and operates at a higher level of musical abstraction.

**Strategy:** Reimplement Impro-Visor's roadmap analysis in Python. The Java system uses a CYK (Cocke-Younger-Kasami) parser over a recursive context-free grammar defined in `My.dictionary`. Each matched "brick" (harmonic idiom) carries a key center, and the `PostProcessor.findKeys()` method aggregates brick keys into contiguous `KeySpan` objects.

**Pipeline:**
```
My.dictionary + My.substitutions
      ↓  sexp_parser.py    — parse S-expression files
      ↓  brick_library.py  — build recursive brick grammar
                             (equiv rules, diatonic rules, defbrick definitions)
                             auto-generates Overrun + Dropback for Cadence bricks
      ↓  productions.py    — convert bricks to CYK grammar rules
                             (UnaryProduction, BinaryProduction, binarization)
      ↓  cyk_parser.py     — CYK bottom-up table fill + min-cost solution
      ↓  post_processor.py — aggregate brick keys into KeySpan tonal areas
      ↓
ChordEvent.tonal_area  — music21 Key object
ChordEvent.tonal_area_type — 'diatonic' | 'sequential' | 'passing'
ChordEvent.tonal_area_scale — frozenset of pitch classes
```

**Current status of roadmap module (`python/roadmap/`):**
- `sexp_parser.py` ✓ — tokenizes and parses Impro-Visor S-expression files
- `chord_block.py` ✓ — terminal symbol with family classification and transposition
- `equivalence.py` ✓ — bidirectional equivalence classes + substitution rules
- `brick.py` ✓ — non-terminal with flatten/transpose/resolve operations
- `brick_library.py` ✓ — loads My.dictionary, 818 brick variants, auto Overrun/Dropback
- `productions.py` ✓ — UnaryProduction, BinaryProduction, binarization; chordDiff-based transposition-aware matching
- `cyk_parser.py` — partially working; 2-chord cadences correct, 3-chord cadences mostly correct, key propagation has remaining bugs

**Known remaining issues in `cyk_parser.py`:**
1. 3-chord cadences sometimes detect wrong brick when multiple valid matches exist at equal cost — type cost system implemented but needs tuning
2. `iiø-V-i` (minor ii-V-I) detected as two separate bricks instead of one `Sad Cadence` — overlap brick mechanism
3. Key propagation for F major and non-C keys: bricks detected correctly but key=C instead of key=F
4. `post_processor.py` not yet written — KeySpan aggregation pending

**1c. Note function classifier**
Given any MIDI pitch and the current chord + tonal area, returns its functional label:
`C` (chord tone), `L` (color tone), `S` (scale tone), `A` (approach), `X` (outside).

**1d. OSC broadcaster**
- At startup: sends chord timeline + tonal area map to SuperCollider
- During playback: answers real-time note-function queries from SC

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

## Phase 3 — Improv Generation

### Goal
Given a live chord timeline (from Phase 1 via OSC) and a loaded player grammar (from Phase 2), generate in real time a musically coherent N-bar improv phrase as a sequence of `(pitch_midi, duration, velocity)` triples.

### Resources
- **SuperCollider** — Patterns library (`Pbind`, `Pwrand`, `Pseq`, `Pdef`) for grammar execution and real-time generation. MIDI output via `MIDIOut` to a JACK virtual port. Prototype already implemented for Bye Bye Blackbird.
- **Python via OSC** — for note-function classification queries better handled by music21 than reimplemented in SC.
- **JACK** — low-latency MIDI routing from SC to Reaper on Linux (Arch). Tool: `a2jmidid` to bridge ALSA MIDI and JACK MIDI if needed.
- **Reaper** — receives MIDI stream on a dedicated track, plays through a sampled instrument VSTi (e.g. Kontakt, sforzando + a jazz piano soundfont). A separate synchronized track carries the rhythm section.

### Key deliverables

**3a. Grammar executor**
Loads the Phase 2 grammar and expands it into a typed rhythm skeleton for the current phrase. Implemented as nested SC Patterns:
```supercollider
// A production rule like:
//   Phrase → (0.6) ChordToneRun | (0.4) ScalarLine
// becomes:
~Phrase = Pwrand([~ChordToneRun, ~ScalarLine], [0.6, 0.4], 1);
```

**3b. Pitch filler** (extends current `~pickNote`)
Takes the typed skeleton and the current chord, selects actual MIDI pitches:
- `C` — weighted toward root, 3rd, 5th, 7th
- `L` — tensions appropriate to chord quality (b9, #11, 13, etc.)
- `S` — full scale, contour-weighted
- `A` — chromatic or diatonic neighbor of the next chord tone
- Contour memory: tracks recent interval direction to prevent random-walk behavior

**3c. Phrase shape controller**
Manages higher-level structure across multiple bars:
- Phrase arc: beginning / peak / resolution
- Avoids uniform rhythmic density throughout
- Respects the N-bar trading boundary

**3d. MIDI output and articulation model**
Converts the generated (pitch, duration, velocity) sequence to MIDI events via SC's `MIDIOut` class, sent to a JACK virtual port that Reaper subscribes to:
- Chord tones on strong beats: higher velocity (e.g. 90–110)
- Approach tones: softer (e.g. 60–75)
- Rests: explicit MIDI note-off, no filler
- Note duration mapped to MIDI note-on/note-off timing with legato control

**3e. Transport and form manager**
Handles AABA or other form; tracks bar position; generates the next phrase slightly before the current one ends to avoid latency at phrase boundaries (cf. Impro-Visor's `lead` parameter).

### Open questions
- Generate one full phrase ahead of time (offline within SC) then play it, or generate note-by-note in real time? Offline is simpler; real-time enables reactive playing.
- Autonomous generation only, or active trading (SC listens to human player and responds)?

---

## Summary Table

| Phase | What | Where | Key resource | Status |
|---|---|---|---|---|
| 1a | Lead sheet parsing | Python | Impro-Visor .ls format | ✓ Done |
| 1b prep | Chord symbol normalizer | Python | music21 | ✓ Done (832/832) |
| 1b | Harmonic annotator | Python | music21 | WIP |
| 1b-roadmap | CYK brick parser | Python | My.dictionary | WIP (see below) |
| 1c | Note function classifier | Python | music21 | TODO |
| 1d | OSC broadcaster | Python | python-osc | TODO |
| 2a–2b | Corpus ingestion + segmentation | Python | Weimar Jazz DB | TODO |
| 2c | Grammar induction | Python | nltk / numpy | TODO |
| 2d | Grammar serializer → SC | Python | JSON / .scd | TODO |
| 2e | Hand-crafted grammar library | SC | Patterns | TODO |
| 3a | Grammar executor | SC | Patterns | TODO |
| 3b | Pitch filler | SC + Python OSC | extended `~pickNote` | TODO |
| 3c | Phrase shape controller | SC | Patterns + TempoClock | TODO |
| 3d | MIDI output + articulation | SC → JACK → Reaper | MIDIOut + VSTi | TODO |
| 3e | Transport and form manager | SC + Reaper | TempoClock + JACK transport | TODO |

---

## Current State of the Project

### What is done

**Phase 1a — Lead sheet parser** (`python/leadsheet/parser.py`)
Parses Impro-Visor `.ls` files into `LeadSheet` objects with full `ChordEvent` timelines. Handles all meters, slash chords, NC tokens, repeat bars. 100% pass rate across 2600+ corpus files.

**Phase 1b prep — Chord preprocessor** (`python/leadsheet/chord_preprocessor.py`)
Normalizes Impro-Visor chord symbols to music21-compatible figure strings. Handles flat-root parsing bug, unsupported quality abbreviations (`7alt`, `maj9`, `m69` etc.). 832/832 corpus symbols passing music21.

**Harmonic annotator** (`python/leadsheet/annotator.py`)
Annotates each `ChordEvent` with music21 `ChordSymbol`, chord tones, color tones, scale tones, and scale name. Uses resolution-aware lookahead for dominant chords (e.g. `D7→Gm7` gets `hw_diminished`, `C7→FM7` gets `mixolydian`).

**Roadmap module** (`python/roadmap/`) — partial
Reimplements Impro-Visor's CYK-based harmonic analysis in Python:
- `sexp_parser.py` — S-expression parser for `.dictionary` files
- `chord_block.py` — terminal symbol with family classification
- `equivalence.py` — bidirectional chord equivalence + substitution
- `brick.py` — recursive harmonic pattern (non-terminal)
- `brick_library.py` — loads My.dictionary, 818 brick variants
- `productions.py` — CYK grammar rules with transposition-aware matching
- `cyk_parser.py` — CYK parser, partially working

### What is in progress

**`cyk_parser.py`** — three known bugs remain:
1. 3-chord cadences occasionally pick wrong brick (e.g. `Happenstance Cadence` instead of `Straight Cadence`) when multiple matches have equal cost
2. Minor ii-V-i detected as two overlapping bricks instead of one `Sad Cadence`
3. Key propagation for non-C keys partially broken — some bricks return key=C instead of actual key

**Next immediate task:** fix these three bugs in `cyk_parser.py`, then write `post_processor.py` to aggregate brick keys into `KeySpan` tonal areas (mirrors `PostProcessor.findKeys()` in Impro-Visor Java).

### What is not yet started

Phases 1c, 1d, 2a–2d, 2e, 3a–3e.

---

## Repository Structure (proposed)

```
trad-four/
├── README.md
├── python/
│   ├── leadsheet/
│   │   ├── parser.py              # Phase 1a — Impro-Visor .ls parser ✓
│   │   ├── chord_preprocessor.py  # Phase 1b prep — music21 symbol normalizer ✓
│   │   ├── annotator.py           # Phase 1b — harmonic annotation (WIP)
│   │   ├── tonal_areas.py         # Phase 1b — Roman numeral tonal area (superseded)
│   │   ├── classifier.py          # Phase 1c — note function classifier
│   │   └── osc_bridge.py          # Phase 1d — OSC broadcaster
│   ├── roadmap/                   # Phase 1b-roadmap — CYK brick parser
│   │   ├── __init__.py
│   │   ├── sexp_parser.py         # S-expression tokenizer/parser ✓
│   │   ├── chord_block.py         # terminal symbol ✓
│   │   ├── equivalence.py         # EquivalenceDictionary + SubstitutionDictionary ✓
│   │   ├── brick.py               # non-terminal symbol ✓
│   │   ├── brick_library.py       # loads My.dictionary, 818 variants ✓
│   │   ├── productions.py         # UnaryProduction, BinaryProduction ✓
│   │   ├── cyk_parser.py          # CYK table fill + solution extraction (WIP)
│   │   └── post_processor.py      # KeySpan aggregation (TODO)
│   ├── grammar/
│   │   ├── ingestion.py           # Phase 2a — Weimar DB corpus reader
│   │   ├── segmenter.py           # Phase 2b — phrase segmenter
│   │   ├── inducer.py             # Phase 2c — grammar induction
│   │   └── serializer.py          # Phase 2d — JSON / .scd export
│   ├── tests/
│   │   ├── test_parser.py         # corpus-wide parser tests ✓
│   │   └── test_music21_chords.py # music21 symbol compatibility tests ✓
│   └── requirements.txt
├── supercollider/
│   ├── trad_four_prototype.scd    # current prototype (Bye Bye Blackbird test case)
│   ├── grammar_executor.scd       # Phase 3a
│   ├── pitch_filler.scd           # Phase 3b
│   ├── phrase_shape.scd           # Phase 3c
│   ├── midi_out.scd               # Phase 3d — MIDI output via JACK to Reaper
│   ├── transport.scd              # Phase 3e
│   └── grammars/                  # Phase 2e — hand-crafted grammars
│       ├── bebop.scd
│       ├── modal.scd
│       └── post_bop.scd
├── data/
│   ├── leadsheets/                # Impro-Visor .ls files (from imaginary-book)
│   ├── weimar/                    # Weimar Jazz Database SQLite
│   └── chord_symbols.txt          # unique chord vocabulary extracted from corpus ✓
└── docs/
    ├── plan.md                    # this document
    ├── literature_review.md       # survey of algorithmic jazz improvisation research
    └── related_projects.md        # survey of reusable softwar2e (dicy2, roadmap_parser, etc.)
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
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
Given a lead sheet as input, produce a structured runtime object that the improv engine can query: *"at beat 3 of bar 7, what chord is playing, what are its chord tones, what scale applies, and what is the melodic note?"*

### Resources
- **`music21`** (MIT, actively maintained) — MusicXML parsing, chord symbol interpretation, scale selection, note function classification, key/time signature metadata. Can dynamically answer "is MIDI note 62 a chord tone over Gm7?" for any chord.
- **`pretty_midi`** — fallback for ingesting MIDI representations of lead sheets.
- **iRealPro** — MusicXML exports of chord changes for 3000+ jazz standards; directly readable by music21.

### Key deliverables

**1a. Lead sheet parser**
Reads a MusicXML or iRealPro file and produces a Python data structure:
- Time signature, key signature, tempo
- Chord timeline: list of `(bar, beat, chord_symbol, duration_in_beats)`
- Melody timeline: list of `(bar, beat, pitch_midi, duration_in_beats)`

**1b. Harmonic annotator**
For each chord in the timeline, computes and caches:
- Root, quality, extensions
- Chord tones (R, 3, 5, 7)
- Color tones (tensions: 9, 11, 13 and their alterations)
- Associated scale (Dorian, Mixolydian, Lydian dominant, Locrian #2, etc.)
- Full MIDI note pool for a given register

**1c. Note function classifier**
Given any MIDI pitch and the current chord, returns its functional label:
- `C` — chord tone
- `L` — color/tension tone
- `S` — scale tone
- `A` — chromatic or diatonic approach tone
- `X` — outside/chromatic

This is the primary runtime query interface for Phase 3.

**1d. OSC broadcaster**
- At startup: sends the full chord timeline to SuperCollider
- During playback: answers real-time note-function queries from SC

### Open questions
- Do we treat the melody as a constraint on the improv (motivic development), or purely as reference material? This significantly affects 1b.
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

| Phase | What | Where | Key resource | Main risk |
|---|---|---|---|---|
| 1a–1b | Lead sheet parsing + harmonic annotation | Python | music21 + Impro-Visor .ls | music21 learning curve |
| 1c | Note function classifier | Python | music21 | edge cases in altered chords |
| 1d | OSC broadcaster | Python | python-osc | latency / timing sync |
| 2a–2b | Corpus ingestion + phrase segmentation | Python | Weimar Jazz DB | phrase boundary heuristics |
| 2c | Grammar induction | Python | nltk / numpy | sparse data for rare players |
| 2d | Grammar serializer → SC | Python | JSON / .scd | format design |
| 2e | Hand-crafted grammar library | SC | Patterns | musical quality |
| 3a | Grammar executor | SC | Patterns | CFG → Pattern mapping |
| 3b | Pitch filler | SC + Python OSC | extended `~pickNote` | contour / musical coherence |
| 3c | Phrase shape controller | SC | Patterns + TempoClock | real-time reliability |
| 3d | MIDI output + articulation | SC → JACK → Reaper | MIDIOut + VSTi | JACK routing / latency |
| 3e | Transport and form manager | SC + Reaper | TempoClock + JACK transport | tempo sync |

---

## Suggested Build Order

Rather than building phases strictly sequentially, this order minimises time to first audible result and keeps each step independently testable:

1. **Phase 1a–1b** — lead sheet parser and harmonic annotator. Establishes the data model everything else depends on.
2. **Phase 3b** — pitch filler upgrade using hardcoded theory. Immediately improves the existing SC prototype.
3. **Phase 2e** — hand-crafted grammar in SC Patterns. Gives a working end-to-end system quickly.
4. **Phase 1c + 1d** — OSC bridge. Replaces the hardcoded chord dictionary with live music21 queries.
5. **Phase 2a–2d** — full grammar induction from Weimar corpus. The most ambitious piece; tackled once the rest works.
6. **Phase 3c–3e** — phrase shape, articulation, and transport polish.

Steps 1–3 produce a system that plays music. Steps 4–6 make it progressively more musically intelligent.

---

## Current Prototype Status

A working SuperCollider prototype exists for **Bye Bye Blackbird** (F major, 32-bar AABA) implementing a simplified version of Phase 3:

- Hardcoded chord → scale dictionary (`~scaleLib`, `~chordMap`)
- Hybrid pitch filler (`~pickNote`) with chord-tone / scale-tone weighting and contour memory
- Swing 8th rhythm cells with probabilistic selection (`Pwrand`)
- Simple additive sine SynthDef (`\jazzTone`) — **to be replaced by MIDI output to Reaper**
- Full 32-bar chord timeline (`~changes`)

This prototype lives at `supercollider/trad_four_prototype.scd` and corresponds roughly to **Phase 3b + 2e (partial)**, without the Python layer or OSC bridge. It serves as the execution scaffold into which Phase 1 and Phase 2 outputs will be integrated.

---

## Repository Structure (proposed)

```
trad-four/
├── README.md
├── python/
│   ├── leadsheet/
│   │   ├── parser.py              # Phase 1a — Impro-Visor .ls parser ✓
│   │   ├── chord_preprocessor.py  # Phase 1b prep — music21 symbol normalizer ✓
│   │   ├── annotator.py           # Phase 1b — harmonic annotation
│   │   ├── classifier.py          # Phase 1c — note function classifier
│   │   └── osc_bridge.py          # Phase 1d — OSC broadcaster
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
    └── plan.md                    # this document
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

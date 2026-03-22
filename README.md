# Trad-Four

A computational jazz improvisation system that generates melodic lines over a given harmonic structure, in the style of a target player, heavily borrowing from Bob Keller's [impro-visor](https://www.impro-visor.com)'s approach to solos' construction.

The name refers to the jazz practice of "trading fours" — alternating 4-bar phrases between two players.

## What it does

Given a lead sheet and a player grammar, Trad-Four generates an improvised melodic line that respects the harmonic structure of the tune and reflects the rhythmic and melodic tendencies of the target player. The generated line is output as a MIDI stream into a DAW (Reaper), where it plays through a sampled instrument alongside a rhythm section.

## Architecture

```
Lead sheet (.ls)  +  Player grammar (.grammar)
        |                        |
        v                        v
  Phase 1 (Python)         Phase 3a (Python)
  Harmonic analysis        Grammar converter (.grammar -> .json)
        |                        |
        | OSC                    | JSON file
        v                        v
             Phase 3 (SuperCollider)
             Grammar expansion + pitch resolution
                     | MIDI via JACK
                     v
                  Reaper
         Track 1: melody (VSTi)
         Track 2: rhythm section
```

- **Phase 1** (Python) — parses Impro-Visor `.ls` leadsheet files, performs CYK-based harmonic brick analysis, assigns tonal areas, classifies note functions, and broadcasts the annotated chord timeline via OSC to SuperCollider.
- **Phase 2** (Python, TODO) — will ingest transcribed solos from the Weimar Jazz Database and induce weighted context-free grammars capturing player-specific rhythmic patterns and note-type preferences.
- **Phase 3** (Python + SuperCollider) — converts Impro-Visor `.grammar` files to JSON, loads them in SuperCollider, expands the probabilistic grammar into a typed note sequence, resolves pitches against the chord timeline, and plays the result as MIDI via JACK to Reaper.

## Status

- [x] Phase 1a — Impro-Visor `.ls` leadsheet parser
- [x] Phase 1b prep — music21 chord symbol preprocessor (832/832 corpus symbols passing)
- [x] Phase 1b — harmonic annotator + CYK brick analysis + tonal areas
- [x] Phase 1c — note function classifier (C/L/S/A/X/NC)
- [x] Phase 1d — OSC bridge
- [ ] Phase 2 — grammar induction pipeline (Weimar Jazz DB corpus)
- [x] Phase 3a — grammar converter (.grammar S-exp → JSON)
- [x] Phase 3b — SC OSC chord receiver
- [x] Phase 3c — SC grammar loader
- [x] Phase 3d — SC grammar expander (BRICK + Cluster Markov chain)
- [x] Phase 3e — SC pitch resolver (note types → MIDI pitches)
- [x] Phase 3f — SC MIDI playback engine
- [x] Phase 3g — SC main launcher + integration

## Usage

Running Trad-Four requires coordinating four pieces of software: JACK (audio routing), Reaper (DAW), SuperCollider (improvisation engine), and Python (harmonic analysis + grammar conversion). Here is the full startup procedure.

### Prerequisites

**Software:**
- Python 3.10+ with dependencies (see Requirements below)
- SuperCollider (standard installation, no additional Quarks needed)
- JACK2 (`jack2` package on Arch Linux)
- Reaper (or another DAW that accepts JACK MIDI input)
- A sampled jazz instrument VSTi (e.g. Kontakt, sforzando + a jazz soundfont)

**One-time setup — convert the grammar:**
```bash
cd /path/to/trad-four
python -m python.grammar.converter LesterYoung
```
This reads `data/grammars/LesterYoung.grammar` and produces `supercollider/grammars/LesterYoung.json`. Only needs to be re-run if the grammar source changes or you want to use a different player.

### Step 1: Start JACK

```bash
# Start the JACK server (adjust parameters to your audio interface)
jackd -d alsa -r 48000 -p 256 -n 2 &

# If using PipeWire (common on modern Arch/Fedora), JACK is usually
# already available via PipeWire's JACK compatibility layer.
```

### Step 2: Start Reaper

1. Launch Reaper
2. Set audio system to JACK in Preferences → Audio → Device
3. Create a MIDI track for the improvised melody:
   - Arm the track for recording
   - Set MIDI input to "SuperCollider:out0" (will appear once SC is running)
   - Load a jazz instrument VSTi on the track (piano, saxophone, etc.)
4. Optionally add a second track for rhythm section backing (audio or MIDI)
5. Set the project tempo to match your lead sheet

### Step 3: Start SuperCollider

1. Open SuperCollider IDE
2. Boot the server: `s.boot`
3. Open and execute `supercollider/main.scd` (select all, Cmd+Enter or Ctrl+Enter)

You should see in the SC post window:
```
TradFour: all modules loaded
GrammarLoader: loaded 'LesterYoung' — 24 params, ...
TradFourPlayer: MIDI output → SuperCollider:out0

=== Trad-Four Improvisation Engine ===
  Grammar:  LesterYoung
  Pitch:    58–82
  Waiting for chord data via OSC...
```

### Step 4: Send a lead sheet from Python

From a terminal, in the project root directory:
```bash
python -m python.leadsheet.osc_bridge data/leadsheets/ByeByeBlackbird.ls
```

This runs the full Phase 1 pipeline (parse → annotate → CYK brick analysis → tonal areas) and broadcasts the chord timeline to SuperCollider via OSC. SuperCollider will automatically:
1. Receive and store the chord data
2. Expand the Lester Young grammar into a note sequence
3. Resolve note types to MIDI pitches against the chord progression
4. Play the solo via MIDI to Reaper

### Controls

In the SuperCollider IDE post window:
```supercollider
~tradFour.generate;   // generate and play a new solo (new random seed)
~tradFour.stop;       // stop playback
```

To use a different lead sheet, simply run the Python OSC bridge again with a different file — SuperCollider will receive the new chords and auto-generate a fresh solo.

### Using a different player grammar

85 player grammars are included in `data/grammars/`. To use a different one:
```bash
# Convert the grammar (just use the player name)
python -m python.grammar.converter CharlieParker

# Then in SuperCollider, reload main.scd (or modify the grammarPath variable)
```

### Troubleshooting

- **No MIDI output in Reaper:** Check that Reaper's MIDI input is set to "SuperCollider:out0" and the track is armed. Verify JACK connections with `jack_lsp` or QJackCtl.
- **OSC not received:** Ensure SuperCollider is listening on the default port (57120). Check that no firewall blocks localhost UDP.
- **Grammar conversion fails:** Check that the grammar file exists in `data/grammars/`. Run `ls data/grammars/` to see available players.

## Data

- **Leadsheets** — Impro-Visor imaginary-book `.ls` files (2600+ jazz standards). Included in the repository under `data/leadsheets/`.
- **Grammars** — Impro-Visor `.grammar` files (85 player grammars). Included in the repository under `data/grammars/`. Originally from [impro-visor.com](https://www.impro-visor.com).
- **Solo corpus** — [Weimar Jazz Database](https://jazzomat.hfm-weimar.de) (456 annotated jazz solos, SQLite format). Not yet integrated (Phase 2).

## Requirements

**Python (3.10+)**
```bash
pip install -r python/requirements.txt
```

Key dependencies: `music21`, `python-osc`, `numpy`, `nltk`, `pretty_midi`

**SuperCollider** — standard installation, no additional Quarks required.

**Audio** (Linux) — JACK2, Reaper, a sampled jazz instrument VSTi.

## Project documentation

See [`docs/Trad-four-plan.md`](docs/Trad-four-plan.md) for the full project plan including phase descriptions, data sources, architecture details, and open design questions.

## License

GPL-2.0 — consistent with Impro-Visor, whose grammar format and leadsheet vocabulary this project draws on.

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
- **Phase 3** (Python + SuperCollider) — converts Impro-Visor `.grammar` files to JSON, loads them in SuperCollider, expands the probabilistic grammar into a typed note sequence, resolves pitches against the chord timeline, and plays the result as MIDI via JACK to Reaper. Includes MIDI clock sync with Reaper (master/slave), trading bars mode, and a Qt GUI.

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
- [x] Phase 3h — MIDI sync (Reaper as master via ddwMIDI MIDISyncClock)
- [x] Phase 3i — Trading bars (independent N-bar phrase generation)
- [x] Phase 3j — Minimalist Qt GUI (grammar selector, lead sheet loader, trading controls)

## Usage

Running Trad-Four requires coordinating four pieces of software: JACK (audio routing), Reaper (DAW), SuperCollider (improvisation engine), and Python (harmonic analysis + grammar conversion). Here is the full startup procedure.

### Prerequisites

**Software:**
- Python 3.10+ with dependencies (see Requirements below)
- SuperCollider with the ddwMIDI Quark (for MIDI clock sync with Reaper)
- JACK2 (`jack2` package on Arch Linux)
- Reaper (or another DAW that accepts JACK MIDI input)
- A sampled jazz instrument VSTi (e.g. Kontakt, sforzando + a jazz soundfont)

**One-time setup — install the ddwMIDI Quark in SuperCollider:**
```supercollider
Quarks.install("ddwMIDI");
thisProcess.recompile;
```

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
3. Enable MIDI clock output: Preferences → MIDI Devices → Output → enable "Send MIDI clock to all" (this lets SC sync to Reaper's transport)
4. Create a MIDI track for the improvised melody:
   - Arm the track for recording
   - Set MIDI input to "SuperCollider:out0" (will appear once SC is running)
   - Load a jazz instrument VSTi on the track (piano, saxophone, etc.)
5. Optionally add a second track for rhythm section backing (audio or MIDI)
6. Set the project tempo to match your lead sheet

### Step 3: Start SuperCollider

1. Open SuperCollider IDE
2. Boot the server: `s.boot`
3. Open and execute `supercollider/main.scd` (select all, Cmd+Enter or Ctrl+Enter)

You should see in the SC post window:
```
TradFour: all modules loaded
GrammarLoader: loaded 'LesterYoung' — 24 params, ...
MIDISyncSetup: listening for MIDI clock from Reaper
TradFourPlayer: MIDI output initialized (port 0)

=== Trad-Four Improvisation Engine ===
  Grammar:  LesterYoung
  Pitch:    58–82
  Clock:    MIDI sync (Reaper master)
  Waiting for chord data via OSC...
```

A GUI window will also appear with controls for grammar selection, lead sheet loading, trading bars, and playback.

### Step 4: Send a lead sheet

**Option A — via the GUI:**
In the SC GUI window, click "Browse" to select a lead sheet file, then click "Send to SC". The GUI runs the Python pipeline automatically.

**Option B — from the terminal:**
```bash
python -m python.leadsheet.osc_bridge data/leadsheets/ByeByeBlackbird.ls
```

Either way, the full Phase 1 pipeline runs (parse → annotate → CYK brick analysis → tonal areas) and broadcasts the chord timeline to SuperCollider via OSC. SuperCollider will automatically:
1. Receive and store the chord data
2. Expand the Lester Young grammar into a note sequence
3. Resolve note types to MIDI pitches against the chord progression
4. Play the solo via MIDI to Reaper

### Controls

**Via the GUI** (recommended):
- **Grammar dropdown** — select a player grammar (auto-populated from `supercollider/grammars/`)
- **Generate / Reseed / Stop** buttons — generate a solo, regenerate with a new random seed, or stop playback
- **Trading mode** checkbox — enable trading bars (computer and human alternate N-bar phrases)
- **Bars dropdown** — set trading bars per turn (2, 4, or 8)
- **Human first** checkbox — who starts (computer or human)
- **Status bar** — shows current action, tune name + key, tempo (live from Reaper's MIDI clock)

**Via the SC post window:**
```supercollider
~tradFour[\generate].value(~tradFour);   // generate and play a new solo
~tradFour[\stop].value(~tradFour);       // stop playback
~tradFour[\tradingMode] = true;          // enable trading bars
~tradFour[\tradingBars] = 4;             // 4 bars per turn
~tradFour[\humanFirst] = false;          // computer goes first
```

To use a different lead sheet, send it via the GUI or run the Python OSC bridge again — SuperCollider will receive the new chords and auto-generate a fresh solo.

### Using a different player grammar

85 player grammars are included in `data/grammars/`. To use a different one:
```bash
# Convert the grammar (just use the player name)
python -m python.grammar.converter CharlieParker

# Then in SuperCollider, reload main.scd (or modify the grammarPath variable)
```

### Troubleshooting

- **No MIDI output in Reaper:** Check that Reaper's MIDI input is set to "SuperCollider:out0" and the track is armed. Verify JACK connections with `jack_lsp` or QJackCtl.
- **MIDI sync not working:** Ensure Reaper has "Send MIDI clock" enabled in Preferences → MIDI Devices → Output. Verify JACK MIDI routing from Reaper to SC. The GUI tempo display should show the BPM from Reaper. For standalone testing without Reaper, set `~midiSyncSetup[\useMIDISync] = false` before loading `main.scd`.
- **OSC not received:** Ensure SuperCollider is listening on the default port (57120). Check that no firewall blocks localhost UDP.
- **Grammar conversion fails:** Check that the grammar file exists in `data/grammars/`. Run `ls data/grammars/` to see available players.
- **ddwMIDI Quark not found:** Run `Quarks.install("ddwMIDI")` in SC, then recompile the class library (`thisProcess.recompile`).

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

**SuperCollider** — standard installation + ddwMIDI Quark (for MIDI clock sync with Reaper). Install in SC: `Quarks.install("ddwMIDI"); thisProcess.recompile;`

**Audio** (Linux) — JACK2, Reaper, a sampled jazz instrument VSTi.

## Project documentation

See [`docs/Trad-four-plan.md`](docs/Trad-four-plan.md) for the full project plan including phase descriptions, data sources, architecture details, and open design questions.

## License

GPL-2.0 — consistent with Impro-Visor, whose grammar format and leadsheet vocabulary this project draws on.

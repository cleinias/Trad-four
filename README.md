# Trad-Four

A computational jazz improvisation system that generates melodic lines over a given harmonic structure, in the style of a target player, heavily borrowing from [impro-visor](https://www.impro-visor.com)'s approach to solos' construction.

The name refers to the jazz practice of "trading fours" — alternating 4-bar phrases between two players.

## What it does

Given a lead sheet and a corpus of transcribed solos by a target player, Trad-Four generates a real-time improvised melodic line that respects the harmonic structure of the tune and reflects the rhythmic and melodic tendencies of the target player. The generated line is output as a MIDI stream into a DAW (Reaper), where it plays through a sampled instrument alongside a rhythm section.

## Architecture

```
Lead sheet (.ls)  +  Player corpus (Weimar Jazz DB)
        │                        │
        ▼                        ▼
  Phase 1 (Python)         Phase 2 (Python)
  Harmonic analysis        Style grammar induction
        │                        │
        └────────────┬───────────┘
                     │ OSC
                     ▼
             Phase 3 (SuperCollider)
             Real-time improv generation
                     │ MIDI via JACK
                     ▼
                  Reaper
         Track 1: melody (VSTi)
         Track 2: rhythm section
```

- **Phase 1** — parses Impro-Visor `.ls` leadsheet files and builds a queryable harmonic model using music21: chord tones, available tensions, and scale associations for every chord in the progression.
- **Phase 2** — ingests transcribed solos from the Weimar Jazz Database and induces a weighted context-free grammar capturing the player's rhythmic patterns and note-type preferences.
- **Phase 3** — executes the grammar in real time in SuperCollider, selects pitches from the harmonic model, and streams the result as MIDI to Reaper via JACK.

## Status

Work in progress. Current state:

- [x] Phase 1a — Impro-Visor `.ls` leadsheet parser
- [x] Phase 1b prep — music21 chord symbol preprocessor (832/832 corpus symbols passing)
- [ ] Phase 1b — harmonic annotator
- [ ] Phase 1c — note function classifier
- [ ] Phase 1d — OSC bridge
- [ ] Phase 2 — grammar induction pipeline
- [ ] Phase 3 — SuperCollider generation engine + MIDI output

A working SuperCollider prototype exists (`supercollider/trad_four_prototype.scd`) demonstrating the core generation approach over Bye Bye Blackbird changes.

## Data

- **Leadsheets** — Impro-Visor imaginary-book `.ls` files (2600+ jazz standards). Impro-Visor is available at [impro-visor.com](https://www.impro-visor.com).
- **Solo corpus** — [Weimar Jazz Database](https://jazzomat.hfm-weimar.de) (456 annotated jazz solos, SQLite format).

The impro-visor source leadsheets files are  included in the repository, the Weimar Solos database is not. See `docs/plan.md` for download instructions.

## Requirements

**Python (3.10+)**
```bash
pip install -r python/requirements.txt
```

Key dependencies: `music21`, `python-osc`, `numpy`, `nltk`, `pretty_midi`

**SuperCollider** — standard installation, no additional Quarks required.

**Audio** (Linux) — JACK2, Reaper, a sampled jazz instrument VSTi.

## Project documentation

See [`docs/plan.md`](docs/plan.md) for the full project plan including phase descriptions, data sources, build order, and open design questions.

## License

GPL-2.0 — consistent with Impro-Visor, whose grammar format and leadsheet vocabulary this project draws on.

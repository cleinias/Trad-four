# Related Projects and Reusable Software

*Trad-Four project reference — software landscape survey*

---

## Overview

This document surveys existing open-source software systems for algorithmic music improvisation that are potentially reusable in Trad-Four, either as direct dependencies, as implementation references, or as architectural inspiration. Systems are ranked by practical relevance to the Trad-Four architecture.

---

## Tier 1 — High Relevance, Consider Direct Use

### dicy2-python (IRCAM)

**Repository:** https://github.com/DYCI2/Dicy2-python  
**License:** GPL-3.0  
**Install:** `pip install dicy2`  
**Language:** Python  

The generative core of the DYCI2/Somax2 research program at IRCAM, extracted as a standalone Python library independent of Max. Implements the Factor Oracle automaton and several navigation strategies derived from the OMax, ImproteK, and Somax2 systems.

**Architecture:**
- `Generator` class — offline generation from a corpus, good starting point for batch use
- `GenerationScheduler` class — real-time generation with time management
- `dicy2_server.py` — OSC interface for integration with external environments (SC, Max, etc.)
- Works on sequences of abstract labels — including chord labels directly
- Scenario-based generation: given a target sequence of chord labels (the lead sheet), generates a new sequence by recombining corpus segments that match those labels

**Relevance to Trad-Four:**
This is the most directly applicable external system. The scenario-driven generation mode — "produce output consistent with this chord progression" — maps almost exactly onto Trad-Four's Phase 3 requirements. The OSC interface fits naturally with the existing Python→SC→Reaper signal chain.

**Potential use:** Replace or complement Phase 2 (grammar induction) and Phase 3 (SC grammar executor) with a Factor Oracle navigator over the Weimar Jazz Database corpus. The two approaches are not mutually exclusive — the grammar approach generates fresh melodic material in a player's style; the factor oracle approach recombines actual recorded phrases. Both are musically valid.

**To explore:** Install and run against a Weimar solo indexed by chord labels, guided by a Bye Bye Blackbird chord progression, to assess musical output quality.

**Known limitation:** Factor Oracle systems lack long-range phrase structure (tension/release arc). This is a documented weakness across all OMax-derived systems.

---

### rpgomez/vomm

**Repository:** https://github.com/rpgomez/vomm  
**Language:** Python  

A clean Python implementation of two variable-order Markov model algorithms — PPM (Predict by Partial Match) and PST (Probabilistic Suffix Tree) — based on the Begleiter, El-Yaniv, and Yona (2004) JAIR paper that underpins Pachet's Continuator.

**Relevance to Trad-Four:**
Directly useful for Phase 2c as the Markov baseline for grammar induction. Rather than implementing a variable-order Markov chain from scratch, this library provides a tested PST implementation that can be trained on Weimar note-type sequences and used to generate typed rhythm skeletons — an alternative to the PCFG approach.

**Potential use:** Train on labeled Weimar sequences (note-type × duration-class pairs), then sample from the PST to generate rhythm skeletons as a simpler alternative to NLTK PCFG induction. Easier to get working quickly, easier to inspect, less musically structured than a CFG.

---

## Tier 2 — Useful for Reference and Partial Reuse

### jpgsloan/basic-continuator

**Repository:** https://github.com/jpgsloan/basic-continuator  
**Language:** Python (pedagogical implementation)  

A basic Python reimplementation of Pachet's Continuator, written for educational purposes. Not a production system, but useful for understanding how the variable-order Markov tree is built and navigated over MIDI note sequences — cleaner and more readable than a full production implementation.

**Relevance to Trad-Four:**
Good reference for understanding the PST data structure and suffix-matching algorithm at the MIDI note level. Read the source before implementing the Markov path in Phase 2c.

---

### Impro-Visor grammar files

**Location:** `/usr/share/impro-visor/grammars/` (local installation)  
**Repository:** https://github.com/Impro-Visor/Impro-Visor/tree/master/grammars  
**Format:** Custom S-expression DSL (`.grammar` files)  
**License:** GPL-2.0  

The grammar files distributed with Impro-Visor represent a substantial hand-curated library of player style grammars, including grammars for specific players (Woody Shaw, Wes Montgomery), specific contexts (trading 2s, trading 4s, chord tones only, color tones), and specific styles (bebop, modal). These are data assets, not code.

**Relevance to Trad-Four:**
These files are Phase 2e (hand-crafted grammar library) almost for free. A parser for the `.grammar` format (an S-expression CFG with weights) would let Trad-Four load and execute any of Impro-Visor's existing grammars in the SC Pattern engine, bypassing Phase 2a–2d entirely for an initial working system.

**To explore:** Write a small Python parser for the `.grammar` format and convert one or two grammars (e.g. `trade-4-A-chord.grammar`) to SC Pattern code or JSON for use in Phase 3a.

---

### Somax2 Python layer (IRCAM)

**Repository:** https://github.com/DYCI2/Somax2 (`python/somax` subtree)  
**License:** GPL-3.0  
**Language:** Python + Max  

Somax2's Python layer implements a multilevel musical memory architecture with three key abstractions:
- `Atom` — a single layer of the multilevel representation (one for harmony, one for pitch, etc.)
- `StreamView` — a recursive tree structure containing StreamViews and Atoms
- `Player` — the root class through which all generation interaction occurs

The Python layer is tightly coupled to Max via OSC and is not designed to be used standalone. However, the `Atom`/`StreamView` architecture is a sophisticated design for representing musical memory at multiple simultaneous levels of abstraction — worth reading as a reference for how to structure multilevel corpus navigation.

**Relevance to Trad-Four:** Design reference only. Not directly extractable without significant work.

---

## Tier 3 — Interesting but Not Directly Applicable

### PyOracle

**Repository:** https://github.com/surgesg/PyOracle  
**Install:** `pip install PyOracle`  
**Language:** Python  
**Paper:** Surges and Dubnov, "Feature Selection and Composition Using PyOracle," MML 2013  

A Python implementation of the Audio Oracle algorithm — an extension of the Factor Oracle — for music analysis and machine improvisation. Works in the audio domain: extracts features (MFCC, chroma, centroid, RMS, zero crossings) from an audio file, builds an oracle from those features, and generates new sequences by navigating the oracle.

Includes automatic model calibration based on Information Rate measures from Music Information Dynamics, and an audio-based query mode where a live input signal influences the generative output.

**Relevance to Trad-Four:** Low. PyOracle operates on audio features rather than symbolic MIDI data. Using it for Trad-Four would require converting Weimar MIDI solos to audio, extracting features, and building the oracle from those features — a lossy and roundabout path compared to working directly with symbolic data as Dicy2 does. Interesting if Trad-Four ever extends to audio-domain generation.

---

### Pachet's Continuator (original)

**Website:** https://www.francoispachet.fr/continuator/ (currently down)  
**Language:** Originally Max/MSP, never open-sourced  

The original Continuator was never released as open source. Pachet's Sony CSL group has not made the implementation available. The algorithm is fully described in the 2003 JNMR paper and can be reimplemented from the paper — which is essentially what `rpgomez/vomm` and `jpgsloan/basic-continuator` do.

**Relevance to Trad-Four:** Reference only. Use `rpgomez/vomm` for the actual implementation.

---

## Summary Table

| System | Language | Install | Paradigm | Trad-Four relevance |
|---|---|---|---|---|
| dicy2-python | Python | `pip install dicy2` | Factor Oracle | High — try first |
| rpgomez/vomm | Python | clone | Variable-order Markov | High — Phase 2c baseline |
| basic-continuator | Python | clone | Variable-order Markov | Medium — read source |
| Impro-Visor grammars | S-expr data | local | CFG | High — Phase 2e for free |
| Somax2 python layer | Python+Max | clone | Factor Oracle multilevel | Low — design reference |
| PyOracle | Python | `pip install PyOracle` | Audio Oracle | Low — wrong domain |
| Continuator (original) | Max | not available | Variable-order Markov | None — read paper |

---

## Next Steps

1. **`pip install dicy2`** and run against a Weimar solo indexed by Bye Bye Blackbird chord labels — assess musical output quality before committing to grammar induction.
2. **Parse Impro-Visor `.grammar` files** — a small parser would unlock the entire Impro-Visor grammar library as Phase 2e content.
3. **Read `rpgomez/vomm`** source — understand the PST structure before deciding whether Phase 2c uses PCFG or Markov.

---

*Last updated: March 2026. This document is part of the Trad-Four project (`docs/`).*

// PitchResolver.scd — Trad-Four Phase 3
// Maps typed note events to MIDI pitches using chord pitch class sets.
//
// Note type resolution:
//   C  → chord_tones, closest to previous pitch
//   L  → color_tones (fallback: scale_tones), closest to previous pitch
//   S  → scale_tones, closest to previous pitch
//   A  → chromatic half-step approach to nearest chord tone
//   X  → scale degree → semitone offset from chord root
//   H  → same as C (harmonic tone synonym)
//   R  → rest (nil pitch)
//
// All pitches clamped to min_pitch..max_pitch from grammar parameters.
//
// Usage:
//   ~pitchResolver.resolve(noteEvents, chordTimeline, grammar);
//   // Returns array of (midi: pitch_or_nil, dur: beats, type: symbol)

(
~pitchResolver = (

    // ---------------------------------------------------------------
    // Scale degree string → semitone offset from root
    // ---------------------------------------------------------------
    degreeToSemitones: (
        "1":  0,  "#1": 1,  "b2": 1,
        "2":  2,  "#2": 3,  "b3": 3,
        "3":  4,  "#3": 5,  "b4": 4,
        "4":  5,  "#4": 6,  "b5": 6,
        "5":  7,  "#5": 8,  "b6": 8,
        "6":  9,  "#6": 10, "b7": 10,
        "7":  11, "#7": 11
    ),

    // ---------------------------------------------------------------
    // Find the pitch in pool closest to targetMidi within range
    // ---------------------------------------------------------------
    closestPitch: { |self, pool, targetMidi, minP, maxP|
        var candidates, best;
        if(pool.size == 0) { nil } {
            // Generate all MIDI pitches from pool PCs within range
            candidates = Array.new(64);
            pool.do { |pc|
                var midi = pc;
                // Start from below minP and walk up
                while { midi < minP } { midi = midi + 12 };
                while { midi <= maxP } {
                    candidates = candidates.add(midi);
                    midi = midi + 12;
                };
            };
            if(candidates.size == 0) { nil } {
                best = candidates.minItem { |m| (m - targetMidi).abs };
                best
            }
        }
    },

    // ---------------------------------------------------------------
    // Resolve a single X-degree note
    // ---------------------------------------------------------------
    resolveX: { |self, degree, chord, targetMidi, minP, maxP|
        var semitones, root, pc, midi;
        semitones = self[\degreeToSemitones][degree];
        if(semitones.isNil) {
            // Unknown degree — try parsing as number
            semitones = degree.asInteger % 12;
        };
        root = chord[\tonalKey];
        if(root < 0) { root = chord[\chordTones][0] ? 0 };
        pc = (root + semitones) % 12;
        self.closestPitch([pc], targetMidi, minP, maxP)
    },

    // ---------------------------------------------------------------
    // Resolve a chromatic approach note
    // ---------------------------------------------------------------
    resolveApproach: { |self, chord, targetMidi, prevMidi, minP, maxP|
        var chordPitches, nearest, approach;
        // Find nearest chord tone pitch
        chordPitches = self.closestPitch(chord[\chordTones], targetMidi, minP, maxP);
        if(chordPitches.isNil) { nil } {
            nearest = chordPitches;
            // Approach from below or above depending on direction from prevMidi
            if(prevMidi <= nearest) {
                approach = nearest - 1;  // chromatic below
            } {
                approach = nearest + 1;  // chromatic above
            };
            approach.clip(minP, maxP)
        }
    },

    // ---------------------------------------------------------------
    // Flatten slope notes into simple note events
    // ---------------------------------------------------------------
    flattenSlope: { |self, slopeEvent|
        // A slope contains inner notes with types; return them as-is
        // The slope start/end contour values guide pitch resolution
        // but the note types still determine the pitch pool
        slopeEvent[\notes]
    },

    // ---------------------------------------------------------------
    // Main resolution: note events + chord timeline → MIDI sequence
    // ---------------------------------------------------------------
    resolve: { |self, noteEvents, chordTimeline, grammar|
        var minP, maxP, result, prevMidi, beatPos, chordIdx, chord;
        var flatEvents;

        minP = grammar[\params][\min_pitch] ? 58;
        maxP = grammar[\params][\max_pitch] ? 82;
        prevMidi = ((minP + maxP) / 2).round.asInteger;  // start in middle of range
        beatPos = 0.0;
        chordIdx = 0;

        // First flatten any slopes into their component notes
        flatEvents = Array.new(noteEvents.size * 2);
        noteEvents.do { |evt|
            if(evt[\type] == \slope) {
                self.flattenSlope(evt).do { |inner|
                    flatEvents = flatEvents.add(inner);
                };
            } {
                flatEvents = flatEvents.add(evt);
            };
        };

        // Advance to the chord active at the current beat position
        result = Array.new(flatEvents.size);

        flatEvents.do { |evt|
            var midi, pool;

            // Find the active chord for the current beat position
            while {
                (chordIdx < (chordTimeline.size - 1))
                and: { beatPos >= (chordTimeline[chordIdx][\beat]
                    + chordTimeline[chordIdx][\duration]) }
            } {
                chordIdx = chordIdx + 1;
            };
            chord = chordTimeline[chordIdx];

            // Resolve pitch by note type
            midi = case
                { evt[\type] == \R } { nil }
                { evt[\type] == \C or: { evt[\type] == \H } } {
                    self.closestPitch(chord[\chordTones], prevMidi, minP, maxP)
                }
                { evt[\type] == \L } {
                    pool = chord[\colorTones];
                    if(pool.size == 0) { pool = chord[\scaleTones] };
                    self.closestPitch(pool, prevMidi, minP, maxP)
                }
                { evt[\type] == \S } {
                    self.closestPitch(chord[\scaleTones], prevMidi, minP, maxP)
                }
                { evt[\type] == \A } {
                    self.resolveApproach(chord, prevMidi, prevMidi, minP, maxP)
                }
                { evt[\type] == \X } {
                    self.resolveX(evt[\degree], chord, prevMidi, minP, maxP)
                }
                { nil };  // unknown type → rest

            if(midi.notNil) { prevMidi = midi };

            result = result.add(
                (midi: midi, dur: evt[\dur], type: evt[\type])
            );

            beatPos = beatPos + evt[\dur];
        };

        result
    }
);
)

// TradFourPlayer.scd — Trad-Four Phase 3
// MIDI playback engine for pre-generated note sequences.
//
// Uses TempoClock synced to lead sheet tempo. MIDI output via MIDIOut
// to a JACK virtual port, routed to Reaper.
//
// Velocity varies by note type:
//   C (chord tone): 90    — strong, prominent
//   L (color tone): 75    — moderate
//   S (scale tone): 70    — moderate
//   X (interval):   80    — context-dependent
//   A (approach):   65    — softer, leading
//   H (harmonic):   90    — same as C
//   R (rest):       0     — no note
//
// Usage:
//   ~tradFourPlayer.init;                    // initialize MIDI
//   ~tradFourPlayer.play(resolvedNotes);     // start playback
//   ~tradFourPlayer.stop;                    // stop playback

(
~tradFourPlayer = (

    midiOut: nil,
    midiChan: 0,
    clock: nil,
    routine: nil,

    // Velocity by note type
    velocityMap: (
        C: 90, H: 90,
        X: 80,
        L: 75, S: 70,
        A: 65,
        R: 0
    ),

    // ---------------------------------------------------------------
    // Initialize MIDI output
    // ---------------------------------------------------------------
    init: { |self|
        MIDIClient.init;
        // Use MIDIOut(0) which creates a virtual output port.
        // External apps (Reaper) connect to SC's MIDI output via JACK/ALSA.
        self[\midiOut] = MIDIOut(0);
        self[\midiOut].latency = 0;
        "TradFourPlayer: MIDI output initialized (port 0)".postln;
        "TradFourPlayer: Connect Reaper's MIDI input to SuperCollider:out0 via JACK".postln;
        self
    },

    // ---------------------------------------------------------------
    // Play a resolved note sequence
    // ---------------------------------------------------------------
    play: { |self, resolvedNotes, tempo|
        var bpm;

        bpm = tempo ? (~trad4[\tempo] ? 120);

        // Create a TempoClock at the lead sheet tempo
        if(self[\clock].notNil) { self[\clock].stop };
        self[\clock] = TempoClock(bpm / 60);

        "TradFourPlayer: playing % notes at % bpm".format(
            resolvedNotes.size, bpm
        ).postln;

        self[\routine] = Routine({
            resolvedNotes.do { |evt|
                var midi, dur, vel, type;
                midi = evt[\midi];
                dur  = evt[\dur];
                type = evt[\type];

                if(midi.notNil and: { type != \R }) {
                    vel = self[\velocityMap][type] ? 75;

                    "  note: % (%) vel=% dur=%".format(midi, type, vel, dur.round(0.01)).postln;
                    self[\midiOut].noteOn(self[\midiChan], midi, vel);

                    // Hold for note duration minus a small gap for articulation
                    (dur * 0.9).max(0.05).wait;

                    self[\midiOut].noteOff(self[\midiChan], midi, 0);

                    // Wait for remaining duration
                    (dur * 0.1).max(0).wait;
                } {
                    // Rest — just wait
                    dur.wait;
                };
            };

            "TradFourPlayer: playback complete".postln;

        }).play(self[\clock]);

        self
    },

    // ---------------------------------------------------------------
    // Stop playback
    // ---------------------------------------------------------------
    stop: { |self|
        if(self[\routine].notNil) {
            self[\routine].stop;
            self[\routine] = nil;
        };
        // All notes off
        if(self[\midiOut].notNil) {
            128.do { |note|
                self[\midiOut].noteOff(self[\midiChan], note, 0);
            };
        };
        "TradFourPlayer: stopped".postln;
        self
    }
);
)

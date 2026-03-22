// TradFourPlayer.scd — Trad-Four Phase 3
// MIDI playback engine for pre-generated note sequences.
//
// Uses ~tradFourClock (set by MIDISyncSetup) for tempo sync with Reaper.
// Falls back to a standalone TempoClock if MIDISyncSetup wasn't called.
//
// MIDI output via MIDIOut to a JACK virtual port, routed to Reaper.
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
//   ~tradFourPlayer.init;                           // initialize MIDI output
//   ~tradFourPlayer.play(resolvedNotes, tempo);     // full solo playback
//   ~tradFourPlayer.playTrading(phrases, bpb, n);   // trading bars playback
//   ~tradFourPlayer.stop;                           // stop playback

(
~tradFourPlayer = (

    midiOut: nil,
    midiChan: 0,
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
        // MIDIClient.init is called by MIDISyncSetup — no need to repeat here.
        // Use MIDIOut(0) which creates a virtual output port.
        // External apps (Reaper) connect to SC's MIDI output via JACK/ALSA.
        self[\midiOut] = MIDIOut(0);
        self[\midiOut].latency = 0;
        "TradFourPlayer: MIDI output initialized (port 0)".postln;
        "TradFourPlayer: Connect Reaper's MIDI input to SuperCollider:out0 via JACK".postln;
        self
    },

    // ---------------------------------------------------------------
    // Get the active clock (from MIDISyncSetup or fallback)
    // ---------------------------------------------------------------
    getClock: { |self, tempo|
        var clock = ~tradFourClock;
        if(clock.isNil) {
            // Fallback if MIDISyncSetup wasn't called
            var bpm = tempo ? (~trad4[\tempo] ? 120);
            clock = TempoClock(bpm / 60);
            "TradFourPlayer: no ~tradFourClock — using fallback TempoClock (% bpm)".format(bpm).postln;
        };
        clock
    },

    // ---------------------------------------------------------------
    // Play a sequence of note events (inline, blocking)
    // Used by both play and playTrading
    // ---------------------------------------------------------------
    playNotes: { |self, notes|
        notes.do { |evt|
            var midi, dur, vel, type;
            midi = evt[\midi];
            dur  = evt[\dur];
            type = evt[\type];

            if(midi.notNil and: { type != \R }) {
                vel = self[\velocityMap][type] ? 75;

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
    },

    // ---------------------------------------------------------------
    // Play a resolved note sequence (full solo, non-trading mode)
    // ---------------------------------------------------------------
    play: { |self, resolvedNotes, tempo|
        var clock = self[\getClock].value(self, tempo);

        "TradFourPlayer: playing % notes".format(resolvedNotes.size).postln;

        self[\routine] = Routine({
            self[\playNotes].value(self, resolvedNotes);
            "TradFourPlayer: playback complete".postln;
        }).play(clock);

        self
    },

    // ---------------------------------------------------------------
    // Play trading bars: alternate computer phrases and human silence
    // ---------------------------------------------------------------
    playTrading: { |self, phrases, beatsPerBar, tradingBars|
        var clock = self[\getClock].value(self);

        self[\routine] = Routine({
            phrases.do { |phrase|
                var waitBeats = tradingBars * beatsPerBar;

                if(phrase[\notes].notNil) {
                    // Computer's turn — play the phrase
                    "TradFourPlayer: computer plays bars %-%".format(
                        phrase[\barStart] + 1, phrase[\barEnd]
                    ).postln;
                    // Fire status callback for GUI
                    if(~tradFour[\onStatus].notNil) {
                        { ~tradFour[\onStatus].value(
                            "Computer: bars %-%".format(
                                phrase[\barStart] + 1, phrase[\barEnd])
                        ) }.defer;
                    };
                    // Play notes inline
                    self[\playNotes].value(self, phrase[\notes]);
                } {
                    // Human's turn — silence for N bars
                    "TradFourPlayer: human plays bars %-%".format(
                        phrase[\barStart] + 1, phrase[\barEnd]
                    ).postln;
                    if(~tradFour[\onStatus].notNil) {
                        { ~tradFour[\onStatus].value(
                            "Human: bars %-%".format(
                                phrase[\barStart] + 1, phrase[\barEnd])
                        ) }.defer;
                    };
                    waitBeats.wait;
                };
            };
            "TradFourPlayer: trading complete".postln;
            if(~tradFour[\onStatus].notNil) {
                { ~tradFour[\onStatus].value("Idle") }.defer;
            };
        }).play(clock);

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

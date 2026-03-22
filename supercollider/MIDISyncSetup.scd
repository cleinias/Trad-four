// MIDISyncSetup.scd — Trad-Four Phase 3
// MIDI clock synchronization: Reaper as master, SC as slave.
//
// Uses ddwMIDI Quark's MIDISyncClock to receive MIDI clock (F8 ticks),
// start (FA), stop (FC), and continue (FB) messages from Reaper.
//
// Prerequisite: Quarks.install("ddwMIDI"); thisProcess.recompile;
//
// Setup in Reaper:
//   Preferences → MIDI Devices → Output → enable "Send MIDI clock"
//   Route Reaper's MIDI output to SC via JACK
//
// Stores the active clock in ~tradFourClock for use by TradFourPlayer.
//
// Fallback: set useMIDISync: false for standalone mode (internal TempoClock).
//
// Usage:
//   ~midiSyncSetup[\init].value(~midiSyncSetup);
//   ~tradFourClock   // the active clock (MIDISyncClock or TempoClock)

(
~midiSyncSetup = (

    clock: nil,
    useMIDISync: true,   // set false for standalone testing without Reaper

    // ---------------------------------------------------------------
    // Initialize clock
    // ---------------------------------------------------------------
    init: { |self|
        if(self[\useMIDISync]) {
            // MIDISyncClock is a singleton from ddwMIDI
            self[\clock] = MIDISyncClock;
            ~tradFourClock = self[\clock];
            "MIDISyncSetup: listening for MIDI clock from Reaper".postln;
            "MIDISyncSetup: press Play in Reaper to start clock".postln;
        } {
            // Standalone fallback — use lead sheet tempo or 120 bpm default
            var bpm = ~trad4[\tempo] ? 120;
            self[\clock] = TempoClock(bpm / 60);
            ~tradFourClock = self[\clock];
            "MIDISyncSetup: standalone mode (% bpm)".format(bpm).postln;
        };
        self
    },

    // ---------------------------------------------------------------
    // Update standalone tempo (no-op in MIDI sync mode)
    // ---------------------------------------------------------------
    setStandaloneTempo: { |self, bpm|
        if(self[\useMIDISync].not) {
            self[\clock].tempo = bpm / 60;
            "MIDISyncSetup: standalone tempo set to % bpm".format(bpm).postln;
        };
        self
    }
);
)

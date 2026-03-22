// main.scd — Trad-Four Phase 3
// Integration launcher: loads all modules, initializes MIDI,
// loads grammar, starts OSC listener, and auto-generates solos.
//
// Usage (in SuperCollider):
//   1. Execute this file (Cmd+Enter on the whole file)
//   2. From terminal: python -m python.leadsheet.osc_bridge data/leadsheets/ByeByeBlackbird.ls
//   3. SC receives chords, generates solo, plays via MIDI → JACK → Reaper
//
// To replay with a new solo over the same chords:
//   ~tradFour[\generate].value(~tradFour);
//
// To stop playback:
//   ~tradFour[\stop].value(~tradFour);

(
// ---------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------
var grammarPath = thisProcess.nowExecutingPath.dirname +/+ "grammars/LesterYoung.json";

// ---------------------------------------------------------------
// Load all modules
// ---------------------------------------------------------------
var dir = thisProcess.nowExecutingPath.dirname;
(dir +/+ "TradFourReceiver.scd").load;
(dir +/+ "GrammarLoader.scd").load;
(dir +/+ "GrammarExpander.scd").load;
(dir +/+ "PitchResolver.scd").load;
(dir +/+ "TradFourPlayer.scd").load;

"TradFour: all modules loaded".postln;

// ---------------------------------------------------------------
// Load grammar
// ---------------------------------------------------------------
~grammarLoader[\load].value(~grammarLoader, grammarPath);

// ---------------------------------------------------------------
// Initialize MIDI
// ---------------------------------------------------------------
~tradFourPlayer[\init].value(~tradFourPlayer);

// ---------------------------------------------------------------
// Main controller
// ---------------------------------------------------------------
~tradFour = (

    // Generate and play a solo over the current chord timeline
    generate: { |self|
        var totalBeats, totalTicks, noteEvents, resolved;

        if(~trad4.isNil or: { ~trad4[\chords].isNil } or: { ~trad4[\chords].size == 0 }) {
            "TradFour: no chord data loaded — send a lead sheet via OSC first".postln;
        } {
            // Calculate total duration from chord timeline
            totalBeats = ~trad4[\chords].sum { |c| c[\duration] };
            totalTicks = (totalBeats * ~grammarExpander[\ticksPerBeat]).asInteger;

            "TradFour: generating solo — % beats (% ticks) over % chords".format(
                totalBeats, totalTicks, ~trad4[\chords].size
            ).postln;

            // Expand grammar → note events
            noteEvents = ~grammarExpander[\expand].value(~grammarExpander, totalTicks);
            "TradFour: expanded to % note events".format(noteEvents.size).postln;

            // Resolve pitches using chord timeline
            resolved = ~pitchResolver[\resolve].value(
                ~pitchResolver, noteEvents, ~trad4[\chords], ~grammar
            );
            "TradFour: resolved % pitches".format(resolved.size).postln;

            // Play
            ~tradFourPlayer[\play].value(~tradFourPlayer, resolved, ~trad4[\tempo]);
        };
    },

    // Stop playback
    stop: { |self|
        ~tradFourPlayer[\stop].value(~tradFourPlayer);
    }
);

// ---------------------------------------------------------------
// Start OSC receiver with auto-generate callback
// ---------------------------------------------------------------
~trad4Receiver[\start].value(~trad4Receiver);
~trad4[\onDone] = { |trad4|
    "TradFour: auto-generating solo...".postln;
    AppClock.sched(0.1, {
        ~tradFour[\generate].value(~tradFour);
        nil  // don't reschedule
    });
};

"".postln;
"=== Trad-Four Improvisation Engine ===".postln;
"  Grammar:  %".format(~grammar[\player]).postln;
"  Pitch:    %–%".format(
    ~grammar[\params][\min_pitch], ~grammar[\params][\max_pitch]
).postln;
"  Waiting for chord data via OSC...".postln;
"  Send: python -m python.leadsheet.osc_bridge <leadsheet>".postln;
"  Replay:  ~tradFour[\\generate].value(~tradFour)".postln;
"  Stop:    ~tradFour[\\stop].value(~tradFour)".postln;
"========================================".postln;
)

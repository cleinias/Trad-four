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
//   ~tradFour.generate;
//
// To stop playback:
//   ~tradFour.stop;

(
// ---------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------
var grammarPath = thisProcess.nowExecutingPath.dirname +/+ "grammars/LesterYoung.json";

// ---------------------------------------------------------------
// Load all modules
// ---------------------------------------------------------------
(thisProcess.nowExecutingPath.dirname +/+ "TradFourReceiver.scd").load;
(thisProcess.nowExecutingPath.dirname +/+ "GrammarLoader.scd").load;
(thisProcess.nowExecutingPath.dirname +/+ "GrammarExpander.scd").load;
(thisProcess.nowExecutingPath.dirname +/+ "PitchResolver.scd").load;
(thisProcess.nowExecutingPath.dirname +/+ "TradFourPlayer.scd").load;

"TradFour: all modules loaded".postln;

// ---------------------------------------------------------------
// Load grammar
// ---------------------------------------------------------------
~grammarLoader.load(grammarPath);

// ---------------------------------------------------------------
// Initialize MIDI
// ---------------------------------------------------------------
~tradFourPlayer.init;

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
            totalBeats = ~trad4[\chords].collect(_.duration).sum;
            totalTicks = (totalBeats * ~grammarExpander[\ticksPerBeat]).asInteger;

            "TradFour: generating solo — % beats (% ticks) over % chords".format(
                totalBeats, totalTicks, ~trad4[\chords].size
            ).postln;

            // Expand grammar → note events
            noteEvents = ~grammarExpander.expand(totalTicks);
            "TradFour: expanded to % note events".format(noteEvents.size).postln;

            // Resolve pitches using chord timeline
            resolved = ~pitchResolver.resolve(noteEvents, ~trad4[\chords], ~grammar);
            "TradFour: resolved % pitches".format(resolved.size).postln;

            // Play
            ~tradFourPlayer.play(resolved, ~trad4[\tempo]);
        };
    },

    // Stop playback
    stop: { |self|
        ~tradFourPlayer.stop;
    }
);

// ---------------------------------------------------------------
// Start OSC receiver with auto-generate callback
// ---------------------------------------------------------------
~trad4Receiver.start;
~trad4[\onDone] = { |trad4|
    "TradFour: auto-generating solo...".postln;
    // Small delay to ensure all OSC messages are processed
    { ~tradFour.generate }.defer(0.1);
};

"".postln;
"=== Trad-Four Improvisation Engine ===".postln;
"  Grammar:  %".format(~grammar[\player]).postln;
"  Pitch:    %–%".format(
    ~grammar[\params][\min_pitch], ~grammar[\params][\max_pitch]
).postln;
"  Waiting for chord data via OSC...".postln;
"  Send: python -m python.leadsheet.osc_bridge <leadsheet>".postln;
"  Replay:  ~tradFour.generate".postln;
"  Stop:    ~tradFour.stop".postln;
"========================================".postln;
)

// main.scd — Trad-Four Phase 3
// Integration launcher: loads all modules, initializes MIDI sync and output,
// loads grammar, starts OSC listener, and provides generate/stop controls.
//
// Supports two modes:
//   - Full solo: generate entire improvisation over all bars
//   - Trading bars: alternate N-bar phrases between computer and human
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
(dir +/+ "MIDISyncSetup.scd").load;
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
// Initialize MIDI sync (clock) and MIDI output
// ---------------------------------------------------------------
~midiSyncSetup[\init].value(~midiSyncSetup);
~tradFourPlayer[\init].value(~tradFourPlayer);

// ---------------------------------------------------------------
// Main controller
// ---------------------------------------------------------------
~tradFour = (

    // Trading configuration
    tradingMode: false,    // false = full solo, true = trading bars
    tradingBars: 4,        // bars per turn (2, 4, or 8)
    humanFirst: false,     // who starts: false = computer first

    // Status callback (set by GUI)
    onStatus: nil,

    // ---------------------------------------------------------------
    // Generate: dispatch to full solo or trading mode
    // ---------------------------------------------------------------
    generate: { |self|
        if(~trad4.isNil or: { ~trad4[\chords].isNil } or: { ~trad4[\chords].size == 0 }) {
            "TradFour: no chord data loaded — send a lead sheet via OSC first".postln;
        } {
            // Update standalone clock tempo if needed
            ~midiSyncSetup[\setStandaloneTempo].value(~midiSyncSetup, ~trad4[\tempo]);

            if(self[\tradingMode]) {
                self[\generateTrading].value(self);
            } {
                self[\generateFull].value(self);
            };
        };
    },

    // ---------------------------------------------------------------
    // Generate and play a full solo over all bars
    // ---------------------------------------------------------------
    generateFull: { |self|
        var totalBeats, totalTicks, noteEvents, resolved;

        // Calculate total duration from chord timeline
        totalBeats = ~trad4[\chords].sum { |c| c[\duration] };
        totalTicks = (totalBeats * ~grammarExpander[\ticksPerBeat]).asInteger;

        "TradFour: generating full solo — % beats (% ticks) over % chords".format(
            totalBeats, totalTicks, ~trad4[\chords].size
        ).postln;

        if(self[\onStatus].notNil) {
            { self[\onStatus].value("Generating full solo...") }.defer;
        };

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
    },

    // ---------------------------------------------------------------
    // Generate and play trading bars
    // Each computer turn is an independently generated phrase with
    // its own melodic arc, not a fragment of a longer solo.
    // ---------------------------------------------------------------
    generateTrading: { |self|
        var bpb, tradingBars, totalBars, phraseTicks, phrases, chords;
        var turnCount, barStart;

        bpb = ~trad4[\beatsPerBar];
        tradingBars = self[\tradingBars] ? 4;
        totalBars = ~trad4[\totalBars];
        chords = ~trad4[\chords];
        phraseTicks = (tradingBars * bpb * ~grammarExpander[\ticksPerBeat]).asInteger;

        // How many turns total (computer + human)?
        turnCount = (totalBars / tradingBars).ceil.asInteger;

        "TradFour: generating trading — % bars per turn, % turns total".format(
            tradingBars, turnCount
        ).postln;

        if(self[\onStatus].notNil) {
            { self[\onStatus].value("Generating trading phrases...") }.defer;
        };

        // Pre-generate a phrase for each computer turn
        phrases = Array.new(turnCount);
        barStart = 0;

        turnCount.do { |turnIdx|
            var barEnd, isComputerTurn, chordWindow, noteEvents, resolved;
            barEnd = (barStart + tradingBars).min(totalBars);
            isComputerTurn = if(self[\humanFirst]) { turnIdx.odd } { turnIdx.even };

            if(isComputerTurn) {
                // Extract chords for this bar window
                chordWindow = chords.select { |c|
                    (c[\bar] - 1) >= barStart and: { (c[\bar] - 1) < barEnd }
                };
                // Adjust chord beat offsets to be window-relative
                // (so resolver sees beats starting from 0)
                chordWindow = chordWindow.collect { |c|
                    var adjusted = c.copy;
                    adjusted[\beat] = c[\beat] - (barStart * bpb);
                    adjusted
                };

                // Generate independent phrase for this window
                noteEvents = ~grammarExpander[\expand].value(
                    ~grammarExpander, phraseTicks
                );
                resolved = ~pitchResolver[\resolve].value(
                    ~pitchResolver, noteEvents, chordWindow, ~grammar
                );
                phrases = phrases.add(
                    (notes: resolved, barStart: barStart, barEnd: barEnd)
                );
            } {
                // Human turn — store nil (silence)
                phrases = phrases.add(
                    (notes: nil, barStart: barStart, barEnd: barEnd)
                );
            };

            barStart = barEnd;
        };

        "TradFour: generated % phrases (% computer, % human)".format(
            phrases.size,
            phrases.count { |p| p[\notes].notNil },
            phrases.count { |p| p[\notes].isNil }
        ).postln;

        // Start playback
        ~tradFourPlayer[\playTrading].value(
            ~tradFourPlayer, phrases, bpb, tradingBars
        );
    },

    // ---------------------------------------------------------------
    // Stop playback
    // ---------------------------------------------------------------
    stop: { |self|
        ~tradFourPlayer[\stop].value(~tradFourPlayer);
        if(self[\onStatus].notNil) {
            { self[\onStatus].value("Idle") }.defer;
        };
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

// ---------------------------------------------------------------
// Load GUI
// ---------------------------------------------------------------
(dir +/+ "TradFourGUI.scd").load;

"".postln;
"=== Trad-Four Improvisation Engine ===".postln;
"  Grammar:  %".format(~grammar[\player]).postln;
"  Pitch:    %–%".format(
    ~grammar[\params][\min_pitch], ~grammar[\params][\max_pitch]
).postln;
"  Clock:    %".format(
    if(~midiSyncSetup[\useMIDISync]) { "MIDI sync (Reaper master)" } { "standalone" }
).postln;
"  Waiting for chord data via OSC...".postln;
"  Send: python -m python.leadsheet.osc_bridge <leadsheet>".postln;
"  Replay:  ~tradFour[\\generate].value(~tradFour)".postln;
"  Stop:    ~tradFour[\\stop].value(~tradFour)".postln;
"========================================".postln;
)

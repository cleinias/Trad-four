// TradFourReceiver.scd — Trad-Four Phase 3
// OSC receiver for chord timeline data from the Python side.
//
// Protocol (defined in python/leadsheet/osc_bridge.py):
//   /trad4/meta    s:title  s:composer  f:tempo  i:beats_per_bar  i:beat_unit
//                  i:total_bars  s:inferred_key
//   /trad4/chord   i:index  i:bar  f:beat  s:symbol  f:duration
//                  s:chord_tones  s:color_tones  s:scale_tones  s:scale_pcs
//                  s:scale_name  i:tonal_key  s:tonal_mode  s:tonal_scale
//   /trad4/done    i:total_chords
//
// Pitch class sets arrive as CSV strings ("0,4,7,11") and are parsed to Arrays.
//
// Uses OSCdef (named responders) so re-loading this file safely replaces
// previous registrations without accumulating duplicate handlers.
//
// Usage:
//   ~trad4Receiver.start;   // begin listening
//   ~trad4Receiver.stop;    // stop listening
//
// After /trad4/done is received:
//   ~trad4.title            // "Bye Bye Blackbird"
//   ~trad4.tempo            // 160
//   ~trad4.chords.size      // number of chord events
//   ~trad4.chords[0]        // first chord event (Event)

(
~trad4Receiver = (

    // ---------------------------------------------------------------
    // CSV string → integer Array helper
    // ---------------------------------------------------------------
    parseCSV: { |self, str|
        if(str.size == 0) {
            []
        } {
            str.split($,).collect(_.asInteger)
        }
    },

    // ---------------------------------------------------------------
    // Start listening
    // ---------------------------------------------------------------
    start: { |self|
        // Initialize storage
        ~trad4 = ();

        // /trad4/meta — tune metadata
        // OSCdef replaces any previous responder with the same key
        OSCdef(\trad4Meta, { |msg|
            ~trad4[\title]        = msg[1].asString;
            ~trad4[\composer]     = msg[2].asString;
            ~trad4[\tempo]        = msg[3].asFloat;
            ~trad4[\beatsPerBar]  = msg[4].asInteger;
            ~trad4[\beatUnit]     = msg[5].asInteger;
            ~trad4[\totalBars]    = msg[6].asInteger;
            ~trad4[\inferredKey]  = msg[7].asString;
            ~trad4[\chords]       = List.new(256);

            "TradFour: received meta — '%' by % (% bpm, %/%)".format(
                ~trad4[\title], ~trad4[\composer],
                ~trad4[\tempo], ~trad4[\beatsPerBar], ~trad4[\beatUnit]
            ).postln;
        }, '/trad4/meta');

        // /trad4/chord — individual chord events
        OSCdef(\trad4Chord, { |msg|
            var chord = (
                index:      msg[1].asInteger,
                bar:        msg[2].asInteger,
                beat:       msg[3].asFloat,
                symbol:     msg[4].asString,
                duration:   msg[5].asFloat,
                chordTones: self.parseCSV(msg[6].asString),
                colorTones: self.parseCSV(msg[7].asString),
                scaleTones: self.parseCSV(msg[8].asString),
                scalePCs:   self.parseCSV(msg[9].asString),
                scaleName:  msg[10].asString,
                tonalKey:   msg[11].asInteger,
                tonalMode:  msg[12].asString,
                tonalScale: self.parseCSV(msg[13].asString)
            );
            ~trad4[\chords].add(chord);
        }, '/trad4/chord');

        // /trad4/done — completion signal
        OSCdef(\trad4Done, { |msg|
            var count = msg[1].asInteger;
            "TradFour: received % chords for '%'".format(
                count, ~trad4[\title]
            ).postln;

            // Fire callback if registered
            if(~trad4[\onDone].notNil) {
                ~trad4[\onDone].value(~trad4);
            };
        }, '/trad4/done');

        "TradFour: OSC receiver started (listening on default port)".postln;
        self
    },

    // ---------------------------------------------------------------
    // Stop listening
    // ---------------------------------------------------------------
    stop: { |self|
        OSCdef(\trad4Meta).free;
        OSCdef(\trad4Chord).free;
        OSCdef(\trad4Done).free;
        "TradFour: OSC receiver stopped".postln;
        self
    }
);
)

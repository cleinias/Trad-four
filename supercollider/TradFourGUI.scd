// TradFourGUI.scd — Trad-Four Phase 3
// Minimalist Qt GUI for the improvisation engine.
//
// Layout:
//   - Grammar selector (dropdown)
//   - Lead sheet file browser + Send button
//   - Trading bars controls (bars dropdown, human first, trading mode)
//   - Generate / Reseed / Stop buttons
//   - Status display (current action, tune info, tempo)
//
// Loaded by main.scd after all other modules.
// Tempo display reads from ~tradFourClock (updated periodically).

(
var win, grammarsDir, grammarFiles, grammarNames;
var grammarMenu, lsPathText, browseBtn, sendBtn;
var tradingBarsMenu, humanFirstCheck, tradingModeCheck;
var generateBtn, reseedBtn, stopBtn;
var statusText, tuneText, tempoText;
var tempoUpdater;

// ---------------------------------------------------------------
// Discover available grammars
// ---------------------------------------------------------------
grammarsDir = thisProcess.nowExecutingPath.dirname +/+ "grammars";
grammarFiles = (grammarsDir +/+ "*.json").pathMatch.sort;
grammarNames = grammarFiles.collect { |p| PathName(p).fileNameWithoutExtension };

if(grammarNames.size == 0) {
    "TradFourGUI: no grammar files found in %".format(grammarsDir).postln;
    grammarNames = ["(none)"];
    grammarFiles = [nil];
};

// ---------------------------------------------------------------
// Build window
// ---------------------------------------------------------------
win = Window("Trad-Four Improvisation Engine", Rect(100, 100, 420, 340))
    .front
    .onClose_({ tempoUpdater.stop });

win.view.decorator = FlowLayout(win.view.bounds, 10@10, 5@5);

// ---------------------------------------------------------------
// Grammar selector
// ---------------------------------------------------------------
StaticText(win, 400@20).string_("Grammar").font_(Font.default.bold_(true));

grammarMenu = PopUpMenu(win, 400@24)
    .items_(grammarNames)
    .action_({ |menu|
        var path = grammarFiles[menu.value];
        if(path.notNil) {
            ~grammarLoader[\load].value(~grammarLoader, path);
            "TradFourGUI: loaded grammar '%'".format(grammarNames[menu.value]).postln;
        };
    });

// Select current grammar if already loaded
if(~grammar.notNil and: { ~grammar[\player].notNil }) {
    var idx = grammarNames.indexOf(~grammar[\player]);
    if(idx.notNil) { grammarMenu.value = idx };
};

// ---------------------------------------------------------------
// Lead sheet file
// ---------------------------------------------------------------
StaticText(win, 400@20).string_("Lead Sheet").font_(Font.default.bold_(true));

lsPathText = TextField(win, 320@24).string_("").enabled_(false);
browseBtn = Button(win, 70@24)
    .states_([["Browse"]])
    .action_({
        Dialog.openPanel({ |path|
            lsPathText.string = path;
        }, nil, false);
    });

sendBtn = Button(win, 400@24)
    .states_([["Send to SC (run Python pipeline)"]])
    .action_({
        var path = lsPathText.string;
        if(path.size > 0) {
            var cmd = "cd % && python -m python.leadsheet.osc_bridge \"%\"".format(
                thisProcess.nowExecutingPath.dirname.dirname.shellQuote,
                path
            );
            "TradFourGUI: running %".format(cmd).postln;
            cmd.unixCmd({ |exitCode|
                if(exitCode != 0) {
                    "TradFourGUI: Python pipeline failed (exit %)".format(exitCode).postln;
                };
            });
        } {
            "TradFourGUI: no lead sheet file selected".postln;
        };
    });

// ---------------------------------------------------------------
// Trading controls
// ---------------------------------------------------------------
StaticText(win, 400@20).string_("Trading").font_(Font.default.bold_(true));

StaticText(win, 60@22).string_("Bars:");
tradingBarsMenu = PopUpMenu(win, 60@22)
    .items_(["2", "4", "8"])
    .value_(1)   // default: 4
    .action_({ |menu|
        var bars = [2, 4, 8][menu.value];
        ~tradFour[\tradingBars] = bars;
        "TradFourGUI: trading bars = %".format(bars).postln;
    });

humanFirstCheck = CheckBox(win, 130@22)
    .string_("Human first")
    .value_(false)
    .action_({ |cb|
        ~tradFour[\humanFirst] = cb.value;
        "TradFourGUI: human first = %".format(cb.value).postln;
    });

tradingModeCheck = CheckBox(win, 130@22)
    .string_("Trading mode")
    .value_(false)
    .action_({ |cb|
        ~tradFour[\tradingMode] = cb.value;
        "TradFourGUI: trading mode = %".format(cb.value).postln;
    });

// ---------------------------------------------------------------
// Action buttons
// ---------------------------------------------------------------
StaticText(win, 400@8).string_("");  // spacer

generateBtn = Button(win, 125@30)
    .states_([["Generate"]])
    .action_({
        ~tradFour[\generate].value(~tradFour);
    });

reseedBtn = Button(win, 125@30)
    .states_([["Reseed"]])
    .action_({
        thisThread.randSeed_(Date.getDate.rawSeconds.asInteger);
        ~tradFour[\generate].value(~tradFour);
    });

stopBtn = Button(win, 125@30)
    .states_([["Stop", Color.white, Color.red(0.6)]])
    .action_({
        ~tradFour[\stop].value(~tradFour);
    });

// ---------------------------------------------------------------
// Status display
// ---------------------------------------------------------------
StaticText(win, 400@8).string_("");  // spacer

statusText = StaticText(win, 400@20).string_("Status: Idle");
tuneText = StaticText(win, 400@20).string_("Tune: (none loaded)");
tempoText = StaticText(win, 400@20).string_("Tempo: -- bpm");

// ---------------------------------------------------------------
// Wire up status callback
// ---------------------------------------------------------------
~tradFour[\onStatus] = { |msg|
    statusText.string = "Status: " ++ msg;
};

// Update tune info when chords arrive
~trad4[\onDone] = { |trad4|
    {
        tuneText.string = "Tune: % (%)".format(
            ~trad4[\title], ~trad4[\inferredKey]
        );
    }.defer;
    // Trigger auto-generate
    "TradFour: auto-generating solo...".postln;
    AppClock.sched(0.1, {
        ~tradFour[\generate].value(~tradFour);
        nil
    });
};

// ---------------------------------------------------------------
// Periodic tempo display update
// ---------------------------------------------------------------
tempoUpdater = SkipJack({
    var tempoStr;
    if(~tradFourClock.notNil) {
        var bpm;
        try {
            bpm = (~tradFourClock.tempo * 60).round(0.1);
            tempoStr = "Tempo: % bpm".format(bpm);
            if(~midiSyncSetup[\useMIDISync]) {
                tempoStr = tempoStr ++ " (from Reaper)";
            };
        } { |err|
            tempoStr = "Tempo: -- bpm";
        };
    } {
        tempoStr = "Tempo: -- bpm";
    };
    // Add bar count if available
    if(~trad4.notNil and: { ~trad4[\totalBars].notNil }) {
        tempoStr = tempoStr ++ " | % bars".format(~trad4[\totalBars]);
    };
    tempoText.string = tempoStr;
}, 0.5, { win.isClosed }, "TradFourTempoUpdater");

"TradFourGUI: window created".postln;
)

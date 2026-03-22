// GrammarLoader.scd — Trad-Four Phase 3
// Loads a JSON grammar file (produced by python/grammar/converter.py)
// and stores it in the ~grammar environment variable.
//
// Usage:
//   ~grammarLoader.load("supercollider/grammars/LesterYoung.json");
//   ~grammar.player       // "LesterYoung"
//   ~grammar.params[\minPitch]  // 58
//
// Weighted random selection:
//   ~grammarLoader.weightedChoose(rulesArray)  // returns one rule

(
~grammarLoader = (

    // ---------------------------------------------------------------
    // Load a grammar JSON file
    // ---------------------------------------------------------------
    load: { |self, path|
        var jsonStr, raw;

        jsonStr = File.readAllString(path.asString);
        raw = jsonStr.parseYAML;

        ~grammar = ();
        ~grammar[\player] = raw["player"];

        // Parse parameters — convert numeric strings to numbers
        ~grammar[\params] = ();
        raw["parameters"].keysValuesDo { |k, v|
            var key = k.replace("-", "_").asSymbol;
            ~grammar[\params][key] = case
                { v == "true" }  { true }
                { v == "false" } { false }
                { v.asString.any(_.isDecDigit) } { v.asFloat }
                { v };
        };

        // P rules (brick and start)
        ~grammar[\pBrickRules] = raw["p_brick_rules"].collect { |r|
            (sym: r["sym"], ticks: r["ticks"].asInteger, weight: r["weight"].asFloat)
        };
        ~grammar[\pStartRules] = raw["p_start_rules"].collect { |r|
            (sym: r["sym"], count: r["count"].asInteger,
             ticks: r["ticks"].asInteger, weight: r["weight"].asFloat)
        };

        // START rules
        ~grammar[\startRules] = raw["start_rules"].collect { |r|
            (rhs: r["rhs"], weight: r["weight"].asFloat)
        };

        // Cluster transition rules
        ~grammar[\clusterRules] = raw["cluster_rules"].collect { |r|
            (lhs: r["lhs"], terminal: r["terminal"],
             next: r["next"], weight: r["weight"].asFloat)
        };

        // Q rules (keyed by Q0, Q1, etc.)
        ~grammar[\qRules] = ();
        raw["q_rules"].keysValuesDo { |qName, rules|
            ~grammar[\qRules][qName.asSymbol] = rules.collect { |r|
                (notes: self.parseNotes(r["notes"]), weight: r["weight"].asFloat)
            };
        };

        // BRICK rules (keyed by ticks string, then brick name)
        ~grammar[\brickRules] = ();
        raw["brick_rules"].keysValuesDo { |ticksStr, byName|
            var ticksBucket = ();
            byName.keysValuesDo { |brickName, rules|
                ticksBucket[brickName.asSymbol] = rules.collect { |r|
                    (notes: self.parseNotes(r["notes"]), weight: r["weight"].asFloat)
                };
            };
            ~grammar[\brickRules][ticksStr.asInteger] = ticksBucket;
        };

        "GrammarLoader: loaded '%' — % params, % brick types".format(
            ~grammar[\player],
            ~grammar[\params].size,
            ~grammar[\brickRules].collect(_.size).sum
        ).postln;

        ~grammar
    },

    // ---------------------------------------------------------------
    // Parse a note array from JSON
    // ---------------------------------------------------------------
    parseNotes: { |self, notesArray|
        notesArray.collect { |n|
            if(n["type"] == "slope") {
                (type: \slope,
                 start: n["start"].asInteger,
                 end: n["end"].asInteger,
                 notes: self.parseNotes(n["notes"]))
            } {
                if(n["type"] == "X") {
                    (type: \X, degree: n["degree"], dur: n["dur"].asFloat)
                } {
                    (type: n["type"].asSymbol, dur: n["dur"].asFloat)
                }
            }
        }
    },

    // ---------------------------------------------------------------
    // Weighted random choice from an array of rules (each has \weight)
    // ---------------------------------------------------------------
    weightedChoose: { |self, rules|
        var weights, total, r, cumulative;
        weights = rules.collect(_.weight);
        total = weights.sum;
        r = total.rand;
        cumulative = 0;
        rules.detect { |rule|
            cumulative = cumulative + rule.weight;
            cumulative > r
        }
    }
);
)

// GrammarExpander.scd — Trad-Four Phase 3
// Grammar expansion from start symbol P.
//
// Two expansion paths:
//   P → BRICK path: choose BRICK rule by duration, expand to note events
//   P → START path: enter Cluster Markov chain, produce Q terminal sequences
//
// Pre-generates the entire solo before playback (matches Impro-Visor behavior).
// Tracks remaining duration in ticks (120 ticks/beat).
//
// Usage:
//   var noteEvents = ~grammarExpander.expand(totalTicks);
//   // Returns flat array of note event dicts: (type: \C, dur: 0.5, ...)
//   // For X notes: (type: \X, degree: "b6", dur: 0.5)

(
~grammarExpander = (

    ticksPerBeat: 120,

    // ---------------------------------------------------------------
    // Main expansion entry point
    // ---------------------------------------------------------------
    expand: { |self, totalTicks|
        var result, remainingTicks, allPRules, clusterIndex;

        result = List.new(1024);

        // Pre-compute combined P rules (avoid ++ on every iteration)
        allPRules = ~grammar[\pBrickRules] ++ ~grammar[\pStartRules];

        // Pre-index cluster rules by lhs symbol for O(1) lookup
        clusterIndex = IdentityDictionary.new;
        ~grammar[\clusterRules].do { |r|
            var key = r[\lhs].asSymbol;
            if(clusterIndex[key].isNil) {
                clusterIndex[key] = List.new(4);
            };
            clusterIndex[key].add(r);
        };

        // Iterative P expansion
        remainingTicks = totalTicks;
        while { remainingTicks > 0 } {
            var eligible, chosen, ticks;

            eligible = allPRules.select { |r| r[\ticks] <= remainingTicks };

            if(eligible.size == 0) {
                // Fill remaining time with rest
                result.add((type: \R, dur: remainingTicks / self[\ticksPerBeat]));
                remainingTicks = 0;
            } {
                chosen = ~grammarLoader[\weightedChoose].value(~grammarLoader,eligible);

                if(chosen.isNil) {
                    // Safety: all weights zero — fill with rest
                    result.add((type: \R, dur: remainingTicks / self[\ticksPerBeat]));
                    remainingTicks = 0;
                } {
                    ticks = chosen[\ticks];

                    if(ticks <= 0) {
                        // Safety: avoid infinite loop on zero-tick rules
                        remainingTicks = 0;
                    } {
                        if(chosen[\sym] == "BRICK") {
                            self.expandBrick(ticks, result);
                        } {
                            // START path
                            self.expandStart(chosen[\count], result, clusterIndex);
                        };

                        remainingTicks = remainingTicks - ticks;
                    };
                };
            };
        };

        result.asArray
    },

    // ---------------------------------------------------------------
    // Expand a BRICK: choose a rule for the given duration
    // ---------------------------------------------------------------
    expandBrick: { |self, ticks, result|
        var bucket, allBrickRules, chosen;

        bucket = ~grammar[\brickRules][ticks];
        if(bucket.isNil) {
            // No rules for this duration — fill with rest
            result.add((type: \R, dur: ticks / self[\ticksPerBeat]));
        } {
            // Collect all rules across all brick types for this duration
            allBrickRules = List.new(64);
            bucket.keysValuesDo { |name, rules|
                rules.do { |r| allBrickRules.add(r) };
            };

            if(allBrickRules.size == 0) {
                result.add((type: \R, dur: ticks / self[\ticksPerBeat]));
            } {
                chosen = ~grammarLoader[\weightedChoose].value(~grammarLoader,allBrickRules);
                if(chosen.notNil) {
                    chosen[\notes].do { |note| result.add(note) };
                };
            };
        };
    },

    // ---------------------------------------------------------------
    // Expand START → Cluster Markov chain (iterative)
    // ---------------------------------------------------------------
    expandStart: { |self, count, result, clusterIndex|
        var startRule, clusterName, step;

        // Choose initial cluster (Cluster0 or Cluster1)
        startRule = ~grammarLoader[\weightedChoose].value(~grammarLoader,~grammar[\startRules]);

        if(startRule.notNil) {
            clusterName = startRule[\rhs];

            // Run Markov chain for 'count' steps
            step = 0;
            while { (step < count) and: { clusterName.notNil } } {
                var eligible, chosen, terminal;

                eligible = clusterIndex[clusterName.asSymbol];

                if(eligible.isNil or: { eligible.size == 0 }) {
                    // No transitions from this state — stop chain
                    clusterName = nil;
                } {
                    chosen = ~grammarLoader[\weightedChoose].value(~grammarLoader,eligible);
                    if(chosen.isNil) {
                        clusterName = nil;
                    } {
                        terminal = chosen[\terminal].asSymbol;

                        // Expand the Q terminal
                        self.expandQ(terminal, result);

                        clusterName = chosen[\next];
                        step = step + 1;
                    };
                };
            };
        };
    },

    // ---------------------------------------------------------------
    // Expand a Q terminal: choose a rule and emit notes
    // ---------------------------------------------------------------
    expandQ: { |self, qName, result|
        var rules, chosen;

        rules = ~grammar[\qRules][qName];
        if(rules.notNil and: { rules.size > 0 }) {
            chosen = ~grammarLoader[\weightedChoose].value(~grammarLoader,rules);
            if(chosen.notNil) {
                chosen[\notes].do { |note| result.add(note) };
            };
        };
    }
);
)

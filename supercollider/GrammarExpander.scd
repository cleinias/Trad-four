// GrammarExpander.scd — Trad-Four Phase 3
// Recursive grammar expansion from start symbol P.
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
        var result;
        result = Array.new(512);
        self.expandP(totalTicks, result);
        result
    },

    // ---------------------------------------------------------------
    // Expand P symbol: choose BRICK or START path
    // ---------------------------------------------------------------
    expandP: { |self, remainingTicks, result|
        var allRules, eligible, chosen, ticks;

        if(remainingTicks <= 0) {
            // Base case: no more time
        } {
            // Combine brick and start P rules, filter by remaining duration
            allRules = ~grammar[\pBrickRules] ++ ~grammar[\pStartRules];
            eligible = allRules.select { |r| r[\ticks] <= remainingTicks };

            if(eligible.size == 0) {
                // Fill remaining time with rest
                var restBeats = remainingTicks / self[\ticksPerBeat];
                result.add((type: \R, dur: restBeats));
            } {
                chosen = ~grammarLoader.weightedChoose(eligible);
                ticks = chosen[\ticks];

                if(chosen[\sym] == "BRICK") {
                    self.expandBrick(ticks, result);
                } {
                    // START path
                    self.expandStart(chosen[\count], result);
                };

                // Recurse for remaining time
                self.expandP(remainingTicks - ticks, result);
            };
        };
    },

    // ---------------------------------------------------------------
    // Expand a BRICK: choose a rule for the given duration
    // ---------------------------------------------------------------
    expandBrick: { |self, ticks, result|
        var bucket, allBrickRules, chosen;

        bucket = ~grammar[\brickRules][ticks];
        if(bucket.isNil) {
            // No rules for this duration — fill with rest
            var restBeats = ticks / self[\ticksPerBeat];
            result.add((type: \R, dur: restBeats));
        } {
            // Collect all rules across all brick types for this duration
            allBrickRules = Array.new(64);
            bucket.keysValuesDo { |name, rules|
                rules.do { |r| allBrickRules = allBrickRules.add(r) };
            };

            chosen = ~grammarLoader.weightedChoose(allBrickRules);
            chosen[\notes].do { |note|
                result.add(note);
            };
        };
    },

    // ---------------------------------------------------------------
    // Expand START → Cluster Markov chain
    // ---------------------------------------------------------------
    expandStart: { |self, count, result|
        var startRule, clusterName;

        // Choose initial cluster (Cluster0 or Cluster1)
        startRule = ~grammarLoader.weightedChoose(~grammar[\startRules]);
        clusterName = startRule[\rhs];

        // Run Markov chain for 'count' steps
        self.expandCluster(clusterName, count, result);
    },

    // ---------------------------------------------------------------
    // Expand a Cluster state: emit Q terminal, transition to next
    // ---------------------------------------------------------------
    expandCluster: { |self, clusterName, stepsRemaining, result|
        var eligible, chosen, terminal, nextCluster;

        if(stepsRemaining <= 0) {
            // Base case
        } {
            // Find cluster rules matching this cluster name
            eligible = ~grammar[\clusterRules].select { |r|
                r[\lhs] == clusterName
            };

            if(eligible.size == 0) {
                // Terminal cluster state (base case with no transitions)
            } {
                chosen = ~grammarLoader.weightedChoose(eligible);
                terminal = chosen[\terminal].asSymbol;  // Q0 or Q1
                nextCluster = chosen[\next];

                // Expand the Q terminal
                self.expandQ(terminal, result);

                // Transition to next cluster state
                self.expandCluster(nextCluster, stepsRemaining - 1, result);
            };
        };
    },

    // ---------------------------------------------------------------
    // Expand a Q terminal: choose a rule and emit notes
    // ---------------------------------------------------------------
    expandQ: { |self, qName, result|
        var rules, chosen;

        rules = ~grammar[\qRules][qName];
        if(rules.isNil or: { rules.size == 0 }) {
            // Unknown Q symbol — skip
        } {
            chosen = ~grammarLoader.weightedChoose(rules);
            chosen[\notes].do { |note|
                result.add(note);
            };
        };
    }
);
)

# sim-grammar status (updated 2026-11-09, stopped for the day)

**Open PRs:** only #237 claude/grammar-12 (prohibition family + near-misses). Everything below it (#193..#236) and all
inherited gzones/gplayers PRs are merged/closed. Branch is current with main (remote merge 099bd30; local == origin).
Pilot gate PASS: all +34 full, Standard +4, 0 regressions; delta is now in the PR body.

**Review request on #237 (NOT started, do this first):** sim-review: Render Silent counts full but "its controller
can't cast spells this turn" bans no one, because `cx_grammar.players()` ignores a StackItem `prev` (the countered
spell's controller). Details in the PR comment. Fix on claude/grammar-12: make `players(..., who="controller")`
resolve a StackItem prev to its controller (or reject the sentence after a spell target), add a test that resolves
Render Silent and checks the ban, then check other "its controller" users after counterspells.

**Shutdown check:** clean. Nothing uncommitted, no WIP commit, nothing unpushed.

**Issues:** #297 parked ("defending player" = controller's opponent edge case). No other lane:grammar issues;
none open for lane:gzones / lane:gplayers.

**Next round (not started):** lists/units-latest.csv is stale against main (many listed damage/"it deals" units
already parse, e.g. Ankh of Mishra, Aether Flash, Arc Trail are full). First run a fresh census on grammar-12
(`~/mtg-worktrees/bin/heavy .venv/bin/python -m mtgsim.database_coverage --save <dir>`, must run outside the
sandbox because of the lock dir; it was stopped mid-run today), then rank. Candidates seen in probes that still fail:
damage sentences with back-refs/riders ("~ deals that much damage to you", "to them", "to each of two targets",
"to any other target", "it deals N to any target and N to you", "each creature blocking it", "target creature
defending player controls", "damage equal to the number of ...") and "you may have it deal / fight ..." (base-form
verbs after "you may have it"). Also from older list: "can't play lands [this turn]", blink (exile then return), "N or more
target creatures".

**Open questions:** none.

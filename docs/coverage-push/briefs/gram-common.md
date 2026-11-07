# Grammar extension lanes (sim-gzones, sim-gplayers, sim-gcond): shared part
Read COMMON.md first, then this, then your own brief.

sim-grammar (Opus) built `mtgsim/cx_grammar.py`: a compositional fallback parser that reads an effect sentence as
subject + verb chain + duration and maps it onto existing engine kinds (PR #189: +280 full cards from a handful of
verbs). Rounds 2-4 (statics, "target player" subjects, "for each" quantities) are stacked behind it, and next it
builds a plug-in VERB REGISTRY plus `mtgsim/GRAMMAR.md` so several agents can add verb families in parallel. You
are one of those agents. Your family's verbs go into your own module(s) that register with that registry; you
never edit `cx_grammar.py` itself (ask sim-grammar or the lead if the interface lacks something).

Phase 1 (now, until the registry is merged; no PR yet):
1. Read PR #189 and sim-grammar's branches: `git fetch origin && git log --oneline origin/main..origin/claude/grammar-1`
   (and grammar-2.. if pushed); `gh pr view 189`. Understand subjects, durations, rejection rules, the AI `side` rule.
2. Go through your work list (`~/mtg-worktrees/briefs/lists/<family>.csv`, ranked by `sole`): group units into
   verb + object shapes, and for each shape note which existing engine kind executes it (grep `engine/kinds/`,
   `@kind(`), or that a new kind is needed. Estimate cards per shape.
3. Write the plan to `~/mtg-worktrees/briefs/plans/<your-name>.md` (verb shapes ranked by cards, engine kind per
   shape, new kinds needed, tricky rules) and send the lead a 5-line summary.
4. Prepare tests (real DB cards, resolved in a game) so you can build as soon as the registry lands.
Phase 2 (when the lead says the registry is merged): `git merge origin/main`, implement your verbs as registry
modules, one verb family slice per PR (aim for 50+ newly full cards per PR), via sim-review like everyone else.

Rules that matter most here: the fallback must reject anything it can't execute faithfully; who is affected
(you / target player / each opponent / each player) must be exact; "up to N", "any number of", optional "may" and
"instead" must be honoured or the sentence rejected.

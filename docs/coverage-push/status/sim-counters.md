# sim-counters handoff (2026-11-06)
Worktrees: ~/mtg-worktrees/counters (branch claude/counters-2) and ~/mtg-worktrees/counters-b (second worktree, shares .venv/cards.sqlite3 via symlinks; never git clean -x/-X).
Open PRs, stacked in order (all approved on code by sim-review, waiting for gate PASS / merge):
 #190 claude/counters-1  each-of-up-to-N targets, X-entry any counter kind, poison that player/its controller/you
 #192 claude/counters-2  per-counter amounts (ctr:<kind> in counting.count: pump/draw/life/damage, equipment/auras)
 #194 claude/counters-3  distribute/remove/move counters, him/her=self, HeuristicAI tests (tests/test_cx_counters_ai.py)
 #217 claude/counters-4  enters with / put counters equal to known quantity or for each (gate PASS: whole stack +99 full)
Local only: claude/counters-5 (in counters-b), branched from counters-4, NO commits, nothing started (stopped before round 5 work). Both worktrees clean.
Merge notes: when a lower PR merges: git fetch origin && git merge origin/main on the next branch, push once. #190 already merged with main (conflict was kinds/__init__.py import list).
Open issue filed: #257 (remove/move drop 'you may').
Next step: round 5. Candidates: engine referent for "each of them" (all previous targets) ~10 cards; #257; fresh scan of units vs real census (my normalised-text scan was unreliable).
Open question: sim-review was 'agent_blocked' (needs interactive input) when I tried to tell it #190 only needs a conflict check.
Rules to remember: lint + own tests only before PR; no local pilot_gate/fast_check; new effect kind => HeuristicAI game test; push only when ready.
Shutdown stop (state final): nothing uncommitted, nothing unpushed except counters-4 merge of counters-3 (local only, harmless). Resume: round 5 = 'each of them' referent.

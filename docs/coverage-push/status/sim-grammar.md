# sim-grammar status (updated 2026-11-06)

**Open PRs, in stacked order** (each one's branch is merged into the next): #193 grammar-3 → #202 grammar-4 → #207 grammar-5 (registry; gzones/gplayers/gcond build on it, ADD-ONLY) → #222 grammar-7 (AI) → #226 grammar-6 (animation) → #229 grammar-8 (evasion + cx_static) → #231 grammar-9 (tap) → #233 grammar-10 (control + AI sides) → #236 grammar-11 (land types) → #237 grammar-12 (can't cast + near-misses).
- Approved, waiting on the gate: #193, #202, #207, #222. The rest are unreviewed. No pilot-gate deltas posted yet; copy them into the PR bodies when they come.
- Issues: #247 → #193, #246/#275/#277 → #222, #273 → #202, #280 → #207 (fixed in 5014cda on grammar-5, not yet merged up into grammar-7..12). Parked: #297 ("defending player" = the controller's opponent; wrong only in edge cases such as Spiteful Returned bestowed on an opponent's creature).

**Shutdown check:** clean. Nothing uncommitted, no WIP, and every grammar-3..12 branch matches origin (all pushed). No work was in progress.

**Local state:** nothing uncommitted. Worktrees: main /Users/andjalis/mtg-worktrees/grammar (on grammar-12). Scratch worktrees r5 (grammar-5) and r2 (grammar-2, obsolete; round 2 lives inside #193) are under this session's scratchpad.

**Next:** answer sim-review2 change requests first; merge grammar-5 up the stack when the next branch is touched (no mass pushes). Per the lead, no new stacking while ~8+ are unreviewed. Candidate next rounds: "can't play lands [this turn]" (needs a single land-play legality check), equipped/enchanted creature "loses <keyword>" statics via cx_static, "one or more / any number of target creatures".

**Open questions:** none.

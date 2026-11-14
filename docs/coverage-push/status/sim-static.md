# sim-static (2026-11-13, stopped 15:20 at the lead's wrap-up)
Open PRs (stack, all pushed, lint + tests/test_cx_static_gate.py green; CI was still queued):
- #433 claude/static-398 -> main: condition gate + quantity scale on grammar statics (cx_static_gate), +130 full. Review fix pushed ("other" in group/host scales = recipient unless the source fits the noun; refused if both); waiting for sim-review's re-check. CI numbers (parse-diff, pilot gate) still to be put in the PR body.
- #437 claude/static-401 -> claude/static-398: characteristic-defining P/T (cx_static_cda, base P/T in continuous.pt/base_pt), +32 over #433.
- #441 claude/static-398b -> claude/static-401: more static conditions (cx_static_cond) + graveyard statics (Anger cycle), +16 over #437.
- claude/static-400 (pushed, NO PR): WIP "~ can't attack/block unless C" as a gated restriction with not(C); measured 0 gain so far (lines still not reaching the gate / conditions unknown: "you control a 1/1 creature", "there is a Mountain on the battlefield") — debug before opening a PR.
Filed #431 (lane:grammar): _count_spec / _xq misread several quantities and copies.fits counts 0 for "instant and sorcery", "legendary creature".
Next: 1) when CI lands, put parse-diff / pilot-gate deltas into #433/#437/#441; 2) finish #400: debug the "unless C" route, then "can't be blocked except by/by <np>" leftovers and "creatures blocking ~" selectors (discovery issue 04); 3) remaining #398 conditions are a thin one-card tail (another X entered this turn, it attacked this turn).

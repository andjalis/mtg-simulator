# sim-static handoff (updated 2026-11-09, stop for the day)
Worktree ~/mtg-worktrees/static, clean, on claude/static-8 (new, = origin/main 52b84d4, no commits yet, not pushed). No WIP.
Open PRs: none. All earlier PRs (#186, #195, #213, #220, #224, #230, #238, #294) are merged.
Open lane issues: #259 chosen-colour anthems (Caged Sun, Hall of Triumph, Heraldic Banner, Gauntlet of Power), #296 (parked: protection-from-chosen-colour AI picks white on an empty board).

Findings this session:
- lists/units-latest.csv is stale for my lane: devotion Gods and Sphere of Duty/Grace/Law show as blockers but are full on main.
  Still partial on main (checked): Ardenvale Paladin ("if at least N COLOR mana was spent to cast ~, ~ enters with a +1/+1 counter"),
  Auriok Champion ("Protection from black and from red"), Caged Sun (chosen-colour anthem + extra mana trigger).
- I started a fresh census (database_coverage via heavy) into my scratchpad and stopped it at shutdown; nothing saved.

Next step:
1. Get a fresh census (lead's, or `heavy .venv/bin/python -m mtgsim.database_coverage --save <dir>` then blocking_units) and re-rank static shapes.
2. claude/static-8: #259 chosen-colour anthems (anthem_sub tag "chosen_color", fits() reads the source's chosen_color; AI picks its own most common creature colour), bundled with #296 if cheap.
3. Then candidate bundles: "protection from COLOR and from COLOR"; "if at least N COLOR mana was spent to cast ~" entering rules (needs mana-spent tracking per colour); attack/block taxes ("can't attack unless its controller pays {N}"); "spells your opponents cast that target ~ cost {M} more"; "~ costs {M} less if it targets a COLOR permanent".
Notes: heavy queue and gh need the sandbox off; make branches with `git switch --no-track -c`; a CardDB check script needs PYTHONPATH=. when run from $TMPDIR.
Open questions: none.

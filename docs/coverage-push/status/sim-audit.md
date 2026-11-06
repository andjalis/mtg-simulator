# sim-audit handoff (updated 2026-11-06, stopped for the machine shutdown)

- Role: behaviour auditor. I have no PRs or branches. The worktree ~/mtg-worktrees/audit is a detached checkout of origin/main at a26de6e and is clean, so there was nothing to commit. Harness scripts are saved in ~/mtg-worktrees/audits/harness/: h.py is the helper module, b1.py and b2.py are this batch. Run them as `PYTHONPATH=. .venv/bin/python <script> ~/mtg-worktrees/audits/harness`.
- **In the middle of:** the audit batch for PRs #185 (keyword costs), #188 (day/night) and #206 (divided damage). No report written yet and no issues filed for it.
  - #185 done, 7 cards:
    - Correct: Borrowed Hostility (escalate gives +3/+0 and first strike; the plain cast picks one mode), Collective Resistance escalate_2 (all three modes resolve), Demonic Collusion buyback with 2 discards, Constant Mists buyback (sacrifices a land, returns to hand), Curtains' Call and Sublime Exhalation undaunted costs ({4}{B}, {5}{W}).
    - Curtains' Call: the AI targets Craw Wurm twice, so only one creature is destroyed. This is the same bug as #275 (fix in #222). Add a comment on #275; don't file a new issue.
    - Demonic Collusion: with only 1 spare card the buyback variant is still listed in `spell_options`, but `cast()` returns False. Check whether the AI's `main_phase` then stops casting for the turn (`if not game.cast: break`). If so, file it as follow-up, lane:mech.
    - Collective Resistance: the AI didn't cast it in main phase, though the board had an artifact and an enchantment to destroy. Probably modal instants are held for responses: can't tell yet.
  - #188 to do. Use Tavern Ruffian, Reckless Stormseeker and Spellrune Painter. Check the cycle in a full turn: no spells makes it night, then 2 spells makes it day. Check that a daybound card entering at night comes in as its back face. Check that Reckless Stormseeker's "target creature you control" can't target an opponent's creature (it parsed as target='creature' with no filter).
  - #206 to do. Use Arc Lightning, Electrolyze, Fire // Ice, Pyrokinesis (creature targets only), Inferno Titan's ETB, and Forked Bolt. Check the AI's division and that a share for a target that has become illegal is lost.
  - Then write ~/mtg-worktrees/audits/audit-<UTC>.md, file issues per the brief (check for duplicates first), notify owners, and tell the lead "audit done".
- Earlier batch (#181–#189) is finished: report audits/audit-20261106T2031Z.md, issues #273 #275 #277 #279 #281 #282. Re-audit as these fix PRs merge: #202 #209 #219 #221 #222 #225.
- Open questions: none.
- Note: gh and git fetch need to run outside the sandbox (network and TLS).

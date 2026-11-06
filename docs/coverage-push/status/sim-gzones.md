# sim-gzones handoff (updated 2026-11-06, machine shutdown)

Worktree ~/mtg-worktrees/gzones (checked out: claude/gzones-4). Plan: ~/mtg-worktrees/briefs/plans/sim-gzones.md.
Reviewer: sim-review2. Working tree clean, every branch pushed, no WIP.

## Open PRs (all base main)
- #228 claude/gzones-1b (+116): zones family (destroy/exile/bounce objects, cx_edict, @ai_value). On claude/grammar-7 (#222).
  Last push: fixed CI fast-check failure (tests/test_chonk_smol6_reveal_dig expected Extract the Truth's edict mode
  unsupported; it is now read by cx_edict, assertion updated).
- #232 claude/gzones-3 on #228: core.json removal wordings narrowed (8 false-full -> honest partial).
- #241 claude/gzones-2 on #228: Game.put_in_library + library_top/bottom; old tuck kinds off the graveyard; cx_tuck (+26).
- #288 claude/gzones-4 on #228: cards out of an exact graveyard, cx_card_move (+28).
All four had gzones-1b merged in and pushed; 197 related test modules (5.4k tests) pass locally on each.

## Next step
1. Re-check CI on #228/#232/#241/#288 (fast check reruns after the push; read the pilot-gate comment) and fix FAILs
   on the branch (fix on 1b first, then merge 1b into 3/2/4).
2. gh issue list -R andjalis/mtg-simulator --label lane:gzones --state open.
3. Next round (not started): blink "exile <obj>, then return it/that card to the battlefield under its owner's/your
   control [tapped]" (~29 sole), branch from claude/gzones-1b; then back-references only where unambiguous.

## Open questions
None.

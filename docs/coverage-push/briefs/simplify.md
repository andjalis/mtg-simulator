# Lane: simplified -> full (you are `sim-simplify`, branch prefix `claude/simplify`, worktree ~/mtg-worktrees/simplify)
Read COMMON.md in this folder first.

396 cards parse but carry a recorded simplification (status `simplified` in
`results/database_coverage_2026-11-06/cards.csv`, column `simplifications`). Each is a place where the engine
plays something close to, but not exactly, the printed rules. Your job: implement the real rule so the
simplification disappears and the card becomes full. Grouped by simplification (cards):
madness 46, unearth cast like a spell 38, cost reduction ignored 37, divided damage on resolution 27,
day/night not tracked 27, mana amount fixed 23, mutate 22, backup grants only keywords 20, enchanted-land extra
mana colour 15, never paid 13, tap-lock single skipped untap 13, filter lands 10, mana pool empties each phase 9,
harmonize 8, tribute always paid 8, and a tail. Grep the repo for each simplification string to find where it is
recorded. Rank by cards per code (day/night, madness, unearth and cost reduction look like the best ratios);
send the lead a short ranked plan before coding, then one rule per PR. Your PRs touch existing modules more than
other lanes do: keep diffs tight and say in the PR which lane's files you touched.

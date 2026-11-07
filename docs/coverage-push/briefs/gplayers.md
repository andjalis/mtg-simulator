# Lane: grammar verbs: player effects (you are `sim-gplayers`, branch prefix `claude/gplayers`, worktree ~/mtg-worktrees/gplayers)
Read COMMON.md and gram-common.md first. Work list: lists/players.csv (3,675 units, 1,703 cards blocked by one).
Verbs: deals N damage to <any target / each creature / each opponent / that player ...>, loses / gains life,
draws, discards (at random, chosen, "a card", "their hand"), mills, reveals, looks at. sim-grammar's round 3 adds
"target player/opponent" subjects and an AI side rule: build on it rather than duplicating it. Damage sources
("~ deals", "it deals", "that creature deals") and division ("divided as you choose") must be exact or rejected.
"For each" / "equal to" amounts come from the conditions lane (sim-gcond) and sim-grammar's round 4: coordinate,
don't duplicate.

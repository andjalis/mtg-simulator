# sim-gcond status (2026-11-09, stopped for the day)

State: clean. Nothing uncommitted, no WIP commit needed, nothing pushed today. No open PRs: #215 and #290 are merged
(#239's commits went in through #290, which was stacked on it). No open lane:gcond issues.
Worktree is on a new local branch `claude/gcond-4` = origin/main @ 52b84d4, with no commits yet and nothing pushed.
(The upstream config write failed in the sandbox, which is harmless: push with `git push -u origin claude/gcond-4`.)

What I did today (analysis only, no code):
- `lists/conditions.csv` (09:26 today) looks partly stale: units such as "if {R} was spent to cast it" are already
  handled in cx_condlib, so re-check every candidate unit against the current parse before choosing work.
- I started a fresh census of main (`database_coverage --save <scratchpad>/census_base`, through `heavy`) and stopped it
  at the lead's request, so it didn't finish. Start of next session: run it again (needs the sandbox disabled, because
  `heavy` writes ~/mtg-worktrees/.locks; takes more than 10 minutes, so run it in the background), then
  `blocking_units` on its cards.csv for real gcond units.
- The referent-stat family ("equal to its power / that creature's toughness / target creature's power / that card's
  mana value"): 704 DB cards match, 443 of them partial, but it is a very long tail (1-2 cards per wording). Today
  `_xq` maps "its power" to ("stat","self"), meaning the source. It needs a general rule: resolve "its" / "that creature's"
  to the subject or the previous object of the sentence, and "target creature's" to a target.
- "If C, B" units with a known body and an unknown condition: about 226 sole cards in total, the largest being "you lose the
  flip" (7), "this ability has been activated N or more times this turn" (3), "you controlled that permanent" (3),
  "a card left your graveyard this turn" (3), "you control your commander" (3), "<thing> is dealt damage / destroyed this way" (~6).

Next step (round 4, on claude/gcond-4): pick one of these from the fresh census:
  (a) referent stats for "equal to <ref>'s power|toughness|mana value", bound to the grammar subject/object (a general rule,
      largest pool), or
  (b) a batch of cx_condlib conditions: "this way" results, coin flip, activation count, "left your graveyard this turn".
Then the "for each" bodies with data['scales'], and "for as long as <cond>" durations (still open from the last note).
Tool: my scan script (status and ignored lines of DB cards matching a regex) was in the session scratchpad and may be gone.
It's about 30 lines: CardDB() + coverage.card_coverage over `SELECT name, oracle_text FROM cards`.
Open questions: none.

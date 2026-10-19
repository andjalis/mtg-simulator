# Joint costs, type/color views and phase triggers

This batch adds joint mana and sacrifice/craft planning, including multiple
sacrifices, fallback additional mana and reserved X resources. It adds scoped
type/subtype/color continuous effects with copiable values and last-known
characteristics, plus shared upkeep/end-step triggers with phase-player context
and recognized intervening-if checks at triggering and resolution.

Unknown token keywords/trailing clauses and unsupported relative-clause copy
selectors remain visible as coverage gaps. These corrections can lower a card's
template status even while the engine gains support elsewhere.

The implementation was ported as file changes onto public main
`5bb050e302a1771baee7102127182786a2b3f363`. The engine, parser and rules files touched
by the previous batch exactly matched their pre-split base; no old Git ancestry
was imported. The public clone contains no `web/` history. The old checkout and
archive were preserved. The separate local-only Scryfall branch was unavailable
in this execution environment; the public main does contain the gzip/JSON Lines
download fix, but that does not verify every change on that local-only branch.

AI behavior, Forge measurements and private gauntlet code are outside this batch.
While validation ran, public main advanced to
`29851a4`, merging the engine file split, AI fixes and Forge results. This branch
reconciles the file split by keeping casting in `play.py` and moving the activation
planner changes to `abilities.py`. The merged Round 18 test combined two different
lint cleanups and referenced an undefined `h2`; this branch retains the second-Hero
assertion and restores its variable. Upstream AI behavior and Forge results are
preserved as merged, with no additional changes to either.

Validation and inventory results are recorded in `validation.json`. Full database
CSVs and scenario traces are generated locally instead of checking large duplicate
inventory files into this patch. Reproduce the scenario ledger with:

```sh
python3 -m unittest discover -s tests -t . -q
python3 scripts/lint.py  # requires the CI-only pyflakes package
python3 -m mtgsim.behavior_coverage --run --save /tmp/costs-types-triggers-evidence
python3 -m mtgsim.database_coverage --save /tmp/costs-types-triggers-inventory
```

The inventory uses the existing local database; a newly downloaded database may
have different totals. Full template matching is distinct from complete card
rules support, which remains unmeasured. Scoped scenario passes apply to the
declared capability subsets, not every card in the database. Payment planning
still delegates to the existing mana solver; type/color effects are registered
through the continuous-effect API rather than a general Oracle-text parser.

The existing parse-diff script compares `repr(CardDef)`, which contains only a
card's name. Its no-new-exceptions check is useful, but its reported count of
changed parses does not measure these behavior/template changes. The separate
inventory delta in `coverage-delta.json` records status and ignored-text changes.

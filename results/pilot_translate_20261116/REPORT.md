# Pilot: per-card translations instead of parser growth (2026-11-16, opus-pilot)

**Question:** if each PARTIAL card's Oracle text is translated by hand straight into the engine's own structures
(stored per card, loaded instead of the parser's result), how many cards does that cover, how fast, and how often
are the translations wrong?

**Short answer:** about **1 in 7 partial cards** (14.5%, 95% CI 10–20%) can be translated using only what the engine
already runs and still pass verification; another 2% have text with no effect in this simulator (commander/draft,
2-player). Most cards (74%) need an engine capability that doesn't exist yet: about a third of those are small
(one missing condition predicate, selector trait, cost or quantity in an existing system), the rest are real
features. **16% of translation attempts failed verification at least once** and 9% couldn't be fixed without
engine work. Two more passed only by accident and were caught later. Translation is fast, but it isn't a way
round the engine work: it reaches the same wall the parser does, just sooner.

## Method

- **Sample:** 200 PARTIAL cards on main at the branch point (3aea767a; 12,104 partial), seeded random draw,
  **seed 20261116**, stratified by primary type x rarity (proportional, largest remainder), excluding the
  498 partial cards whose exact name appears in an open PR's diff or body (57 open PRs). Script:
  `scripts/translate_sample.py`; list: `sample.tsv`. Rarity came from the same-day Scryfall Oracle bulk file.
  Note: the exclusion is a substring match, so it slightly under-samples cards with short common names.
- **Format** (`mtgsim/translated.py`, files in `mtgsim/data/translated/<slug>.json`): patches that `set`/`add`
  CardDef fields with tagged JSON (`{"$dc": "mtgsim.cards.model:Effect", ...}`, tuples, frozensets). Encoding is
  exact (round trip checked on 600 random parsed cards). A file applies only while the card's Oracle hash **and**
  the parser's ignored lines are unchanged; otherwise the card stays as the parser left it.
  `translated.check` rejects unknown CardDef fields and effect kinds with no engine handler.
- **Hook:** one line in `CardDB.get`: `translated.apply(card_from_scryfall(...))`.
  `MTGSIM_NO_TRANSLATIONS=1` turns it off.
- **Label:** coverage reports a translated card as `full (translated)` (`coverage.TRANSLATED`), counted
  separately by `card_coverage`, `deck_coverage` and `scripts/coverage_check.py`. Never mixed into parser-full.
- **Verification** (`tests/translated/test_cards.py`, harness `tests/translated/harness.py`, runner
  `scripts/translate_verify.py`). The docstring of each test class states the expected outcome from the Oracle
  text, written before the translation was run. The test drives the real engine (fixed seed) and asserts zones,
  life, counters, P/T, tapped state and targets. It also plays 3 seeded HeuristicAI games with 4 copies in the
  deck: no exceptions, hostile effects never aimed at the controller, and (where the card is proactive) the AI
  must actually use it.
- **Authoring:** `scripts/translate_tool.py` (`show`, `probe`/`probes`, `new`, `check`). Most translations
  were built by finding a wording the parser already turns into the right structures (`probe`), checking that
  it means the same thing as the Oracle text, then editing the structures by hand (gates, targets,
  conditions). That's the cheap path, and it's also why so many cards land in "needs-engine-small".
- **Strictness:** after the lead's instruction (and a reconciliation with opus-discovery), "needs-engine"
  means no existing effect kind or engine system can express the card, not just that the parser lacks a
  template. I re-audited every verdict: 5 moved from needs-engine to translated, and Breathkeeper Seraph
  was a miscall (soulbond exists).

## Results (200 cards)

| Outcome | Cards | Share |
| --- | ---: | ---: |
| translated + verified | 29 | 14.5% |
| translated no-op (text has no effect here: commander/draft only, turn order with 2 players) | 4 | 2.0% |
| translation failed verification (card left partial) | 3 | 1.5% |
| needs-engine-small (one predicate/selector/cost/quantity missing in an existing system) | 50 | 25.0% |
| needs-engine (a missing feature) | 98 | 49.0% |
| skipped (Un-cards, Planechase, draft-matters) | 16 | 8.0% |

Per card: `outcomes.tsv` (verdict + named capability) and `percard.tsv` (plus the parser's ignored clauses).

**Whole-database check** (`coverage_check --base 3aea767a`): exactly 33 cards moved from partial to
`full (translated)`, with no other parse changes, no lost full cards and no parse errors. `fast_check`: PASS.

### Translation error rate

Of 32 translations that reached the tests (29 kept + 3 failed):

- **5 failed verification at least once (16%).**
  - Alistair, the Brigadier: missing the `paid` gate, so the pump happened unpaid. Fixed.
  - Thunder Salvo: the count read 0 because of the loader issue below. Fixed in the loader.
  - Wall of Resistance: the `hist` "~ is dealt damage" isn't per permanent. Unfixable without engine work.
  - Brackish Blunder: `prev_is tapped` doesn't see a bounced creature's state. Unfixable.
  - Blizzard Brawl: the rules tests passed, but HeuristicAI never casts the composed version. Unfixable without
    AI work.
- **2 passed for the wrong reason (6%).** The Raven Man and Proctor of Potential use turn-history conditions,
  and the condition library only counts history "heads" registered as a side effect of parsing. Their tests
  passed only because other parsed text had registered the same heads. The loader now registers every head a
  translation uses (`_register_history`). That is the clearest case of a wrong translation passing its tests.
- **3 kept with a documented edge deviation:**
  - Death Baron: wrong only if the Baron itself becomes a Skeleton.
  - Thunder Salvo: a copy that wasn't cast gets 1 less damage.
  - Keeper of the Beasts: the opponent isn't really targeted, which only matters for player hexproof, and the
    engine doesn't model that.
- **2 close readings:**
  - Mirkwood Bats: "you create a token" is read as "a token you control enters".
  - Telekinetic Bonds: the second "you may" after paying is dropped.

  Both are listed in the files' `notes`.

The verification itself was fallible. 8 specs or harness steps needed fixing; every one is recorded in the
test docstrings or in `outcomes.tsv`:

- 3 were my spec errors: Nils (the AI legally declines "up to one"), Squirrel Girl (she is a Squirrel), and
  Transmogrant's Crown (P/T misremembered, corrected from the Oracle text before the first run).
- 3 were too few lands or a wrong token name.
- 2 were harness gaps: per-effect target padding and load order.

### Speed

All agent wall-clock time, one agent:

- Infrastructure (format, loader, coverage label, sampler, harness): about 40 min.
- Per-card phase (all 200 triaged, 36 translation attempts written and verified, strict re-audit):
  **20:51 to 21:25, about 35 min.** That's about **340 cards triaged/h** and **about 50 verified translations/h**.
- Verification run: 108 tests in 230 s (the AI smoke games dominate). Whole-database checks via `heavy`:
  about 4 min each.

### Extrapolation to all ~12,100 partial cards

Wilson 95% intervals:

| Outcome | Share (95% CI) | Cards (95% CI) |
| --- | --- | --- |
| translated + verified | 14.5% (10.3–20.0%) | **≈1,750 (1,250–2,400)** |
| incl. no-ops | 16.5% (12.0–22.3%) | ≈2,000 (1,450–2,700) |
| needs-engine-small | 25% (19.5–31.4%) | ≈3,000 (2,350–3,800) |

Each needs-engine-small card is one small engine addition away. They are mostly different additions, so each
one unlocks few cards.

Effort for all 12,100: about 36 agent-hours of triage and translation, plus the independent audits. Expect
about 9% of attempts to need engine work anyway and about 6% to pass tests for the wrong reason unless the
harness gets stronger.

### Top missing capabilities (how many sampled cards each would unlock)

1. Alchemy/digital mechanics: perpetual, seek, conjure, spellbook, boons, specialize. **14**
   (an engine feature family).
2. New condition predicates for existing condition systems. **About 12**, each with 1–2 cards. Examples:
   - least power;
   - surge paid;
   - clash won;
   - "if you can't";
   - dealt noncombat damage this turn;
   - attacked last turn;
   - never dealt damage;
   - extra turn;
   - "not named ~" died.
3. New selector traits or card filters. **About 9**:
   - unblocked;
   - has a {T} ability;
   - mana value exactly X;
   - with flashback;
   - with cycling;
   - power greater than base power;
   - creature and/or Vehicle count;
   - subtype-union copy condition;
   - non-Human source.
4. Linked exile pools with retrieval (Shelob, Sisters of Stone Death, Gelatinous Cube, Gustha's Scepter). **4**
5. Delayed "when that creature dies this turn" on a target (Fatal Fissure, Devouring Tendrils). **2**;
   fight between two targets (Dissension; Blizzard Brawl's AI). **2**
6. Emblems that grant abilities (Koth, Tezzeret, Nissa). **3**; mana-ability triggers (Forsaken Monument,
   Nissa, Who Shakes the World). **2**; search hand and/or library or graveyard (Last Light, The Five Doctors).
   **2**; "move any number of counters" (Forgotten Ancient, Aetherborn Marauder, Galloping Lizrog). **3**
7. Costs: loyalty −X, discard a named card, sacrifice by colours, life per counter, energy unearth,
   "tap N <subtype>". **6**, one each.

The long tail is the finding. Outside the digital family, no single capability unlocks more than about 2% of
the sample.

## Risks

- **Wrong translations that pass tests.** Shown above (6% passed for the wrong reason; 3 edge deviations
  kept). A test checks one board, and a translation can be right there and wrong elsewhere. The independent
  audit of about 40 translations is the real error estimate.
- **Hidden parse-time side effects.** The engine has state the parser fills in as it reads text: turn-history
  heads, now handled in the loader. There are probably others (registries filled by template modules). A
  translation built from structures alone can silently miss them.
- **Maintenance when the engine changes.** Translations store engine internals: kind names, data keys,
  `lib:` codes, Activated/Trigger field names. A refactor of any of these breaks translations silently unless
  `translate_verify.py` runs in CI. `check()` catches unknown kinds and fields, but not changed semantics.
  Staleness guards (Oracle hash and ignored lines) turn errata and parser changes into "not applied". When
  the parser learns a translated card's last line, the guard drops the translation, which is the right
  outcome.
- **Tests that pin parser gaps collide with translations.** One existing test, `test_cx_combat_costs`
  (Nils), asserted a gap that the translation filled. I changed it to read the parser's own result. More of
  these will appear as coverage grows.
- **Rules drift and AI blindness.** A translation can be rules-correct while the AI can't use it (Blizzard
  Brawl), because AI heuristics key on the parser's usual effect patterns.
- **Coverage optics.** `full (translated)` is labelled separately so it can be audited, but deck coverage
  percentages now include it. Readers should know the two numbers differ in kind.

## For the independent audit

`audit_list.tsv`: card, translation file, test class (33 files: 29 translations and 4 no-ops). Each JSON file
has `notes` explaining non-obvious choices and deviations. Each test class docstring is the expected outcome
from the Oracle text. Failed translations are kept in `failed/` with their skipped tests.

## Files

`mtgsim/translated.py`, `mtgsim/data/translated/*.json`, the hook in `mtgsim/carddb.py`, the label in
`mtgsim/coverage.py` and `scripts/coverage_check.py`, `scripts/translate_{sample,tool,verify}.py`,
`tests/translated/`, `tests/test_translated_loader.py`, and `results/pilot_translate_20261116/`.

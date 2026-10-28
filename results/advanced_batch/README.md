# Thirty shared card capabilities

All thirty requested tasks are implemented through shared rule paths. All 32
originally ignored example clauses now match. Twenty-two example cards are full
template matches; eight retain nine unrelated ignored clauses. The
[completion archive](completed-backlog.json) preserves the original scopes, and
[clause results](completed-clauses.json) record what remains on each example.
The [active backlog](../../BACKLOG.md) excludes every completed effect.

## Implementations

| Shared capability | Behavior covered |
| --- | --- |
| Base-stat predicates | Printed/base-setting characteristics, separate from counters and pumps; grouped Bess entries |
| Equipment grants | Attached recipient activates and pays; moving or suppressing the Equipment removes the grant |
| Event quantities | Triggering spell's fixed and X mana payments captured in its context |
| Counter allocations | One declared slot per counter; repeated recipients aggregate before replacement; illegal targets lose their assigned counters; ward triggers once per recipient |
| Next-turn durations | Stat changes persist through cleanup and expire as the effect controller's next turn begins |
| Multiple graveyard targets | Optional distinct targets sharing a creature type, Changeling, and physical generation references |
| Sacrifice protection | Opponent-controlled resolving effects cannot force sacrifice; voluntary activation/casting costs remain payable |
| Token abilities | Quoted activated bodies become recipient-bound abilities on created tokens |
| Aura predicates | Non-subtype host filters apply to casting, attachment, movement and state checks |
| Activation discounts | Creature abilities receive generic reductions with the printed one-mana floor |
| Attack taxes | Each attacker pays for attacking the player; attacks at planeswalkers are exempt |
| Control durations | Aura attachment/controller/ability changes, source-bound ETB control, and indefinite control preserve object ownership |
| Graveyard library placement | Targeted type unions, top-of-library placement, and untapped-entry trigger conditions |
| Opponent payments | The triggering opponent can pay to prevent the controller's draw |
| Populate | Copy a chosen creature token's copiable values; entry batching and token doublers |
| Counter replacements | Each active source adds to a positive placement, including entry counters; removals remain removals |
| Token replacements | Clue/Food/Treasure creation becomes one of each; multiple Manufactors and doublers compose |
| Sunburst | Distinct colored mana actually assigned to payment; charge or +1/+1 entry counters; uncast entries have none |
| Energy | Shared player resource, triggered gains, validated activated costs and payment |
| Draw replacements/limits | Each replacement source applies once per event; first draw-step draw exception; per-turn opponent limits |
| Graveyard replacements | Discard, mill, spell destinations, death, tokens and other zone insertions redirect to exile |
| Graveyard permissions | Per-source, per-own-turn instant/sorcery casts; source availability and exile on resolution/countering |
| Cipher | Optional encoding and combat triggers; current host controller casts a free copy; stale references and ability suppression end applicability |
| Aftermath | Right half only from the graveyard; exile on resolution, countering or bouncing |
| Opponent exile permissions | Look/select/random bottom placement, face-down exile flag, persistent generation-bound permission, any-mana payment and owner destinations |
| Conditional casting limits | Opposing noncreatures compare mana value with their caster's actual land count |
| Land conversion | Nonbasic lands become Mountains, lose printed abilities and gain red mana; entry abilities are removed before entry and characteristics restore when the source leaves |

Exact templates are conservative: unimplemented variants such as allocating X
counters remain ignored. These implementations do not establish complete Magic
rules correctness or full support for every wording in a mechanic family.

## Measurements and validation

The complete **34,129-card** census improves **278 cards**, including **129 newly
full matches**, with zero status regressions and zero parser errors.

| Classification | Before | After |
| --- | ---: | ---: |
| Full template match | 11,840 | 11,969 |
| Recorded simplifications | 228 | 229 |
| Partial | 22,061 | 21,931 |
| Parser error | 0 | 0 |

The 67 new behavior tests pass. The final full run executes all **1,490 tests** in
117 modules: **1,489 pass and one optional test skips**, with zero failures or
errors. Discovered and executed IDs match exactly, including duplicate discovery
occurrences. Lint reports zero findings and whitespace checks pass. Runtime/test
source hashes recorded before the run are verified unchanged afterward. The full
run took 210.4 seconds with four module processes.

## Choices and reproduction

Existing `cast` and activation APIs accept explicit targets. Fixed counter
allocations use one target entry per counter: `[a, a, a, b]` assigns three to `a`
and one to `b`. Optional `choose_populate`, `choose_encode`, `choose_cipher_cast`
and `choose_exile_card` policy hooks can override deterministic defaults. The
simulator continues to use its existing information/AI model; the face-down flag
does not introduce a separate hidden-information policy engine.

Run the behavior checks with:

```sh
.venv/bin/python -m unittest tests.test_advanced_batch -q
.venv/bin/python scripts/lint.py
```

The full validation and database coverage measurements are recorded in
[validation.json](validation.json), [coverage-delta.json](coverage-delta.json) and
the [complete after census](after/README.md). Test runs use four isolated module
processes and a temporary regex cache capacity of 32,768; the production cache
and test assertions are unchanged. No win-rate or pilot-strength claim is made.

# Counter and combat card batch

This batch implements all ten requested changes. The nine named cards now have
no ignored text or declared simplifications in the local database's parser output.
Template matching remains distinct from complete rules verification.

| Change | Implementation and direct tests |
| --- | --- |
| Graft | Entry counters, independent native instances, optional transfers to either player's entering creature, source/recipient departure, and source death after its last counter moves |
| Any-counter costs | Tayam grants vigilance counters and pays with mixed positive counter types from controlled creatures; its existing mill/return effects can return a newly milled permanent |
| X counter costs | Retribution's debuff uses the selected counter payment rather than mana spent; zero is legal, while negative and unavailable amounts fail |
| Positive variable costs | Ooze Flux requires at least one +1/+1 counter and creates a green Ooze whose size is fixed by the counters actually paid |
| Counter inheritance | Parish-Blade Trainee transfers all positive counter types using last-known values and a legal recipient |
| Training events and linked exile | Savior's exile triggers specifically from training; battlefield and graveyard choices, optional zero targets, generation checks and leave-triggered returns are covered |
| Granted dethrone | Marchesa grants independent instances to other controlled creatures; they stack with native dethrone and end when the source leaves |
| Delayed return | Marchesa schedules the exact dying card for the next end step under the trigger controller; tests cover stolen creatures, tokens, source departure, simultaneous destruction/sacrifices, and graveyard reentry |
| Additional combats | Scourge checks its first declared attack, rechecks its intervening-if condition, untaps current attackers, and inserts combats before the second main phase |
| Optional attack payments | Gryffwing targets another nonflying attacker before resolution, can decline or fail payment, and grants temporary flying only after successful payment |

The implementation adds last-known trigger snapshots for objects leaving the
battlefield. Losing abilities before departure suppresses a printed death trigger;
losing training after it triggered does not cancel its counter effect. A newly
lethal creature caused by the loss of a static source does not reuse that source's
counter-death listener as though the deaths were simultaneous.

Shared payment planning reserves storage counters separately from counter costs.
An unreserved storage counter may pay mana, and reserving every storage counter
still permits a land's ordinary mana ability. Counter donors consumed by mana
abilities remain unavailable for the subsequent counter cost. Failed activations
restore the engine state through the existing transaction boundary.

## Choices

The public activation API keeps existing calls compatible:

```python
game.activate_ability(player, retribution, 0, [target], x=2)
game.activate_ability(player, ooze_flux, 0, x=3)
game.activate_ability(player, tayam, 0, counter_choices=[
    (first_creature, "vigilance", 1),
    (second_creature, "charge", 2),
])
```

Choices are positive `(permanent, counter type, amount)` triples. Repeated entries
are summed and cannot spend a counter twice. Without explicit choices, fixed costs
prefer non-stat counters and variable costs choose the largest payable amount.
The optional `choose_graft(game, player, source, recipient)` AI hook can accept or
decline a transfer; the default accepts transfers to its own creatures and declines
transfers to opponents. Existing attack-selection heuristics are unchanged.

## Validation and coverage

`tests/test_counter_card_batch.py` adds 56 behavior tests across all ten changes,
including default-pilot selection and automatic targeting for counter-based X.
The focused regression run also includes payment transactions, storage/restricted
mana, identity events, existing creature keywords, and combat triggers.
`smoke.json` records automatic main-phase activation of Retribution and Ooze Flux
with both HeuristicAI and BaselineAI, plus real-database checks for Llanowar Reborn
and Broodguard Elite. These are functional checks, not pilot-strength comparisons.

The targeted inventory compares 84 database records containing the relevant
wording, keeping the same Forge-derived database in both runs. There are no parse
errors. Twenty-nine records improve, with sixteen becoming fully template-matched
and one becoming simplified. The other improvements retain their remaining ignored
text. `coverage-delta.json` records the exact changes and database metadata; this
is not a full-database census or a claim of complete rules support for those cards.

Direct checks can be rerun from the repository root:

```sh
.venv/bin/python -m unittest tests.test_counter_card_batch tests.test_shared_counter_costs tests.test_training_dethrone tests.test_costs_types_triggers tests.test_zone_actions_layers tests.test_identity_events tests.test_creature_keywords tests.test_combat_triggers tests.test_storage_lands tests.test_restricted_mana -q
.venv/bin/python -m unittest discover -s tests -t . -v
.venv/bin/python scripts/lint.py
```

The full run in `validation.json` uses four independent unittest processes, grouped
by module. Its discovered and executed test inventories are compared as multisets,
so duplicates, missing tests and extra tests are accounted for. Every worker's
exit status, failures, errors, skips and expected/unexpected outcomes are retained.

The engine remains a two-player simulator with bounded parser templates and an
incomplete general layer/replacement system. Variable typed counter costs covered
here are +1/+1 costs and unspecified counter types; arbitrary named-counter cost
wordings and unbounded "any number" costs are still ignored. Existing keyword-set
grants can still coalesce repeated grants stored in the same set; printed and
separate Marchesa grant instances are counted independently. These changes do not
add an arbitrary delayed-trigger language or certify simulator win-rate accuracy.

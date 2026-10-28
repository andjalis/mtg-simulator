# Training and dethrone

Training and dethrone now use attack triggers on the existing stack. Training checks
for another attacking creature its controller controls with strictly greater power.
Dethrone checks that the attacked player has the highest life total, including ties
and the attacker's controller. Attacking a planeswalker does not trigger dethrone.
Neither ability rechecks its condition on resolution. Counters go on the original
permanent only if it is still on the battlefield.

Printed instances stack, as do native and Equipment/Aura-granted instances. The
existing keyword representation also supports training tokens and temporary grants.
Repeated grants stored in the same temporary/permanent keyword set still coalesce;
this batch does not implement a general ability-layer or grant-instance system.
AI attack selection is unchanged.

`tests/test_training_dethrone.py` exercises actual combats, attack-time power and
life checks, multiple instances, token creation, Equipment grants, suppression,
and responses that remove an ally, remove/reenter the source, or change life totals.
The focused run also covers existing exalted behavior because its instance counting
is shared with these keywords.

The database comparison examines all 35 records whose JSON contains `training` or
`dethrone`, using the same local Forge-derived database before and after the change.
Twenty records lose ignored text. Nine become fully template-matched:

- Apprentice Sharpshooter
- Enraged Revolutionary
- Grenzo's Cutthroat
- Gryff Rider
- Marchesa's Emissary
- Marchesa's Infiltrator
- Rural Recruit
- Torens, Fist of the Angels
- Treasonous Ogre

Template matching is not complete rules verification. Other ignored text remains
visible, including Marchesa's team grant and delayed return, Hopeful Initiate's
shared counter cost, Savior of Ollenbock's training-event trigger, and Scourge of
the Throne's additional combat. The comparison does not claim a full-database
census or certify the remaining abilities on all affected cards.

Run validation from the repository root:

```sh
.venv/bin/python -m unittest tests.test_training_dethrone tests.test_infect_devoid_exalted -v
.venv/bin/python -m unittest discover -s tests -t . -v
.venv/bin/python scripts/lint.py
```

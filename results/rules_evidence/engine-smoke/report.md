# Small archetype diagnostic

Status: complete. Run identity: `a502334bf15e8419c6ae02ef8b9efeb40588e223b3919e7baae00ffcb8272126`.

Repository fixtures, main-deck games only. Mixed card pools; no claim of format legality, tournament provenance or current metagame representativeness.

Main-deck games only; no sideboarding or BO3 match prediction. Results measure deck + rules implementation + AI pilot under these settings. Forge is an independent comparator, not ground truth. Both pilots can misplay, especially control and combo; agreement cannot establish human accuracy. Confidence intervals describe sampling uncertainty under an independent-game model, not rules errors or pilot bias. Ranks and MMR elsewhere in this project are internal pool scores, not Arena equivalents.

## Coverage and human evidence

- Missing coverage: combo: one compact curated fixture only (Kiln Fiend); no copy-effect combos (Reflection of Kiki-Jiki copying is unsupported) and no tournament-sourced combo list
- No verified human main-deck game dataset applicable to these exact lists and conditions. No human matchup expectations are asserted. Tournament BO3 match rates and archetype popularity are not main-deck game evidence.
- Human expectations are absent for every matchup without reviewed, applicable game evidence.
- Repository deck comments are not evidence of format legality or tournament provenance.

## Run configuration

Engines: builtin, forge; 2 games per pairing/engine; seed 1; Forge jobs 1, game clock 15 s, worker wall timeout 120.

Full content fingerprints, settings and counts: [results.json](results.json).

- aggro (aggro): 60 main-deck cards. Pressure, burn, prowess and adventure decisions.
- midrange (midrange): 60 main-deck cards. Discard, removal, threats and graveyard/transform decisions.
- control (control): 60 main-deck cards. Counters, sweepers, planeswalkers and delayed win conditions.
- combo (combo): 60 main-deck cards. Compact curated Kiln Fiend + double-strike fixture: cast triggers, keyword grants, pump and burn sequencing.

## Simulated games

A win probability counts draws as non-wins; its 95% Wilson interval uses all games. Score = (wins + half draws) / games and is displayed separately. Small samples are diagnostic only.

| Matchup (A vs B) | Engine | W–L–D | A win probability (95% CI) | A score | Review logs |
|---|---|---|---|---|---|
| aggro vs control | builtin | 1–1–0 | 50.0% (9.5%–90.5%) | 50.0% | [first-game.log](logs/aggro-vs-control/builtin/fe71fa50b20d/first-game.log) |
| aggro vs control | forge | 2–0–0 | 100.0% (34.2%–100.0%) | 100.0% | [worker-0.log](logs/aggro-vs-control/forge/80ce8e41f0e8/worker-0.log) |
| aggro vs midrange | builtin | 1–1–0 | 50.0% (9.5%–90.5%) | 50.0% | [first-game.log](logs/aggro-vs-midrange/builtin/4cd6baf74bc9/first-game.log) |
| aggro vs midrange | forge | 1–1–0 | 50.0% (9.5%–90.5%) | 50.0% | [worker-0.log](logs/aggro-vs-midrange/forge/031bbc5cedb8/worker-0.log) |
| combo vs midrange | builtin | 1–1–0 | 50.0% (9.5%–90.5%) | 50.0% | [first-game.log](logs/combo-vs-midrange/builtin/3892388321d5/first-game.log) |
| combo vs midrange | forge | 0–2–0 | 0.0% (0.0%–65.8%) | 0.0% | [worker-0.log](logs/combo-vs-midrange/forge/1518988cce74/worker-0.log) |
| midrange vs control | builtin | 2–0–0 | 100.0% (34.2%–100.0%) | 100.0% | [first-game.log](logs/midrange-vs-control/builtin/deb97710a19c/first-game.log) |
| midrange vs control | forge | 1–1–0 | 50.0% (9.5%–90.5%) | 50.0% | [worker-0.log](logs/midrange-vs-control/forge/e4c461ef58e2/worker-0.log) |

### Observed first-player balance and game length

Each split gives W–L–D and A's win probability with a 95% Wilson interval; draws count as non-wins. Unknown first players are excluded from both splits. Turn units are individual player-turns.

| Matchup / engine | A on play | A on draw | Unknown first | Mean player-turns (known games) |
|---|---|---|---|---|
| aggro-vs-control/builtin | 1–0–0; 100.0% (20.7%–100.0%) | 0–1–0; 0.0% (0.0%–79.3%) | 0 | 24.0 (2/2) |
| aggro-vs-control/forge | 1–0–0; 100.0% (20.7%–100.0%) | 1–0–0; 100.0% (20.7%–100.0%) | 0 | 10.5 (2/2) |
| aggro-vs-midrange/builtin | 1–0–0; 100.0% (20.7%–100.0%) | 0–1–0; 0.0% (0.0%–79.3%) | 0 | 16.0 (2/2) |
| aggro-vs-midrange/forge | 0–1–0; 0.0% (0.0%–79.3%) | 1–0–0; 100.0% (20.7%–100.0%) | 0 | 16.5 (2/2) |
| combo-vs-midrange/builtin | 1–0–0; 100.0% (20.7%–100.0%) | 0–1–0; 0.0% (0.0%–79.3%) | 0 | 8.0 (2/2) |
| combo-vs-midrange/forge | 0–2–0; 0.0% (0.0%–65.8%) | no observations | 0 | 14.5 (2/2) |
| midrange-vs-control/builtin | 1–0–0; 100.0% (20.7%–100.0%) | 1–0–0; 100.0% (20.7%–100.0%) | 0 | 23.5 (2/2) |
| midrange-vs-control/forge | 1–0–0; 100.0% (20.7%–100.0%) | 0–1–0; 0.0% (0.0%–79.3%) | 0 | 27.5 (2/2) |

Builtin alternates the first player (A starts the first game; odd samples are unbalanced). Forge first player and length are parsed conservatively from full logs; quiet or incomplete metadata stays unknown. Forge starting players are observed, not forced balanced; reversing seats would not guarantee balance. Seeds are engine-specific, not paired random games. Forge uses fresh default settings per worker; jobs changes partitioning and seeds. Builtin draws include the turn cap; Forge draws can include clock expirations or internal errors. Raw logs need review to distinguish causes.

## Engine comparison

- aggro vs midrange: builtin − Forge win-probability gap +0.0%. Inspect both intervals and logs; no accuracy verdict follows from this gap.
- aggro vs control: builtin − Forge win-probability gap -50.0%. Inspect both intervals and logs; no accuracy verdict follows from this gap.
- midrange vs control: builtin − Forge win-probability gap +50.0%. Inspect both intervals and logs; no accuracy verdict follows from this gap.
- combo vs midrange: builtin − Forge win-probability gap +50.0%. Inspect both intervals and logs; no accuracy verdict follows from this gap.

## Builtin card coverage

Template coverage is not a rules-correctness guarantee. Details also apply when only Forge ran.

```text
aggro: 93% matched by templates (including simplifications) (56 fully template-matched, 4 partly supported; 60 cards)
   4 Kumano Faces Kakkazan [partial]
       ignored: II — When you next cast a creature spell this turn, that creature enters with an additional +1/+1 counter on it.
```

```text
midrange: 87% matched by templates (including simplifications) (48 fully template-matched, 4 simplified, 8 partly supported; 60 cards)
   4 Fatal Push [partial]
       ignored: Revolt — Destroy that creature if it has mana value 4 or less instead if a permanent left the battlefield under your control this turn.
   4 Tenacious Underdog [partial]
       ignored: You may cast this card from your graveyard using its blitz ability.
   4 Graveyard Trespasser [simplified]
       simplified: day/night isn't tracked: it stays on its front face
```

```text
control: 97% matched by templates (including simplifications) (55 fully template-matched, 3 simplified, 2 partly supported; 60 cards)
   1 Eiganjo, Seat of the Empire [partial]
       ignored: Channel — {2}{W}, Discard this card: It deals 4 damage to target attacking or blocking creature. This ability costs {1} less to activate for each legendary creature you control.
   1 Otawara, Soaring City [partial]
       ignored: Channel — {3}{U}, Discard this card: Return target artifact, creature, enchantment, or planeswalker to its owner's hand. This ability costs {1} less to activate for each legendary creature you control.
   3 Make Disappear [simplified]
       simplified: never paid: Casualty 1
```

```text
combo: 87% matched by templates (including simplifications) (52 fully template-matched, 8 partly supported; 60 cards)
   4 Lava Dart [partial]
       ignored: Flashback—Sacrifice a Mountain.
   4 Temur Battle Rage [partial]
       ignored: Ferocious — That creature also gains trample until end of turn if you control a creature with power 4 or greater.
```

## Review procedure

1. Check coverage gaps, deck sizes, settings and missing human evidence.
2. Read each retained builtin game log and Forge worker log; inspect mulligans, mana, targets, combat, sweepers, win conditions, draws and exceptions. Logs are not automatically adjudicated.
3. Reproduce suspicious decisions with these decks/seeds; add rules regression tests or pilot comparisons before interpreting win-rate changes.
4. Use a new output directory for changed inputs/settings or independent seeds. Only compare to reviewed, applicable main-deck human games; BO3 matches cannot supply that baseline.

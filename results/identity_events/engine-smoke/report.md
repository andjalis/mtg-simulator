# Small archetype diagnostic

Status: complete. Run identity: `e6e6fa0b73df170668c7aa823dba1bfd33c66338e7fce69ff62e5c0cdc606463`.

Repository fixtures, main-deck games only. Mixed card pools; no claim of format legality, tournament provenance or current metagame representativeness.

Main-deck games only; no sideboarding or BO3 match prediction. Results measure deck + rules implementation + AI pilot under these settings. Forge is an independent comparator, not ground truth. Both pilots can misplay, especially control and combo; agreement cannot establish human accuracy. Confidence intervals describe sampling uncertainty under an independent-game model, not rules errors or pilot bias. Ranks and MMR elsewhere in this project are internal pool scores, not Arena equivalents.

## Coverage and human evidence

- Missing coverage: combo: one compact curated fixture only (Kiln Fiend); no copy-effect combos (Reflection of Kiki-Jiki copying is unsupported) and no tournament-sourced combo list
- No verified human main-deck game dataset applicable to these exact lists and conditions. No human matchup expectations are asserted. Tournament BO3 match rates and archetype popularity are not main-deck game evidence.
- Human expectations are absent for every matchup without reviewed, applicable game evidence.
- Repository deck comments are not evidence of format legality or tournament provenance.

## Run configuration

Engines: builtin; 20 games per pairing/engine; seed 1; Forge jobs 1, game clock 30 s, worker wall timeout automatic.

Full content fingerprints, settings and counts: [results.json](results.json).

- aggro (aggro): 60 main-deck cards. Pressure, burn, prowess and adventure decisions.
- midrange (midrange): 60 main-deck cards. Discard, removal, threats and graveyard/transform decisions.
- control (control): 60 main-deck cards. Counters, sweepers, planeswalkers and delayed win conditions.
- combo (combo): 60 main-deck cards. Compact curated Kiln Fiend + double-strike fixture: cast triggers, keyword grants, pump and burn sequencing.

## Simulated games

A win probability counts draws as non-wins; its 95% Wilson interval uses all games. Score = (wins + half draws) / games and is displayed separately. Small samples are diagnostic only.

| Matchup (A vs B) | Engine | W–L–D | A win probability (95% CI) | A score | Review logs |
|---|---|---|---|---|---|
| aggro vs control | builtin | 13–7–0 | 65.0% (43.3%–81.9%) | 65.0% | [first-game.log](logs/aggro-vs-control/builtin/9388c5f38e1b/first-game.log) |
| aggro vs midrange | builtin | 6–14–0 | 30.0% (14.5%–51.9%) | 30.0% | [first-game.log](logs/aggro-vs-midrange/builtin/dc1a64131316/first-game.log) |
| combo vs midrange | builtin | 5–15–0 | 25.0% (11.2%–46.9%) | 25.0% | [first-game.log](logs/combo-vs-midrange/builtin/633aa5c95a2b/first-game.log) |
| midrange vs control | builtin | 11–9–0 | 55.0% (34.2%–74.2%) | 55.0% | [first-game.log](logs/midrange-vs-control/builtin/001e6ee49ee9/first-game.log) |

### Observed first-player balance and game length

Each split gives W–L–D and A's win probability with a 95% Wilson interval; draws count as non-wins. Unknown first players are excluded from both splits. Turn units are individual player-turns.

| Matchup / engine | A on play | A on draw | Unknown first | Mean player-turns (known games) |
|---|---|---|---|---|
| aggro-vs-control/builtin | 8–2–0; 80.0% (49.0%–94.3%) | 5–5–0; 50.0% (23.7%–76.3%) | 0 | 17.9 (20/20) |
| aggro-vs-midrange/builtin | 5–5–0; 50.0% (23.7%–76.3%) | 1–9–0; 10.0% (1.8%–40.4%) | 0 | 15.0 (20/20) |
| combo-vs-midrange/builtin | 4–6–0; 40.0% (16.8%–68.7%) | 1–9–0; 10.0% (1.8%–40.4%) | 0 | 11.4 (20/20) |
| midrange-vs-control/builtin | 6–4–0; 60.0% (31.3%–83.2%) | 5–5–0; 50.0% (23.7%–76.3%) | 0 | 21.0 (20/20) |

Builtin alternates the first player (A starts the first game; odd samples are unbalanced). Forge first player and length are parsed conservatively from full logs; quiet or incomplete metadata stays unknown. Forge starting players are observed, not forced balanced; reversing seats would not guarantee balance. Seeds are engine-specific, not paired random games. Forge uses fresh default settings per worker; jobs changes partitioning and seeds. Builtin draws include the turn cap; Forge draws can include clock expirations or internal errors. Raw logs need review to distinguish causes.

## Engine comparison

- aggro vs midrange: comparison missing (both engines must finish).
- aggro vs control: comparison missing (both engines must finish).
- midrange vs control: comparison missing (both engines must finish).
- combo vs midrange: comparison missing (both engines must finish).

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

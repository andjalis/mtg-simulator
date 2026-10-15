# UB Snow Control testing

- `decks/ub_snow_control.txt`: the user's list (main 60 + 15 sideboard; the sim plays the main deck).
- Gauntlet (2022-era Standard, matching the deck's card pool): `mono_red_aggro`, `mono_green_stompy`,
  `rakdos_midrange` (copied from `decks/forge`) and `azorius_control` (built here as the control stand-in).
- `python_current.txt`: latest Python-engine results; `forge_results.txt`: Forge results.
- `forge_ladder.txt`: the deck climbing the test tiers (`--ladder`) in Forge, 50 games per opponent.

Rerun from the repository root:

    python3 -m mtgsim \
      results/ub_snow_control/decks/ub_snow_control.txt --offline --seed 1 -n 500 --gauntlet \
      results/ub_snow_control/decks/{mono_red_aggro,mono_green_stompy,rakdos_midrange,azorius_control}.txt

## Results (2026-10-15, current engine and AI)

UB Snow Control's win rate, draws counted as half a win, 95% range in brackets.

| Opponent | Forge, 100 games | Python engine, 500 games |
|---|---|---|
| Mono-Red Aggro | 31% (23–41) | 23% (19–27) |
| Mono-Green Stompy | 38% (29–48) | 33% (29–38) |
| Rakdos Midrange | 26% (18–35) | 29% (25–33) |
| Azorius Control | 31% (23–41) | 55% (50–59) |
| **Overall** | **31.5% (27–36)** | **35% (33–37)** |

The engines now agree within a few points on everything except the control mirror.

- Forge: `forge_results.txt` (`--engine forge --forge-dir ~/forge -n 100 --jobs 4 --seed 1`).
- Python: `python_current.txt` (rerun command above, `-n 500 --seed 1`). Still not modelled: Jwari Ruins and
  Kazandu Valley back faces, Wandering Emperor and Elspeth +1, Casualty, Old-Growth Troll returning, Soul-Scar Mage.
- Earlier Python runs, kept for history only (engine had large gaps then): `baseline_python.txt` (48%, no stack),
  `python_after_stack.txt` (72%, opponents' key cards blank), `python_new_ai.txt` (82%, same gap).

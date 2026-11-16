#!/bin/sh
# before/after for #801 (painland damage, PR #808): the four benchmarks/small.json matchups, 400 games, seed 5.
# usage: run.sh   (from a checkout of e5fa948e^1 for "before" and e5fa948e for "after")
cd "$(dirname "$0")/../.."
P=${PYTHON:-.venv/bin/python}
for m in "decks/ranks/4-platinum/mono_red_aggro.txt decks/ranks/4-platinum/rakdos_midrange.txt" \
         "decks/ranks/4-platinum/mono_red_aggro.txt decks/ranks/4-platinum/azorius_control.txt" \
         "decks/ranks/4-platinum/rakdos_midrange.txt decks/ranks/4-platinum/azorius_control.txt" \
         "decks/combo/kiln_fiend_strobe.txt decks/ranks/4-platinum/rakdos_midrange.txt"; do
  set -- $m
  echo "== $1 vs $2"; $P -m mtgsim "$1" "$2" -n 400 --seed 5 2>/dev/null | grep -E "wins|score|on the play|average"
done

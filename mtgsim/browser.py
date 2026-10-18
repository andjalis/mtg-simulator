"""Run the built-in engine in a web browser (Pyodide), so games use the visitor's own CPU.

    python3 -m mtgsim.browser                       # bundle every deck under decks/ into web/static/local/build
    python3 -m mtgsim.browser A.txt B.txt --out DIR # only the cards these decks use

The bundle has three files the page loads next to Pyodide:
- mtgsim.zip: this package's Python source (no card database),
- cards.json: Scryfall-shaped data for just the cards the bundled decks use, in place of the
  26 MB cards.sqlite3 (Pyodide's core has no sqlite3 module, and the download would be too big),
- decks.json: each bundled deck's main deck, by name.

In the browser, web/static/local/worker.js unpacks the zip and calls run_local() a few games at a
time, so it can report progress between chunks.
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import time
import zipfile
from pathlib import Path

from .carddb import CardDB
from .decklist import load_deck_full
from .runner import build_deck, run_match

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "web" / "static" / "local" / "build"


def deck_name(path: Path) -> str:
    return f"{path.parent.name}/{path.stem}" if path.parent.name != "decks" else path.stem


def package_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        pkg = Path(__file__).parent
        for f in sorted(pkg.rglob("*.py")):
            z.write(f, f"mtgsim/{f.relative_to(pkg).as_posix()}")
        z.write(Path(__file__).parent / "data" / "builtin_cards.json", "mtgsim/data/builtin_cards.json")
    return buf.getvalue()


def bundle(deck_paths, out: Path) -> dict:
    db = CardDB(offline=True)
    decks, cards = {}, {}
    for path in deck_paths:
        main = load_deck_full(path)[1].main
        decks[deck_name(path)] = main
        db.ensure(main)
        for name in main:
            cards[db._key(name)] = db.raw[db._key(name)]
    out.mkdir(parents=True, exist_ok=True)
    files = {
        "mtgsim.zip": package_zip(),
        "cards.json": json.dumps(list(cards.values()), separators=(",", ":")).encode(),
        "decks.json": json.dumps(decks, indent=1).encode(),
    }
    sizes = {}
    for name, data in files.items():
        (out / name).write_bytes(data)
        sizes[name] = (len(data), len(gzip.compress(data)))
    return {"decks": len(decks), "cards": len(cards), "sizes": sizes}


def run_local(cards, deck_a, deck_b, games, seed=None, name_a="A", name_b="B"):
    """Play games between two {card: count} decks using only the given card data; returns a
    plain dict (the worker passes it to JavaScript)."""
    db = CardDB(offline=True)
    for card in cards:
        db.raw[card["name"].lower()] = card
    a, b = build_deck(db, deck_a), build_deck(db, deck_b)
    start = time.perf_counter()
    res, _ = run_match(name_a, a, name_b, b, games=games, seed=seed)
    return {"games": res.games, "wins_a": res.wins_a, "wins_b": res.wins_b, "draws": res.draws,
            "wins_a_on_play": res.wins_a_on_play, "games_a_on_play": res.games_a_on_play,
            "turns": res.turns, "seconds": time.perf_counter() - start}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("decks", nargs="*", type=Path, help="decklists (default: every .txt under decks/)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    paths = args.decks or sorted(p for p in (ROOT / "decks").rglob("*.txt"))
    info = bundle(paths, args.out)
    print(f"{info['decks']} decks, {info['cards']} cards -> {args.out}")
    for name, (raw, gz) in info["sizes"].items():
        print(f"  {name}: {raw / 1024:.0f} KB ({gz / 1024:.0f} KB gzipped)")


if __name__ == "__main__":
    main()

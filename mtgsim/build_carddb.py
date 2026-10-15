"""Build the offline card database (mtgsim/data/cards.sqlite3) from every Magic card.

    python3 -m mtgsim.build_carddb                     # try Scryfall bulk data, else Forge on GitHub
    python3 -m mtgsim.build_carddb --scryfall oracle-cards.json   # a Scryfall bulk file you downloaded
    python3 -m mtgsim.build_carddb --forge ~/forge     # a Forge checkout or release you already have

Sources, best first:
1. Scryfall "Oracle Cards" bulk data (https://scryfall.com/docs/api/bulk-data): one entry per card,
   already in the shape the engine reads.
2. Forge's card scripts (forge-gui/res/cardsfolder, about 34,000 files), fetched with a sparse,
   shallow git clone. Each script has the card's Oracle text, cost, types, P/T and faces; we convert
   them to Scryfall's field names. Forge has no set or legality data.

Every row stores a Scryfall-shaped JSON object (name, mana_cost, cmc, type_line, oracle_text,
power, toughness, loyalty, defense, colors, color_identity, keywords, layout, card_faces).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.request
from pathlib import Path

DEFAULT_DB = Path(__file__).parent / "data" / "cards.sqlite3"
SCRYFALL_BULK = "https://api.scryfall.com/bulk-data/oracle-cards"
FORGE_GIT = "https://github.com/Card-Forge/forge"
FORGE_CARDS = "forge-gui/res/cardsfolder"

KEEP = ("name", "mana_cost", "cmc", "type_line", "oracle_text", "power", "toughness", "loyalty",
        "defense", "colors", "color_identity", "keywords", "layout", "card_faces")
FACE_KEEP = ("name", "mana_cost", "type_line", "oracle_text", "power", "toughness", "loyalty",
             "defense", "colors")
SKIP_LAYOUTS = {"token", "double_faced_token", "emblem", "art_series", "vanguard", "scheme", "planar"}


def normalize(name: str) -> str:
    """Lookup key: lower case, accents and ligatures folded ("Lim-Dûl" == "lim-dul")."""
    name = name.replace("Æ", "Ae").replace("æ", "ae").replace("’", "'")
    name = unicodedata.normalize("NFKD", name)
    return "".join(c for c in name if not unicodedata.combining(c)).lower().strip()


# ---------------------------------------------------------------- Scryfall bulk data

def scryfall_cards(path: Path):
    for card in json.loads(path.read_text(encoding="utf-8")):
        if card.get("layout") in SKIP_LAYOUTS:
            continue
        out = {k: card[k] for k in KEEP if k in card}
        if "card_faces" in out:
            out["card_faces"] = [{k: f[k] for k in FACE_KEEP if k in f} for f in out["card_faces"]]
        yield out


def download_scryfall(dest: Path) -> Path:
    req = urllib.request.Request(SCRYFALL_BULK, headers={"User-Agent": "mtgsim/0.1", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        uri = json.load(resp)["download_uri"]
    path = dest / "oracle-cards.json"
    urllib.request.urlretrieve(uri, path)
    return path


# ---------------------------------------------------------------- Forge card scripts

CARD_TYPES = ("Land", "Creature", "Artifact", "Enchantment", "Planeswalker", "Instant", "Sorcery",
              "Battle", "Tribal", "Kindred", "Conspiracy", "Dungeon", "Phenomenon", "Plane", "Scheme",
              "Vanguard")
SUPERTYPES = ("Basic", "Legendary", "Snow", "World", "Ongoing", "Host", "Elite")
COLOR_WORDS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
WUBRG = "WUBRG"
FORGE_LAYOUTS = {"Split": "split", "Adventure": "adventure", "Flip": "flip", "Meld": "meld",
                 "Modal": "modal_dfc", "DoubleFaced": "transform", "Omen": "omen",
                 "Prepare": "prepare", "Specialize": "specialize"}


def forge_symbol(tok: str) -> tuple[str, float]:
    """One Forge cost token ("2", "R", "BG", "2R", "BP", "RWP", "2/R") -> ("{B/G}", mana value)."""
    if tok.isdigit():
        return "{" + tok + "}", int(tok)
    if "/" in tok:
        parts = tok.split("/")
    else:
        phyrexian = "P" in tok[1:] or (tok.startswith("P") and len(tok) > 1)
        letters = [c for c in tok if c != "P"] if phyrexian else list(tok)
        parts = letters + (["P"] if phyrexian else [])
    if parts[0] == "2" and len(parts) == 2:
        return "{2/" + parts[1] + "}", 2
    return "{" + "/".join(parts) + "}", (0 if parts == ["X"] or parts == ["Y"] else 1)


def forge_cost(raw: str | None) -> tuple[str, float]:
    if not raw or raw.strip() == "no cost":
        return "", 0
    syms = [forge_symbol(t) for t in raw.split()]
    return "".join(s for s, _ in syms), sum(v for _, v in syms)


def cost_colors(cost: str) -> list[str]:
    return [c for c in WUBRG if re.search(r"\{[^}]*" + c + r"[^}]*\}", cost)]


def forge_face(block: str) -> tuple[dict, dict]:
    fields: dict[str, str] = {}
    keywords = []
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key == "K":
            keywords.append(value.split(":")[0].split(" ")[0] if value[:1].isupper() else value)
        fields.setdefault(key, value)
    cost, mv = forge_cost(fields.get("ManaCost"))
    types = fields.get("Types", "").split()
    supers = [t for t in types if t in SUPERTYPES]
    main = [t for t in types if t in CARD_TYPES]
    subs = [t for t in types if t not in SUPERTYPES and t not in CARD_TYPES]
    type_line = " ".join(supers + main) + (" — " + " ".join(subs) if subs else "")
    oracle = fields.get("Oracle", "").replace("\\n", "\n").replace("CARDNAME", fields.get("Name", ""))
    # Forge writes loyalty abilities as "[+2]:" / "[-1]:"; Scryfall as "+2:" / "−1:"
    oracle = re.sub(r"^\[([+\-−]?)(\w+)\]:", lambda m: m[1].replace("-", "−") + m[2] + ":", oracle, flags=re.M)
    if "Colors" in fields:
        colors = [COLOR_WORDS[c] for c in fields["Colors"].split(",") if c in COLOR_WORDS]
        colors.sort(key=WUBRG.index)
    else:
        colors = cost_colors(cost)
    face = {"name": fields.get("Name", ""), "mana_cost": cost, "type_line": type_line,
            "oracle_text": oracle, "colors": colors}
    if "PT" in fields:
        face["power"], _, face["toughness"] = fields["PT"].partition("/")
    if "Loyalty" in fields:
        face["loyalty"] = fields["Loyalty"]
    if "Defense" in fields:
        face["defense"] = fields["Defense"]
    return face, {"cmc": mv, "keywords": [k for k in keywords if k and k[0].isalpha()]}


def forge_card(text: str) -> dict | None:
    blocks = re.split(r"^(?:ALTERNATE|SPECIALIZE:.*)\s*$", text, flags=re.M)
    mode = re.search(r"^AlternateMode:(\w+)", text, re.M)
    layout = FORGE_LAYOUTS.get(mode[1], mode[1].lower()) if mode else "normal"
    if layout == "specialize":
        blocks = blocks[:1]  # the specialized versions are separate states, not faces
    faces = [forge_face(b) for b in blocks if "Name:" in b]
    if not faces or not faces[0][0]["name"]:
        return None
    front, extra = faces[0]
    identity = set()
    for face, _ in faces:
        identity |= set(face["colors"]) | set(cost_colors(face["mana_cost"]))
        identity |= set(cost_colors(" ".join(re.findall(r"\{[^}]+\}", face["oracle_text"]))))
    keywords = sorted({k for _, e in faces for k in e["keywords"]})
    if len(faces) == 1:
        card = dict(front)
        card["cmc"] = extra["cmc"]
    else:
        card = {"name": " // ".join(f["name"] for f, _ in faces),
                "type_line": " // ".join(f["type_line"] for f, _ in faces)}
        if layout in ("split",):  # both halves' costs; mana value is the sum
            card["mana_cost"] = " // ".join(f["mana_cost"] for f, _ in faces)
            card["cmc"] = sum(e["cmc"] for _, e in faces)
        else:
            card["mana_cost"] = front["mana_cost"]
            card["cmc"] = extra["cmc"]
        card["colors"] = sorted({c for f, _ in faces for c in f["colors"]}, key=WUBRG.index) \
            if layout in ("split", "flip", "adventure") else front["colors"]
        card["card_faces"] = [f for f, _ in faces]
    card["color_identity"] = sorted(identity, key=WUBRG.index)
    card["keywords"] = keywords
    card["layout"] = layout
    return card


def forge_cards(cardsfolder: Path):
    for path in sorted(cardsfolder.rglob("*.txt")):
        card = forge_card(path.read_text(encoding="utf-8", errors="replace"))
        if card:
            yield card


def clone_forge(dest: Path) -> Path:
    repo = dest / "forge"
    run = lambda *a: subprocess.run(a, check=True, cwd=dest if a[1] == "clone" else repo)
    run("git", "clone", "-q", "--depth", "1", "--filter=blob:none", "--sparse", FORGE_GIT, str(repo))
    run("git", "sparse-checkout", "set", FORGE_CARDS)
    return repo / FORGE_CARDS


def find_cardsfolder(path: Path) -> Path:
    for candidate in (path, path / "res" / "cardsfolder", path / FORGE_CARDS):
        if candidate.is_dir() and any(candidate.glob("*/*.txt")):
            return candidate
    sys.exit(f"No Forge card scripts under {path}")


# ---------------------------------------------------------------- writing the database

def write_db(cards, out: Path, source: str) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript("""
        CREATE TABLE cards (key TEXT PRIMARY KEY, name TEXT, mana_cost TEXT, cmc REAL, type_line TEXT,
            oracle_text TEXT, power TEXT, toughness TEXT, colors TEXT, layout TEXT, data TEXT);
        CREATE TABLE names (alias TEXT PRIMARY KEY, key TEXT);
        CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT);
    """)
    n = 0
    for card in cards:
        key = normalize(card["name"])
        faces = card.get("card_faces") or []
        text = card.get("oracle_text") or "\n//\n".join(f.get("oracle_text", "") for f in faces)
        front = faces[0] if faces else card
        con.execute("INSERT OR REPLACE INTO cards VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            key, card["name"], card.get("mana_cost", ""), card.get("cmc", 0), card.get("type_line", ""),
            text, front.get("power"), front.get("toughness"), "".join(card.get("colors") or []),
            card.get("layout", "normal"), json.dumps(card, ensure_ascii=False, separators=(",", ":"))))
        aliases = [key] + [normalize(f["name"]) for f in faces if f.get("name")]
        for i, alias in enumerate(aliases):  # full name and front face win over back faces
            con.execute(f"INSERT OR {'REPLACE' if i < 2 else 'IGNORE'} INTO names VALUES (?,?)", (alias, key))
        n += 1
    con.executemany("INSERT INTO meta VALUES (?,?)", [
        ("source", source), ("built", time.strftime("%Y-%m-%d %H:%M:%S")), ("cards", str(n))])
    con.commit()
    con.execute("VACUUM")
    con.close()
    tmp.replace(out)
    return n


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scryfall", type=Path, help="Scryfall bulk JSON file (Oracle Cards or Default Cards)")
    p.add_argument("--forge", type=Path, help="Forge checkout, release or cardsfolder")
    p.add_argument("--source", choices=("auto", "scryfall", "forge"), default="auto",
                   help="what to download when no local file is given (default: Scryfall, else Forge)")
    p.add_argument("-o", "--out", type=Path, default=DEFAULT_DB)
    args = p.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if args.scryfall:
            cards, source = scryfall_cards(args.scryfall), f"scryfall:{args.scryfall.name}"
        elif args.forge:
            cards, source = forge_cards(find_cardsfolder(args.forge)), "forge:local"
        else:
            cards = None
            if args.source in ("auto", "scryfall"):
                try:
                    print("Downloading Scryfall Oracle Cards bulk data...", file=sys.stderr)
                    cards, source = scryfall_cards(download_scryfall(tmp)), "scryfall:oracle-cards"
                except Exception as e:  # blocked network, Scryfall down
                    if args.source == "scryfall":
                        sys.exit(f"Scryfall download failed: {e}")
                    print(f"Scryfall unavailable ({e}); using Forge's card scripts", file=sys.stderr)
            if cards is None:
                print(f"Cloning Forge card scripts from {FORGE_GIT}...", file=sys.stderr)
                folder = clone_forge(tmp)
                rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=folder,
                                     capture_output=True, text=True).stdout.strip()
                cards, source = forge_cards(folder), f"forge:{rev}"
        n = write_db(cards, args.out, source)
    print(f"Wrote {n} cards to {args.out} ({args.out.stat().st_size / 1e6:.1f} MB, source {source})")


if __name__ == "__main__":
    main()

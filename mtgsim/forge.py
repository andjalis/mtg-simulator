"""Run matches through Forge's headless simulator for near-complete card coverage.

Forge (https://github.com/Card-Forge/forge) is a GPL-3 Java rules engine with
its own AI. Its desktop build has a `sim` mode:

    java -jar forge-gui-desktop-<ver>-jar-with-dependencies.jar sim -d a.dck b.dck -D <dir> -n 100 -q

This module writes our decklists as .dck files, runs that command from the
Forge install folder, and turns its "Game Result" lines into a MatchResult.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .runner import MatchResult

JAVA_ARGS = [
    "-Xmx4096m", "-Dio.netty.tryReflectionSetAccessible=true", "-Dfile.encoding=UTF-8",
    *[x for mod in (
        "java.desktop/java.beans", "java.desktop/javax.swing.border", "java.desktop/javax.swing.event",
        "java.desktop/sun.swing", "java.desktop/java.awt.image", "java.desktop/java.awt.color",
        "java.desktop/sun.awt.image", "java.desktop/javax.swing", "java.desktop/java.awt",
        "java.base/java.util", "java.base/java.lang", "java.base/java.lang.reflect", "java.base/java.text",
        "java.desktop/java.awt.font", "java.base/jdk.internal.misc", "java.base/sun.nio.ch",
        "java.base/java.nio", "java.base/java.math", "java.base/java.util.concurrent", "java.base/java.net",
    ) for x in ("--add-opens", f"{mod}=ALL-UNNAMED")],
]
RESULT = re.compile(r"Game Result: Game (\d+) ended in (?:a Draw|\d+ ms\. (.+) has won)")


class ForgeError(RuntimeError):
    pass


def find_forge(forge_dir: str | None = None) -> tuple[Path, Path]:
    """Return (install folder, desktop jar). Looks at forge_dir, then $FORGE_HOME."""
    folder = forge_dir or os.environ.get("FORGE_HOME")
    if not folder:
        raise ForgeError("Point --forge-dir (or FORGE_HOME) at your Forge install folder.")
    folder = Path(folder).expanduser().resolve()
    jars = sorted(folder.glob("forge-gui-desktop-*-jar-with-dependencies.jar"))
    if not jars:
        raise ForgeError(f"No forge-gui-desktop-*-jar-with-dependencies.jar in {folder}")
    return folder, jars[-1]


def forge_card_names(folder: Path) -> set[str] | None:
    """All card names Forge knows, read from res/cardsfolder (a folder or cardsfolder.zip)."""
    base = folder / "res" / "cardsfolder"
    names = set()

    def read(text: str):
        m = re.search(r"^Name:(.+)$", text, flags=re.M)
        if m:
            names.add(m[1].strip().lower())

    if base.is_dir():
        for f in base.rglob("*.txt"):
            read(f.read_text(encoding="utf-8", errors="replace"))
    elif (base / "cardsfolder.zip").exists():
        with zipfile.ZipFile(base / "cardsfolder.zip") as z:
            for info in z.infolist():
                if info.filename.endswith(".txt"):
                    read(z.read(info).decode("utf-8", errors="replace"))
    return names or None


def to_dck(name: str, counts: dict[str, int]) -> str:
    lines = ["[metadata]", f"Name={name}", "[Main]"]
    lines += [f"{n} {card}" for card, n in counts.items()]
    return "\n".join(lines) + "\n"


def parse_results(lines, name_a: str, name_b: str) -> MatchResult:
    """Read Forge sim output. Forge names players Ai(1)-<deck> and Ai(2)-<deck>."""
    res = MatchResult(name_a, name_b, play_draw_known=False)
    for line in lines:
        m = RESULT.search(line)
        if not m:
            if "Could not load deck" in line:
                raise ForgeError(line.strip())
            continue
        res.games += 1
        winner = m[2]
        if winner is None:
            res.draws += 1
        elif winner.startswith("Ai(1)"):
            res.wins_a += 1
        elif winner.startswith("Ai(2)"):
            res.wins_b += 1
        else:
            res.draws += 1
    return res


def run_forge_match(name_a, counts_a, name_b, counts_b, games=100, seed=None, forge_dir=None,
                    java="java", clock=120, check_cards=True, progress=None, jobs=1) -> MatchResult:
    """Play games in Forge. jobs > 1 splits them across that many Java processes."""
    folder, jar = find_forge(forge_dir)
    if check_cards:
        known = forge_card_names(folder)
        if known is not None:
            missing = sorted({c for c in (*counts_a, *counts_b) if c.lower() not in known})
            if missing:
                raise ForgeError(f"Forge doesn't know these cards (check spelling): {', '.join(missing)}")
    jobs = max(1, min(jobs, games))
    shares = [games // jobs + (i < games % jobs) for i in range(jobs)]
    done, lock = [0], threading.Lock()

    def on_game():
        with lock:
            done[0] += 1
            if progress:
                progress(done[0], games)

    with tempfile.TemporaryDirectory(prefix="mtgsim-forge-") as tmp:
        tmp = Path(tmp)
        (tmp / "a.dck").write_text(to_dck(name_a, counts_a), encoding="utf-8")
        (tmp / "b.dck").write_text(to_dck(name_b, counts_b), encoding="utf-8")

        def run_share(i):
            cmd = [shutil.which(java) or java, *JAVA_ARGS, "-jar", str(jar), "sim",
                   "-d", "a.dck", "b.dck", "-D", str(tmp), "-n", str(shares[i]), "-c", str(clock), "-q"]
            if seed is not None:
                cmd += ["-s", str(seed + i)]
            lines = []
            with subprocess.Popen(cmd, cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, encoding="utf-8", errors="replace") as proc:
                for line in proc.stdout:
                    lines.append(line)
                    if RESULT.search(line):
                        on_game()
            return lines, proc.returncode

        with ThreadPoolExecutor(jobs) as pool:
            outputs = list(pool.map(run_share, range(jobs)))

    res = MatchResult(name_a, name_b, play_draw_known=False)
    for lines, code in outputs:
        part = parse_results(lines, name_a, name_b)
        if part.games == 0:
            tail = "".join(lines[-20:])
            raise ForgeError(f"Forge finished without reporting any games (exit code {code}):\n{tail}")
        res.games += part.games
        res.wins_a += part.wins_a
        res.wins_b += part.wins_b
        res.draws += part.draws
    return res

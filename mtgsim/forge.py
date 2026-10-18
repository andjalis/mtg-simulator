"""Run matches through Forge's headless simulator for near-complete card coverage.

Forge (https://github.com/Card-Forge/forge) is a GPL-3 Java rules engine with
its own AI. Its desktop build has a `sim` mode:

    java -jar forge-gui-desktop-<ver>-jar-with-dependencies.jar sim -d a.dck b.dck -D <dir> -n 100 -q

This module writes our decklists as .dck files, runs that command from the
Forge install folder, and turns its "Game Result" lines into a MatchResult.

Forge has no option to choose the starting player: the first game of a run is
a coin flip and the loser of each game starts the next. Left alone, a deck that
loses most games is mostly on the play. So the wrapper reads each game's starter
from the game log and keeps only as many games of each starter as an even
play/draw split needs, discarding the rest (see run_forge_match).
"""
from __future__ import annotations

import os
from collections import deque
from contextlib import nullcontext
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
TURN = re.compile(r"^Turn: Turn (\d+) \(Ai\(([12])\)-.*\)\s*$")
OUTCOME_TURN = re.compile(r"^Game Outcome: Turn (\d+)\s*$")


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
    # Release installs can keep scripts in an archive inside this directory,
    # optionally alongside loose scripts. Checking it with elif makes the
    # archive unreachable because its parent directory necessarily exists.
    if (base / "cardsfolder.zip").exists():
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
    res = MatchResult(name_a, name_b)
    seen = set()
    turns, malformed, outcome_turn = [], False, None
    for line in lines:
        turn = TURN.match(line)
        if turn:
            turns.append((int(turn[1]), int(turn[2]) - 1))
        elif line.startswith("Turn:"):
            malformed = True
        outcome = OUTCOME_TURN.match(line)
        if outcome:
            outcome_turn = int(outcome[1])
        m = RESULT.search(line)
        if not m:
            if "Could not load deck" in line:
                raise ForgeError(line.strip())
            if "Game Result:" in line:
                raise ForgeError(f"Malformed Forge result: {line.strip()}")
            continue
        if int(m[1]) in seen:
            raise ForgeError(f"Duplicate Forge game number: {m[1]}")
        seen.add(int(m[1]))
        winner = m[2]
        if winner is None:
            seat = None
        elif winner.startswith("Ai(1)-"):
            seat = 0
        elif winner.startswith("Ai(2)-"):
            seat = 1
        else:
            raise ForgeError(f"Unrecognised Forge winner: {winner}")
        # Turn numbers are player-turns, whereas Game Outcome: Turn is a round
        # counter. Never double the latter to manufacture a game length.
        first = (turns[0][1] if turns and turns[0][0] == 1 and
                 sum(n == 1 for n, _ in turns) == 1 and not malformed else None)
        complete = (first is not None and [n for n, _ in turns] == list(range(1, len(turns) + 1))
                    and outcome_turn == (len(turns) + 1) // 2)
        res.add_game(seat, first, len(turns) if complete else None, game_number=int(m[1]))
        turns, malformed, outcome_turn = [], False, None
    if not res.games:
        res.play_draw_known = False
    return res


def play_quotas(shares: list[int]) -> list[int]:
    """Games each worker keeps with deck A on the play: half its share, odd halves alternating."""
    quotas, extra = [], 0
    for share in shares:
        quotas.append(share // 2 + (share % 2 and extra % 2 == 0))
        extra += share % 2
    return quotas


def run_forge_match(name_a, counts_a, name_b, counts_b, games=100, seed=None, forge_dir=None,
                    java="java", clock=120, check_cards=True, progress=None, jobs=1,
                    log_dir=None, isolated=False, worker_timeout=None, max_factor=4) -> MatchResult:
    """Play games in Forge, half with deck A on the play and half on the draw.

    jobs > 1 splits them across that many Java processes. Each worker asks Forge
    for up to max_factor times its share and keeps a game only while its
    starter's quota is open, so which games are kept depends on who started them,
    never on their own result. Games whose starter can't be read are discarded.
    If the cap is reached first (a very lopsided matchup), the worker keeps the
    next games whatever their starter; the play/draw counts then show the skew.
    """
    if (games < 1 or jobs < 1 or clock < 1 or max_factor < 1
            or (worker_timeout is not None and worker_timeout < 1)):
        raise ForgeError("games, jobs, clock and max_factor must be positive")
    folder, jar = find_forge(forge_dir)
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
    if check_cards:
        known = forge_card_names(folder)
        if known is not None:
            missing = sorted({c for c in (*counts_a, *counts_b) if c.lower() not in known})
            if missing:
                raise ForgeError(f"Forge doesn't know these cards (check spelling): {', '.join(missing)}")
    jobs = max(1, min(jobs, games))
    shares = [games // jobs + (i < games % jobs) for i in range(jobs)]
    quotas = play_quotas(shares)
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
            cwd = folder
            extra, env = [], None
            if isolated:
                # Keep preferences and generated files out of the installed Forge/user profile.
                cwd = tmp / f"worker-{i}"
                cwd.mkdir()
                (cwd / "res").symlink_to(folder / "res", target_is_directory=True)
                (cwd / "forge.profile.properties").write_text(
                    "userDir=user\ncacheDir=cache\n", encoding="utf-8")
                extra = [f"-Duser.home={cwd}"]
                env = os.environ.copy()
                for key in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"):
                    env.pop(key, None)
            cap = shares[i] * max_factor
            # No -q: the full game log carries the Turn lines that name each game's starter.
            cmd = [shutil.which(java) or java, *JAVA_ARGS, *extra, "-jar", str(jar), "sim",
                   "-d", "a.dck", "b.dck", "-D", str(tmp), "-n", str(cap), "-c", str(clock)]
            if seed is not None:
                cmd += ["-s", str(seed + i)]
            kept, pending, numbers = MatchResult(name_a, name_b), [], set()
            want = {0: quotas[i], 1: shares[i] - quotas[i]}
            seen = [0]
            tail = deque(maxlen=20)
            expired, finished = threading.Event(), threading.Event()

            def take(lines):
                part = parse_results(lines, name_a, name_b)
                for meta in part.game_metadata:
                    if meta["game_number"] in numbers:
                        raise ForgeError(f"Duplicate Forge game number: {meta['game_number']}")
                    numbers.add(meta["game_number"])
                    seen[0] += 1
                    first = meta["first_player"]
                    if seen[0] > cap - (shares[i] - kept.games) or want.get(first, 0) > 0:
                        # Past this point every remaining game is needed to reach the share.
                        if first in want and want[first] > 0:
                            want[first] -= 1
                        kept.add_game(**meta)
                        on_game()

            with (log_dir / f"worker-{i}.log").open("w", encoding="utf-8") if log_dir else nullcontext() as raw:
                with subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, encoding="utf-8", errors="replace") as proc:
                    def stop():
                        expired.set()
                        proc.kill()

                    timer = threading.Timer(worker_timeout or (60 + cap * (clock + 5)), stop)
                    timer.start()
                    try:
                        for line in proc.stdout:
                            tail.append(line)
                            if raw:
                                raw.write(line)
                                raw.flush()
                            # Retain compact per-game metadata as well as results.
                            if (RESULT.search(line) or "Game Result:" in line or "Could not load deck" in line
                                    or line.startswith(("Turn:", "Game Outcome: Turn"))):
                                pending.append(line)
                            if "Game Result:" in line:
                                take(pending)
                                pending = []
                                if kept.games == shares[i]:
                                    finished.set()
                                    proc.kill()
                                    break
                        proc.wait()
                    finally:
                        timer.cancel()
                        if proc.poll() is None:
                            proc.kill()
                        proc.stdout.close()
            if expired.is_set():
                raise ForgeError(f"Forge worker {i} exceeded wall timeout; raw log retained")
            take(pending)   # surfaces "Could not load deck" and other trailing errors
            return kept, seen[0], 0 if finished.is_set() else proc.returncode, "".join(tail)

        with ThreadPoolExecutor(jobs) as pool:
            outputs = list(pool.map(run_share, range(jobs)))

    res = MatchResult(name_a, name_b)
    for i, (part, seen, code, tail) in enumerate(outputs):
        if seen == 0:
            raise ForgeError(f"Forge finished without reporting any games (exit code {code}):\n{tail}")
        if code != 0 or part.games != shares[i]:
            raise ForgeError(f"Forge worker {i} reported {part.games}/{shares[i]} games "
                             f"(exit code {code}); incomplete results rejected")
        for metadata in part.game_metadata:
            res.add_game(**metadata, worker=i)
    return res

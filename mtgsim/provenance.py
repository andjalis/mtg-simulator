"""Content identities and atomic checkpoints for reproducible offline experiments."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

from . import carddb
from .forge import JAVA_ARGS, find_forge

ROOT = Path(__file__).resolve().parent.parent
ISOLATION = "fresh worker home/profile/cache; default preferences; no inherited Java options; v1"


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_hash(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_hash(path: Path) -> dict:
    """Hash names and contents, including symlinked resource directories; never mtime-only."""
    entries = {}
    if path.exists():
        for base, dirs, files in os.walk(path, followlinks=True):
            dirs.sort()
            for name in sorted(files):
                p = Path(base) / name
                entries[p.relative_to(path).as_posix()] = file_hash(p)
    return {"sha256": digest(entries), "files": len(entries), "exists": path.exists()}


def runtime_identity(include_forge=False, forge_dir=None, java="java") -> dict:
    data = {str(p.resolve()): file_hash(p) for p in
            (carddb.BUILTIN, carddb.CACHE, carddb.ALL_CARDS,
             Path(str(carddb.ALL_CARDS) + "-wal"))}
    identity = {"schema": 1, "code": {p.name: file_hash(p) for p in sorted((ROOT / "mtgsim").glob("*.py"))},
                "card_data": data, "python": platform.python_version(), "platform": platform.platform()}
    if include_forge:
        folder, jar = find_forge(forge_dir)
        executable = shutil.which(java) or java
        env = os.environ.copy()
        for key in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS"):
            env.pop(key, None)
        version = subprocess.run([executable, "-version"], capture_output=True, text=True,
                                 timeout=15, check=True, env=env)
        identity["forge"] = {"folder": str(folder), "jar": file_hash(jar), "jar_name": jar.name,
                             "resources": tree_hash(folder / "res"), "java": str(Path(executable).resolve()),
                             "java_sha256": file_hash(Path(executable)),
                             "java_version": version.stdout + version.stderr, "java_args": JAVA_ARGS,
                             "settings": ISOLATION,
                             "locale": {k: os.environ.get(k) for k in ("LANG", "LC_ALL", "TZ")}}
    return identity


def deck_identity(path: Path, counts: dict) -> dict:
    return {"path": str(path.resolve()), "sha256": file_hash(path), "main_deck": counts}


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextmanager
def output_lock(folder: Path):
    folder.mkdir(parents=True, exist_ok=True)
    lock = folder / ".run.lock"
    try:
        with lock.open("x") as f:
            f.write(f"pid={os.getpid()}\n")
    except FileExistsError:
        raise ValueError(f"Run locked: {lock}. Remove only after confirming its process has stopped.") from None
    try:
        yield
    finally:
        lock.unlink()


def artifacts(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): file_hash(p) for p in sorted(folder.rglob("*")) if p.is_file()}


def valid_artifacts(folder: Path, expected: dict) -> bool:
    if not isinstance(expected, dict) or not expected:
        return False
    root = folder.resolve()
    try:
        for name, sha in expected.items():
            if not isinstance(name, str) or not isinstance(sha, str):
                return False
            path = folder / name
            if (Path(name).is_absolute() or not path.resolve().is_relative_to(root)
                    or not path.is_file() or file_hash(path) != sha):
                return False
    except (OSError, ValueError):
        return False
    return True

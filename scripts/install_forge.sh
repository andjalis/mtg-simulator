#!/usr/bin/env bash
# Build Forge from source into a folder mtgsim can use with --forge-dir.
# Needs git, a JDK 17+ (including javac) and Maven. About 1.5 GB of disk.
#
#   scripts/install_forge.sh [INSTALL_DIR] [COMMIT]     (default: ~/forge, upstream HEAD)
#
# Alternatively, download a release from https://github.com/Card-Forge/forge/releases,
# unpack it, and pass that folder as --forge-dir.
set -euo pipefail
DEST="${1:-$HOME/forge}"
SRC="$DEST/src"
REV="${2:-}"
mkdir -p "$DEST"
if [ ! -d "$SRC/.git" ]; then
  git clone --depth 1 --filter=blob:none https://github.com/Card-Forge/forge.git "$SRC"
elif [ -z "$REV" ]; then
  git -C "$SRC" pull --ff-only
fi
if [ -n "$REV" ]; then
  git -C "$SRC" fetch --depth 1 origin "$REV"
  git -C "$SRC" checkout --detach FETCH_HEAD
fi
(cd "$SRC" && mvn -B -q -pl forge-gui-desktop -am package -DskipTests -Dcheckstyle.skip -Dmaven.javadoc.skip)
rm -f "$DEST"/forge-gui-desktop-*-jar-with-dependencies.jar
cp "$SRC"/forge-gui-desktop/target/forge-gui-desktop-*-jar-with-dependencies.jar "$DEST"/
ln -sfn "$SRC/forge-gui/res" "$DEST/res"
git -C "$SRC" rev-parse HEAD > "$DEST/source-commit.txt"
echo "Forge ready in $DEST"
echo "Try: python3 -m mtgsim DECK_A DECK_B --engine forge --forge-dir $DEST -n 20"

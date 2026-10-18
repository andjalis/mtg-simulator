#!/usr/bin/env bash
# Run the bounded TestNG probe in the pinned Forge source checkout.
# Usage: MVN=mvn scripts/forge_rules_probe.sh FORGE_DIR [extra Maven options...]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FORGE_DIR="$(cd "${1:?provide the Forge install directory}" && pwd)"
shift
SRC="$FORGE_DIR/src"
EXPECTED="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["commit"])' "$ROOT/rules/forge/pin.json")"
ACTUAL="$(git -C "$SRC" rev-parse HEAD)"
if [ "$ACTUAL" != "$EXPECTED" ]; then
  echo "Forge source commit does not match rules/forge/pin.json" >&2
  exit 1
fi
TARGET="$SRC/forge-gui-desktop/src/test/java/forge/game/RulesContractProbe.java"
CREATED=0
if [ -e "$TARGET" ]; then
  cmp "$ROOT/rules/forge/RulesContractProbe.java" "$TARGET"
else
  cp "$ROOT/rules/forge/RulesContractProbe.java" "$TARGET"
  CREATED=1
fi
PROFILE="$(mktemp -d "${TMPDIR:-/tmp}/mtgsim-forge-probe.XXXXXX")"
cleanup() {
  if [ "$CREATED" = 1 ]; then rm -f "$TARGET"; fi
  rm -rf "$PROFILE"
}
trap cleanup EXIT
"${MVN:-mvn}" -B -f "$SRC/pom.xml" -pl forge-gui-desktop -am test \
  -Dtest=forge.game.RulesContractProbe -Dsurefire.failIfNoSpecifiedTests=false \
  -Dcheckstyle.skip -Duser.home="$PROFILE" "$@"

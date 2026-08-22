#!/usr/bin/env bash
# Preflight: prueft die Arbeitsbasis, bevor am Standard etwas geaendert wird.
#
# Ein Standard vertraegt keinen stillen Basiswechsel: Wer auf einer
# unerwarteten Basis arbeitet, veroeffentlicht spaeter eine Version, die
# niemand reproduzieren kann.
#
# Exit-Codes: 0 = Basis in Ordnung, 1 = Basis abweichend, 2 = Umgebungsfehler
set -euo pipefail

WURZEL="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$WURZEL"

BLOCK_DATEI="scripts/project/block.json"
FEHLER=0
WARNUNGEN=0

melde()  { printf '  %-7s %s\n' "$1" "$2"; }
fehler() { melde "FEHLER" "$1"; FEHLER=$((FEHLER + 1)); }
warnung(){ melde "WARNUNG" "$1"; WARNUNGEN=$((WARNUNGEN + 1)); }
ok()     { melde "ok" "$1"; }

echo "preflight: swisscomfort/datenfluss-standard"

for werkzeug in git python3; do
  command -v "$werkzeug" >/dev/null 2>&1 || { echo "FEHLER: $werkzeug fehlt" >&2; exit 2; }
done
git rev-parse --git-dir >/dev/null 2>&1 || { echo "FEHLER: kein Git-Repository" >&2; exit 2; }
ok "Umgebung: git, python3 $(python3 -c 'import platform;print(platform.python_version())')"

[ -f "$BLOCK_DATEI" ] || { echo "FEHLER: $BLOCK_DATEI fehlt" >&2; exit 2; }
feld() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1],encoding="utf-8")).get(sys.argv[2],""))' "$BLOCK_DATEI" "$1"; }

BLOCK_ID="$(feld id)"
BLOCK_STATUS="$(feld status)"
BLOCK_BRANCH="$(feld branch)"
BLOCK_BASE="$(feld base_sha)"
ok "Block: $BLOCK_ID ($BLOCK_STATUS)"

if [ "$BLOCK_STATUS" != "IN_PROGRESS" ]; then
  warnung "Block $BLOCK_ID steht auf $BLOCK_STATUS - es wird gerade kein Block bearbeitet"
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [ "$BRANCH" = "$BLOCK_BRANCH" ]; then
  ok "Branch: $BRANCH"
else
  fehler "Branch: $BRANCH, erwartet $BLOCK_BRANCH"
fi

if git cat-file -e "${BLOCK_BASE}^{commit}" 2>/dev/null; then
  if git merge-base --is-ancestor "$BLOCK_BASE" HEAD; then
    ok "Basis: ${BLOCK_BASE:0:12} ist Vorfahr von HEAD ($(git rev-parse --short HEAD))"
  else
    fehler "Basis: ${BLOCK_BASE:0:12} ist kein Vorfahr von HEAD - unerwartete Arbeitsbasis"
  fi
else
  fehler "Basis: Commit ${BLOCK_BASE:0:12} liegt nicht im Repository"
fi

for datei in PROJECT_SCOPE.md PROJECT_RULES.md CLAUDE.md AGENTS.md; do
  [ -f "$datei" ] || fehler "kanonische Datei fehlt: $datei"
done
[ "$FEHLER" -eq 0 ] && ok "kanonische Quellen vollstaendig"

if [ -n "$(git status --porcelain)" ]; then
  warnung "Arbeitsbaum ist nicht sauber - make verify und make handoff verlangen einen sauberen Stand"
else
  ok "Arbeitsbaum sauber"
fi

echo
python3 - "$BLOCK_ID" "$BRANCH" "$FEHLER" "$WARNUNGEN" <<'PY'
import json, subprocess, sys
block, branch, fehler, warnungen = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
print(json.dumps({
    "command": "preflight",
    "block": block,
    "branch": branch,
    "head_sha": head,
    "findings": fehler,
    "warnings": warnungen,
    "result": "FAIL" if fehler else "PASS",
}, ensure_ascii=False))
PY

if [ "$FEHLER" -gt 0 ]; then
  echo "preflight: FAIL ($FEHLER Befunde)"
  exit 1
fi
echo "preflight: PASS"

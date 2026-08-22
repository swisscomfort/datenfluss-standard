#!/usr/bin/env bash
# Verify: die gemeinsame Pruefmaschine fuer lokale Arbeit und CI.
#
# Bisher stand die Pruefwahrheit in der Workflow-Datei: Wer lokal arbeitete,
# musste fuenf Befehle aus dem YAML abschreiben. Zwei Pruefwahrheiten driften,
# und danach beweist ein gruener Lauf nur noch, dass die abgeschriebene
# Variante gruen ist. Es gibt deshalb nur diesen Pfad; CI ruft ihn auf.
#
# Geprueft wird die Anweisungsschicht und der bestehende Standardkern:
# Beispiel-Deklaration, Konformitaets-Testsuite und die netzfreien
# Selbsttests der Messwerkzeuge.
#
# Abhaengigkeit: jsonschema, gepinnt. Fehlt sie, wird eine Umgebung
# ausserhalb des Repositories angelegt - ein venv im Arbeitsbaum wuerde den
# Stand verschmutzen und jeden Handoff ungueltig machen.
#
# Exit-Codes: 0 = alles bestanden, 1 = mindestens ein Befund, 2 = Umgebungsfehler
set -euo pipefail

WURZEL="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$WURZEL"

JSONSCHEMA_VERSION="4.23.0"
PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || { echo "FEHLER: $PYTHON fehlt" >&2; exit 2; }

# --- Laufzeit mit jsonschema ------------------------------------------------
if ! "$PYTHON" -c 'import jsonschema' >/dev/null 2>&1; then
  VENV="${DATENFLUSS_VENV:-${XDG_CACHE_HOME:-$HOME/.cache}/datenfluss-standard/venv}"
  echo "Hinweis: jsonschema fehlt in $PYTHON - verwende $VENV"
  if [ ! -x "$VENV/bin/python" ]; then
    "$PYTHON" -m venv "$VENV" || { echo "FEHLER: venv nicht anlegbar" >&2; exit 2; }
  fi
  if ! "$VENV/bin/python" -c 'import jsonschema' >/dev/null 2>&1; then
    "$VENV/bin/pip" install --quiet --disable-pip-version-check \
      "jsonschema==$JSONSCHEMA_VERSION" \
      || { echo "FEHLER: jsonschema==$JSONSCHEMA_VERSION nicht installierbar" >&2; exit 2; }
  fi
  PYTHON="$VENV/bin/python"
fi

SCHRITTE=()
ERGEBNISSE=()
FEHLER=0

schritt() {
  local name="$1"; shift
  echo
  echo "── $name"
  if "$@"; then
    SCHRITTE+=("$name"); ERGEBNISSE+=("PASS")
  else
    SCHRITTE+=("$name"); ERGEBNISSE+=("FAIL")
    FEHLER=$((FEHLER + 1))
  fi
}

pruefe_shell_syntax() {
  local rc=0
  for datei in scripts/project/*.sh; do
    bash -n "$datei" || rc=1
  done
  return $rc
}

pruefe_python_syntax() {
  "$PYTHON" -m py_compile scripts/project/*.py
}

pruefe_ausfuehrbar() {
  local rc=0
  for datei in scripts/project/preflight.sh scripts/project/verify.sh; do
    if [ ! -x "$datei" ]; then
      echo "FEHLER: $datei ist nicht ausfuehrbar"
      rc=1
    fi
  done
  return $rc
}

echo "verify: swisscomfort/datenfluss-standard"
echo "python: $PYTHON"

schritt "Shell-Syntax der Arbeitsmaschine" pruefe_shell_syntax
schritt "Python-Syntax der Arbeitsmaschine" pruefe_python_syntax
schritt "Skripte ausfuehrbar" pruefe_ausfuehrbar
schritt "Anweisungs-Waechter" "$PYTHON" scripts/project/check_instructions.py
schritt "Negativtests des Waechters" "$PYTHON" scripts/project/test_check_instructions.py
schritt "Beispiel-Deklaration validieren" "$PYTHON" werkzeuge/validator.py beispiele/beispiel-deklaration.json
schritt "Konformitaets-Testsuite" "$PYTHON" werkzeuge/konformitaet.py
schritt "Selbsttest DNS-Messung (ohne Netzzugriff)" "$PYTHON" werkzeuge/test_dns_messung.py
schritt "Selbsttest Einwilligungs-Leser (ohne Netzzugriff)" "$PYTHON" werkzeuge/test_einwilligung.py
schritt "Regressionstests der Sanierung (ohne Netzzugriff)" "$PYTHON" werkzeuge/test_sanierung.py

echo
python3 - "$FEHLER" "${SCHRITTE[@]}" -- "${ERGEBNISSE[@]}" <<'PY'
import json, sys
argv = sys.argv[1:]
fehler = int(argv[0])
rest = argv[1:]
trenner = rest.index("--")
schritte, ergebnisse = rest[:trenner], rest[trenner + 1:]
print(json.dumps({
    "command": "verify",
    "steps": [{"name": n, "result": e} for n, e in zip(schritte, ergebnisse)],
    "findings": fehler,
    "result": "FAIL" if fehler else "PASS",
}, ensure_ascii=False))
PY

if [ "$FEHLER" -gt 0 ]; then
  echo "verify: FAIL ($FEHLER von ${#SCHRITTE[@]} Schritten)"
  exit 1
fi
echo "verify: PASS (${#SCHRITTE[@]} Schritte)"

#!/usr/bin/env python3
"""Konformitaets-Testsuite: prueft eine Implementierung gegen die Testfaelle.

Warum es das gibt: Der Standard wird mehrfach umgesetzt – hier in Python,
im Browser des Deklarations-Generators, spaeter vielleicht von Dritten.
Ohne gemeinsame Testfaelle driften diese Umsetzungen auseinander, und ein
Werkzeug sagt "gueltig", waehrend das andere "ungueltig" sagt. Genau das
darf einem Standard nicht passieren.

Die Testfaelle in spec/v0.1/konformitaet/ sind die verbindliche Referenz.
Wer den Standard umsetzt, sollte sie bestehen.

Verwendung:
    python3 werkzeuge/konformitaet.py          # prueft den Python-Validator
    python3 werkzeuge/konformitaet.py --json   # maschinenlesbares Ergebnis

Exit-Code: 0 = alle Faelle bestanden, 1 = mindestens ein Fall gescheitert.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
REPO = HIER.parent
FAELLE = REPO / "spec" / "v0.1" / "konformitaet"
SCHEMA = REPO / "spec" / "v0.1" / "datenfluss.schema.json"

sys.path.insert(0, str(HIER))
from validator import Befund, PROFILE, lade_json, pruefe_schema, pruefe_semantik_universell  # noqa: E402


def pruefe(deklaration: dict, schema: dict, profil: str = "ch") -> Befund:
    """Fuehrt dieselbe Pruefkette aus wie der Validator."""
    befund = Befund()
    pruefe_schema(deklaration, schema, befund)
    if not befund.fehler:
        pruefe_semantik_universell(deklaration, befund)
        PROFILE[profil][1](deklaration, befund)
    return befund


def enthalten(meldungen: list[str], teil: str) -> bool:
    return any(teil in m for m in meldungen)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prueft den Validator gegen die Konformitaets-Testfaelle.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    schema = lade_json(SCHEMA)
    erwartungen = json.loads((FAELLE / "erwartungen.json").read_text(encoding="utf-8"))

    ergebnisse, gescheitert = [], 0
    for datei, erwartet in sorted(erwartungen.items()):
        if datei.startswith("_"):
            continue  # Kommentarschluessel wie _hinweis
        deklaration = lade_json(FAELLE / datei)
        befund = pruefe(deklaration, schema)
        gueltig = befund.standard_konform
        probleme = []

        # 'gueltig' meint Standardkonformitaet. Profil-Befunde (Rechtsraum)
        # laufen getrennt – sie duerfen eine Datei nie standardwidrig machen.
        if gueltig != erwartet["gueltig"]:
            probleme.append(f"erwartet standardkonform={erwartet['gueltig']}, war {gueltig}"
                            + (f" ({befund.fehler[0]})" if befund.fehler else ""))
        for teil in erwartet.get("fehler_enthalten", []):
            if not enthalten(befund.fehler, teil):
                probleme.append(f"Standard-Fehler zu '{teil}' fehlt")
        for teil in erwartet.get("warnung_enthalten", []):
            if not enthalten(befund.warnungen, teil):
                probleme.append(f"Standard-Warnung zu '{teil}' fehlt")
        for teil in erwartet.get("profil_fehler_enthalten", []):
            if not enthalten(befund.profil_fehler, teil):
                probleme.append(f"Profil-Problem zu '{teil}' fehlt")
        for teil in erwartet.get("profil_warnung_enthalten", []):
            if not enthalten(befund.profil_warnungen, teil):
                probleme.append(f"Profil-Hinweis zu '{teil}' fehlt")
        # Gegenrichtung: Ein Fall ohne erwartete Profil-Befunde darf keine haben,
        # sonst schleichen sich Rechtsregeln in Faelle, die Standardregeln testen.
        if erwartet["gueltig"] and not erwartet.get("profil_fehler_enthalten") \
                and not erwartet.get("profil_warnung_enthalten") \
                and (befund.profil_fehler or befund.profil_warnungen):
            probleme.append("unerwartete Profil-Befunde: "
                            + "; ".join(befund.profil_fehler + befund.profil_warnungen))

        if probleme:
            gescheitert += 1
        ergebnisse.append({"fall": datei, "bestanden": not probleme, "probleme": probleme})

    if args.json:
        print(json.dumps({"gescheitert": gescheitert, "ergebnisse": ergebnisse},
                         ensure_ascii=False, indent=2))
    else:
        print(f"Konformitaets-Testsuite – {len(ergebnisse)} Faelle")
        print("-" * 60)
        for r in ergebnisse:
            zeichen = "OK  " if r["bestanden"] else "FEHL"
            print(f"  {zeichen}  {r['fall']}")
            for p in r["probleme"]:
                print(f"          {p}")
        print("-" * 60)
        print(f"Ergebnis: {len(ergebnisse) - gescheitert} bestanden, {gescheitert} gescheitert.")
    return 1 if gescheitert else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validator fuer Datenfluss-Deklarationen (Spezifikation v0.1, Entwurf).

Prueft eine Deklaration in zwei Stufen:
  1. Formal gegen das JSON Schema (datenfluss.schema.json) – rechtsraumunabhaengig
  2. Semantisch: universelle Regeln (Datumslogik, eindeutige IDs, Signatur)
     plus ein waehlbares Pruefprofil fuer den Rechtsraum (--profil, Standard: ch)

Das Format selbst ist rechtsraumneutral; juristische Logik (etwa die Schweizer
Drittland-Regeln) lebt ausschliesslich in Pruefprofilen. Ein weiterer Rechtsraum
(z. B. 'eu' fuer die DSGVO) wird als zusaetzliches Profil in PROFILE ergaenzt,
ohne dass Schema oder Deklarationen sich aendern.

Verwendung:
    python3 validator.py beispiel-deklaration.json
    python3 validator.py --profil ch deklaration.json
    python3 validator.py --schema pfad/zum/schema.json deklaration.json

Exit-Codes: 0 = gueltig (Warnungen moeglich), 1 = Fehler gefunden, 2 = Aufruf-/Dateifehler
Abhaengigkeit: pip install jsonschema
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # pragma: no cover
    print("Fehler: Bibliothek 'jsonschema' fehlt. Installation: pip install jsonschema")
    sys.exit(2)

# ---------------------------------------------------------------------------
# Pruefprofil 'ch' – Vereinfachte Liste der Staaten mit angemessenem
# Datenschutzniveau aus Schweizer Sicht (massgeblich ist Anhang 1 der
# Datenschutzverordnung DSV).
# USA sind bewusst NICHT enthalten: Angemessenheit gilt dort nur fuer
# Empfaenger, die unter dem Swiss-U.S. Data Privacy Framework (DPF)
# zertifiziert sind -> eigener Garantien-Wert 'angemessenheit_dpf_zertifiziert'.
# ---------------------------------------------------------------------------
EU_EWR = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
    "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
    "SI", "ES", "SE", "IS", "LI", "NO",
}
WEITERE_ANGEMESSEN = {
    "GB", "AD", "AR", "CA", "FO", "GG", "IM", "IL", "JE", "MC", "NZ", "UY",
}
ANGEMESSENE_LAENDER = EU_EWR | WEITERE_ANGEMESSEN | {"CH"}

DPF_LISTE_URL = "https://www.dataprivacyframework.gov/list"
MAX_ALTER_TAGE = 548  # ~18 Monate: danach gilt die Deklaration als veraltet


class Befund:
    """Sammelt Fehler und Warnungen mit Fundstelle."""

    def __init__(self) -> None:
        self.fehler: list[str] = []
        self.warnungen: list[str] = []

    def f(self, pfad: str, text: str) -> None:
        self.fehler.append(f"[{pfad}] {text}")

    def w(self, pfad: str, text: str) -> None:
        self.warnungen.append(f"[{pfad}] {text}")


def lade_json(pfad: Path) -> dict:
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"Fehler: Datei nicht gefunden: {pfad}")
        sys.exit(2)
    except json.JSONDecodeError as exc:
        print(f"Fehler: {pfad} ist kein gueltiges JSON ({exc})")
        sys.exit(2)


def pruefe_schema(deklaration: dict, schema: dict, befund: Befund) -> None:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for err in sorted(validator.iter_errors(deklaration), key=lambda e: list(e.absolute_path)):
        pfad = "/".join(str(p) for p in err.absolute_path) or "(wurzel)"
        befund.f(pfad, err.message)


def parse_datum(wert: str | None) -> date | None:
    if not wert:
        return None
    try:
        return date.fromisoformat(wert)
    except ValueError:
        return None


def pruefe_semantik_universell(dekl: dict, befund: Befund) -> None:
    """Rechtsraumunabhaengige Regeln: Datumslogik, eindeutige IDs, Signatur."""
    heute = date.today()

    # --- Datumslogik -------------------------------------------------------
    stand = parse_datum(dekl.get("stand"))
    if stand:
        if stand > heute:
            befund.f("stand", f"Stand-Datum liegt in der Zukunft ({stand}).")
        elif (heute - stand).days > MAX_ALTER_TAGE:
            befund.w("stand", f"Deklaration ist aelter als 18 Monate (Stand {stand}) – Ueberpruefung faellig.")
    naechste = parse_datum(dekl.get("naechste_ueberpruefung"))
    if naechste and stand and naechste <= stand:
        befund.w("naechste_ueberpruefung", "Liegt nicht nach dem Stand-Datum.")
    if naechste and naechste < heute:
        befund.w("naechste_ueberpruefung", f"Ueberpruefungstermin ist verstrichen ({naechste}).")

    # --- Eindeutige IDs ----------------------------------------------------
    ids: dict[str, int] = {}
    for i, b in enumerate(dekl.get("bearbeitungen", [])):
        bid = b.get("id")
        if isinstance(bid, str):
            if bid in ids:
                befund.f(f"bearbeitungen/{i}/id", f"ID '{bid}' bereits in Bearbeitung {ids[bid]} verwendet – IDs muessen eindeutig sein.")
            ids[bid] = i

    # --- Signatur ----------------------------------------------------------
    if "signatur" not in dekl:
        befund.w("signatur", "Deklaration ist unsigniert – zulaessig in v0.1, ab v1.0 verpflichtend.")


def pruefe_profil_ch(dekl: dict, befund: Befund) -> None:
    """Pruefprofil Schweiz: Drittlandtransfers (Art. 16 f. DSG, DSV Anhang 1)
    und DSFA-Hinweise (Art. 22 DSG)."""

    # --- Drittlandtransfers und Garantien ---------------------------------
    for i, b in enumerate(dekl.get("bearbeitungen", [])):
        sensibel = bool(b.get("besonders_schuetzenswert"))
        for j, e in enumerate(b.get("empfaenger", [])):
            pfad = f"bearbeitungen/{i}/empfaenger/{j}"
            land = e.get("land", "")
            garantien = e.get("garantien")
            name = e.get("name", "?")

            if land == "US":
                if garantien == "nicht_erforderlich_angemessenes_land":
                    befund.f(pfad, f"USA gelten nicht generell als angemessen – fuer '{name}' ist eine Garantie noetig (DPF-Zertifizierung, Standarddatenschutzklauseln o. ae.).")
                elif garantien == "angemessenheit_dpf_zertifiziert":
                    befund.w(pfad, f"DPF-Zertifizierung von '{name}' periodisch pruefen: {DPF_LISTE_URL}")
                elif not garantien:
                    befund.f(pfad, f"US-Empfaenger '{name}' ohne Angabe einer Garantie.")
            elif land in ANGEMESSENE_LAENDER:
                if not garantien:
                    befund.w(pfad, f"'{name}' ({land}): Garantie fehlt – 'nicht_erforderlich_angemessenes_land' kann gesetzt werden.")
                elif garantien == "angemessenheit_dpf_zertifiziert":
                    befund.f(pfad, "Garantie 'angemessenheit_dpf_zertifiziert' ist US-Empfaengern vorbehalten.")
            else:  # weder angemessen noch US
                if not garantien:
                    befund.f(pfad, f"'{name}' ({land}): Land ohne angemessenes Schutzniveau – Garantie erforderlich (Art. 16 f. DSG).")
                elif garantien == "nicht_erforderlich_angemessenes_land":
                    befund.f(pfad, f"'{name}' ({land}): Land gilt nicht als angemessen – 'nicht_erforderlich_angemessenes_land' ist unzulaessig.")
                elif garantien == "angemessenheit_dpf_zertifiziert":
                    befund.f(pfad, "Garantie 'angemessenheit_dpf_zertifiziert' ist US-Empfaengern vorbehalten.")

            if sensibel and land not in ANGEMESSENE_LAENDER:
                befund.w(pfad, f"Besonders schuetzenswerte Daten fliessen an '{name}' ({land}) – erhoehte Sorgfalt und ggf. DSFA angezeigt.")

    # --- DSFA-Hinweise -----------------------------------------------------
    dsfa = dekl.get("dsfa_vorhanden")
    for i, b in enumerate(dekl.get("bearbeitungen", [])):
        if b.get("profiling_hohes_risiko") and not dsfa:
            befund.w(f"bearbeitungen/{i}", "Profiling mit hohem Risiko deklariert, aber keine DSFA vorhanden (Art. 22 DSG pruefen).")
        if b.get("automatisierte_einzelentscheidung") and not dsfa:
            befund.w(f"bearbeitungen/{i}", "Automatisierte Einzelentscheidung deklariert – DSFA-Pflicht pruefen.")


# Registrierte Pruefprofile: Kuerzel -> (Beschreibung, Pruef-Funktion).
# Ein neuer Rechtsraum braucht nur einen weiteren Eintrag hier.
PROFILE = {
    "ch": ("Schweiz – DSG/DSV: Drittlandtransfers, DPF-Sonderfall, DSFA-Hinweise", pruefe_profil_ch),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validiert eine Datenfluss-Deklaration gegen Spezifikation v0.1.")
    parser.add_argument("deklaration", type=Path, help="Pfad zur Deklarations-Datei (JSON)")
    parser.add_argument("--schema", type=Path, default=Path(__file__).resolve().parents[1] / "spec" / "v0.1" / "datenfluss.schema.json",
                        help="Pfad zum JSON Schema (Standard: spec/v0.1/datenfluss.schema.json)")
    parser.add_argument("--profil", choices=sorted(PROFILE), default="ch",
                        help="Pruefprofil fuer den Rechtsraum (Standard: ch). " +
                             " | ".join(f"{k}: {v[0]}" for k, v in sorted(PROFILE.items())))
    args = parser.parse_args()

    schema = lade_json(args.schema)
    deklaration = lade_json(args.deklaration)

    befund = Befund()
    pruefe_schema(deklaration, schema, befund)
    if not befund.fehler:  # Semantik nur pruefen, wenn die Struktur stimmt
        pruefe_semantik_universell(deklaration, befund)
        PROFILE[args.profil][1](deklaration, befund)

    name = deklaration.get("organisation", {}).get("name", args.deklaration.name)
    print(f"Datenfluss-Validator v0.1 – Pruefung von: {name} (Pruefprofil: {args.profil})")
    print("-" * 60)
    for w in befund.warnungen:
        print(f"  WARNUNG  {w}")
    for f in befund.fehler:
        print(f"  FEHLER   {f}")
    print("-" * 60)
    if befund.fehler:
        print(f"Ergebnis: UNGUELTIG – {len(befund.fehler)} Fehler, {len(befund.warnungen)} Warnungen.")
        return 1
    print(f"Ergebnis: GUELTIG – 0 Fehler, {len(befund.warnungen)} Warnungen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

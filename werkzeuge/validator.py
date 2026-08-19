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

Exit-Codes:
  0 = standardkonform, keine Profil-Probleme
  1 = Standard verletzt
  2 = Aufruf-/Dateifehler
  3 = standardkonform, aber das Pruefprofil meldet Probleme (Rechtsbefund)
Die Trennung 1/3 ist Absicht: Standardkonformitaet haengt nur an der Datei und
ist stabil. Der Rechtsbefund haengt an der aktuellen Rechtslage und kann sich
aendern, ohne dass sich ein Zeichen der Datei aendert.
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
    "GB", "AD", "AR", "FO", "GG", "GI", "IM", "IL", "JE", "MC", "NZ", "UY",
}

# Bedingt angemessen: Anhang 1 DSV listet diese Staaten nur unter einem
# Vorbehalt. Ob der Vorbehalt erfuellt ist, haengt vom konkreten Empfaenger ab
# und laesst sich aus einer Deklaration allein nicht entscheiden. Sie deshalb
# stillschweigend als angemessen zu behandeln, waere ein falscher Freispruch;
# sie als Drittland zu behandeln, ein falscher Vorwurf. Beides waere schlimmer
# als die Wahrheit: hier muss ein Mensch pruefen.
BEDINGT_ANGEMESSEN = {
    "CA": ("nur soweit das kanadische PIPEDA im Privatsektor anwendbar ist oder "
           "ein weitgehend entsprechendes Provinzgesetz gilt (Anhang 1 DSV)"),
}
ANGEMESSENE_LAENDER = EU_EWR | WEITERE_ANGEMESSEN | {"CH"}

DPF_LISTE_URL = "https://www.dataprivacyframework.gov/list"
MAX_ALTER_TAGE = 548  # ~18 Monate: danach gilt die Deklaration als veraltet


class Befund:
    """Sammelt zwei getrennte Urteile ueber dieselbe Datei.

    Die Trennung ist keine Formsache, sondern der Kern der Versionierbarkeit:

      **Standardkonformitaet ist stabil.** Sie haengt nur an Schema und
      universellen Regeln. Eine Datei, die heute standardkonform ist, bleibt es
      -- solange sich die Datei nicht aendert.

      **Rechtskonformitaet ist zeitabhaengig.** Streicht der Bundesrat morgen
      ein Land von der Angemessenheitsliste, aendert sich die rechtliche
      Beurteilung derselben unveraenderten Datei.

    Wuerde ein Rechtsbefund die Standardkonformitaet kippen, wuerde eine
    gestern gueltige Deklaration heute formal standardwidrig, ohne dass jemand
    ein Zeichen daran geaendert hat. Ein Standard, der sich so verhaelt, ist
    als Fundament unbrauchbar -- niemand kann darauf aufbauen.
    """

    def __init__(self) -> None:
        self.fehler: list[str] = []          # Standard verletzt
        self.warnungen: list[str] = []       # Standard: Hinweis
        self.profil_fehler: list[str] = []   # Rechtsraum verletzt
        self.profil_warnungen: list[str] = []

    def f(self, pfad: str, text: str) -> None:
        """Standardverletzung: die Datei entspricht der Spezifikation nicht."""
        self.fehler.append(f"[{pfad}] {text}")

    def w(self, pfad: str, text: str) -> None:
        self.warnungen.append(f"[{pfad}] {text}")

    def pf(self, pfad: str, text: str) -> None:
        """Rechtsbefund: standardkonform, aber im geprueften Rechtsraum problematisch."""
        self.profil_fehler.append(f"[{pfad}] {text}")

    def pw(self, pfad: str, text: str) -> None:
        self.profil_warnungen.append(f"[{pfad}] {text}")

    @property
    def standard_konform(self) -> bool:
        return not self.fehler


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
    """Rechtsraumunabhaengige, **uhrzeitfreie** Regeln.

    Hier darf nichts stehen, was von der aktuellen Zeit abhaengt. Sonst kippt
    eine unveraenderte Datei ihr Standardurteil beim blossen Verstreichen von
    Zeit -- genau das, was der Docstring von `Befund` ausschliesst.
    Zeitabhaengiges gehoert in `pruefe_aktualitaet()`.
    """
    # --- Datumslogik: nur Beziehungen der Felder untereinander --------------
    stand = parse_datum(dekl.get("stand"))
    naechste = parse_datum(dekl.get("naechste_ueberpruefung"))
    if naechste and stand and naechste <= stand:
        befund.w("naechste_ueberpruefung", "Liegt nicht nach dem Stand-Datum.")

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


def pruefe_aktualitaet(dekl: dict, befund: Befund, heute: date | None = None) -> None:
    """Zeitabhaengige Pruefungen -- bewusst NICHT Teil der Standardkonformitaet.

    Ob eine Deklaration aktuell ist, haengt am Kalender und aendert sich, ohne
    dass jemand die Datei anfasst. Dieses Urteil gehoert deshalb zum
    zeitabhaengigen Befund, genau wie die Rechtslage.

    `heute` ist injizierbar, damit Tests nicht von der Systemuhr abhaengen.
    """
    heute = heute or date.today()
    stand = parse_datum(dekl.get("stand"))
    if stand:
        if stand > heute:
            befund.pf("stand", f"Stand-Datum liegt in der Zukunft ({stand}) – "
                               f"die Deklaration beschreibt einen Zustand, der noch nicht eingetreten ist.")
        elif (heute - stand).days > MAX_ALTER_TAGE:
            befund.pw("stand", f"Deklaration ist aelter als 18 Monate (Stand {stand}) – Ueberpruefung faellig.")
    naechste = parse_datum(dekl.get("naechste_ueberpruefung"))
    if naechste and naechste < heute:
        befund.pw("naechste_ueberpruefung", f"Ueberpruefungstermin ist verstrichen ({naechste}).")


def pruefe_profil_ch(dekl: dict, befund: Befund) -> None:
    """Pruefprofil Schweiz: Drittlandtransfers (Art. 16 f. DSG, DSV Anhang 1)
    und DSFA-Hinweise (Art. 22 DSG).

    Alle Befunde hier landen bewusst in befund.pf()/pw() -- sie beurteilen die
    Rechtslage, nicht die Standardkonformitaet. Aendert sich das Recht, aendert
    sich dieses Urteil; das Urteil ueber die Datei als Datenfluss-Deklaration
    bleibt davon unberuehrt.
    """

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
                    befund.pf(pfad, f"USA gelten nicht generell als angemessen – fuer '{name}' ist eine Garantie noetig (DPF-Zertifizierung, Standarddatenschutzklauseln o. ae.).")
                elif garantien == "angemessenheit_dpf_zertifiziert":
                    befund.pw(pfad, f"DPF-Zertifizierung von '{name}' periodisch pruefen: {DPF_LISTE_URL}")
                elif not garantien:
                    befund.pf(pfad, f"US-Empfaenger '{name}' ohne Angabe einer Garantie.")
            elif land in BEDINGT_ANGEMESSEN:
                vorbehalt = BEDINGT_ANGEMESSEN[land]
                if garantien == "nicht_erforderlich_angemessenes_land":
                    befund.pw(pfad, f"'{name}' ({land}): angemessen {vorbehalt}. "
                                    f"Aus der Deklaration nicht entscheidbar – bitte manuell pruefen.")
                elif not garantien:
                    befund.pw(pfad, f"'{name}' ({land}): angemessen {vorbehalt}. "
                                    f"Ohne Garantie nur zulaessig, wenn der Vorbehalt erfuellt ist – manuell pruefen.")
                elif garantien == "angemessenheit_dpf_zertifiziert":
                    befund.pf(pfad, "Garantie 'angemessenheit_dpf_zertifiziert' ist US-Empfaengern vorbehalten.")
            elif land in ANGEMESSENE_LAENDER:
                if not garantien:
                    befund.pw(pfad, f"'{name}' ({land}): Garantie fehlt – 'nicht_erforderlich_angemessenes_land' kann gesetzt werden.")
                elif garantien == "angemessenheit_dpf_zertifiziert":
                    befund.pf(pfad, "Garantie 'angemessenheit_dpf_zertifiziert' ist US-Empfaengern vorbehalten.")
            else:  # weder angemessen noch US
                if not garantien:
                    befund.pf(pfad, f"'{name}' ({land}): Land ohne angemessenes Schutzniveau – Garantie erforderlich (Art. 16 f. DSG).")
                elif garantien == "nicht_erforderlich_angemessenes_land":
                    befund.pf(pfad, f"'{name}' ({land}): Land gilt nicht als angemessen – 'nicht_erforderlich_angemessenes_land' ist unzulaessig.")
                elif garantien == "angemessenheit_dpf_zertifiziert":
                    befund.pf(pfad, "Garantie 'angemessenheit_dpf_zertifiziert' ist US-Empfaengern vorbehalten.")

            if sensibel and land not in ANGEMESSENE_LAENDER:
                befund.pw(pfad, f"Besonders schuetzenswerte Daten fliessen an '{name}' ({land}) – erhoehte Sorgfalt und ggf. DSFA angezeigt.")

    # --- DSFA-Hinweise -----------------------------------------------------
    dsfa = dekl.get("dsfa_vorhanden")
    for i, b in enumerate(dekl.get("bearbeitungen", [])):
        if b.get("profiling_hohes_risiko") and not dsfa:
            befund.pw(f"bearbeitungen/{i}", "Profiling mit hohem Risiko deklariert, aber keine DSFA vorhanden (Art. 22 DSG pruefen).")
        if b.get("automatisierte_einzelentscheidung") and not dsfa:
            befund.pw(f"bearbeitungen/{i}", "Automatisierte Einzelentscheidung deklariert – DSFA-Pflicht pruefen.")


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
        pruefe_aktualitaet(deklaration, befund)
        PROFILE[args.profil][1](deklaration, befund)

    name = deklaration.get("organisation", {}).get("name", args.deklaration.name)
    print(f"Datenfluss-Validator v0.1 – Pruefung von: {name}")
    print("-" * 60)
    print("STANDARD v0.1 (rechtsraumunabhaengig)")
    for f in befund.fehler:
        print(f"  FEHLER   {f}")
    for w in befund.warnungen:
        print(f"  WARNUNG  {w}")
    if befund.standard_konform:
        print(f"  -> STANDARDKONFORM ({len(befund.warnungen)} Warnung(en))")
    else:
        print(f"  -> NICHT STANDARDKONFORM ({len(befund.fehler)} Fehler)")

    print(f"PRUEFPROFIL {args.profil} – {PROFILE[args.profil][0]}")
    for f in befund.profil_fehler:
        print(f"  PROBLEM  {f}")
    for w in befund.profil_warnungen:
        print(f"  HINWEIS  {w}")
    if not befund.profil_fehler and not befund.profil_warnungen:
        print("  -> keine Befunde")
    print("-" * 60)

    # Zwei getrennte Urteile, drei Exit-Codes:
    #   0 = standardkonform, keine Profil-Probleme
    #   1 = Standard verletzt (stabil: aendert sich nur, wenn die Datei sich aendert)
    #   3 = standardkonform, aber das Pruefprofil meldet Probleme (zeitabhaengig:
    #       kann sich mit der Rechtslage aendern, ohne dass die Datei sich aendert)
    # CI-Nutzer, die auf beides reagieren wollen, pruefen auf != 0 wie bisher.
    if not befund.standard_konform:
        print(f"Ergebnis: NICHT STANDARDKONFORM – {len(befund.fehler)} Fehler.")
        return 1
    if befund.profil_fehler:
        print(f"Ergebnis: STANDARDKONFORM, aber {len(befund.profil_fehler)} Problem(e) "
              f"im Pruefprofil {args.profil}.")
        return 3
    print(f"Ergebnis: STANDARDKONFORM – 0 Fehler, {len(befund.warnungen)} Warnung(en), "
          f"{len(befund.profil_warnungen)} Profil-Hinweis(e).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

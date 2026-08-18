#!/usr/bin/env python3
"""Regressionstests fuer die Sanierung vom 18.08.2026.

Jeder Test hier steht fuer einen Fehler, der einmal real im Repository war und
in einer externen Pruefung gefunden wurde. Sie sind bewusst als eigene Datei
gefuehrt: Wer einen dieser Tests rot macht, hat einen bereits behobenen Mangel
wieder eingebaut.

Aufruf:  python3 werkzeuge/test_sanierung.py
Rueckgabe: 0 = alle Pruefungen bestanden, 1 = mindestens eine fehlgeschlagen.
Kein Netzzugriff.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from email.message import Message
from pathlib import Path

HIER = Path(__file__).resolve().parent
REPO = HIER.parent
sys.path.insert(0, str(HIER))

import renderer  # noqa: E402
import scanner  # noqa: E402
import validator  # noqa: E402
from jsonschema import Draft202012Validator, FormatChecker  # noqa: E402

FEHLER: list[str] = []
GEPRUEFT = 0


def pruefe(bedingung: bool, was: str) -> None:
    global GEPRUEFT
    GEPRUEFT += 1
    if not bedingung:
        FEHLER.append(was)


# ---------------------------------------------------------------------------
# 1. Renderer fuehrte Code aus fremden Deklarationen aus (XSS)
#    'javascript:alert(1)' enthaelt kein Zeichen, das html.escape() veraendert,
#    und landete unveraendert als klickbarer href in der Karte.
# ---------------------------------------------------------------------------
for boese in ("javascript:alert(1)", "JavaScript:alert(1)", "  javascript:alert(1)",
              "data:text/html,<script>alert(1)</script>", "vbscript:msgbox(1)",
              "file:///etc/passwd", "mailto:a@b.ch"):
    pruefe(renderer.sichere_url(boese) is None,
           f"XSS: unzulaessiges Schema wird verlinkt: {boese!r}")

for gut in ("https://firma.example/auskunft", "http://firma.example/f",
            "HTTPS://FIRMA.EXAMPLE/F"):
    pruefe(renderer.sichere_url(gut) is not None, f"XSS-Schutz zu streng: {gut!r}")

pruefe(renderer.sichere_url("https://x.example/?a=1&b=<script>") is not None
       and "&lt;" in renderer.sichere_url("https://x.example/?a=1&b=<script>"),
       "Erlaubte URL wird nicht escaped")
pruefe(renderer.sichere_url(None) is None, "sichere_url(None) muss None ergeben")

# Das Schema selbst darf solche Werte gar nicht erst annehmen (Tiefenschutz).
schema = json.loads((REPO / "spec" / "v0.1" / "datenfluss.schema.json").read_text())
feld = schema["properties"]["auskunft"]["properties"]["formular_url"]
sv = Draft202012Validator(feld, format_checker=FormatChecker())
pruefe(list(sv.iter_errors("javascript:alert(1)")), "Schema akzeptiert javascript:-URL")
pruefe(not list(sv.iter_errors("https://ok.example/f")), "Schema lehnt gueltige https-URL ab")

# ---------------------------------------------------------------------------
# 2. Standardkonformitaet haengte an der Systemuhr
#    Eine unveraenderte Datei kippte ihr Standardurteil beim blossen
#    Verstreichen von Zeit -- der Docstring von Befund schliesst genau das aus.
# ---------------------------------------------------------------------------
zukunft = json.loads(
    (REPO / "spec" / "v0.1" / "konformitaet" / "profilfehler-stand-in-zukunft.json").read_text())

urteile = set()
for stichtag in (date(2020, 1, 1), date(2026, 3, 1), date(2200, 1, 1)):
    b = validator.Befund()
    validator.pruefe_semantik_universell(zukunft, b)
    validator.pruefe_aktualitaet(zukunft, b, heute=stichtag)
    urteile.add(b.standard_konform)
pruefe(urteile == {True},
       f"Standardurteil aendert sich mit der Uhr (beobachtet: {urteile})")

# Der Zeitbefund selbst DARF sich aendern -- er gehoert zum zeitabhaengigen Teil.
b_frueh = validator.Befund()
validator.pruefe_aktualitaet(zukunft, b_frueh, heute=date(2026, 3, 1))
b_spaet = validator.Befund()
validator.pruefe_aktualitaet(zukunft, b_spaet, heute=date(2200, 1, 1))
pruefe(bool(b_frueh.profil_fehler) and not b_spaet.profil_fehler,
       "Zeitbefund reagiert nicht auf den Stichtag")

# Die uhrzeitfreie Pruefung darf ueberhaupt keine Zeit lesen.
b_rein = validator.Befund()
validator.pruefe_semantik_universell(zukunft, b_rein)
pruefe(not any("Zukunft" in m for m in b_rein.fehler + b_rein.warnungen),
       "Zeitabhaengige Meldung steckt wieder in der universellen Pruefung")

# ---------------------------------------------------------------------------
# 3. Kanada wurde pauschal als angemessen behandelt
#    Anhang 1 DSV listet Kanada nur unter Vorbehalt (PIPEDA bzw. entsprechendes
#    Provinzgesetz). Pauschale Angemessenheit war ein falscher Freispruch.
# ---------------------------------------------------------------------------
pruefe("CA" not in validator.ANGEMESSENE_LAENDER,
       "Kanada steht wieder pauschal in ANGEMESSENE_LAENDER")
pruefe("CA" in validator.BEDINGT_ANGEMESSEN, "Kanada fehlt in BEDINGT_ANGEMESSEN")
pruefe("PIPEDA" in validator.BEDINGT_ANGEMESSEN.get("CA", ""),
       "Vorbehalt zu Kanada nennt die Rechtsgrundlage nicht")

ca_dekl = {"bearbeitungen": [{"id": "a", "empfaenger": [
    {"name": "Beispiel Inc.", "rolle": "auftragsbearbeiter", "land": "CA",
     "garantien": "nicht_erforderlich_angemessenes_land"}]}]}
b_ca = validator.Befund()
validator.pruefe_profil_ch(ca_dekl, b_ca)
pruefe(bool(b_ca.profil_warnungen) or bool(b_ca.profil_fehler),
       "Kanadischer Empfaenger laeuft kommentarlos durch")
pruefe(any("manuell" in m.lower() for m in b_ca.profil_warnungen + b_ca.profil_fehler),
       "Kanada-Befund verlangt keine manuelle Pruefung")

# ---------------------------------------------------------------------------
# 4. Cookies wurden ueber split(",") gezaehlt
#    'Expires=Wed, 09 Jun 2027' enthaelt selbst ein Komma; ausserdem gab get()
#    nur den ersten Header zurueck.
# ---------------------------------------------------------------------------
# Ein einzelner Header mit Komma im Expires-Wert: richtig ist 1, der alte
# split(",") zaehlte 2. Dieses Beispiel trennt beide Verfahren wirklich.
einer = Message()
einer["Set-Cookie"] = "a=1; Expires=Wed, 09 Jun 2027 10:18:14 GMT; Path=/"
pruefe(len(einer.get_all("Set-Cookie") or []) == 1,
       "Cookie-Zaehlung verzaehlt sich bei Komma im Expires-Wert")
pruefe(len((einer.get("Set-Cookie") or "").split(",")) == 2,
       "Testannahme: der alte split(',') muss hier nachweislich falsch zaehlen")

# Und mehrere Header: get() saehe nur den ersten.
mehrere = Message()
mehrere["Set-Cookie"] = "a=1; Path=/"
mehrere["Set-Cookie"] = "b=2; Path=/"
pruefe(len(mehrere.get_all("Set-Cookie") or []) == 2,
       "Cookie-Zaehlung erkennt mehrere Header nicht")
pruefe(len((mehrere.get("Set-Cookie") or "").split(",")) == 1,
       "Testannahme: get() sieht nur den ersten Header")

# ---------------------------------------------------------------------------
# 5. Jeder Abruffehler wurde als "keine Deklaration gefunden" gemeldet
#    Nicht-Wissen als Abwesenheit auszugeben ist fuer ein Register untragbar.
# ---------------------------------------------------------------------------
def zusammenfassung_fuer(status: str, fehler: str = "") -> str:
    p = {"url": "https://x.example", "status": 200, "drittanbieter": [],
         "unbekannte_externe_hosts": [], "cookies_beim_erstaufruf": 0,
         "datenfluss_deklaration": {"status": status, "vorhanden": False,
                                    "abruf_fehler": fehler}}
    return scanner.zusammenfassung(p)

fehlend = zusammenfassung_fuer("nicht_vorhanden")
pruefe("keine" in fehlend.lower(), "Abwesenheit wird nicht als solche benannt")

for status in ("nicht_erreichbar", "nicht_abrufbar", "kein_gueltiges_json",
               "pruefung_fehlgeschlagen"):
    text = zusammenfassung_fuer(status, "TimeoutError: x")
    pruefe("UNGEKLAERT" in text, f"Status {status} wird nicht als ungeklaert gemeldet")
    pruefe("kein Nachweis" in text,
           f"Status {status}: fehlender Hinweis, dass Abwesenheit nicht bewiesen ist")
    pruefe("keine /.well-known" not in text,
           f"Status {status} wird faelschlich als 'keine Deklaration' ausgegeben")


# ---------------------------------------------------------------------------
# 6. SSRF: Scanner rief jedes Ziel ab, auch interne Adressen
#    Ein Werkzeug, das fuer Fremde Abrufe ausfuehrt und das Ergebnis
#    veroeffentlicht, ist ohne Zielpruefung ein Bote in fremde Netze.
# ---------------------------------------------------------------------------
import netzschutz  # noqa: E402

VERBOTEN = [
    "http://169.254.169.254/latest/meta-data/",   # Cloud-Metadaten
    "http://[fd00:ec2::254]/",                    # Cloud-Metadaten IPv6
    "http://127.0.0.1:8737/api/vorschlaege",      # lokaler Dienst
    "http://localhost/",
    "http://10.0.0.5/", "http://192.168.1.1/", "http://172.16.0.1/",
    "http://[::1]/", "http://0.0.0.0/",
    "http://100.64.0.1/",                         # Carrier-NAT
    "file:///etc/passwd", "gopher://x/", "ftp://x/",
]
for ziel in VERBOTEN:
    pruefe(not netzschutz.ziel_erlaubt(ziel), f"SSRF: internes Ziel erlaubt: {ziel}")

pruefe(netzschutz.ziel_erlaubt("https://example.com/"),
       "SSRF-Schutz blockiert ein oeffentliches Ziel")

# Weiterleitungen muessen erneut geprueft werden -- der uebliche Umweg.
pruefe(hasattr(scanner, "_GeprueftUmleiten"), "Scanner prueft Weiterleitungsziele nicht")
pruefe(hasattr(scanner._GeprueftUmleiten, "redirect_request"),
       "Weiterleitungspruefung greift nicht in redirect_request ein")

# Die Verweigerung muss als eigener Zustand erscheinen, nicht als Absturz
# und nicht als gewoehnlicher Messfehler.
verweigert = scanner.zusammenfassung({
    "url": "http://127.0.0.1/", "status": "abgelehnt_kein_oeffentliches_ziel",
    "fehler": "Loopback-Adresse"})
pruefe("abgelehnt_kein_oeffentliches_ziel" in verweigert,
       "Verweigertes Ziel wird in der Zusammenfassung nicht benannt")


def main() -> int:
    if FEHLER:
        print(f"FEHLGESCHLAGEN ({len(FEHLER)}):")
        for f in FEHLER:
            print(f"  - {f}")
        return 1
    print(f"Sanierung: alle Pruefungen bestanden ({GEPRUEFT} Faelle, ohne Netzzugriff).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

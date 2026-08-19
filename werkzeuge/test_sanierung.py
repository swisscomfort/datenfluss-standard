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
pruefe(hasattr(netzschutz, "GeprueftUmleiten"), "Weiterleitungspruefung fehlt")
pruefe(hasattr(netzschutz.GeprueftUmleiten, "redirect_request"),
       "Weiterleitungspruefung greift nicht in redirect_request ein")

# Die Verweigerung muss als eigener Zustand erscheinen, nicht als Absturz
# und nicht als gewoehnlicher Messfehler.
verweigert = scanner.zusammenfassung({
    "url": "http://127.0.0.1/", "status": "abgelehnt_kein_oeffentliches_ziel",
    "fehler": "Loopback-Adresse"})
pruefe("abgelehnt_kein_oeffentliches_ziel" in verweigert,
       "Verweigertes Ziel wird in der Zusammenfassung nicht benannt")


# ---------------------------------------------------------------------------
# 7. Zweite Gegenpruefung: SSRF ueber Weiterleitung im Einwilligungs-Leser
#    pruefe_ziel() sicherte nur die Eingangs-URL; urlopen() folgt Umleitungen
#    selbsttaetig. Beide Werkzeuge muessen dieselbe geprueffte Schicht nutzen.
# ---------------------------------------------------------------------------
import einwilligung  # noqa: E402

quelltext = (HIER / "einwilligung.py").read_text()
pruefe("oeffne(" in quelltext, "Einwilligungs-Leser nutzt die geprueffte Abrufschicht nicht")
pruefe("urlopen(req" not in quelltext,
       "Einwilligungs-Leser ruft weiterhin ungeprueft mit urlopen ab")
pruefe(hasattr(netzschutz, "GeprueftUmleiten") and hasattr(netzschutz, "oeffne"),
       "Gemeinsame redirect-sichere Abrufschicht fehlt")
scanner_text = (HIER / "scanner.py").read_text()
pruefe("class _GeprueftUmleiten" not in scanner_text,
       "Scanner haelt eine zweite Kopie der Umleitungspruefung -- eine Quelle genuegt")
pruefe("oeffne(req" in scanner_text, "Scanner nutzt die gemeinsame Abrufschicht nicht")

# ---------------------------------------------------------------------------
# 8. DNS-Antwortcode wurde nicht ausgewertet
#    SERVFAIL/REFUSED lieferten eine leere Antwortliste -- und daraus wurde
#    "kein MX-Eintrag gefunden". Nichtwissen als Abwesenheit, erneut.
# ---------------------------------------------------------------------------
import dns_messung  # noqa: E402

pruefe(hasattr(dns_messung, "RCODE_NAMEN"), "DNS-Antwortcodes sind nicht benannt")
pruefe(dns_messung.RCODE_NAMEN.get(2) == "SERVFAIL", "SERVFAIL nicht bekannt")
pruefe(dns_messung.RCODE_NAMEN.get(5) == "REFUSED", "REFUSED nicht bekannt")
pruefe(dns_messung.RCODE_KEIN_FEHLER == 0 and dns_messung.RCODE_NAME_EXISTIERT_NICHT == 3,
       "Gueltige Antwortcodes falsch definiert")
a = dns_messung.Aufloeser()
pruefe(hasattr(a, "ungeklaert"), "Aufloeser fuehrt keine ungeklaerten Fragen")

zusammen = dns_messung.zusammenfassung({
    "domain": "x.ch", "post_empfaenger": [],
    "sendeberechtigte": {"vorhanden": False, "dienste": [], "unbekannte_includes": []},
    "erste_partei_tarnung": [], "laender_hinweise": [],
    "ungeklaerte_fragen": [{"name": "x.ch", "typ": "MX", "grund": "SERVFAIL"}]})
pruefe("UNGEKLAERT" in zusammen, "Ungeklaerte DNS-Frage wird nicht als solche gemeldet")
pruefe("kein MX-Eintrag gefunden" not in zusammen,
       "SERVFAIL erscheint weiterhin als 'kein Eintrag gefunden'")

leer = dns_messung.zusammenfassung({
    "domain": "x.ch", "post_empfaenger": [],
    "sendeberechtigte": {"vorhanden": False, "dienste": [], "unbekannte_includes": []},
    "erste_partei_tarnung": [], "laender_hinweise": []})
pruefe("kein MX-Eintrag vorhanden" in leer,
       "Echte Abwesenheit wird nicht mehr als Abwesenheit benannt")

# SPF-Umfang darf nicht mehr behaupten, er kenne die Sendeberechtigung.
pruefe("wer darf in ihrem Namen senden" not in dns_messung.sendeberechtigte.__doc__.lower()
       or "nicht" in dns_messung.sendeberechtigte.__doc__.lower(),
       "SPF-Aussage weiterhin zu stark formuliert")

# ---------------------------------------------------------------------------
# 9. Schema und Renderer akzeptierten unterschiedliche Schreibweisen
# ---------------------------------------------------------------------------
for schreibweise in ("HTTPS://OK.EXAMPLE/F", "HtTpS://x.ch", "https://ok.example/f"):
    vom_schema = not list(sv.iter_errors(schreibweise))
    vom_renderer = renderer.sichere_url(schreibweise) is not None
    pruefe(vom_schema == vom_renderer,
           f"Schema und Renderer sind uneinig ueber {schreibweise!r}: "
           f"Schema={vom_schema}, Renderer={vom_renderer}")

# ---------------------------------------------------------------------------
# 10. Aktualitaetsbefund war beim Herausloesen der Uhrzeit still verschwunden
# ---------------------------------------------------------------------------
pruefe(hasattr(scanner, "_aktualitaet_pruefen"),
       "Scanner ermittelt keinen Aktualitaetsbefund mehr")
befunde_akt = scanner._aktualitaet_pruefen(zukunft)
pruefe(any("Zukunft" in b for b in befunde_akt),
       "Zukunftsdatum taucht im Profil nicht mehr auf")
pruefe(scanner._deklaration_pruefen(zukunft)[0] == "konform",
       "Aktualitaet kippt faelschlich die Konformitaet")

# ---------------------------------------------------------------------------
# 11. Der vollstaendige scanne()-Pfad -- nicht nur seine Einzelteile
#
#     Die Runden 1 und 2 hatten je einen Fehler, den die Tests nicht sahen,
#     weil sie nur die neue Regel isoliert prueften und nie den Weg, ueber den
#     diese Regel spaeter in ein oeffentliches Profil gelangt:
#       - hole() gab die Kopfzeilen als dict zurueck, scanne() rief darauf
#         get_all() auf. Ein dict hat kein get_all -> AttributeError mitten in
#         einem *erfolgreichen* Scan. Der Test prueffte Message.get_all()
#         allein und war gruen.
#       - Der Aktualitaetsbefund wurde in dekl_info geschrieben, bevor dekl_info
#         neu zugewiesen wurde -- und war damit wieder weg. Der Test rief
#         _aktualitaet_pruefen() direkt auf und war gruen.
#
#     Daraus die Regel fuer alles Weitere: Jede Regel, die spaeter Geld,
#     oeffentliche Befunde oder Kundenalarme beeinflusst, wird mindestens
#     einmal ueber ihren vollstaendigen Pfad geprueft.
# ---------------------------------------------------------------------------
_dekl_e2e = json.loads(json.dumps(zukunft))
_dekl_e2e["stand"] = "2999-01-01"   # unabhaengig vom Kalender in der Zukunft

_kopf_e2e = Message()
_kopf_e2e["Content-Type"] = "text/html; charset=utf-8"
# Drei echte Set-Cookie-Zeilen, eine davon mit Komma im Expires-Wert:
# genau die Antwort, an der sowohl dict() als auch split(",") scheitern.
_kopf_e2e["Set-Cookie"] = "a=1; Path=/"
_kopf_e2e["Set-Cookie"] = "b=2; Expires=Wed, 09 Jun 2027 10:18:14 GMT"
_kopf_e2e["Set-Cookie"] = "c=3; Secure"

_HTML_E2E = ("<html><head><script src='https://www.googletagmanager.com/gtag/js'>"
             "</script></head><body>hallo</body></html>")


class _AntwortE2E:
    """Antwortobjekt in der Form, die urllib liefert.

    Die Attrappe sitzt bewusst UNTER hole(), nicht darueber: Der erste
    Anlauf dieses Tests ersetzte hole() selbst -- und uebersprang damit
    genau die Zeile, die in der Produktion abstuerzte. Ein Testdoppel darf
    nie den Code ersetzen, den es pruefen soll.
    """

    def __init__(self, url, status, kopf, koerper):
        self._url, self.status, self.headers = url, status, kopf
        self._koerper = koerper.encode("utf-8")

    def read(self, n=-1):
        return self._koerper[:n] if n and n > 0 else self._koerper

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _oeffne_e2e(req, timeout=None):
    """Testdoppel fuer netzschutz.oeffne(): kein Netz, sonst alles echt."""
    url = req if isinstance(req, str) else req.full_url
    if url.endswith("/.well-known/datenfluss.json"):
        return _AntwortE2E(url, 200, Message(), json.dumps(_dekl_e2e))
    if url.endswith("/.well-known/security.txt"):
        return _AntwortE2E(url, 404, Message(), "")
    return _AntwortE2E(url, 200, _kopf_e2e, _HTML_E2E)


_echtes_oeffne, _echtes_robots = scanner.oeffne, scanner.robots_erlaubt
scanner.oeffne, scanner.robots_erlaubt = _oeffne_e2e, lambda _url: True
try:
    _profil = scanner.scanne("https://beispiel.example")
finally:
    scanner.oeffne, scanner.robots_erlaubt = _echtes_oeffne, _echtes_robots

pruefe(_profil.get("status") == 200,
       f"scanne() bricht bei einer erfolgreichen Antwort ab: {_profil.get('status')!r} "
       f"{_profil.get('fehler', '')}")
pruefe(_profil.get("cookies_beim_erstaufruf") == 3,
       f"Set-Cookie-Zeilen falsch gezaehlt: {_profil.get('cookies_beim_erstaufruf')!r} statt 3")

_d = _profil.get("datenfluss_deklaration", {})
pruefe(_d.get("status") == "konform",
       f"Deklaration im vollen Pfad nicht als konform erkannt: {_d.get('status')!r}")
pruefe("aktualitaet" in _d,
       "Aktualitaetsbefund fehlt im erzeugten Profil (wird ueberschrieben)")
pruefe(any("Zukunft" in b for b in _d.get("aktualitaet", [])),
       f"Zukunftsdatum nicht im Profilbefund: {_d.get('aktualitaet')!r}")

# Und die Zaehlkapsel selbst: sie muss auch eine abgeflachte Abbildung
# ueberleben, statt einen erfolgreichen Scan mit AttributeError zu beenden.
pruefe(scanner.zaehle_cookies(_kopf_e2e) == 3, "zaehle_cookies zaehlt Message falsch")
pruefe(scanner.zaehle_cookies(dict(_kopf_e2e)) == 1,
       "zaehle_cookies stuerzt bei einem dict ab, statt zu wenig zu zaehlen")
pruefe(scanner.zaehle_cookies(Message()) == 0, "zaehle_cookies zaehlt ohne Cookies falsch")

# ---------------------------------------------------------------------------
# 12. CNAME: ungeklaert darf nicht zu "keiner zeigt auf einen Dritten" werden
# ---------------------------------------------------------------------------
_dns_offen = {
    "domain": "beispiel.ch", "post_empfaenger": [],
    "sendeberechtigte": {"dienste": [], "unbekannte_includes": []},
    "erste_partei_tarnung": [], "laender_hinweise": [],
    "ungeklaerte_fragen": [{"name": "metrics.beispiel.ch", "typ": "CNAME",
                            "grund": "SERVFAIL"}],
}
_text_offen = dns_messung.zusammenfassung(_dns_offen)
pruefe("Keine der geprueften Subdomains zeigt auf einen Dritten" not in _text_offen,
       "Abwesenheitsbehauptung trotz ungeklaerter CNAME-Frage")
pruefe("ungeklaert" in _text_offen,
       "Ungeklaerte CNAME-Frage wird in der Zusammenfassung nicht benannt")

_dns_klar = {**_dns_offen, "ungeklaerte_fragen": []}
pruefe("Keine der geprueften Subdomains zeigt auf einen Dritten"
       in dns_messung.zusammenfassung(_dns_klar),
       "Bei vollstaendig beantworteten Fragen fehlt die klare Aussage")


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

#!/usr/bin/env python3
"""Selbsttest des Einwilligungs-Lesers. Laeuft ohne Netz: geprueft wird die
Auswertungslogik an festen Beispieldaten, nicht der Abruf.

Aufruf:  python3 werkzeuge/test_einwilligung.py
Rueckgabe: 0 = alle Pruefungen bestanden, 1 = mindestens eine fehlgeschlagen.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import einwilligung as ew  # noqa: E402

FEHLER: list[str] = []
GEPRUEFT = 0


def pruefe(bedingung: bool, was: str) -> None:
    global GEPRUEFT
    GEPRUEFT += 1
    if not bedingung:
        FEHLER.append(was)


# --- Kennung im Quelltext finden -------------------------------------------
KENNUNG = "f1aeb90f-3d11-4baf-b163-9b7fc7e715cd"
pruefe(ew.finde_onetrust(
    f'<script src="https://cdn.cookielaw.org/scripttemplates/otSDKStub.js" '
    f'data-domain-script="{KENNUNG}"></script>') == KENNUNG,
    "Kennung: doppelte Anfuehrungszeichen")
pruefe(ew.finde_onetrust(f"<script data-domain-script='{KENNUNG}'>") == KENNUNG,
       "Kennung: einfache Anfuehrungszeichen")
pruefe(ew.finde_onetrust(f'data-domain-script="{KENNUNG}-test"') == f"{KENNUNG}-test",
       "Kennung: Testumgebungs-Suffix wird mitgenommen")
pruefe(ew.finde_onetrust("<html><body>nichts</body></html>") is None,
       "Kennung: Seite ohne CMP ergibt None")
pruefe(ew.finde_onetrust('data-domain-script="keine-uuid"') is None,
       "Kennung: Nicht-UUID wird nicht akzeptiert")

# --- Regelsaetze ------------------------------------------------------------
konfig = {"RuleSet": [
    {"Id": "aaa", "Name": "Global", "Countries": ["us", "de"], "Default": True},
    {"Id": "bbb", "Name": "Switzerland", "Countries": ["CH"], "Default": False},
    {"Id": "ccc", "Name": "Ohne Laender", "Countries": [], "Default": False},
]}
s = ew.regelsaetze(konfig)
pruefe(len(s) == 3, "Regelsaetze: alle uebernommen")
pruefe(s[1]["gilt_fuer_schweiz"] is True, "Regelsaetze: CH wird unabhaengig von Gross/Klein erkannt")
pruefe(s[0]["gilt_fuer_schweiz"] is False, "Regelsaetze: fremder Satz nicht als CH markiert")
pruefe(s[0]["ist_standard"] is True and s[1]["ist_standard"] is False,
       "Regelsaetze: Standard-Kennzeichen uebernommen")
pruefe(s[2]["laender_anzahl"] == 0, "Regelsaetze: leere Laenderliste ist kein Fehler")
pruefe(ew.regelsaetze({}) == [], "Regelsaetze: fehlender Schluessel ergibt leere Liste")

# --- Kategorien und Deutung -------------------------------------------------
dd = {"Groups": [
    {"GroupName": "Unbedingt erforderlich", "Status": "always active", "IsIabPurpose": False},
    {"GroupName": "Marketing", "Status": "active", "IsIabPurpose": False},
    {"GroupName": "Profilbildung", "Status": "inactive", "IsIabPurpose": True},
    {"GroupName": "Ohne Status", "IsIabPurpose": False},
]}
k = ew.kategorien(dd)
pruefe(len(k) == 4, "Kategorien: alle uebernommen")
pruefe(k[0]["status_deutung"] == "immer aktiv (nicht abwaehlbar)", "Kategorien: always active gedeutet")
pruefe(k[1]["status_deutung"] == "vorbelegt aktiv (Widerspruch noetig)", "Kategorien: active gedeutet")
pruefe(k[2]["status_deutung"] == "vorbelegt inaktiv (Zustimmung noetig)", "Kategorien: inactive gedeutet")
pruefe(k[3]["status_roh"] is None and k[3]["status_deutung"] == "unbekannt",
       "Kategorien: fehlender Status wird nicht geraten")
pruefe(all("status_roh" in e for e in k),
       "Kategorien: Rohwert bleibt neben der Deutung erhalten")
pruefe(k[2]["ist_iab_zweck"] is True, "Kategorien: IAB-Zweck markiert")

# --- Namen aufloesen --------------------------------------------------------
liste = {"vendors": {"1": {"name": "Alpha"}, "2": {"name": "Beta"}, "3": {}}}
namen, offen = ew._anbieternamen([1, 2, 3, 99], liste)
pruefe(namen == ["Alpha", "Beta"], "Namen: bekannte werden aufgeloest und sortiert")
pruefe(offen == 2, "Namen: unaufgeloeste werden gezaehlt (fehlender Name und fehlende ID)")
pruefe(ew._anbieternamen([], liste) == ([], 0), "Namen: leere Liste ist kein Fehler")
pruefe(ew._anbieternamen([1], {})[1] == 1, "Namen: fehlende Anbieterliste raet nicht")

# --- Laenderunterschied -----------------------------------------------------
gleich = [
    {"regelsatz": "A", "kategorien": [{"name": "Marketing", "status_roh": "inactive"}]},
    {"regelsatz": "B", "kategorien": [{"name": "Marketing", "status_roh": "inactive"}]},
]
pruefe(ew._laenderunterschied(gleich)["kategorien_mit_abweichender_vorbelegung"] == [],
       "Unterschied: gleiche Vorbelegung ergibt keinen Befund")
verschieden = [
    {"regelsatz": "A", "kategorien": [{"name": "Marketing", "status_roh": "inactive"},
                                      {"name": "Technik", "status_roh": "always active"}]},
    {"regelsatz": "B", "kategorien": [{"name": "Marketing", "status_roh": "active"},
                                      {"name": "Technik", "status_roh": "always active"}]},
]
u = ew._laenderunterschied(verschieden)
pruefe(u["kategorien_mit_abweichender_vorbelegung"] == ["Marketing"],
       "Unterschied: abweichende Kategorie wird benannt")
pruefe("Technik" not in u["kategorien_mit_abweichender_vorbelegung"],
       "Unterschied: uebereinstimmende Kategorie bleibt aussen vor")
pruefe(ew._laenderunterschied(gleich[:1])["vergleichbar"] is False,
       "Unterschied: ein einzelner Regelsatz ist nicht vergleichbar")
pruefe(ew._laenderunterschied([{"regelsatz": "A", "fehler": "x"},
                               {"regelsatz": "B", "fehler": "y"}])["vergleichbar"] is False,
       "Unterschied: nur fehlerhafte Saetze sind nicht vergleichbar")

# --- Zusammenfassung --------------------------------------------------------
messung = {
    "url": "https://beispiel.ch", "status": "gemessen", "plattform": "OneTrust",
    "auswertung": [{
        "regelsatz": "Switzerland", "gilt_fuer_schweiz": True,
        "iab_partner_freigeschaltet": 714, "google_partner_freigeschaltet": 546,
        "weitere_partner_ausserhalb_iab": 0,
        "kategorien": [{"name": "Marketing", "status_roh": "active",
                        "status_deutung": "vorbelegt aktiv (Widerspruch noetig)",
                        "ist_iab_zweck": False}],
    }],
    "laenderunterschied": {"vergleichbar": True, "kategorien_gesamt": 1,
                           "kategorien_mit_abweichender_vorbelegung": ["Marketing"]},
}
text = ew.zusammenfassung(messung)
pruefe("714" in text and "546" in text, "Zusammenfassung: Zahlen erscheinen")
pruefe("gilt fuer die Schweiz" in text, "Zusammenfassung: CH-Regelsatz markiert")
pruefe("Obergrenze" in text, "Zusammenfassung: Deutung als Obergrenze wird immer mitgegeben")

ohne = ew.zusammenfassung({"url": "https://beispiel.ch",
                           "status": "keine_bekannte_plattform",
                           "hinweis": "kein Nachweis"})
pruefe("kein Nachweis" in ohne,
       "Zusammenfassung: fehlende Plattform wird als Nichtwissen ausgegeben")
fehler = ew.zusammenfassung({"url": "https://x.ch", "status": "fehler", "fehler": "URLError: x"})
pruefe("URLError" in fehler, "Zusammenfassung: Abruffehler wird sichtbar gemacht")

mit_fehlerhaftem_satz = dict(messung)
mit_fehlerhaftem_satz["auswertung"] = [{"regelsatz": "Global", "fehler": "HTTPError: 404"}]
pruefe("nicht lesbar" in ew.zusammenfassung(mit_fehlerhaftem_satz),
       "Zusammenfassung: unlesbarer Regelsatz wird benannt statt uebergangen")


def main() -> int:
    if FEHLER:
        print(f"FEHLGESCHLAGEN ({len(FEHLER)}):")
        for f in FEHLER:
            print(f"  - {f}")
        return 1
    print(f"Einwilligung: alle Pruefungen bestanden ({GEPRUEFT} Faelle, ohne Netzzugriff).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

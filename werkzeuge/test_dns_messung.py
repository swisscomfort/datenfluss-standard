#!/usr/bin/env python3
"""Selbsttest der DNS-Messung. Laeuft ohne Netz: der Aufloeser wird durch
feste Antworten ersetzt. Geprueft wird die Auswertungslogik, nicht das DNS.

Aufruf:  python3 werkzeuge/test_dns_messung.py
Rueckgabe: 0 = alle Pruefungen bestanden, 1 = mindestens eine fehlgeschlagen.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dns_messung as dm  # noqa: E402

FEHLER: list[str] = []
GEPRUEFT = 0


def pruefe(bedingung: bool, was: str) -> None:
    global GEPRUEFT
    GEPRUEFT += 1
    if not bedingung:
        FEHLER.append(was)


class FesterAufloeser(dm.Aufloeser):
    """Aufloeser mit vorgegebenen Antworten – kein Netzzugriff."""

    def __init__(self, antworten: dict[tuple[str, str], list[str]]) -> None:
        self.dienst = "test"
        self.basis = ""
        self.speicher = {}
        self.fehler = []
        self._antworten = {(n.lower(), t.upper()): v for (n, t), v in antworten.items()}

    def frage(self, name: str, typ: str) -> list[str]:
        return list(self._antworten.get((name.lower(), typ.upper()), []))


# --- registrierbar ---------------------------------------------------------
pruefe(dm.registrierbar("www.landi.ch") == "landi.ch", "registrierbar: Subdomain")
pruefe(dm.registrierbar("landi.ch") == "landi.ch", "registrierbar: nackte Domain")
pruefe(dm.registrierbar("A.B.EXAMPLE.COM") == "example.com", "registrierbar: Grossschreibung")
pruefe(dm.registrierbar("localhost") == "localhost", "registrierbar: einteilig")
pruefe(dm.registrierbar("x.y.z.co.uk") == "co.uk",
       "registrierbar: zusammengesetzte Endung wird bewusst zu grob zusammengefasst")

# --- _zuordnen: laengste Uebereinstimmung gewinnt ---------------------------
tabelle = [("outlook.com", "Outlook", "US"), ("mail.protection.outlook.com", "M365", "US")]
treffer = dm._zuordnen("firma.mail.protection.outlook.com", tabelle)
pruefe(treffer is not None and treffer[1] == "M365", "_zuordnen: spezifischer Eintrag gewinnt")
pruefe(dm._zuordnen("beispiel.test", tabelle) is None, "_zuordnen: Unbekanntes bleibt unbekannt")
pruefe(dm._zuordnen("nichtoutlook.com", tabelle) is None,
       "_zuordnen: Teilstring ohne Punktgrenze zaehlt nicht")

# --- Post-Empfaenger -------------------------------------------------------
a = FesterAufloeser({
    ("firma.ch", "MX"): ["10 firma-ch.mail.protection.outlook.com.",
                         "20 firma-ch.mail.protection.outlook.com."],
})
post = dm.post_empfaenger(a, "firma.ch")
pruefe(len(post) == 1, "MX: gleiche Anbieter werden zusammengefasst")
pruefe(post and post[0]["anbieter"] == "Microsoft 365", "MX: Anbieter erkannt")
pruefe(post and post[0]["sitz_hinweis"] == "US", "MX: Sitz-Hinweis gesetzt")
pruefe(post and post[0]["erkannt"] is True, "MX: als erkannt markiert")

a = FesterAufloeser({("firma.ch", "MX"): ["10 mx.eigener-anbieter.example."]})
post = dm.post_empfaenger(a, "firma.ch")
pruefe(post and post[0]["erkannt"] is False, "MX: Unbekanntes wird als unerkannt gemeldet")
pruefe(post and post[0]["sitz_hinweis"] == "unbekannt", "MX: kein geratener Sitz")

pruefe(dm.post_empfaenger(FesterAufloeser({}), "firma.ch") == [],
       "MX: fehlender Eintrag ergibt leere Liste, keinen Fehler")

# --- SPF -------------------------------------------------------------------
a = FesterAufloeser({("firma.ch", "TXT"): [
    '"v=spf1 ip4:1.2.3.4 include:spf.protection.outlook.com '
    'include:servers.mcsv.net include:spf.eigen.example ~all"',
    '"google-site-verification=abc"',
]})
spf = dm.sendeberechtigte(a, "firma.ch")
pruefe(spf["vorhanden"] is True, "SPF: Eintrag gefunden")
namen = [d["anbieter"] for d in spf["dienste"]]
pruefe("Microsoft 365" in namen and "Mailchimp" in namen, "SPF: bekannte Dienste erkannt")
pruefe(spf["unbekannte_includes"] == ["spf.eigen.example"],
       "SPF: unbekannte Includes werden ausgewiesen statt geraten")

pruefe(dm.sendeberechtigte(FesterAufloeser({}), "firma.ch")["vorhanden"] is False,
       "SPF: kein Eintrag ist kein Fehler")
a = FesterAufloeser({("firma.ch", "TXT"): ['"nur-irgendein-txt"']})
pruefe(dm.sendeberechtigte(a, "firma.ch")["vorhanden"] is False,
       "SPF: fremde TXT-Eintraege werden nicht als SPF gelesen")

# --- Erste-Partei-Tarnung --------------------------------------------------
a = FesterAufloeser({
    ("metrics.firma.ch", "CNAME"): ["firma.data.adobedc.net."],
    ("www.firma.ch", "CNAME"): ["edge.firma.ch."],          # eigen -> kein Befund
    ("shop.firma.ch", "CNAME"): ["laden.unbekannt.example."],
})
befunde = dm.erste_partei_tarnung(a, "firma.ch", ("metrics", "www", "shop"))
subs = {b["subdomain"]: b for b in befunde}
pruefe("metrics.firma.ch" in subs, "CNAME: fremdes Ziel wird gemeldet")
pruefe(subs.get("metrics.firma.ch", {}).get("anbieter") == "Adobe Experience Cloud",
       "CNAME: Anbieter erkannt")
pruefe("www.firma.ch" not in subs, "CNAME: eigenes Ziel erzeugt keinen Befund")
pruefe(subs.get("shop.firma.ch", {}).get("erkannt") is False,
       "CNAME: unbekanntes Ziel wird gemeldet, aber nicht zugeordnet")
pruefe(dm.erste_partei_tarnung(FesterAufloeser({}), "firma.ch", ("www",)) == [],
       "CNAME: keine Eintraege ergibt leere Liste")

# --- Zusammenfassung laeuft auf leerem Befund durch ------------------------
leer = {
    "domain": "firma.ch", "post_empfaenger": [],
    "sendeberechtigte": {"vorhanden": False, "dienste": [], "unbekannte_includes": []},
    "erste_partei_tarnung": [], "laender_hinweise": [],
}
try:
    text = dm.zusammenfassung(leer)
    pruefe("kein MX-Eintrag gefunden" in text, "Zusammenfassung: leerer Befund wird benannt")
except Exception as exc:  # pragma: no cover - soll nie eintreten
    FEHLER.append(f"Zusammenfassung wirft bei leerem Befund: {exc!r}")

# --- Tabellen sind widerspruchsfrei ---------------------------------------
for name, tab in (("POSTANBIETER", dm.POSTANBIETER), ("SPF_VERSENDER", dm.SPF_VERSENDER)):
    schluessel = [e[0] for e in tab]
    pruefe(len(schluessel) == len(set(schluessel)), f"{name}: keine doppelten Host-Endungen")
cname_schluessel = [e[0] for e in dm.CNAME_ZIELE]
pruefe(len(cname_schluessel) == len(set(cname_schluessel)),
       "CNAME_ZIELE: keine doppelten Host-Endungen")
pruefe(all(len(e) == 4 for e in dm.CNAME_ZIELE), "CNAME_ZIELE: vier Felder je Eintrag")
pruefe(len(set(dm.SUBDOMAIN_STICHPROBE)) == len(dm.SUBDOMAIN_STICHPROBE),
       "SUBDOMAIN_STICHPROBE: keine Doppelten")


def main() -> int:
    if FEHLER:
        print(f"FEHLGESCHLAGEN ({len(FEHLER)}):")
        for f in FEHLER:
            print(f"  - {f}")
        return 1
    print(f"DNS-Messung: alle Pruefungen bestanden ({GEPRUEFT} Faelle, ohne Netzzugriff).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Einwilligungs-Umfang statisch lesen – ohne JavaScript, ohne Klick.

Warum diese Ebene:
  Der Website-Scanner sieht die statisch eingebundenen Dienste. Was nach einem
  Klick auf «Alle akzeptieren» passiert, sieht er nicht – und ein Browser-Lauf
  loest die Uebertragung tatsaechlich aus, misst nur *einen* Aufruf und haengt
  von Region, Werbeauktion und Banner-Variante ab.

  Die Einwilligungsplattform (CMP) veroeffentlicht ihre Konfiguration aber als
  gewoehnliche JSON-Datei. Darin steht, wie viele Partner ueberhaupt
  einwilligungsfaehig geschaltet sind, welche Kategorien es gibt – und in
  welchem Zustand diese Kategorien **je Land** vorbelegt sind. Das ist
  reproduzierbar, unabhaengig vom Zufall eines einzelnen Seitenaufrufs, und es
  loest keine einzige Uebertragung an Werbepartner aus.

Was gemessen wird (und was ausdruecklich nicht):
  GEMESSEN:  Wie viele Partner *koennen* eine Einwilligung erhalten, wie
             heissen sie, und wie sind die Kategorien je Regelsatz vorbelegt.
  NICHT:     Wer bei einem konkreten Besuch tatsaechlich Daten bekommen hat.
             Der Einwilligungsumfang ist eine Obergrenze, so wie der
             Website-Scan eine Untergrenze ist. Beides sind Randwerte, keine
             Messung des realen Einzelfalls – und sie duerfen nie als solche
             dargestellt werden.

Bewusste Grenzen:
  - Heute wird nur OneTrust erkannt. Andere Plattformen (Sourcepoint, Usercentrics,
    Cookiebot, Didomi) sind nicht umgesetzt; ihr Fehlen heisst nicht, dass keine
    CMP vorhanden ist.
  - Die Bedeutung des Feldes `Status` ("active"/"inactive") ist aus den Daten
    erschlossen und im Ergebnis als solche gekennzeichnet. Bevor daraus je eine
    oeffentliche Aussage wird, muss sie gegen die Herstellerdokumentation
    bestaetigt werden.
  - Namen der Partner stammen aus der globalen IAB-Anbieterliste. Wer dort
    fehlt, wird als unaufgeloest gezaehlt und nicht geraten.

Verwendung:
    python3 einwilligung.py https://www.beispiel.ch
    python3 einwilligung.py --json --namen https://www.beispiel.ch

Nur Python-Standardbibliothek.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from netzschutz import ZielAbgelehnt, pruefe_ziel  # noqa: E402

TIMEOUT = 20
USER_AGENT = "DatenflussScanner/0.1 (offener-standard-prototyp)"

ONETRUST_CDN = "https://cdn.cookielaw.org"
IAB_ANBIETERLISTE = f"{ONETRUST_CDN}/vendorlist/iab2V2Data.json"

# OneTrust-Kennung im Seitenquelltext, z. B.
#   <script ... data-domain-script="f1aeb90f-3d11-4baf-b163-9b7fc7e715cd">
ONETRUST_KENNUNG = re.compile(
    r'data-domain-script=["\']([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-'
    r'[0-9a-f]{4}-[0-9a-f]{12}(?:-test)?)["\']', re.I)

# Deutung der Vorbelegung. Erschlossen, nicht aus der Herstellerdoku belegt –
# deshalb wird sie im Ergebnis immer zusammen mit dem Rohwert ausgegeben.
STATUS_DEUTUNG = {
    "always active": "immer aktiv (nicht abwaehlbar)",
    "active": "vorbelegt aktiv (Widerspruch noetig)",
    "inactive": "vorbelegt inaktiv (Zustimmung noetig)",
}


def hole(url: str) -> bytes:
    """Abruf nur auf oeffentliche Ziele -- siehe netzschutz.pruefe_ziel()."""
    pruefe_ziel(url)
    req = Request(url, headers={"user-agent": USER_AGENT, "accept": "*/*"})
    with urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def hole_json(url: str) -> dict:
    return json.loads(hole(url).decode("utf-8", "replace"))


def finde_onetrust(html: str) -> str | None:
    """Sucht die OneTrust-Kennung im Seitenquelltext."""
    treffer = ONETRUST_KENNUNG.search(html)
    return treffer.group(1) if treffer else None


def regelsaetze(konfig: dict) -> list[dict]:
    """Die Regelsaetze der Plattform samt der Laender, fuer die sie gelten."""
    saetze = []
    for r in konfig.get("RuleSet") or []:
        laender = [c.lower() for c in (r.get("Countries") or [])]
        saetze.append({
            "id": r.get("Id"),
            "name": r.get("Name"),
            "laender_anzahl": len(laender),
            "gilt_fuer_schweiz": "ch" in laender,
            "ist_standard": bool(r.get("Default")),
        })
    return saetze


def kategorien(domain_daten: dict) -> list[dict]:
    """Die Einwilligungs-Kategorien mit ihrer Vorbelegung."""
    ergebnis = []
    for g in domain_daten.get("Groups") or []:
        roh = (g.get("Status") or "").strip().lower()
        ergebnis.append({
            "name": g.get("GroupName"),
            "status_roh": roh or None,
            "status_deutung": STATUS_DEUTUNG.get(roh, "unbekannt"),
            "ist_iab_zweck": bool(g.get("IsIabPurpose")),
        })
    return ergebnis


def _anbieternamen(ids: list[int], liste: dict) -> tuple[list[str], int]:
    anbieter = liste.get("vendors") or {}
    namen = [anbieter[str(i)]["name"] for i in ids
             if str(i) in anbieter and anbieter[str(i)].get("name")]
    return sorted(namen), len(ids) - len(namen)


def messe(url: str, mit_namen: bool = False) -> dict:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    ergebnis: dict = {
        "url": url,
        "gemessen_am": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "methodik": ("Statisches Lesen der veroeffentlichten CMP-Konfiguration. "
                     "Kein JavaScript, kein Klick, keine Uebertragung an Partner."),
        "bedeutung": ("Obergrenze: wie viele Partner einwilligungsfaehig geschaltet "
                      "sind – nicht, wer bei einem Besuch Daten erhalten hat."),
    }
    try:
        html = hole(url).decode("utf-8", "replace")
    except ZielAbgelehnt as exc:
        ergebnis["status"] = "abgelehnt_kein_oeffentliches_ziel"
        ergebnis["fehler"] = str(exc)
        return ergebnis
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        ergebnis["status"] = "fehler"
        ergebnis["fehler"] = f"{type(exc).__name__}: {exc}"
        return ergebnis

    kennung = finde_onetrust(html)
    if not kennung:
        ergebnis["status"] = "keine_bekannte_plattform"
        ergebnis["hinweis"] = ("Keine OneTrust-Kennung gefunden. Andere Plattformen "
                               "werden noch nicht erkannt – das ist kein Nachweis, "
                               "dass keine Einwilligungsplattform vorhanden ist.")
        return ergebnis

    ergebnis["plattform"] = "OneTrust"
    ergebnis["kennung"] = kennung
    basis = f"{ONETRUST_CDN}/consent/{kennung}"
    try:
        konfig = hole_json(f"{basis}/{kennung}.json")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        ergebnis["status"] = "konfiguration_nicht_lesbar"
        ergebnis["fehler"] = f"{type(exc).__name__}: {exc}"
        return ergebnis

    ergebnis["status"] = "gemessen"
    saetze = regelsaetze(konfig)
    ergebnis["regelsaetze"] = saetze

    liste = None
    if mit_namen:
        try:
            liste = hole_json(IAB_ANBIETERLISTE)
            ergebnis["anbieterliste_version"] = liste.get("vendorListVersion")
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            ergebnis["anbieterliste_fehler"] = f"{type(exc).__name__}: {exc}"

    ergebnis["auswertung"] = []
    for satz in saetze:
        if not satz["id"]:
            continue
        try:
            detail = hole_json(f"{basis}/{satz['id']}/de.json")
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            ergebnis["auswertung"].append({"regelsatz": satz["name"],
                                           "fehler": f"{type(exc).__name__}: {exc}"})
            continue
        dd = detail.get("DomainData") or {}
        ids = [i for i in (dd.get("Vendors") or []) if isinstance(i, int)]
        eintrag = {
            "regelsatz": satz["name"],
            "gilt_fuer_schweiz": satz["gilt_fuer_schweiz"],
            "iab_partner_freigeschaltet": len(ids),
            "google_partner_freigeschaltet": len(dd.get("OverridenGoogleVendors") or []),
            "weitere_partner_ausserhalb_iab": len(dd.get("GeneralVendors") or []),
            "kategorien": kategorien(dd),
        }
        if liste:
            namen, unaufgeloest = _anbieternamen(ids, liste)
            eintrag["partner_namen"] = namen
            eintrag["partner_unaufgeloest"] = unaufgeloest
        ergebnis["auswertung"].append(eintrag)

    ergebnis["laenderunterschied"] = _laenderunterschied(ergebnis["auswertung"])
    return ergebnis


def _laenderunterschied(auswertung: list[dict]) -> dict:
    """Unterscheidet sich die Vorbelegung zwischen den Regelsaetzen?

    Ein Unterschied heisst: Fuer Besucherinnen aus verschiedenen Laendern ist
    dieselbe Kategorie unterschiedlich vorbelegt. Das ist eine Tatsache aus der
    Konfiguration, keine Bewertung.
    """
    gueltige = [a for a in auswertung if "kategorien" in a]
    if len(gueltige) < 2:
        return {"vergleichbar": False}
    je_kategorie: dict[str, set[str]] = {}
    for a in gueltige:
        for k in a["kategorien"]:
            if k["name"]:
                je_kategorie.setdefault(k["name"], set()).add(k["status_roh"] or "")
    abweichend = sorted(n for n, s in je_kategorie.items() if len(s) > 1)
    return {"vergleichbar": True,
            "kategorien_gesamt": len(je_kategorie),
            "kategorien_mit_abweichender_vorbelegung": abweichend}


def zusammenfassung(m: dict) -> str:
    z = [f"\n=== {m['url']} (Einwilligungsumfang, statisch gelesen) ==="]
    if m.get("status") != "gemessen":
        z.append(f"  {m.get('status')}: {m.get('hinweis') or m.get('fehler', '')}")
        return "\n".join(z)
    z.append(f"  Plattform: {m['plattform']}")
    for a in m.get("auswertung", []):
        if "fehler" in a:
            z.append(f"  Regelsatz {a['regelsatz']}: nicht lesbar ({a['fehler']})")
            continue
        marke = " [gilt fuer die Schweiz]" if a["gilt_fuer_schweiz"] else ""
        z.append(f"  Regelsatz «{a['regelsatz']}»{marke}")
        z.append(f"    einwilligungsfaehige Partner: {a['iab_partner_freigeschaltet']} (IAB)"
                 f" + {a['google_partner_freigeschaltet']} (Google)"
                 f" + {a['weitere_partner_ausserhalb_iab']} (weitere)")
        if "partner_unaufgeloest" in a:
            z.append(f"    davon namentlich aufloesbar: "
                     f"{len(a['partner_namen'])}, unaufgeloest: {a['partner_unaufgeloest']}")
        vorbelegt = [k for k in a["kategorien"] if k["status_roh"] == "active"]
        if vorbelegt:
            z.append(f"    vorbelegt aktiv: {', '.join(k['name'] for k in vorbelegt)}")
    lu = m.get("laenderunterschied") or {}
    if lu.get("kategorien_mit_abweichender_vorbelegung"):
        z.append("  Unterschiedliche Vorbelegung je Regelsatz bei: "
                 + ", ".join(lu["kategorien_mit_abweichender_vorbelegung"]))
    z.append("  Hinweis: Obergrenze (einwilligungsfaehig), nicht gemessener Einzelfall.")
    return "\n".join(z)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("urls", nargs="+")
    p.add_argument("--namen", action="store_true",
                   help="Partner-Namen ueber die globale IAB-Anbieterliste aufloesen")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    alle = [messe(u, args.namen) for u in args.urls]
    if args.json:
        json.dump(alle if len(alle) > 1 else alle[0], sys.stdout,
                  ensure_ascii=False, indent=2)
        print()
    else:
        for m in alle:
            print(zusammenfassung(m))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""DNS-Messung: welche Datenfluesse eine Organisation im DNS selbst veroeffentlicht.

Warum diese Ebene:
  Der Website-Scanner sieht nur, was im HTML der Startseite steht – und das ist
  eine Untergrenze. Das DNS beantwortet dagegen Fragen, die im HTML gar nicht
  vorkommen: Wohin geht die Post der Organisation? Wer darf in ihrem Namen
  senden? Sieht eine Subdomain nur wie ein eigener Dienst aus, zeigt aber auf
  einen fremden?

Was diese Befunde sind - und was nicht:
  Sie sind **Infrastruktur-Hinweise**, keine nachgewiesenen Personendatenfluesse.
  Ein MX-Eintrag belegt, wer Post *annimmt*, nicht dass dort gerade Daten
  liegen. Ein SPF-Include belegt eine Sendeberechtigung, nicht eine laufende
  Bearbeitung. Ein CNAME belegt eine Infrastrukturbeziehung, nicht deren
  Inhalt. Wer daraus eine "Bekanntgabe an Dritte im Sinne des DSG" macht,
  zieht einen Schluss, den die Messung nicht traegt. Diese Befunde taugen als
  **Anlass zur Nachfrage** und zum Abgleich mit einer Deklaration - nicht als
  Feststellung.

Warum sie fair ist:
  Es wird keine einzige Anfrage an die Server der gemessenen Organisation
  gestellt. Gelesen werden ausschliesslich Angaben, die sie selbst
  veroeffentlicht hat, damit die Welt sie liest. Die Messung erzeugt bei der
  gemessenen Stelle keine Last und laesst sich nicht abweisen – deshalb gilt
  hier besonders, dass der Befund sachlich und ohne Wertung bleibt.

Bewusste Grenzen (Teil der Methodik, gehoeren in jede Veroeffentlichung):
  - MX sagt, wer Post *annimmt*, nicht wo sie danach liegt.
  - SPF sagt, wer senden *darf*, nicht wer tatsaechlich sendet.
  - Die CNAME-Pruefung testet eine feste Liste ueblicher Namen; sie ist eine
    Stichprobe, keine vollstaendige Aufzaehlung der Subdomains.
  - Die Zuordnung Anbieter -> Land ist ein Hinweis auf den Konzernsitz, keine
    Aussage ueber den physischen Speicherort.
  - Aufgeloest wird ueber einen fremden DNS-over-HTTPS-Dienst. Das ist selbst
    ein Datenfluss; er wird im Ergebnis benannt.

Verwendung:
    python3 dns_messung.py landi.ch migros.ch
    python3 dns_messung.py --json landi.ch

Nur Python-Standardbibliothek.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

TIMEOUT = 12

# DNS-Antwortcodes (RFC 1035). Nur diese beiden sind eine gueltige Antwort auf
# die Frage "gibt es diesen Eintrag": kein Fehler (ggf. mit leerer Antwort =
# Eintrag existiert nicht) und Name existiert nicht. Alles andere heisst
# "nicht beantwortet" und darf nie als "kein Eintrag" erscheinen.
RCODE_KEIN_FEHLER = 0
RCODE_NAME_EXISTIERT_NICHT = 3
RCODE_NAMEN = {
    0: "NOERROR", 1: "FORMERR", 2: "SERVFAIL", 3: "NXDOMAIN",
    4: "NOTIMP", 5: "REFUSED", 9: "NOTAUTH", 10: "NOTZONE",
}

USER_AGENT = "DatenflussScanner/0.1 (offener-standard-prototyp)"

# Aufloeser. Der erste, der antwortet, wird verwendet; welcher es war, steht im
# Ergebnis. Eigener Resolver waere sauberer und ist als Ausbau vorgesehen.
AUFLOESER: dict[str, str] = {
    "cloudflare": "https://cloudflare-dns.com/dns-query",
    "google": "https://dns.google/resolve",
}

# ---------------------------------------------------------------------------
# Kuratierte Zuordnungen. Bewusst klein; Unbekanntes wird als unbekannt
# ausgewiesen und nie geraten.
# ---------------------------------------------------------------------------
POSTANBIETER: list[tuple[str, str, str]] = [
    # (Host-Endung, Anbieter, Sitz-Hinweis)
    ("protection.outlook.com", "Microsoft 365", "US"),
    ("mail.protection.outlook.com", "Microsoft 365", "US"),
    ("aspmx.l.google.com", "Google Workspace", "US"),
    ("googlemail.com", "Google Workspace", "US"),
    ("pphosted.com", "Proofpoint", "US"),
    ("mimecast.com", "Mimecast", "US/UK"),
    ("barracudanetworks.com", "Barracuda", "US"),
    ("messagingengine.com", "Fastmail", "AU"),
    ("protonmail.ch", "Proton Mail", "CH"),
    ("protonmail.com", "Proton Mail", "CH"),
    ("hostpoint.ch", "Hostpoint", "CH"),
    ("cyon.ch", "cyon", "CH"),
    ("infomaniak.ch", "Infomaniak", "CH"),
    ("infomaniak.com", "Infomaniak", "CH"),
    ("green.ch", "Green", "CH"),
    ("metanet.ch", "Metanet", "CH"),
    ("nine.ch", "nine", "CH"),
    ("hostedmail.ch", "Hosted Mail", "CH"),
]

SPF_VERSENDER: list[tuple[str, str, str]] = [
    ("spf.protection.outlook.com", "Microsoft 365", "US"),
    ("_spf.google.com", "Google Workspace", "US"),
    ("servers.mcsv.net", "Mailchimp", "US"),
    ("sendgrid.net", "SendGrid (Twilio)", "US"),
    ("mailgun.org", "Mailgun", "US"),
    ("sparkpostmail.com", "SparkPost", "US"),
    ("amazonses.com", "Amazon SES", "US"),
    ("salesforce.com", "Salesforce", "US"),
    ("hubspotemail.net", "HubSpot", "US"),
    ("sendinblue.com", "Brevo", "FR"),
    ("brevo.com", "Brevo", "FR"),
    ("mailjet.com", "Mailjet", "FR"),
    ("zendesk.com", "Zendesk", "US"),
    ("mailerlite.com", "MailerLite", "LT"),
    ("cleverreach.com", "CleverReach", "DE"),
    ("newsletter2go.com", "Newsletter2Go", "DE"),
    ("infomaniak.ch", "Infomaniak", "CH"),
    ("hostpoint.ch", "Hostpoint", "CH"),
    ("protonmail.ch", "Proton Mail", "CH"),
    ("umantis.com", "Abacus Umantis (Bewerbungen)", "CH"),
    ("successfactors.com", "SAP SuccessFactors (Personal)", "DE/US"),
    ("xcampaign.de", "xCampaign", "DE"),
]

# Fremde Ziele, auf die eine Subdomain zeigen kann. Trifft eine Subdomain der
# eigenen Marke auf eines dieser Ziele, sieht der Dienst fuer Besucherinnen wie
# ein eigener aus, ist es aber nicht ("First-Party-Tarnung").
CNAME_ZIELE: list[tuple[str, str, str, str]] = [
    # (Host-Endung, Anbieter, Kategorie, Sitz-Hinweis)
    ("adobedc.net", "Adobe Experience Cloud", "analyse", "US"),
    ("omtrdc.net", "Adobe Analytics", "analyse", "US"),
    ("2o7.net", "Adobe Analytics", "analyse", "US"),
    ("data.microsoft.com", "Microsoft", "analyse", "US"),
    ("hubspot.net", "HubSpot", "marketing", "US"),
    ("hs-sites.com", "HubSpot", "marketing", "US"),
    ("marketo.com", "Marketo (Adobe)", "marketing", "US"),
    ("eloqua.com", "Eloqua (Oracle)", "marketing", "US"),
    ("pardot.com", "Pardot (Salesforce)", "marketing", "US"),
    ("segment.com", "Segment (Twilio)", "analyse", "US"),
    ("matomo.cloud", "Matomo Cloud", "analyse", "DE"),
    ("cloudfront.net", "Amazon CloudFront", "cdn", "US"),
    ("akamaiedge.net", "Akamai", "cdn", "US"),
    ("akamaized.net", "Akamai", "cdn", "US"),
    ("edgekey.net", "Akamai", "cdn", "US"),
    ("fastly.net", "Fastly", "cdn", "US"),
    ("cloudflare.net", "Cloudflare", "cdn", "US"),
    ("cdn.cloudflare.net", "Cloudflare", "cdn", "US"),
    ("azureedge.net", "Microsoft Azure CDN", "cdn", "US"),
    ("googlehosted.com", "Google", "cdn", "US"),
    ("ghs.googlehosted.com", "Google", "cdn", "US"),
    ("wpengine.com", "WP Engine", "hosting", "US"),
    ("shopify.com", "Shopify", "shop", "CA"),
    ("myshopify.com", "Shopify", "shop", "CA"),
    ("squarespace.com", "Squarespace", "website", "US"),
    ("wixdns.net", "Wix", "website", "IL"),
    ("webflow.io", "Webflow", "website", "US"),
    ("typeform.com", "Typeform", "formulare", "ES"),
    ("zendesk.com", "Zendesk", "support", "US"),
    ("statuspage.io", "Atlassian Statuspage", "status", "AU"),
    ("infomaniak.ch", "Infomaniak", "hosting", "CH"),
    ("hostpoint.ch", "Hostpoint", "hosting", "CH"),
    ("cyon.ch", "cyon", "hosting", "CH"),
    ("nine.ch", "nine", "hosting", "CH"),
]

# Uebliche Subdomain-Namen. Stichprobe, bewusst kurz gehalten: jede Abfrage ist
# billig, aber eine lange Liste erzeugt den Eindruck von Vollstaendigkeit, den
# eine Stichprobe nicht einloesen kann.
SUBDOMAIN_STICHPROBE: tuple[str, ...] = (
    "www", "mail", "cdn", "static", "assets", "shop", "blog", "app",
    "metrics", "analytics", "stats", "track", "tracking", "tags",
    "news", "newsletter", "support", "status", "portal", "login",
)


def registrierbar(host: str) -> str:
    """Grobe Zusammenfassung auf die letzten beiden Labels.

    Fuer .ch, .com und die meisten hier vorkommenden Endungen ausreichend.
    Bei zusammengesetzten Endungen (z. B. co.uk) untertreibt sie – sie ordnet
    dann zu grosszuegig als 'eigen' ein und meldet im Zweifel weniger, nicht
    mehr. Das ist die richtige Richtung fuer eine Messung, die belastbar sein
    soll.
    """
    teile = [t for t in host.strip(".").lower().split(".") if t]
    return ".".join(teile[-2:]) if len(teile) >= 2 else ".".join(teile)


def _zuordnen(ziel: str, tabelle: list[tuple]) -> tuple | None:
    z = ziel.strip(".").lower()
    treffer = [e for e in tabelle if z == e[0] or z.endswith("." + e[0])]
    # Laengste Uebereinstimmung gewinnt, damit spezifische Eintraege
    # allgemeinere schlagen.
    return max(treffer, key=lambda e: len(e[0])) if treffer else None


class Aufloeser:
    """DNS-over-HTTPS mit kleinem Zwischenspeicher pro Lauf."""

    def __init__(self, dienst: str = "cloudflare") -> None:
        if dienst not in AUFLOESER:
            raise ValueError(f"Unbekannter Aufloeser: {dienst}")
        self.dienst = dienst
        self.basis = AUFLOESER[dienst]
        self.speicher: dict[tuple[str, str], list[str]] = {}
        self.ungeklaert: dict[tuple[str, str], str] = {}
        self.fehler: list[str] = []

    def frage(self, name: str, typ: str) -> list[str]:
        schluessel = (name.lower(), typ.upper())
        if schluessel in self.speicher:
            return self.speicher[schluessel]
        url = f"{self.basis}?name={quote(name)}&type={quote(typ)}"
        req = Request(url, headers={"accept": "application/dns-json",
                                    "user-agent": USER_AGENT})
        antworten: list[str] = []
        try:
            with urlopen(req, timeout=TIMEOUT) as r:
                daten = json.loads(r.read().decode("utf-8", "replace"))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            self.ungeklaert[schluessel] = f"{type(exc).__name__}"
            self.fehler.append(f"{typ} {name}: {type(exc).__name__}")
            self.speicher[schluessel] = []
            return []

        # Den DNS-Antwortcode auswerten, nicht nur die Antwortliste. Sonst
        # sieht ein SERVFAIL genauso aus wie "es gibt keinen Eintrag" -- und
        # aus Nichtwissen wuerde eine Abwesenheitsbehauptung. Genau diesen
        # Fehler behebt der Scanner an anderer Stelle bereits.
        code = daten.get("Status")
        if code not in (RCODE_KEIN_FEHLER, RCODE_NAME_EXISTIERT_NICHT):
            self.ungeklaert[schluessel] = RCODE_NAMEN.get(code, f"RCODE {code}")
            self.fehler.append(f"{typ} {name}: {RCODE_NAMEN.get(code, f'RCODE {code}')}")
            self.speicher[schluessel] = []
            return []

        for a in daten.get("Answer") or []:
            wert = a.get("data")
            if wert:
                antworten.append(wert)
        self.speicher[schluessel] = antworten
        return antworten

    def ist_ungeklaert(self, name: str, typ: str) -> str | None:
        """Grund, falls diese Frage nicht beantwortet werden konnte."""
        return self.ungeklaert.get((name.lower(), typ.upper()))


def post_empfaenger(aufl: Aufloeser, domain: str) -> list[dict]:
    """MX-Eintraege: wer nimmt die Post dieser Organisation entgegen?"""
    ziele: dict[str, dict] = {}
    for eintrag in aufl.frage(domain, "MX"):
        teile = eintrag.split()
        host = teile[-1].strip(".").lower()
        if not host:
            continue
        z = _zuordnen(host, POSTANBIETER)
        anbieter = z[1] if z else registrierbar(host)
        sitz = z[2] if z else "unbekannt"
        e = ziele.setdefault(anbieter, {"anbieter": anbieter, "sitz_hinweis": sitz,
                                        "erkannt": bool(z), "hosts": set()})
        e["hosts"].add(host)
    return [{**e, "hosts": sorted(e["hosts"])}
            for e in sorted(ziele.values(), key=lambda e: e["anbieter"])]


def sendeberechtigte(aufl: Aufloeser, domain: str) -> dict:
    """Direkte SPF-Includes: Hinweise auf delegierte Sendeinfrastruktur.

    **Umfang, bewusst begrenzt:** Ausgewertet werden ausschliesslich die
    direkten `include:`-Mechanismen. SPF kennt daneben `ip4`, `ip6`, `a`,
    `mx` und `redirect`, und Includes koennen ihrerseits weitere Regeln
    enthalten. Die Aussage lautet deshalb nicht «wer darf in ihrem Namen
    senden», sondern «welche Sendeinfrastruktur ist direkt eingebunden».
    """
    roh = [t.strip('"') for t in aufl.frage(domain, "TXT")]
    spf = next((t for t in roh if t.lower().startswith("v=spf1")), None)
    if not spf:
        return {"vorhanden": False, "dienste": [], "unbekannte_includes": []}
    dienste: dict[str, dict] = {}
    unbekannt: list[str] = []
    for teil in spf.split():
        if not teil.lower().startswith("include:"):
            continue
        ziel = teil.split(":", 1)[1].strip(".").lower()
        z = _zuordnen(ziel, SPF_VERSENDER)
        if z:
            dienste.setdefault(z[1], {"anbieter": z[1], "sitz_hinweis": z[2],
                                      "includes": set()})["includes"].add(ziel)
        else:
            unbekannt.append(ziel)
    return {"vorhanden": True,
            "umfang": ("nur direkte include:-Mechanismen; ip4/ip6/a/mx/redirect "
                       "und verschachtelte Includes werden nicht ausgewertet"),
            "eintrag": spf,
            "dienste": [{**d, "includes": sorted(d["includes"])}
                        for d in sorted(dienste.values(), key=lambda d: d["anbieter"])],
            "unbekannte_includes": sorted(set(unbekannt))}


def erste_partei_tarnung(aufl: Aufloeser, domain: str,
                         namen: tuple[str, ...] = SUBDOMAIN_STICHPROBE) -> list[dict]:
    """Subdomains der eigenen Marke, die auf fremde Ziele zeigen.

    Fuer Besucherinnen sieht 'metrics.firma.ch' nach einem eigenen Dienst aus.
    Zeigt der Name per CNAME auf einen Dritten, ist es keiner.
    """
    eigen = registrierbar(domain)
    befunde: list[dict] = []
    for sub in namen:
        name = f"{sub}.{domain}"
        for ziel in aufl.frage(name, "CNAME"):
            ziel = ziel.strip(".").lower()
            if not ziel or registrierbar(ziel) == eigen:
                continue
            z = _zuordnen(ziel, CNAME_ZIELE)
            befunde.append({
                "subdomain": name,
                "zeigt_auf": ziel,
                "anbieter": z[1] if z else registrierbar(ziel),
                "kategorie": z[2] if z else "unbekannt",
                "sitz_hinweis": z[3] if z else "unbekannt",
                "erkannt": bool(z),
            })
    return befunde


def messe(domain: str, dienst: str = "cloudflare",
          namen: tuple[str, ...] = SUBDOMAIN_STICHPROBE) -> dict:
    """Vollstaendige DNS-Messung einer Domain."""
    domain = domain.strip().lower().removeprefix("https://").removeprefix("http://")
    domain = domain.split("/")[0].removeprefix("www.")
    aufl = Aufloeser(dienst)
    ergebnis = {
        "domain": domain,
        "gemessen_am": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "methodik": ("Ausschliesslich oeffentliche DNS-Eintraege ueber DNS-over-HTTPS. "
                     "Keine Anfrage an Server der gemessenen Organisation."),
        "aufloeser": dienst,
        "post_empfaenger": post_empfaenger(aufl, domain),
        "sendeberechtigte": sendeberechtigte(aufl, domain),
        "erste_partei_tarnung": erste_partei_tarnung(aufl, domain, namen),
        "geprueffte_subdomains": list(namen),
    }
    if aufl.fehler:
        ergebnis["abruf_hinweise"] = aufl.fehler
    if aufl.ungeklaert:
        # Fragen, die der Aufloeser nicht beantworten konnte. Bewusst getrennt
        # von "kein Eintrag vorhanden": Nichtwissen ist keine Abwesenheit.
        ergebnis["ungeklaerte_fragen"] = [
            {"name": n, "typ": t, "grund": g}
            for (n, t), g in sorted(aufl.ungeklaert.items())]
    ergebnis["laender_hinweise"] = sorted({
        *(e["sitz_hinweis"] for e in ergebnis["post_empfaenger"]),
        *(d["sitz_hinweis"] for d in ergebnis["sendeberechtigte"]["dienste"]),
        *(t["sitz_hinweis"] for t in ergebnis["erste_partei_tarnung"]),
    } - {"unbekannt"})
    return ergebnis


def zusammenfassung(m: dict) -> str:
    zeilen = [f"\n=== {m['domain']} (nur DNS, keine Anfrage an deren Server) ==="]
    post = m["post_empfaenger"]
    if post:
        for e in post:
            zeilen.append(f"  Post laeuft ueber: {e['anbieter']} ({e['sitz_hinweis']})")
    else:
        offen = [u for u in m.get("ungeklaerte_fragen", []) if u["typ"] == "MX"]
        zeilen.append("  Post laeuft ueber: UNGEKLAERT – DNS-Frage nicht beantwortet "
                      f"({offen[0]['grund']})" if offen
                      else "  Post laeuft ueber: kein MX-Eintrag vorhanden")
    spf = m["sendeberechtigte"]
    if spf["dienste"]:
        namen = ", ".join(f"{d['anbieter']} ({d['sitz_hinweis']})" for d in spf["dienste"])
        zeilen.append(f"  Direkt eingebundene Sendeinfrastruktur: {namen}")
    if spf.get("unbekannte_includes"):
        zeilen.append(f"  Weitere Sende-Includes (nicht zugeordnet): "
                      f"{', '.join(spf['unbekannte_includes'])}")
    tarn = m["erste_partei_tarnung"]
    if tarn:
        for t in tarn:
            zeilen.append(f"  {t['subdomain']} zeigt auf {t['anbieter']} "
                          f"({t['sitz_hinweis']}, {t['kategorie']}) – {t['zeigt_auf']}")
    else:
        zeilen.append("  Keine der geprueften Subdomains zeigt auf einen Dritten")
    for u in m.get("ungeklaerte_fragen", []):
        zeilen.append(f"  UNGEKLAERT: {u['typ']} fuer {u['name']} – {u['grund']}. "
                      f"Kein Nachweis, dass kein Eintrag existiert.")
    if m["laender_hinweise"]:
        zeilen.append(f"  Sitz-Hinweise insgesamt: {', '.join(m['laender_hinweise'])}")
    return "\n".join(zeilen)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("domains", nargs="+", help="Zu messende Domains")
    p.add_argument("--aufloeser", default="cloudflare", choices=sorted(AUFLOESER),
                   help="DNS-over-HTTPS-Dienst (Standard: cloudflare)")
    p.add_argument("--json", action="store_true", help="Ergebnis als JSON ausgeben")
    args = p.parse_args()

    alle = [messe(d, args.aufloeser) for d in args.domains]
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

#!/usr/bin/env python3
"""Scanner-Prototyp: vermisst, welche Drittanbieter eine Website tatsaechlich
einbindet – die Basis fuer «gemessene Profile» (Vertrauensstufe 1).

Was der Scanner tut:
  1. robots.txt respektieren, dann die Startseite laden (ein einzelner Abruf)
  2. Statisch eingebundene externe Ressourcen erkennen (Scripts, Styles,
     Bilder, Iframes, Fonts, Formular-Ziele) und bekannten Anbietern zuordnen
  3. /.well-known/datenfluss.json pruefen und – falls vorhanden – die
     Abweichung «gemessen vs. deklariert» berechnen
  4. Ergebnis als JSON-Profil speichern und lesbar zusammenfassen

Bewusste Grenzen (ehrlich dokumentiert, Teil der Methodik):
  - Keine JavaScript-Ausfuehrung: dynamisch nachgeladene Dienste und per JS
    gesetzte Cookies sind unsichtbar. Der Befund ist eine Untergrenze.
  - Nur die Startseite; Unterseiten koennen weitere Dienste einbinden.

Verwendung:
    python3 scanner.py https://www.beispielfirma.ch
    python3 scanner.py -o profile/ https://www.eine-firma.example https://www.andere.example

Nur Python-Standardbibliothek.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib import robotparser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

USER_AGENT = "DatenflussScanner/0.1 (offener-standard-prototyp)"
TIMEOUT = 12

# ---------------------------------------------------------------------------
# Kuratierte Zuordnung: Host-Endung -> (Anbieter, Kategorie, Sitz-Hinweis)
# Bewusst klein gehalten; unbekannte Hosts werden separat ausgewiesen.
# ---------------------------------------------------------------------------
TRACKER_DB: dict[str, tuple[str, str, str]] = {
    "google-analytics.com": ("Google Analytics", "analyse", "US"),
    "googletagmanager.com": ("Google Tag Manager", "tag-management", "US"),
    "doubleclick.net": ("Google Ads / DoubleClick", "werbung", "US"),
    "googlesyndication.com": ("Google AdSense", "werbung", "US"),
    "googleadservices.com": ("Google Ads", "werbung", "US"),
    "gstatic.com": ("Google (statische Inhalte/Fonts)", "cdn", "US"),
    "fonts.googleapis.com": ("Google Fonts", "fonts", "US"),
    "maps.googleapis.com": ("Google Maps", "karten", "US"),
    "google.com/recaptcha": ("Google reCAPTCHA", "sicherheit", "US"),
    "youtube.com": ("YouTube", "video", "US"),
    "ytimg.com": ("YouTube (Inhalte)", "video", "US"),
    "connect.facebook.net": ("Meta Pixel", "werbung", "US"),
    "facebook.com": ("Facebook", "social", "US"),
    "instagram.com": ("Instagram", "social", "US"),
    "px.ads.linkedin.com": ("LinkedIn Insight Tag", "werbung", "US"),
    "linkedin.com": ("LinkedIn", "social", "US"),
    "analytics.tiktok.com": ("TikTok Pixel", "werbung", "US"),
    "static.hotjar.com": ("Hotjar", "analyse", "MT"),
    "matomo.cloud": ("Matomo Cloud", "analyse", "DE"),
    "plausible.io": ("Plausible Analytics", "analyse", "EE"),
    "usercentrics.eu": ("Usercentrics", "consent", "DE"),
    "cookiebot.com": ("Cookiebot", "consent", "DK"),
    "onetrust.com": ("OneTrust", "consent", "US"),
    "js.stripe.com": ("Stripe", "zahlung", "US/IE"),
    "paypal.com": ("PayPal", "zahlung", "US"),
    "klarna.com": ("Klarna", "zahlung", "SE"),
    "js.datatrans.com": ("Datatrans", "zahlung", "CH"),
    "chimpstatic.com": ("Mailchimp", "marketing", "US"),
    "list-manage.com": ("Mailchimp", "marketing", "US"),
    "hubspot.com": ("HubSpot", "marketing", "US"),
    "hs-scripts.com": ("HubSpot", "marketing", "US"),
    "cloudflare.com": ("Cloudflare", "cdn", "US"),
    "cloudflareinsights.com": ("Cloudflare Analytics", "analyse", "US"),
    "cdn.jsdelivr.net": ("jsDelivr CDN", "cdn", "US"),
    "cdnjs.cloudflare.com": ("cdnjs (Cloudflare)", "cdn", "US"),
    "unpkg.com": ("unpkg CDN", "cdn", "US"),
    "sentry.io": ("Sentry", "monitoring", "US"),
    "newrelic.com": ("New Relic", "monitoring", "US"),
    "vimeo.com": ("Vimeo", "video", "US"),
    "twitter.com": ("X/Twitter", "social", "US"),
    "x.com": ("X/Twitter", "social", "US"),
    "criteo.com": ("Criteo", "werbung", "FR"),
    "adform.net": ("Adform", "werbung", "DK"),
    "outbrain.com": ("Outbrain", "werbung", "US"),
    "taboola.com": ("Taboola", "werbung", "US"),
}

# Hinweise auf selbst gehostete Analyse (Pfadmuster im HTML)
SELBSTGEHOSTET = {
    # Piwik ist der fruehere Name von Matomo – dasselbe Produkt. Zwei Namen
    # dafuer wuerden denselben Dienst in jeder Auswertung doppelt zaehlen.
    "matomo.js": ("Matomo (selbst gehostet)", "analyse"),
    "piwik.js": ("Matomo (selbst gehostet)", "analyse"),
}


class RessourcenParser(HTMLParser):
    """Sammelt URLs aus src/href/action-Attributen relevanter Tags."""

    RELEVANT = {
        "script": "src", "img": "src", "iframe": "src", "source": "src",
        "video": "src", "audio": "src", "embed": "src", "form": "action",
    }

    def __init__(self) -> None:
        super().__init__()
        self.urls: set[str] = set()
        self.inline_js: list[str] = []
        self._in_script_ohne_src = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "link" and a.get("href"):
            rel = (a.get("rel") or "").lower()
            if any(t in rel for t in ("stylesheet", "preconnect", "dns-prefetch", "preload")):
                self.urls.add(a["href"])
        attr = self.RELEVANT.get(tag)
        if attr and a.get(attr):
            self.urls.add(a[attr])
        if tag == "script" and not a.get("src"):
            self._in_script_ohne_src = True

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script_ohne_src = False

    def handle_data(self, data):
        if self._in_script_ohne_src and data.strip():
            self.inline_js.append(data)


BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def hole(url: str, ua: str = USER_AGENT):
    req = Request(url, headers={
        "User-Agent": ua,
        "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-CH,de;q=0.9",
        "Accept-Encoding": "identity",
    })
    with urlopen(req, timeout=TIMEOUT) as antwort:
        roh = antwort.read(2_000_000)  # 2 MB reichen fuer eine Startseite
        text = roh.decode("utf-8", errors="replace")
        return antwort.geturl(), antwort.status, dict(antwort.headers), text


def _abruf_beleg(exc: Exception) -> dict:
    """Roh-Evidenz eines gescheiterten Abrufs, damit der Befund adjudizierbar ist.

    Ein Profil, das nur "nicht erreichbar" behauptet, ist so unbeweisbar wie
    die Fehlermeldung einer fremden Fetch-Pipeline: Wer den Befund bestreitet,
    steht vor einer Behauptung statt vor einem Beleg. Deshalb halten wir fest,
    was die Messkette tatsaechlich gesehen hat - Fehlerklasse, HTTP-Status und
    ausgewaehlte Antwort-Header (keine Personendaten, nur Server-Metadaten).
    Der Zeitpunkt steht bereits in gescannt_am.
    """
    beleg: dict = {"fehlerklasse": exc.__class__.__name__}
    if isinstance(exc, HTTPError):
        beleg["http_status"] = exc.code
        interessant = ("server", "content-type", "retry-after", "via",
                       "location", "cf-ray", "cf-mitigated", "x-served-by")
        beleg["antwort_header"] = {k: str(v)[:200] for k, v in (exc.headers or {}).items()
                                   if k.lower() in interessant}
    return beleg


def robots_erlaubt(basis: str) -> bool:
    """robots.txt mit eigener Kennung laden und wirklich auswerten.

    Bewusst nicht rp.read(): Python fragt dort mit Standard-Kennung an und
    wertet ein 403 als Totalverbot. Nach RFC 9309 gilt: 4xx = keine wirksamen
    Regeln (Zugriff erlaubt), 5xx = vorsichtshalber nicht crawlen.
    """
    try:
        _, _, _, text = hole(urljoin(basis, "/robots.txt"))
    except HTTPError as exc:
        return exc.code < 500
    except Exception:
        return True
    rp = robotparser.RobotFileParser()
    rp.parse(text.splitlines())
    return rp.can_fetch(USER_AGENT, urljoin(basis, "/"))


def ordne_zu(host_pfad: str) -> tuple[str, str, str] | None:
    for muster, eintrag in TRACKER_DB.items():
        if host_pfad.endswith(muster) or muster in host_pfad:
            return eintrag
    return None


class _DeklFertig(Exception):
    """Kontrollfluss: Deklarations-Status wurde bereits geschrieben."""


def _git_commit() -> str | None:
    """Commit-Hash des Scanner-Codes, falls aus einem Git-Checkout gestartet."""
    try:
        return subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parent), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip() or None
    except Exception:
        return None


def _deklaration_pruefen(dekl: dict) -> tuple[str, list[str]]:
    """Konformitaetsurteil ueber eine gefundene Deklaration.

    Nur eine Datei, die den Standard tatsaechlich erfuellt, verdient spaeter
    das Etikett DEKLARIERT. Ein beliebiges Stueck JSON am richtigen Pfad
    beweist nichts – wer das durchwinkt, macht das Register-Versprechen
    "gemessen -> deklariert -> verifiziert" an der mittleren Stufe wertlos.

    Geprueft wird ausschliesslich die STANDARD-Konformitaet (Schema plus
    universelle Regeln). Rechtsbefunde eines Pruefprofils gehoeren bewusst
    nicht hierher: Sie sind zeitabhaengig und machen eine Datei nie
    standardwidrig – eine Firma mit rechtlichem Klaerungsbedarf hat trotzdem
    korrekt deklariert.
    """
    version = dekl.get("spec_version")
    if version != "0.1":
        return "version_nicht_unterstuetzt", [f"spec_version '{version}' – dieser Scanner kennt 0.1"]
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError:
        return "gefunden_ungeprueft", ["Bibliothek 'jsonschema' fehlt – Konformitaet nicht geprueft"]
    schema_pfad = Path(__file__).resolve().parents[1] / "spec" / "v0.1" / "datenfluss.schema.json"
    if not schema_pfad.exists():
        return "gefunden_ungeprueft", ["Schema nicht gefunden – Konformitaet nicht geprueft"]
    schema = json.loads(schema_pfad.read_text(encoding="utf-8"))

    fehler: list[str] = []
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for err in sorted(validator.iter_errors(dekl), key=lambda e: list(e.absolute_path)):
        pfad = "/".join(str(x) for x in err.absolute_path) or "(wurzel)"
        fehler.append(f"[{pfad}] {err.message}")
    if not fehler:
        # Dieselben universellen Regeln wie der Validator – ein Regelwerk, nicht zwei.
        from validator import Befund, pruefe_semantik_universell
        befund = Befund()
        pruefe_semantik_universell(dekl, befund)
        fehler.extend(befund.fehler)
    if fehler:
        return "nicht_konform", fehler[:5]
    return "konform", []


def scanne(url: str, hartnaeckig: bool = False) -> dict:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    profil: dict = {
        "url": url,
        "gescannt_am": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "methodik": "Statischer Abruf der Startseite ohne JavaScript-Ausfuehrung (Untergrenze).",
        "scanner_version": "0.1",
        # Der genaue Code-Stand der Messung. Ohne ihn kann eine spaetere
        # Abweichung zweierlei bedeuten – die Website hat sich geaendert oder
        # der Scanner – und niemand kann es unterscheiden. Eine Zeitreihe, die
        # Vertrauen tragen soll, muss diese Frage beantworten koennen.
        "scanner_commit": _git_commit(),
    }

    if not robots_erlaubt(url):
        profil["status"] = "uebersprungen_robots_txt"
        return profil

    ua = USER_AGENT
    try:
        try:
            finale_url, status, headers, html_text = hole(url, ua)
        except HTTPError as exc:
            # Bot-Schutz. Standardmaessig respektieren wir die Abweisung: Wer
            # unsere ehrliche Kennung ablehnt, will nicht gemessen werden, und
            # ein Wiederholungsversuch mit Browser-Kennung waere eine
            # Verkleidung. Fuer ein Projekt, dessen Waehrung Glaubwuerdigkeit
            # ist, waere das der falsche Preis fuer ein paar Datenpunkte.
            if exc.code in (403, 406) and hartnaeckig:
                ua = BROWSER_UA
                profil["abruf_hinweis"] = (f"Server blockierte die Scanner-Kennung (HTTP {exc.code}); "
                                           "auf ausdrueckliche Anweisung mit Browser-Kennung wiederholt.")
                finale_url, status, headers, html_text = hole(url, ua)
            elif exc.code in (403, 406):
                profil["abruf_hinweis"] = (f"Server hat die Scanner-Kennung abgewiesen (HTTP {exc.code}). "
                                           "Die Abweisung wird respektiert; es wurde nicht erneut versucht.")
                raise
            else:
                raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        profil["status"] = "fehler"
        profil["fehler"] = str(exc)
        profil["abruf_beleg"] = _abruf_beleg(exc)
        return profil

    profil["finale_url"] = finale_url
    profil["status"] = status
    eigener_host = urlparse(finale_url).hostname or ""

    parser = RessourcenParser()
    parser.feed(html_text)

    gefunden: dict[str, dict] = {}
    unbekannt: set[str] = set()
    for roh_url in parser.urls:
        voll = urljoin(finale_url, roh_url)
        p = urlparse(voll)
        host = (p.hostname or "").lower()
        if not host or host == eigener_host or host.endswith("." + eigener_host):
            continue
        eintrag = ordne_zu(host + p.path)
        if eintrag:
            anbieter, kategorie, sitz = eintrag
            gefunden.setdefault(anbieter, {"anbieter": anbieter, "kategorie": kategorie,
                                           "sitz_hinweis": sitz, "hosts": set()})
            gefunden[anbieter]["hosts"].add(host)
        else:
            unbekannt.add(host)

    inline = " ".join(parser.inline_js)
    for muster, (anbieter, kategorie) in SELBSTGEHOSTET.items():
        if muster in inline or muster in html_text:
            gefunden.setdefault(anbieter, {"anbieter": anbieter, "kategorie": kategorie,
                                           "sitz_hinweis": "eigenes Hosting", "hosts": set()})
    for muster, anbieter, kategorie in (("gtag(", "Google Analytics", "analyse"),
                                        ("fbq(", "Meta Pixel", "werbung"),
                                        ("GTM-", "Google Tag Manager", "tag-management")):
        if muster in inline:
            gefunden.setdefault(anbieter, {"anbieter": anbieter, "kategorie": kategorie,
                                           "sitz_hinweis": "US", "hosts": set()})

    profil["drittanbieter"] = sorted(
        ({**e, "hosts": sorted(e["hosts"])} for e in gefunden.values()),
        key=lambda e: (e["kategorie"], e["anbieter"]),
    )
    profil["unbekannte_externe_hosts"] = sorted(unbekannt)
    cookies = headers.get("Set-Cookie")
    profil["cookies_beim_erstaufruf"] = len(cookies.split(",")) if cookies else 0

    # ---- Deklaration pruefen und Abweichung berechnen ----------------------
    basis = f"{urlparse(finale_url).scheme}://{urlparse(finale_url).netloc}"
    dekl_info: dict = {"status": "nicht_gefunden", "vorhanden": False}
    try:
        _, _, _, dekl_text = hole(urljoin(basis, "/.well-known/datenfluss.json"), ua)
        try:
            dekl = json.loads(dekl_text)
            if not isinstance(dekl, dict):
                raise ValueError("kein JSON-Objekt")
        except ValueError as exc:
            profil["datenfluss_deklaration"] = {
                "status": "unlesbar", "vorhanden": True,
                "befunde": [f"Datei ist kein gueltiges JSON-Objekt ({exc})"]}
            raise _DeklFertig
        status, befunde = _deklaration_pruefen(dekl)
        dekl_info = {"status": status, "vorhanden": True,
                     "spec_version": dekl.get("spec_version"),
                     "stand": dekl.get("stand"),
                     "organisation": dekl.get("organisation", {}).get("name")}
        if befunde:
            dekl_info["befunde"] = befunde
        deklarierte = " ".join(
            f'{e.get("name", "")} {e.get("dienst", "")} {e.get("website", "")}'.lower()
            for b in dekl.get("bearbeitungen", []) for e in b.get("empfaenger", [])
        )
        fehlend = []
        for eintrag in profil["drittanbieter"]:
            kern = eintrag["anbieter"].split(" (")[0].split("/")[0].strip().lower()
            if kern and kern not in deklarierte:
                fehlend.append(eintrag["anbieter"])
        dekl_info["gemessen_aber_nicht_deklariert"] = sorted(fehlend)
        dekl_info["abgleich_hinweis"] = "Namensbasierter Abgleich (Heuristik) – manuell verifizieren."
        profil["datenfluss_deklaration"] = dekl_info
    except _DeklFertig:
        pass  # Status wurde oben bereits gesetzt
    except Exception:
        profil["datenfluss_deklaration"] = dekl_info  # nicht_gefunden

    try:  # kleiner Bruder-Standard als Bonus-Signal
        _, s, _, _ = hole(urljoin(basis, "/.well-known/security.txt"), ua)
        profil["security_txt"] = s == 200
    except Exception:
        profil["security_txt"] = False

    return profil


def zusammenfassung(p: dict) -> str:
    z = [f"\n=== {p.get('finale_url', p['url'])} ==="]
    if p.get("status") in ("fehler", "uebersprungen_robots_txt"):
        z.append(f"  Status: {p['status']} {p.get('fehler', '')}")
        return "\n".join(z)
    if p.get("abruf_hinweis"):
        z.append(f"  Hinweis: {p['abruf_hinweis']}")
    z.append(f"  Drittanbieter erkannt: {len(p['drittanbieter'])}"
             f" | unbekannte externe Hosts: {len(p['unbekannte_externe_hosts'])}"
             f" | Cookies beim Erstaufruf: {p['cookies_beim_erstaufruf']}")
    for e in p["drittanbieter"]:
        z.append(f"    - [{e['kategorie']:>14}] {e['anbieter']} ({e['sitz_hinweis']})")
    d = p["datenfluss_deklaration"]
    status = d.get("status", "nicht_gefunden")
    if status == "konform":
        z.append(f"  Deklaration: KONFORM (Stand {d.get('stand')}, {d.get('organisation')})")
        fehlt = d.get("gemessen_aber_nicht_deklariert", [])
        z.append("  Abweichung gemessen↔deklariert: " + (", ".join(fehlt) if fehlt else "keine"))
    elif status == "nicht_gefunden":
        z.append("  Deklaration: keine /.well-known/datenfluss.json gefunden")
    else:
        z.append(f"  Deklaration: Datei gefunden, aber {status.upper()}")
        for b in d.get("befunde", [])[:3]:
            z.append(f"    {b}")
    z.append(f"  security.txt: {'ja' if p.get('security_txt') else 'nein'}")
    return "\n".join(z)


def main() -> int:
    parser = argparse.ArgumentParser(description="Vermisst Drittanbieter-Einbindungen einer Website (statisch).")
    parser.add_argument("urls", nargs="+", help="Eine oder mehrere Website-Adressen")
    parser.add_argument("-o", "--output", type=Path, default=Path("profile"),
                        help="Ordner fuer die JSON-Profile (Standard: ./profile)")
    parser.add_argument("--hartnaeckig", action="store_true",
                        help="Bei Abweisung (HTTP 403/406) erneut mit Browser-Kennung versuchen. "
                             "Standardmaessig aus: Eine Abweisung wird respektiert.")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    for url in args.urls:
        profil = scanne(url, hartnaeckig=args.hartnaeckig)
        host = urlparse(profil.get("finale_url", profil["url"])).hostname or "unbekannt"
        ziel = args.output / f"profil-{host}.json"
        ziel.write_text(json.dumps(profil, ensure_ascii=False, indent=2), encoding="utf-8")
        print(zusammenfassung(profil))
        print(f"  Profil gespeichert: {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

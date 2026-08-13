#!/usr/bin/env python3
"""Referenz-Renderer: erzeugt aus einer Datenfluss-Deklaration (v0.1) eine
lesbare, in sich geschlossene HTML-Seite – die «Datenfluss-Karte».

Verwendung:
    python3 renderer.py beispiel-deklaration.json
    python3 renderer.py deklaration.json -o karte.html

Nur Python-Standardbibliothek. Vor dem Rendern empfiehlt sich die Pruefung
mit validator.py; dieser Renderer prueft nur das Noetigste.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import date
from pathlib import Path

try:  # Laenderliste aus dem Validator wiederverwenden (gleiche Quelle der Wahrheit)
    from validator import ANGEMESSENE_LAENDER
except Exception:  # pragma: no cover - Fallback, falls Datei einzeln kopiert wird
    ANGEMESSENE_LAENDER = {
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
        "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
        "SI", "ES", "SE", "IS", "LI", "NO", "GB", "AD", "AR", "CA", "FO", "GG",
        "IM", "IL", "JE", "MC", "NZ", "UY", "CH",
    }

LAND_NAMEN = {
    "CH": "Schweiz", "DE": "Deutschland", "FR": "Frankreich", "IT": "Italien",
    "AT": "Österreich", "LI": "Liechtenstein", "IE": "Irland", "NL": "Niederlande",
    "BE": "Belgien", "LU": "Luxemburg", "ES": "Spanien", "PT": "Portugal",
    "DK": "Dänemark", "SE": "Schweden", "FI": "Finnland", "NO": "Norwegen",
    "IS": "Island", "PL": "Polen", "CZ": "Tschechien", "GB": "Grossbritannien",
    "US": "USA", "CA": "Kanada", "NZ": "Neuseeland", "IL": "Israel",
    "AR": "Argentinien", "UY": "Uruguay", "MC": "Monaco", "AD": "Andorra",
    "IN": "Indien", "CN": "China", "SG": "Singapur", "AU": "Australien",
}

ROLLEN = {
    "auftragsbearbeiter": "Auftragsbearbeiter",
    "eigenstaendig_verantwortlich": "Eigenständig verantwortlich",
    "behoerde": "Behörde",
    "konzerngesellschaft": "Konzerngesellschaft",
}

GARANTIEN = {
    "nicht_erforderlich_angemessenes_land": "Angemessenes Schutzniveau",
    "standarddatenschutzklauseln": "Standarddatenschutzklauseln",
    "angemessenheit_dpf_zertifiziert": "Swiss-U.S. DPF zertifiziert",
    "einwilligung": "Einwilligung",
    "vertragserfuellung": "Vertragserfüllung",
    "andere": "Andere Garantie",
}

KATEGORIEN = {
    "stammdaten": "Stammdaten", "kontaktdaten": "Kontaktdaten",
    "vertragsdaten": "Vertragsdaten", "bestelldaten": "Bestelldaten",
    "zahlungsdaten": "Zahlungsdaten", "nutzungsdaten": "Nutzungsdaten",
    "technische_daten": "Technische Daten", "standortdaten": "Standortdaten",
    "kommunikationsinhalte": "Kommunikationsinhalte",
    "bewerbungsdaten": "Bewerbungsdaten", "personaldaten": "Personaldaten",
    "gesundheitsdaten": "Gesundheitsdaten",
    "biometrische_daten": "Biometrische Daten", "weitere": "Weitere",
}


def esc(wert: object) -> str:
    return html.escape(str(wert), quote=True)


def flagge(code: str) -> str:
    """ISO-Laendercode -> Flaggen-Emoji (regionale Indikatoren)."""
    if not re.fullmatch(r"[A-Z]{2}", code or ""):
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)


def land_text(code: str) -> str:
    return LAND_NAMEN.get(code, code)


def huebsch(wert: str) -> str:
    """'vertragsabwicklung' -> 'Vertragsabwicklung'."""
    text = wert.replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else text


def dauer_text(iso: str) -> str:
    m = re.fullmatch(r"P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)W)?(?:(\d+)D)?", iso or "")
    if not m:
        return iso
    teile = []
    einheiten = [("Jahr", "Jahre"), ("Monat", "Monate"), ("Woche", "Wochen"), ("Tag", "Tage")]
    for wert, (sg, pl) in zip(m.groups(), einheiten):
        if wert:
            n = int(wert)
            teile.append(f"{n} {sg if n == 1 else pl}")
    return " ".join(teile) if teile else iso


def chips(werte: list[str], mapping: dict[str, str] | None = None) -> str:
    labels = [mapping.get(w, huebsch(w)) if mapping else huebsch(w) for w in werte]
    return "".join(f'<span class="chip">{esc(l)}</span>' for l in labels)


def empfaenger_knoten(e: dict) -> str:
    land = e.get("land", "")
    tags = []
    if land and land not in ANGEMESSENE_LAENDER:
        tags.append('<span class="tag tag-dritt">Drittland</span>')
    if e.get("garantien"):
        tags.append(f'<span class="tag">{esc(GARANTIEN.get(e["garantien"], huebsch(e["garantien"])))}</span>')
    dienst = f'<span class="knoten-dienst">{esc(e["dienst"])}</span>' if e.get("dienst") else ""
    rolle = ROLLEN.get(e.get("rolle", ""), huebsch(e.get("rolle", "")))
    return (
        '<span class="pfeil" aria-hidden="true">→</span>'
        '<span class="knoten">'
        f'<span class="knoten-name">{esc(e.get("name", "?"))}</span>'
        f"{dienst}"
        f'<span class="knoten-meta">{flagge(land)} {esc(land_text(land))} · {esc(rolle)}</span>'
        f'<span class="knoten-tags">{"".join(tags)}</span>'
        "</span>"
    )


def bearbeitung_html(b: dict, org_name: str) -> str:
    aufbew = b.get("aufbewahrung", {})
    dauer_teile = []
    if aufbew.get("dauer_iso"):
        dauer_teile.append(dauer_text(aufbew["dauer_iso"]))
    if aufbew.get("beschreibung"):
        dauer_teile.append(aufbew["beschreibung"])
    dauer = " · ".join(dauer_teile) or "—"

    fakten = []
    if b.get("besonders_schuetzenswert"):
        fakten.append('<span class="tag tag-dritt">Besonders schützenswerte Daten</span>')
    if b.get("profiling"):
        fakten.append('<span class="tag">Profiling</span>')
    if b.get("profiling_hohes_risiko"):
        fakten.append('<span class="tag tag-dritt">Profiling mit hohem Risiko</span>')
    if b.get("automatisierte_einzelentscheidung"):
        fakten.append('<span class="tag">Automatisierte Einzelentscheidung</span>')

    empfaenger = b.get("empfaenger", [])
    if empfaenger:
        fluss_ziele = "".join(empfaenger_knoten(e) for e in empfaenger)
    else:
        fluss_ziele = (
            '<span class="pfeil" aria-hidden="true">→</span>'
            f'<span class="knoten knoten-intern"><span class="knoten-name">bleibt bei {esc(org_name)}</span>'
            '<span class="knoten-meta">keine externen Empfänger</span></span>'
        )

    beschreibung = f'<p class="b-text">{esc(b["beschreibung"])}</p>' if b.get("beschreibung") else ""

    return f"""
<section class="bearbeitung" id="{esc(b.get("id", ""))}">
  <h3>{esc(b.get("name", b.get("id", "Bearbeitung")))}</h3>
  {beschreibung}
  <div class="fluss" role="img" aria-label="Datenfluss dieser Bearbeitung">
    <span class="knoten knoten-quelle"><span class="knoten-name">Ihre Daten</span></span>
    {fluss_ziele}
  </div>
  <dl class="b-fakten">
    <div><dt>Zwecke</dt><dd>{chips(b.get("zwecke", []))}</dd></div>
    <div><dt>Datenkategorien</dt><dd>{chips(b.get("datenkategorien", []), KATEGORIEN)}</dd></div>
    <div><dt>Aufbewahrung</dt><dd class="mono">{esc(dauer)}</dd></div>
    {f'<div><dt>Merkmale</dt><dd>{"".join(fakten)}</dd></div>' if fakten else ""}
  </dl>
</section>"""


CSS = """
:root{
  --papier:#ECEEE9; --karte:#FFFFFF; --tinte:#171B1D; --grau:#5C6467;
  --linie:#D8DCD4; --feld:#F4F6F1; --rot:#C8102E; --amber:#8A5A00; --amberbg:#F6E7C8;
}
*{box-sizing:border-box;margin:0;padding:0}
html{-webkit-text-size-adjust:100%}
body{background:var(--papier);color:var(--tinte);
  font:400 16px/1.55 "IBM Plex Sans",-apple-system,"Segoe UI",sans-serif;
  padding:40px 16px}
.mono{font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace}
a{color:var(--tinte)}
a:focus-visible,button:focus-visible{outline:3px solid var(--rot);outline-offset:2px}
.karte{max-width:880px;margin:0 auto;background:var(--karte);
  border:1px solid var(--linie);border-radius:10px;overflow:hidden}
header{padding:36px 40px 28px;border-bottom:1px solid var(--linie)}
.kicker{font-family:"IBM Plex Mono",monospace;font-size:12px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--grau)}
h1{font-family:Archivo,"IBM Plex Sans",sans-serif;font-weight:700;
  font-size:clamp(28px,5vw,40px);letter-spacing:-.01em;margin:8px 0 10px}
.meta{font-family:"IBM Plex Mono",monospace;font-size:13px;color:var(--grau);
  display:flex;flex-wrap:wrap;gap:6px 18px}
.meta a{color:var(--grau)}
.fakten{display:grid;grid-template-columns:repeat(3,1fr);border-bottom:1px solid var(--linie)}
.fakt{padding:16px 40px;border-right:1px solid var(--linie)}
.fakt:nth-child(3n){border-right:0}
.fakt:nth-child(n+4){border-top:1px solid var(--linie)}
.fakt b{display:block;font-family:"IBM Plex Mono",monospace;font-weight:600;font-size:17px}
.fakt span{font-size:12.5px;color:var(--grau)}
.rechte{margin:28px 40px;padding:20px 24px;background:var(--feld);
  border-left:4px solid var(--rot);border-radius:0 8px 8px 0}
.rechte h2{font-family:Archivo,sans-serif;font-size:18px;margin-bottom:6px}
.rechte p{font-size:14.5px;color:var(--grau);max-width:60ch}
.rechte-aktionen{margin-top:14px;display:flex;flex-wrap:wrap;gap:10px}
.knopf{display:inline-block;font:600 14px/1 "IBM Plex Sans",sans-serif;
  padding:11px 16px;border-radius:7px;text-decoration:none;
  background:var(--tinte);color:#fff;border:1px solid var(--tinte)}
.knopf.zweit{background:transparent;color:var(--tinte)}
.rechte .frist{font-family:"IBM Plex Mono",monospace;font-size:12.5px;color:var(--grau);margin-top:12px}
main{padding:8px 40px 8px}
main>h2{font-family:Archivo,sans-serif;font-size:14px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--grau);margin:24px 0 4px}
.bearbeitung{padding:22px 0 26px;border-bottom:1px solid var(--linie)}
.bearbeitung:last-of-type{border-bottom:0}
.bearbeitung h3{font-family:Archivo,sans-serif;font-size:21px;margin-bottom:4px}
.b-text{font-size:14.5px;color:var(--grau);max-width:70ch;margin-bottom:14px}
.fluss{display:flex;flex-wrap:wrap;align-items:stretch;gap:8px;
  background:var(--feld);border:1px solid var(--linie);border-radius:8px;
  padding:14px 16px;margin:10px 0 16px}
.pfeil{align-self:center;font-family:"IBM Plex Mono",monospace;color:var(--grau)}
.knoten{display:flex;flex-direction:column;justify-content:center;gap:2px;
  background:var(--karte);border:1px solid var(--linie);border-radius:7px;
  padding:9px 12px;min-width:150px}
.knoten-quelle{background:var(--tinte);border-color:var(--tinte);color:#fff;min-width:auto}
.knoten-intern{border-style:dashed;background:transparent}
.knoten-name{font-weight:600;font-size:14px}
.knoten-dienst{font-size:12.5px;color:var(--grau)}
.knoten-meta{font-family:"IBM Plex Mono",monospace;font-size:11.5px;color:var(--grau)}
.knoten-tags{display:flex;flex-wrap:wrap;gap:4px;margin-top:3px}
.tag{font-family:"IBM Plex Mono",monospace;font-size:10.5px;padding:2px 7px;
  border:1px solid var(--linie);border-radius:99px;color:var(--grau);background:var(--karte)}
.tag-dritt{color:var(--amber);border-color:var(--amber);background:var(--amberbg)}
.b-fakten div{display:grid;grid-template-columns:170px 1fr;gap:10px;
  padding:7px 0;border-top:1px dashed var(--linie);align-items:baseline}
.b-fakten dt{font-family:"IBM Plex Mono",monospace;font-size:12px;
  text-transform:uppercase;letter-spacing:.06em;color:var(--grau)}
.b-fakten dd{font-size:14px}
.chip{display:inline-block;background:var(--feld);border:1px solid var(--linie);
  border-radius:99px;padding:3px 10px;font-size:12.5px;margin:2px 4px 2px 0}
footer{padding:22px 40px 30px;border-top:1px solid var(--linie);
  font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--grau);
  display:flex;flex-wrap:wrap;gap:6px 20px;justify-content:space-between}
@media(max-width:640px){
  body{padding:16px 8px}
  header,main,.rechte,footer{padding-left:20px;padding-right:20px}
  .rechte{margin:20px}
  .fakten{grid-template-columns:1fr 1fr}
  .fakt{padding:14px 20px;border-right:0}
  .fakt:nth-child(odd){border-right:1px solid var(--linie)}
  .fakt:nth-child(n+3){border-top:1px solid var(--linie)}
  .fluss{flex-direction:column;align-items:stretch}
  .pfeil{align-self:flex-start;transform:rotate(90deg);margin-left:14px}
  .b-fakten div{grid-template-columns:1fr}
}
@media print{
  body{background:#fff;padding:0}
  .karte{border:0;border-radius:0;max-width:none}
  .knopf{border:1px solid var(--tinte);background:#fff;color:var(--tinte)}
}
"""


def render(dekl: dict) -> str:
    org = dekl.get("organisation", {})
    name = org.get("name", "Unbekannte Organisation")
    bearbeitungen = dekl.get("bearbeitungen", [])

    alle_empf = [e for b in bearbeitungen for e in b.get("empfaenger", [])]
    laender = sorted({e.get("land", "") for e in alle_empf if e.get("land")})
    drittland = any(l not in ANGEMESSENE_LAENDER for l in laender)
    profiling = any(b.get("profiling") for b in bearbeitungen)
    sensibel = any(b.get("besonders_schuetzenswert") for b in bearbeitungen)

    meta = []
    if org.get("uid"):
        meta.append(f'<span>{esc(org["uid"])}</span>')
    if org.get("website"):
        meta.append(f'<a href="{esc(org["website"])}">{esc(org["website"])}</a>')
    if dekl.get("stand"):
        meta.append(f'<span>Stand {esc(dekl["stand"])}</span>')

    fakten = [
        (str(len(bearbeitungen)), "Bearbeitungen"),
        (str(len({e.get("name") for e in alle_empf})), "externe Empfänger"),
        (" ".join(flagge(l) for l in laender) or "—", "Länder: " + (", ".join(laender) or "keine")),
        ("Ja" if drittland else "Nein", "Empfänger ausserhalb angemessener Staaten"),
        ("Ja" if profiling else "Nein", "Profiling"),
        ("Ja" if sensibel else "Nein", "Besonders schützenswerte Daten"),
    ]
    fakten_html = "".join(f'<div class="fakt"><b>{esc(w)}</b><span>{esc(l)}</span></div>' for w, l in fakten)

    ausk = dekl.get("auskunft", {})
    aktionen = []
    if ausk.get("email"):
        betreff = f"Auskunftsbegehren nach Art. 25 DSG – {name}"
        aktionen.append(f'<a class="knopf" href="mailto:{esc(ausk["email"])}?subject={esc(betreff)}">Auskunft per E-Mail anfragen</a>')
    if ausk.get("formular_url"):
        aktionen.append(f'<a class="knopf zweit" href="{esc(ausk["formular_url"])}">Auskunftsformular öffnen</a>')
    frist = ausk.get("frist_tage", 30)
    hinweis = f' {esc(ausk["hinweis"])}' if ausk.get("hinweis") else ""

    signatur = "signiert" if dekl.get("signatur") else "unsigniert (v0.1)"

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Datenfluss-Karte – {esc(name)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="karte">
<header>
  <p class="kicker">Datenfluss-Karte · Spezifikation v{esc(dekl.get("spec_version", "0.1"))}</p>
  <h1>{esc(name)}</h1>
  <p class="meta">{"".join(meta)}</p>
</header>
<div class="fakten">{fakten_html}</div>
<div class="rechte">
  <h2>Ihre Daten, Ihr Recht</h2>
  <p>Sie können jederzeit kostenlos erfahren, welche Daten diese Organisation über Sie bearbeitet, und deren Berichtigung oder Löschung verlangen.{hinweis}</p>
  <div class="rechte-aktionen">{"".join(aktionen)}</div>
  <p class="frist">Zugesicherte Antwortfrist: {esc(frist)} Tage</p>
</div>
<main>
  <h2>Bearbeitungen und ihre Empfänger</h2>
  {"".join(bearbeitung_html(b, name) for b in bearbeitungen)}
</main>
<footer>
  <span>Deklaration: {esc(signatur)}</span>
  <span>Quelle: /.well-known/datenfluss.json</span>
  <span>Karte erzeugt am {date.today().isoformat()} · Referenz-Renderer v0.1</span>
</footer>
</div>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Rendert eine Datenfluss-Deklaration als HTML-Karte.")
    parser.add_argument("deklaration", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None)
    args = parser.parse_args()

    try:
        dekl = json.loads(args.deklaration.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Fehler beim Lesen der Deklaration: {exc}")
        return 2

    for pflicht in ("spec_version", "organisation", "bearbeitungen"):
        if pflicht not in dekl:
            print(f"Fehler: Feld '{pflicht}' fehlt – bitte zuerst mit validator.py pruefen.")
            return 2

    ziel = args.output or args.deklaration.with_name("datenfluss-karte.html")
    ziel.write_text(render(dekl), encoding="utf-8")
    print(f"Karte erzeugt: {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

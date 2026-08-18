# Datenfluss-Standard v0.1 (Entwurf)

**Ein offener Standard für maschinenlesbare Datenschutz-Transparenz. Das Format ist rechtsraumneutral – Referenzimplementierung und erstes Prüfprofil: Schweiz.**

*English guide: [README.en.md](README.en.md) – the specification's normative language is German.*

Jede Organisation deklariert in einer signierbaren JSON-Datei, welche Personendaten sie zu welchen Zwecken bearbeitet, an wen sie fliessen und wie lange sie aufbewahrt werden. Die Datei liegt auf der eigenen Domain – nicht auf einer Plattform:

```
https://www.beispielfirma.ch/.well-known/datenfluss.json
```

Plattformen, Browser-Erweiterungen, Treuhänder-Software und Register können diese Dateien crawlen, validieren und darstellen. Der Standard gehört niemandem und braucht keinen bestimmten Anbieter, um zu funktionieren.

## Dateien in diesem Paket

| Datei | Inhalt |
|---|---|
| `spec/v0.1/datenfluss.schema.json` | Die formale Spezifikation als JSON Schema (Draft 2020-12), Feldbeschreibungen auf Deutsch |
| `beispiele/beispiel-deklaration.json` | Vollständige Beispiel-Deklaration der fiktiven **Alpenkafi GmbH** (Webshop, Newsletter, Analyse, Support) |
| `werkzeuge/validator.py` | Prüft Deklarationen formal (Schema) und semantisch (universelle Regeln + Prüfprofil je Rechtsraum, heute: `ch`) |
| `werkzeuge/renderer.py` | Referenz-Renderer: erzeugt aus einer Deklaration die lesbare HTML-«Datenfluss-Karte» |
| `beispiele/datenfluss-karte.html` | Gerenderte Beispiel-Karte der Alpenkafi GmbH (im Browser öffnen) |
| `werkzeuge/scanner.py` | Scanner-Prototyp: vermisst statisch eingebundene Drittanbieter einer Website und vergleicht mit deren Deklaration (gemessen ↔ deklariert) |
| `werkzeuge/dns_messung.py` | Misst die im DNS **selbst veröffentlichten** Datenflüsse: Post-Empfänger (MX), Sendeberechtigte (SPF), First-Party-Tarnung (CNAME) – ohne eine einzige Anfrage an die Server der gemessenen Stelle |
| `werkzeuge/konformitaet.py` | Konformitäts-Testsuite: prüft eine Implementierung gegen die verbindlichen Testfälle |
| `spec/v0.1/konformitaet/` | Die Testfälle selbst (10 Deklarationen) samt `erwartungen.json` – die Referenz, an der sich jede Umsetzung messen lassen muss |
| `profile/profil-www.digitale-gesellschaft.ch.json` | Echtes Beispiel eines gemessenen Profils |
| `kommunikation/einseiter.pdf` · `einseiter.py` | Einseiter fürs Gespräch samt Generator-Skript (Schriften: IBM Plex, OFL-lizenziert) |

## Schnellstart

```bash
pip install jsonschema
python3 werkzeuge/validator.py beispiele/beispiel-deklaration.json
python3 werkzeuge/renderer.py beispiele/beispiel-deklaration.json   # erzeugt datenfluss-karte.html
```

Der Renderer braucht nur die Python-Standardbibliothek und erzeugt eine in sich geschlossene HTML-Seite: Kopf mit Kennzahlen, ein Block «Ihre Daten, Ihr Recht» mit direktem Auskunfts-Knopf – und pro Bearbeitung eine **Fluss-Zeile** («Ihre Daten → Empfänger → Empfänger») mit Flaggen, Garantien und Drittland-Markierung.

```bash
python3 werkzeuge/scanner.py https://www.beispielfirma.ch   # gemessenes Profil nach ./profile/
```

Der Scanner respektiert robots.txt (RFC 9309) und identifiziert sich ehrlich als `DatenflussScanner/0.1`. Weist ein Server diese Kennung ab (HTTP 403/406), wird die Abweisung standardmässig respektiert und nicht erneut versucht – wer unsere ehrliche Kennung ablehnt, will nicht vermessen werden. Nur mit dem ausdrücklichen Schalter `--hartnaeckig` wird ein zweiter Versuch mit Browser-Kennung unternommen; er wird dann im Profil als `abruf_hinweis` dokumentiert. Er erkennt rund 45 bekannte Dienste inkl. selbst gehostetem Matomo und Inline-Signaturen (`gtag(`, `fbq(`, `GTM-`), prüft `/.well-known/datenfluss.json` und berechnet die Abweichung **gemessen ↔ deklariert**. Methodik-Grenze, im Profil dokumentiert: statische Analyse ohne JavaScript – dynamisch via Tag Manager nachgeladene Dienste sind unsichtbar, der Befund ist eine Untergrenze. Scheitert ein Abruf, speichert das Profil Roh-Evidenz (`abruf_beleg`: Fehlerklasse, HTTP-Status, ausgewählte Antwort-Header): Ein Messwerkzeug, das «nicht erreichbar» nur behauptet, statt es zu belegen, produziert unbestreitbare Befunde – und genau solche Befunde werden zu Recht bestritten.

```bash
python3 werkzeuge/dns_messung.py landi.ch migros.ch   # oder --json
```

Die DNS-Messung beantwortet Fragen, die im HTML gar nicht vorkommen: **Wohin geht die Post der Organisation?** (MX) · **Wer darf in ihrem Namen senden?** (SPF-Includes – verrät Newsletter-, CRM- und Bewerbungssysteme, die auf der Website nirgends auftauchen) · **Sieht eine Subdomain nur wie ein eigener Dienst aus?** (CNAME-Tarnung, etwa `metrics.firma.ch → adobedc.net`).

Sie stellt dabei **keine einzige Anfrage an die Server der gemessenen Organisation** – gelesen wird ausschliesslich, was diese selbst im DNS veröffentlicht hat, damit die Welt es liest. Die Messung erzeugt keine Last und lässt sich nicht abweisen; genau deshalb bleibt der Befund sachlich und ohne Wertung. Ihre Grenzen stehen im Ergebnis: MX sagt, wer Post *annimmt*, nicht wo sie danach liegt; SPF sagt, wer senden *darf*, nicht wer sendet; die Subdomain-Prüfung ist eine Stichprobe; die Zuordnung Anbieter → Land ist ein Hinweis auf den Konzernsitz, keine Aussage über den Speicherort. Aufgelöst wird über einen fremden DNS-over-HTTPS-Dienst – das ist selbst ein Datenfluss und wird im Ergebnis benannt. Unbekannte Ziele werden als unbekannt ausgewiesen und nie geraten.

Für Register, die auf diesem Standard aufbauen, gilt dabei eine verbindliche Regel: **Als deklariert zählt eine Website nur, wenn ihre Datei die Standardprüfung besteht.** Eine gefundene, aber nicht konforme Datei wird als solche ausgewiesen – mit den konkreten Befunden als Wegbeschreibung, nicht als Pranger. Ohne diese Regel entschiede ein gelungener JSON-Parse statt des Standards darüber, wer die Marke trägt, und die mittlere Vertrauensstufe wäre wertlos.

Der Validator fällt **zwei getrennte Urteile** über dieselbe Datei:

1. **Standardkonformität** (stabil) – Struktur, Pflichtfelder, Formate, universelle Regeln (Stand-Datum nicht in der Zukunft, eindeutige IDs, Signatur-Hinweis). Dieses Urteil hängt nur an der Datei: Eine heute standardkonforme Deklaration bleibt es, solange sich die Datei nicht ändert.
2. **Rechtsbefund des Prüfprofils** (zeitabhängig, `--profil`, Standard `ch`) – Drittlandtransfers (Art. 16 f. DSG), USA-Sonderfall mit Swiss-U.S.-DPF, DSFA-Hinweise bei Hochrisiko-Profiling. Dieses Urteil hängt an der aktuellen Rechtslage und kann sich ändern, ohne dass sich ein Zeichen der Datei ändert.

Die Trennung ist der Kern der Versionierbarkeit: Streicht der Bundesrat morgen ein Land von der Angemessenheitsliste, wird keine einzige bestehende Deklaration dadurch standardwidrig – aber der Validator zeigt das neue rechtliche Problem an. Juristische Logik lebt ausschliesslich in Prüfprofilen; ein weiterer Rechtsraum (z. B. `eu` für die DSGVO) wird als zusätzliches Profil ergänzt, ohne dass sich Schema oder bestehende Deklarationen ändern.

Exit-Codes, direkt in CI/CD einsetzbar: `0` = standardkonform ohne Profil-Probleme · `1` = Standard verletzt · `3` = standardkonform, aber das Prüfprofil meldet Probleme. Wer auf beides reagieren will, prüft wie üblich auf `!= 0`.

### Konformität: wie man eine eigene Umsetzung überprüft

```bash
python3 werkzeuge/konformitaet.py          # 10 Testfälle, Exit 0 = alle bestanden
python3 werkzeuge/konformitaet.py --json   # maschinenlesbares Ergebnis
```

Der Standard wird mehrfach umgesetzt – hier in Python, im Browser eines Deklarations-Generators, morgen vielleicht von Dritten. Ohne gemeinsame Testfälle driften diese Umsetzungen auseinander, bis ein Werkzeug «gültig» sagt und das andere «ungültig». Genau das darf einem Standard nicht passieren.

Deshalb sind die Dateien in `spec/v0.1/konformitaet/` **verbindliche Referenz**, nicht bloss Beispiele. Die Namensgebung trägt die Trennung der zwei Urteile: `fehler-*` verletzt den Standard, `profilfehler-*`/`profilwarnung-*` ist standardkonform mit Rechtsbefund im Profil `ch`. `erwartungen.json` hält je Fall fest, was herauskommen muss. Wer den Standard umsetzt, sollte alle Fälle bestehen; wer ihn erweitert, ergänzt zuerst einen Testfall.

## Vorläufer und verwandte Standards

Die Idee maschinenlesbarer Datenschutz-Angaben ist nicht neu – und wer sie umsetzt, sollte wissen, woran der wichtigste Vorläufer gescheitert ist:

- **W3C P3P** (2002, heute offiziell obsolet) liess Websites ihre Datenpraktiken maschinenlesbar deklarieren. Es scheiterte an zwei Dingen: Es gab kaum Software, die die Angaben konsumierte – und sobald der Internet Explorer die Angaben für Cookie-Entscheide nutzte, kopierten Betreiber generische Policies, statt ihre Praxis zu beschreiben. **Eine standardisierte Behauptung allein schafft keine Transparenz.** Genau deshalb stellt dieser Standard der Selbstdeklaration eine unabhängige Messung gegenüber (gemessen ↔ deklariert) und hält beide strikt getrennt: Die Deklaration ist die Aussage der Organisation, die Messung ist die Beobachtung von aussen, und der Vergleich der beiden ist öffentlich. Eine kopierte Gefälligkeits-Deklaration fällt am Messwert auf.
- **W3C DPV** (Data Privacy Vocabulary) definiert ein umfassendes Vokabular für Zwecke, Empfänger und Rechtsgrundlagen. Dieser Standard erfindet bewusst keine eigene Ontologie dieser Tiefe; ein Mapping der Feldsemantik auf DPV steht auf der Roadmap, damit Deklarationen international anschlussfähig bleiben.
- **Apple Privacy Manifests** und **Google Play Data Safety** verlangen strukturierte, maschinenlesbare Datenschutz-Angaben von Apps und SDKs – dieselbe Bewegung von Fliesstext zu prüfbarer Metainformation, aber innerhalb geschlossener Plattformen. Dieser Standard überträgt das Muster auf das offene Web, wo keine Plattform Deklarationen erzwingen kann – dafür kann jede Person sie unabhängig nachmessen.

Kurz: Neu ist nicht die maschinenlesbare Erklärung. Neu ist die **öffentliche, versionierte Gegenprobe** – Selbsterklärung und unabhängige Messung, getrennt erhoben und maschinell vergleichbar.

## Design-Prinzipien

1. **Dezentral:** Die Deklaration liegt bei der Organisation. Register sind austauschbar.
2. **Ehrlichkeit durch Öffentlichkeit:** Eine falsche öffentliche Deklaration ist lauterkeitsrechtlich angreifbar – Publizität diszipliniert.
3. **Erweiterbar, aber streng:** Unbekannte Felder sind verboten, ausser mit Präfix `x_` (kontrollierte Innovation).
4. **Rechtsraumneutral im Format, DSG-nah im ersten Profil:** Begriffe folgen dem Schweizer DSG; optionale Felder (Rechtsgrundlagen) schlagen die Brücke zur DSGVO. Juristische Prüflogik ist als austauschbares Prüfprofil vom Format getrennt.
5. **Drei Vertrauensstufen** (ausserhalb dieser Spezifikation): gemessen → deklariert → verifiziert.

## Roadmap Richtung v1.0

- Signatur verpflichtend (PGP oder JWS), inkl. Schlüssel-Konvention
- Offizielle Übersetzungen FR/IT (mehrsprachige Deklarationen)
- EU-Prüfprofil (`--profil eu`, DSGVO-Logik) als erstes Nicht-Schweizer Profil
- Registrierung des `/.well-known/`-Pfads (RFC 8615/IANA), Andockpunkt eCH prüfen
- Mapping der Feldsemantik auf das W3C Data Privacy Vocabulary (DPV)
- Abgleich der erkannten Anbieter mit der öffentlichen Swiss-U.S.-DPF-Zertifizierungsliste: macht aus der von aussen unsichtbaren Frage «liegt eine Garantie vor?» ein messbares Signal
- Badge-Widget als Werkzeug in diesem Repo: eine einbettbare Kurzversion der Karte («Datenfluss deklariert · Stand …») existiert bereits als Referenz auf `datenfluss-standard.ch`, fehlt hier aber noch als eigenständiges Werkzeug
- Scanner mit Headless-Browser: erfasst auch dynamisch nachgeladene Dienste (heute nur Untergrenze)
- Ausbau der Konformitäts-Testsuite: mehr Grenzfälle, Testfälle je Prüfprofil

## Lizenz

Code: **MIT** (`LICENSE`) · Spezifikation und Texte: **CC BY 4.0** (`spec/LICENSE-CC-BY-4.0.txt`) · Schriften: IBM Plex unter **SIL OFL 1.1** (`kommunikation/fonts/OFL-LICENSE.txt`). So kann jede Person und Firma den Standard implementieren, ohne zu fragen – genau das ist das Ziel.

## Mitmachen

Issues und Pull Requests sind willkommen. Diskussionsbedarf besteht v. a. beim Zweck-Vokabular, den Datenkategorien und der Signatur-Konvention.

---

*Status: Entwurf v0.1 · August 2026 · Dieses Paket ist der Startpunkt, nicht das Endprodukt.*

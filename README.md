# Datenfluss-Standard v0.1 (Entwurf)

**Ein offener Standard für maschinenlesbare Datenschutz-Transparenz von Schweizer Organisationen.**

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
| `werkzeuge/validator.py` | Prüft Deklarationen formal (Schema) und semantisch (Schweizer Regeln) |
| `werkzeuge/renderer.py` | Referenz-Renderer: erzeugt aus einer Deklaration die lesbare HTML-«Datenfluss-Karte» |
| `beispiele/datenfluss-karte.html` | Gerenderte Beispiel-Karte der Alpenkafi GmbH (im Browser öffnen) |
| `werkzeuge/scanner.py` | Scanner-Prototyp: vermisst statisch eingebundene Drittanbieter einer Website und vergleicht mit deren Deklaration (gemessen ↔ deklariert) |
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

Der Scanner respektiert robots.txt (RFC 9309), identifiziert sich ehrlich als `DatenflussScanner/0.1` (bei Bot-Schutz ein transparent dokumentierter Wiederholungsversuch mit Browser-Kennung), erkennt rund 45 bekannte Dienste inkl. selbst gehostetem Matomo und Inline-Signaturen (`gtag(`, `fbq(`, `GTM-`), prüft `/.well-known/datenfluss.json` und berechnet die Abweichung **gemessen ↔ deklariert**. Methodik-Grenze, im Profil dokumentiert: statische Analyse ohne JavaScript – dynamisch via Tag Manager nachgeladene Dienste sind unsichtbar, der Befund ist eine Untergrenze.

Der Validator prüft zwei Stufen:

1. **Formal** – Struktur, Pflichtfelder, Formate (UID, Datum, Ländercodes, Enums)
2. **Semantisch** – Schweizer Logik:
   - Drittlandtransfers: Empfänger ausserhalb der angemessenen Staaten brauchen eine Garantie (Art. 16 f. DSG)
   - USA-Sonderfall: Angemessenheit nur für Empfänger mit Swiss-U.S.-DPF-Zertifizierung, mit Erinnerung zur periodischen Prüfung
   - Stand-Datum nicht in der Zukunft, Warnung ab 18 Monaten Alter
   - Eindeutige IDs, DSFA-Hinweise bei Hochrisiko-Profiling, Signatur-Hinweis

Exit-Code `0` = gültig, `1` = Fehler – damit direkt in CI/CD einsetzbar (z. B. GitHub Action, die bei jeder Website-Änderung die eigene Deklaration prüft).

## Design-Prinzipien

1. **Dezentral:** Die Deklaration liegt bei der Organisation. Register sind austauschbar.
2. **Ehrlichkeit durch Öffentlichkeit:** Eine falsche öffentliche Deklaration ist lauterkeitsrechtlich angreifbar – Publizität diszipliniert.
3. **Erweiterbar, aber streng:** Unbekannte Felder sind verboten, ausser mit Präfix `x_` (kontrollierte Innovation).
4. **DSG-nah, DSGVO-anschlussfähig:** Begriffe folgen dem Schweizer DSG; optionale Felder (Rechtsgrundlagen) schlagen die Brücke zur DSGVO.
5. **Drei Vertrauensstufen** (ausserhalb dieser Spezifikation): gemessen → deklariert → verifiziert.

## Roadmap Richtung v1.0

- Signatur verpflichtend (PGP oder JWS), inkl. Schlüssel-Konvention
- Offizielle Übersetzungen FR/IT (mehrsprachige Deklarationen)
- Registrierung des `/.well-known/`-Pfads, Andockpunkt eCH prüfen
- Badge-Widget: einbettbare Kurzversion der Karte für Websites («Datenfluss deklariert · Stand …»)
- Scanner mit Headless-Browser: erfasst auch dynamisch nachgeladene Dienste (heute nur Untergrenze)
- Konformitäts-Testsuite (gültige und ungültige Beispieldateien)

## Lizenz

Code: **MIT** (`LICENSE`) · Spezifikation und Texte: **CC BY 4.0** (`spec/LICENSE-CC-BY-4.0.txt`) · Schriften: IBM Plex unter **SIL OFL 1.1** (`kommunikation/fonts/OFL-LICENSE.txt`). So kann jede Person und Firma den Standard implementieren, ohne zu fragen – genau das ist das Ziel.

## Mitmachen

Issues und Pull Requests sind willkommen, sobald das Repo öffentlich ist. Diskussionsbedarf besteht v. a. beim Zweck-Vokabular, den Datenkategorien und der Signatur-Konvention.

---

*Status: Entwurf v0.1 · August 2026 · Dieses Paket ist der Startpunkt, nicht das Endprodukt.*

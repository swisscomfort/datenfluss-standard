# Sicherheitslücken und Fehler melden

## Wohin

**kontakt@datenfluss-standard.ch**

Bitte nicht als öffentliches Issue, solange die Lücke ausnutzbar ist. Wir
antworten innert **fünf Arbeitstagen** und nennen dabei, was wir tun und bis
wann.

Wenn Sie verschlüsselt schreiben wollen: Das Postfach liegt bei Proton Mail,
eine verschlüsselte Antwort ist möglich.

## Was hier als Sicherheitsproblem zählt

Dieses Projekt ist eine Spezifikation mit Werkzeugen, kein betriebener Dienst.
Entsprechend sind das die relevanten Fälle:

- **Validator meldet «gültig», obwohl die Deklaration eine Rechtsverletzung
  beschreibt** – oder umgekehrt. Wer sich auf das Urteil verlässt, wird sonst
  in Sicherheit gewiegt. Das ist für uns die schwerste Kategorie.
- **Renderer erzeugt Karten, die Code aus der Deklaration ausführen.** Die
  Deklaration ist fremde Eingabe; die erzeugte HTML-Seite muss sie behandeln
  wie ein Formularfeld.
- **Renderer erzeugt Seiten, die beim Anzeigen etwas nachladen.** Eine Karte,
  die Besucher an Dritte meldet, ist genau das, was dieses Projekt sichtbar
  machen will. Sie darf null externe Anfragen auslösen.
- **Scanner verletzt fremde Systeme** – ignoriert robots.txt, verschleiert
  seine Kennung, erzeugt Last. Der Scanner misst öffentlich Sichtbares und
  respektiert eine Abweisung.
- Übliche Software-Lücken in den Werkzeugen: Pfad-Ausbruch beim Schreiben von
  Dateien, Ausführung fremder Inhalte, Abhängigkeiten mit bekannten Lücken.

## Was kein Sicherheitsproblem ist

- **Eine Firma deklariert etwas Falsches.** Der Standard prüft Aussagen auf
  Widerspruchsfreiheit, nicht auf Wahrheit. Falsche öffentliche Angaben sind
  ein Fall fürs Lauterkeitsrecht, nicht für diesen Meldeweg.
- **Der Scanner findet nicht alles.** Die statische Analyse führt kein
  JavaScript aus; dynamisch nachgeladene Dienste bleiben unsichtbar. Der
  Befund ist ausdrücklich eine Untergrenze und in jedem Profil so bezeichnet.
- **Meinungsverschiedenheiten über die Prüfregeln.** Die gehören als Issue
  in die Öffentlichkeit – gerade dort ist Streit nützlich.

## Wenn Sie eine Lücke gefunden haben

Hilfreich ist:

1. Was Sie erwartet haben und was passiert ist
2. Eine Datei oder ein Befehl, mit dem wir es nachstellen können
3. Ihre Einschätzung, wer dadurch zu Schaden kommt

Ein Testfall unter `spec/v0.1/konformitaet/` ist die beste Form eines Berichts:
Er beschreibt die Lücke so, dass sie sich nicht wieder einschleichen kann.

## Anerkennung

Wer eine Lücke meldet, wird auf Wunsch im Änderungsprotokoll genannt. Geld gibt
es keines – das Projekt hat keines. Was es gibt, ist ein öffentlicher Dank und
eine schnelle Korrektur.

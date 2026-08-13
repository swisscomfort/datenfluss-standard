#!/usr/bin/env python3
"""Erzeugt den Einseiter «Datenfluss-Standard» als A4-PDF (reportlab).

Gestaltung folgt der Datenfluss-Karte: Papier/Tinte, IBM Plex,
Siegelrot nur als Akzent, Fluss-Zeile als Signatur-Element.
"""

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HIER = Path(__file__).parent
FONTS = HIER / "fonts"
for name, datei in [("PlexSans", "IBMPlexSans-Regular.ttf"),
                    ("PlexSans-SB", "IBMPlexSans-SemiBold.ttf"),
                    ("PlexSans-B", "IBMPlexSans-Bold.ttf"),
                    ("PlexMono", "IBMPlexMono-Regular.ttf"),
                    ("PlexMono-SB", "IBMPlexMono-SemiBold.ttf")]:
    pdfmetrics.registerFont(TTFont(name, str(FONTS / datei)))

PAPIER = HexColor("#ECEEE9")
KARTE = HexColor("#FFFFFF")
TINTE = HexColor("#171B1D")
GRAU = HexColor("#5C6467")
LINIE = HexColor("#D8DCD4")
FELD = HexColor("#F4F6F1")
ROT = HexColor("#C8102E")
AMBER = HexColor("#8A5A00")
AMBERBG = HexColor("#F6E7C8")

B, H = A4  # 595 x 842 pt
RAND = 46


def text(c, x, y, s, font="PlexSans", size=10, farbe=TINTE, ls=0):
    c.setFont(font, size)
    c.setFillColor(farbe)
    if ls:
        c.drawString(x, y, s, charSpace=ls)
    else:
        c.drawString(x, y, s)


def absatz(c, x, y, s, breite, font="PlexSans", size=10, farbe=TINTE, zeile=14):
    c.setFont(font, size)
    c.setFillColor(farbe)
    for z in simpleSplit(s, font, size, breite):
        c.drawString(x, y, z)
        y -= zeile
    return y


def pille(c, x, y, w, h, fuellung, rand, radius=7):
    c.setFillColor(fuellung)
    c.setStrokeColor(rand)
    c.setLineWidth(1)
    c.roundRect(x, y, w, h, radius, stroke=1, fill=1)


def tag(c, x, y, s, farbe=GRAU, bg=KARTE, rand=LINIE):
    w = pdfmetrics.stringWidth(s, "PlexMono", 7.2) + 10
    pille(c, x, y, w, 13, bg, rand, radius=6.5)
    text(c, x + 5, y + 3.6, s, "PlexMono", 7.2, farbe)
    return w


def knoten(c, x, y, titel, meta, w=None, h=52, dunkel=False, tags=None):
    if w is None:
        w = max(pdfmetrics.stringWidth(titel, "PlexSans-SB", 9.5),
                pdfmetrics.stringWidth(meta, "PlexMono", 6.8)) + 20
    pille(c, x, y, w, h, TINTE if dunkel else KARTE, TINTE if dunkel else LINIE)
    text(c, x + 10, y + h - 16, titel, "PlexSans-SB", 9.5, KARTE if dunkel else TINTE)
    text(c, x + 10, y + h - 29, meta, "PlexMono", 6.8, HexColor("#B9BFC1") if dunkel else GRAU)
    if tags:
        tx = x + 10
        for t, warn in tags:
            tx += tag(c, tx, y + 6, t,
                      AMBER if warn else GRAU, AMBERBG if warn else KARTE,
                      AMBER if warn else LINIE) + 4
    return w


def pfeil(c, x, y):
    text(c, x, y, "\u2192", "PlexMono", 11, GRAU)
    return 14


def erstelle(ziel: Path):
    c = canvas.Canvas(str(ziel), pagesize=A4)
    c.setTitle("Datenfluss-Standard – Einseiter")

    # Hintergrund + Karte
    c.setFillColor(PAPIER)
    c.rect(0, 0, B, H, stroke=0, fill=1)
    c.setFillColor(KARTE)
    c.setStrokeColor(LINIE)
    c.roundRect(18, 18, B - 36, H - 36, 10, stroke=1, fill=1)

    y = H - 64
    text(c, RAND, y, "DATENFLUSS-STANDARD · ARBEITSTITEL · SPEZIFIKATION V0.1",
         "PlexMono", 8.5, GRAU, ls=1.4)
    y -= 30
    text(c, RAND, y, "Datenschutz, den man sehen kann.", "PlexSans-B", 27, TINTE)
    y -= 22
    y = absatz(c, RAND, y,
               "Eine maschinenlesbare Datei auf der eigenen Website zeigt, wohin Kundendaten "
               "fliessen – öffentlich, prüfbar, vergleichbar. Was die Datenschutzerklärung "
               "verspricht, wird damit zu einer Karte, die jede Kundin in zehn Sekunden liest "
               "und jedes Werkzeug automatisch prüfen kann.",
               B - 2 * RAND, size=11, farbe=GRAU, zeile=15.5)

    # Fluss-Zeile (Signatur-Element)
    y -= 20
    nh = 52
    fh = nh + 26
    c.setFillColor(FELD)
    c.setStrokeColor(LINIE)
    c.roundRect(RAND, y - fh, B - 2 * RAND, fh, 8, stroke=1, fill=1)
    fy = y - fh + 13
    fx = RAND + 14
    fx += knoten(c, fx, fy, "Ihre Daten", "Kundin", h=nh, dunkel=True) + 4
    fx += pfeil(c, fx, fy + nh / 2 - 4) + 4
    fx += knoten(c, fx, fy, "KMU-Website", ".well-known/datenfluss.json", h=nh) + 4
    fx += pfeil(c, fx, fy + nh / 2 - 4) + 4
    fx += knoten(c, fx, fy, "Stripe", "Zahlung · IE", h=nh) + 4
    fx += pfeil(c, fx, fy + nh / 2 - 4) + 4
    knoten(c, fx, fy, "Mailchimp", "Newsletter · US · DPF", h=nh, tags=[("Drittland", True)])
    y = y - fh - 30

    # Zwei Spalten
    spalte = (B - 2 * RAND - 24) / 2
    x2 = RAND + spalte + 24
    y_start = y

    text(c, RAND, y, "SO FUNKTIONIERT ES", "PlexMono-SB", 8.5, TINTE, ls=1.2)
    yl = y - 18
    schritte = [
        ("1  Deklarieren", "Die Firma beschreibt ihre Datenflüsse einmal in einer offenen "
                           "JSON-Datei auf der eigenen Domain – Zwecke, Empfänger, Länder, Fristen."),
        ("2  Prüfen", "Validator und Website-Scanner gleichen Deklaration und Realität ab: "
                      "gemessen ↔ deklariert, Drittland-Regeln nach DSG inklusive."),
        ("3  Zeigen", "Daraus entstehen automatisch die öffentliche Datenfluss-Karte, ein "
                      "Website-Badge und Antworten auf Kunden-Fragebögen."),
    ]
    for titel, body in schritte:
        text(c, RAND, yl, titel, "PlexSans-SB", 10.5, TINTE)
        yl -= 14
        yl = absatz(c, RAND, yl, body, spalte, size=9.3, farbe=GRAU, zeile=12.5)
        yl -= 8

    text(c, x2, y, "WAS ES BRINGT", "PlexMono-SB", 8.5, TINTE, ls=1.2)
    yr = y - 18
    nutzen = [
        ("KMU", "Datenschutz-Fragebögen von Grosskunden einmal beantworten statt zwanzigmal – "
                "und Vertrauen sichtbar machen, bevor die Konkurrenz es tut."),
        ("Treuhänder", "DSG-Beratung wird zum wiederholbaren Prozess: eine Stunde pro Mandant, "
                       "Werkzeuge erledigen Dokumentation und Aktualität."),
        ("Kundschaft", "Ein Blick statt AGB-Wüste: wohin Daten fliessen und wie man Auskunft "
                       "verlangt – der Knopf dafür ist eingebaut."),
    ]
    for titel, body in nutzen:
        text(c, x2, yr, titel, "PlexSans-SB", 10.5, TINTE)
        yr -= 14
        yr = absatz(c, x2, yr, body, spalte, size=9.3, farbe=GRAU, zeile=12.5)
        yr -= 8

    y = min(yl, yr) - 6

    # Vertrauensstufen
    text(c, RAND, y, "DREI VERTRAUENSSTUFEN", "PlexMono-SB", 8.5, TINTE, ls=1.2)
    y -= 20
    tx = RAND
    for s, warn in [("GEMESSEN – Aussen-Scan", False), ("DEKLARIERT – signierte Datei", False),
                    ("VERIFIZIERT – Prüfung durch Dritte", False)]:
        tx += tag(c, tx, y - 2, s) + 8
        if s != "VERIFIZIERT – Prüfung durch Dritte":
            tx += pfeil(c, tx, y + 1) + 6
    y -= 16
    y = absatz(c, RAND, y,
               "Kein Gütesiegel: Das Register bewertet nicht, es macht sichtbar. Ehrlichkeit "
               "erzwingt die Öffentlichkeit selbst – eine falsche öffentliche Deklaration ist "
               "lauterkeitsrechtlich angreifbar.",
               B - 2 * RAND, size=9.3, farbe=GRAU, zeile=12.5)

    # Status-Box
    y -= 12
    bh = 72
    c.setFillColor(FELD)
    c.setStrokeColor(LINIE)
    c.roundRect(RAND, y - bh, B - 2 * RAND, bh, 8, stroke=1, fill=1)
    c.setFillColor(ROT)
    c.rect(RAND, y - bh + 6, 4, bh - 12, stroke=0, fill=1)
    text(c, RAND + 18, y - 20, "Heute verfügbar", "PlexSans-SB", 10.5, TINTE)
    absatz(c, RAND + 18, y - 35,
           "Offene Spezifikation v0.1 (JSON Schema) · Validator mit Schweizer Drittland-Logik · "
           "Karten-Renderer · Website-Scanner mit Abgleich gemessen ↔ deklariert. "
           "Alles Open Source, ohne Anbieter-Bindung.",
           B - 2 * RAND - 200, size=9, farbe=GRAU, zeile=12)
    text(c, B - RAND - 168, y - 20, "Gesucht", "PlexSans-SB", 10.5, ROT)
    absatz(c, B - RAND - 168, y - 35,
           "10 Pilotfirmen (Aufwand: 1 Stunde, kostenlos) und kritisches Feedback zum Format.",
           152, size=9, farbe=GRAU, zeile=12)

    y = y - bh - 28
    text(c, RAND, y,
         "Vorbilder dieses Wegs: security.txt \u2192 RFC 9116 · ACME \u2192 Let's Encrypt · Creative Commons",
         "PlexMono", 8, GRAU)
    text(c, RAND, y - 13,
         "Werkzeug zuerst – die Norm folgt der Gewohnheit.",
         "PlexMono", 8, GRAU)

    # Fusszeile
    c.setStrokeColor(LINIE)
    c.line(RAND, 64, B - RAND, 64)
    text(c, RAND, 48, "[Vorname Name] · [E-Mail] · [Website / GitHub-Repo]", "PlexMono", 8.5, GRAU)
    text(c, B - RAND - pdfmetrics.stringWidth("Spezifikation CC BY 4.0 · Code MIT", "PlexMono", 8.5),
         48, "Spezifikation CC BY 4.0 · Code MIT", "PlexMono", 8.5, GRAU)

    c.showPage()
    c.save()
    print(f"Einseiter erzeugt: {ziel}")


if __name__ == "__main__":
    erstelle(HIER / "einseiter.pdf")

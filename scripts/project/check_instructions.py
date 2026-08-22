#!/usr/bin/env python3
"""Prueft die aktiven Anweisungspfade des oeffentlichen Standard-Repositories.

Ein offener Standard hat zwei Arten, still zu kippen: Er uebernimmt wieder
eine Geschaeftserzaehlung als Anforderung, oder er saugt eine proprietaere
Abhaengigkeit ein, ohne dass es jemandem auffaellt. Beides sind Textaenderungen
in gewoehnlichen Dateien - deshalb wird beides maschinell geprueft.

Geprueft wird in fuenf Gruppen:

  STRUKTUR      der oeffentliche Scope und die Arbeitsmaschine existieren
  PRAEZEDENZ    CLAUDE.md/AGENTS.md leiten sich aus PROJECT_SCOPE.md ab
  LEGACY        aktive Texte behaupten keine frueheren Geschaefts-, Reader-,
                Register-, Treuhaender- oder Selbstwache-Erzaehlung als
                Anforderung (Treffer nur mit Superseded-Kontext zulaessig)
  OFFENHEIT     keine proprietaere EvidenzPass-Kopplung in Spezifikation,
                Werkzeugen und Beispielen; keine private Projektquelle und
                keine Preisangabe im oeffentlichen Anweisungstext
  SCOPE         der Diff seit base_sha bleibt in allowed_paths und beruehrt
                keinen forbidden_path (nur mit Git-Kontext)

Verwendung:
    python3 scripts/project/check_instructions.py
    python3 scripts/project/check_instructions.py --json
    python3 scripts/project/check_instructions.py --root PFAD --skip-git

Exit-Codes:
  0 = alle Pruefungen bestanden
  1 = mindestens ein Befund
  2 = Aufruf-/Umgebungsfehler
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# --- Erwartungen ------------------------------------------------------------

PFLICHTDATEIEN = [
    "PROJECT_SCOPE.md",
    "PROJECT_RULES.md",
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    "README.en.md",
    "Makefile",
    "scripts/project/block.json",
    "scripts/project/preflight.sh",
    "scripts/project/verify.sh",
    "scripts/project/handoff.py",
    "scripts/project/check_instructions.py",
    "docs/handoffs/README.md",
]

# Aktive Anweisungstexte dieses Repositories. CONTRIBUTING.md und SECURITY.md
# liegen ausserhalb der allowed_paths des aktiven Blocks und werden deshalb
# nicht geprueft; sie sind als offener Punkt an die Projektleitung gemeldet.
AKTIVE_TEXTE = [
    "PROJECT_SCOPE.md",
    "PROJECT_RULES.md",
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    "README.en.md",
]
AKTIVE_TEXT_GLOBS = ["docs/**/*.md"]

LEGACY_MUSTER = [
    (r"\bSelbstwache\w*", "Selbstwache-Erzaehlung"),
    (r"\bTreuh(?:ä|ae)nder\w*", "Treuhaender-Modell"),
    (r"\bfiduciary\b", "Treuhaender-Modell"),
    (r"\bReader\b", "Reader als Produkt"),
    (r"\bSiegel\w*", "Siegel-/Zeichenverkauf"),
    (r"\bGate[ -]?\d\b", "Gate-Regime"),
    (r"Register\s+als\s+(?:Schaufenster|Geschäftsmodell|Geschaeftsmodell)", "Registergeschaeft"),
]

MARKER_MUSTER = [
    r"superseded?",
    r"historisch",
    r"[Hh]istorie",
    r"nicht mehr",
    r"fr(?:ü|ue)her",
    r"ehemalig",
    r"veraltet",
    r"[Ll]egacy",
    r"abgel(?:ö|oe)st",
    r"(?:ü|ue)berholt",
    r"nicht autoritativ",
    r"keine (?:Produktanforderung|normative Vorgabe|Standardentscheidung)",
    r"nicht als (?:Anforderung|Anweisung|Vorgabe)",
    r"d(?:ü|ue)rfen (?:nicht|keine)",
    r"darf (?:nicht|kein)",
    r"keine neue Standardentscheidung",
]

# Reichweite des Superseded-Kontexts: der Absatz selbst - und der Absatz davor,
# wenn er mit einem Doppelpunkt in eine Aufzaehlung fuehrt ("Nicht mehr als
# Hauptnavigation:" gefolgt von den abgeloesten Punkten).
#
# Ein festes Zeilenfenster waere hier falsch: Es wuerde einen neuen Absatz
# mitmarkieren, nur weil weiter oben zufaellig "superseded" stand - und genau
# so wandert eine Altbehauptung unbemerkt zurueck in einen aktiven Text.

# Der offene Standard muss ohne die kommerzielle Anwendung implementierbar
# bleiben. Diese Verzeichnisse tragen die normative Substanz.
NORMATIVE_VERZEICHNISSE = ["spec", "werkzeuge", "beispiele", "profile"]
KOPPLUNGS_MUSTER = [
    (r"(?i)evidenzpass", "proprietaerer Produktname im offenen Standard"),
    (r"(?i)powered\s+by\s+datenfluss", "Pflicht-Branding im offenen Standard"),
]

# Private Projektquellen und Preise gehoeren nicht in ein oeffentliches Repo.
PRIVAT_MUSTER = [
    (r"EVIDENZPASS\.md", "Verweis auf eine private Projektquelle"),
    (r"SECURITY_BOUNDARIES\.md", "Verweis auf eine private Projektquelle"),
    (r"THIRD_PARTY_REGISTER\.md", "Verweis auf eine private Projektquelle"),
    (r"PROJECT_STATE\.md", "Verweis auf eine private Projektquelle"),
    (r"\bCHF\s*\d", "Preisangabe gehoert nicht in den offenen Standard"),
]

SECRET_MUSTER = [
    r"sk_live_[0-9A-Za-z]+",
    r"whsec_[0-9A-Za-z]+",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?i)\bEXOSCALE_API_SECRET\s*[:=]\s*\S+",
]

BLOCK_PFLICHTFELDER = [
    "id",
    "title",
    "status",
    "repository",
    "branch",
    "base_sha",
    "goal",
    "canonical_sources",
    "allowed_paths",
    "forbidden_paths",
    "acceptance_commands",
    "done_when",
]
BLOCK_STATUS = {"PLANNED", "IN_PROGRESS", "DONE", "BLOCKED", "ARCHIVED"}


# --- Werkzeuge --------------------------------------------------------------


class Befunde:
    def __init__(self) -> None:
        self.eintraege: list[dict] = []

    def melden(self, gruppe: str, ort: str, text: str) -> None:
        self.eintraege.append({"gruppe": gruppe, "ort": ort, "befund": text})

    def __bool__(self) -> bool:
        return bool(self.eintraege)


def lies(root: Path, rel: str) -> str | None:
    pfad = root / rel
    if not pfad.is_file():
        return None
    return pfad.read_text(encoding="utf-8", errors="replace")


def git(root: Path, *args: str) -> tuple[int, str]:
    fertig = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True
    )
    return fertig.returncode, fertig.stdout + fertig.stderr


# --- Pruefungen -------------------------------------------------------------


def pruefe_struktur(root: Path, b: Befunde) -> None:
    for rel in PFLICHTDATEIEN:
        if not (root / rel).exists():
            b.melden("STRUKTUR", rel, "Pflichtdatei fehlt")


def pruefe_praezedenz(root: Path, b: Befunde) -> None:
    """PROJECT_SCOPE.md bestimmt die Zielrichtung - auch in der Reihenfolge."""
    for datei in ("CLAUDE.md", "AGENTS.md"):
        text = lies(root, datei)
        if text is None:
            b.melden("PRAEZEDENZ", datei, "Datei fehlt")
            continue
        scope = text.find("PROJECT_SCOPE.md")
        regeln = text.find("PROJECT_RULES.md")
        order = text.find("Work Order")
        if scope < 0:
            b.melden("PRAEZEDENZ", datei, "PROJECT_SCOPE.md wird nicht genannt")
            continue
        if regeln < 0:
            b.melden("PRAEZEDENZ", datei, "PROJECT_RULES.md wird nicht genannt")
        elif regeln < scope:
            b.melden(
                "PRAEZEDENZ", datei, "PROJECT_RULES.md steht vor PROJECT_SCOPE.md"
            )
        if order < 0:
            b.melden("PRAEZEDENZ", datei, "aktiver Work Order wird nicht als Quelle genannt")
        elif order < scope:
            b.melden("PRAEZEDENZ", datei, "Work Order steht vor PROJECT_SCOPE.md")

    scope_text = lies(root, "PROJECT_SCOPE.md")
    if scope_text is None:
        b.melden("PRAEZEDENZ", "PROJECT_SCOPE.md", "Datei fehlt")
        return
    for pflicht, hinweis in (
        (r"offene[rn]?\s+modulare[rn]?\s+Standard", "Zielbild 'offener modularer Standard'"),
        (r"\.well-known/datenfluss\.json", "stabiler Einstiegspunkt"),
        (r"supplier_declaration", "Herkunftsklassen"),
    ):
        if not re.search(pflicht, scope_text):
            b.melden("PRAEZEDENZ", "PROJECT_SCOPE.md", f"{hinweis} fehlt")

    regeln_text = lies(root, "PROJECT_RULES.md")
    if regeln_text is None:
        b.melden("PRAEZEDENZ", "PROJECT_RULES.md", "Datei fehlt")
    else:
        scope_pos = regeln_text.find("PROJECT_SCOPE.md")
        if scope_pos < 0:
            b.melden("PRAEZEDENZ", "PROJECT_RULES.md", "PROJECT_SCOPE.md wird nicht genannt")


def aktive_textdateien(root: Path) -> list[str]:
    dateien = [rel for rel in AKTIVE_TEXTE if (root / rel).is_file()]
    for muster in AKTIVE_TEXT_GLOBS:
        for pfad in sorted(root.glob(muster)):
            rel = pfad.relative_to(root).as_posix()
            if rel not in dateien:
                dateien.append(rel)
    return dateien


def absatz_grenzen(zeilen: list[str], index: int) -> tuple[int, int]:
    """Anfang und Ende des Absatzes, in dem die Zeile steht."""
    anfang = index
    while anfang > 0 and zeilen[anfang - 1].strip():
        anfang -= 1
    ende = index
    while ende + 1 < len(zeilen) and zeilen[ende + 1].strip():
        ende += 1
    return anfang, ende + 1


def enthaelt_marker(zeilen: list[str]) -> bool:
    text = "\n".join(zeilen)
    return any(re.search(m, text, re.IGNORECASE) for m in MARKER_MUSTER)


def hat_marker(zeilen: list[str], index: int, absatzweise: bool = True) -> bool:
    # In JSON gibt es keine Absaetze: Die ganze Datei waere ein Block, und ein
    # beliebiges "Legacy" in einem anderen Feld wuerde jede Altbehauptung
    # decken. Dort zaehlt deshalb nur die Zeile selbst.
    if not absatzweise:
        return enthaelt_marker([zeilen[index]])

    anfang, ende = absatz_grenzen(zeilen, index)
    if enthaelt_marker(zeilen[anfang:ende]):
        return True

    # Einleitender Absatz mit Doppelpunkt: Er markiert die folgende Aufzaehlung.
    vor_ende = anfang
    while vor_ende > 0 and not zeilen[vor_ende - 1].strip():
        vor_ende -= 1
    if vor_ende == 0:
        return False
    vor_anfang, _ = absatz_grenzen(zeilen, vor_ende - 1)
    einleitung = zeilen[vor_anfang:vor_ende]
    if einleitung and einleitung[-1].rstrip().endswith(":"):
        return enthaelt_marker(einleitung)
    return False


def pruefe_legacy(root: Path, b: Befunde) -> None:
    for rel in aktive_textdateien(root):
        text = lies(root, rel)
        if text is None:
            continue
        zeilen = text.splitlines()
        absatzweise = not rel.endswith(".json")
        for i, zeile in enumerate(zeilen):
            for muster, bedeutung in LEGACY_MUSTER:
                treffer = re.search(muster, zeile)
                if not treffer:
                    continue
                if hat_marker(zeilen, i, absatzweise):
                    continue
                b.melden(
                    "LEGACY",
                    f"{rel}:{i + 1}",
                    f"{bedeutung}: '{treffer.group(0)}' ohne Superseded-Kontext",
                )


def pruefe_offenheit(root: Path, b: Befunde) -> None:
    """Dritte muessen den Standard ohne die kommerzielle Anwendung umsetzen."""
    for verzeichnis in NORMATIVE_VERZEICHNISSE:
        wurzel = root / verzeichnis
        if not wurzel.is_dir():
            continue
        for pfad in sorted(wurzel.rglob("*")):
            if not pfad.is_file() or pfad.suffix.lower() not in (
                ".json", ".py", ".md", ".html", ".txt", ".yml", ".yaml"
            ):
                continue
            rel = pfad.relative_to(root).as_posix()
            text = pfad.read_text(encoding="utf-8", errors="replace")
            for muster, bedeutung in KOPPLUNGS_MUSTER:
                treffer = re.search(muster, text)
                if treffer:
                    b.melden("OFFENHEIT", rel, f"{bedeutung}: '{treffer.group(0)}'")

    for rel in aktive_textdateien(root):
        text = lies(root, rel) or ""
        for i, zeile in enumerate(text.splitlines()):
            for muster, bedeutung in PRIVAT_MUSTER:
                treffer = re.search(muster, zeile)
                if treffer:
                    b.melden("OFFENHEIT", f"{rel}:{i + 1}", f"{bedeutung}: '{treffer.group(0)}'")
        for muster in SECRET_MUSTER:
            if re.search(muster, text):
                b.melden("OFFENHEIT", rel, "sieht aus wie ein Secret im Klartext")
                break


def lade_block(root: Path, b: Befunde) -> dict | None:
    pfad = root / "scripts" / "project" / "block.json"
    if not pfad.is_file():
        b.melden("SCOPE", "scripts/project/block.json", "Blockangabe fehlt")
        return None
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
    except json.JSONDecodeError as fehler:
        b.melden("SCOPE", "scripts/project/block.json", f"nicht maschinenlesbar: {fehler}")
        return None
    for feld in BLOCK_PFLICHTFELDER:
        if feld not in daten:
            b.melden("SCOPE", "scripts/project/block.json", f"Pflichtfeld fehlt: {feld}")
    if daten.get("status") not in BLOCK_STATUS:
        b.melden(
            "SCOPE",
            "scripts/project/block.json",
            f"unzulaessiger Status: {daten.get('status')!r}",
        )
    return daten


def pfad_passt(pfad: str, muster: list[str]) -> bool:
    for m in muster:
        if m.endswith("/**"):
            if pfad.startswith(m[:-2]):
                return True
        elif pfad == m:
            return True
    return False


def pruefe_scope(root: Path, block: dict | None, b: Befunde) -> dict:
    zusammenfassung: dict = {"base_sha": None, "head_sha": None, "changed_files": []}
    if block is None or "base_sha" not in block:
        return zusammenfassung

    base = block["base_sha"]
    code, head = git(root, "rev-parse", "HEAD")
    head = head.strip()
    if code != 0:
        b.melden("SCOPE", ".", f"HEAD nicht lesbar: {head}")
        return zusammenfassung
    zusammenfassung["base_sha"] = base
    zusammenfassung["head_sha"] = head

    code, _ = git(root, "merge-base", "--is-ancestor", base, "HEAD")
    if code != 0:
        b.melden(
            "SCOPE",
            ".",
            f"base_sha {base[:12]} ist kein Vorfahr von HEAD; unerwartete Arbeitsbasis",
        )
        return zusammenfassung

    code, ausgabe = git(root, "diff", "--name-only", "--no-renames", base, "HEAD")
    if code != 0:
        b.melden("SCOPE", ".", f"Diff nicht lesbar: {ausgabe.strip()}")
        return zusammenfassung
    geaendert = [z for z in ausgabe.splitlines() if z.strip()]

    code, ausgabe = git(root, "status", "--porcelain", "--no-renames", "-uall")
    if code == 0:
        for zeile in ausgabe.splitlines():
            if len(zeile) < 4:
                continue
            pfad = zeile[3:].strip().strip('"')
            if pfad and pfad not in geaendert:
                geaendert.append(pfad)

    zusammenfassung["changed_files"] = sorted(geaendert)
    erlaubt = block.get("allowed_paths", [])
    verboten = block.get("forbidden_paths", [])
    for pfad in zusammenfassung["changed_files"]:
        if pfad_passt(pfad, verboten):
            b.melden("SCOPE", pfad, "Datei liegt in forbidden_paths des Blocks")
        elif not pfad_passt(pfad, erlaubt):
            b.melden("SCOPE", pfad, "Datei liegt ausserhalb der allowed_paths des Blocks")
    return zusammenfassung


# --- Einstieg ---------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--skip-git", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"FEHLER: {root} ist kein Verzeichnis", file=sys.stderr)
        return 2

    b = Befunde()
    pruefe_struktur(root, b)
    pruefe_praezedenz(root, b)
    pruefe_legacy(root, b)
    pruefe_offenheit(root, b)
    block = lade_block(root, b)
    scope: dict = {"base_sha": None, "head_sha": None, "changed_files": []}
    if not args.skip_git:
        scope = pruefe_scope(root, block, b)

    ergebnis = {
        "check": "instructions",
        "root": str(root),
        "block": (block or {}).get("id"),
        "base_sha": scope.get("base_sha"),
        "head_sha": scope.get("head_sha"),
        "changed_files": scope.get("changed_files", []),
        "findings": b.eintraege,
        "result": "FAIL" if b else "PASS",
    }

    if args.json:
        print(json.dumps(ergebnis, ensure_ascii=False, indent=2))
    else:
        for eintrag in b.eintraege:
            print(f"[{eintrag['gruppe']}] {eintrag['ort']}: {eintrag['befund']}")
        print(
            f"\ncheck_instructions: FAIL ({len(b.eintraege)} Befunde)"
            if b
            else "check_instructions: PASS"
        )
    return 1 if b else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

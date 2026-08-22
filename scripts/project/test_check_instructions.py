#!/usr/bin/env python3
"""Negativtests fuer den Anweisungs-Waechter des offenen Standards.

Derselbe Grundsatz wie bei der Konformitaets-Testsuite: Ein Werkzeug, das nur
im Gutfall geprueft wird, ist kein Beweis. Jede Regel dieses Waechters wird
deshalb einmal absichtlich gebrochen; bleibt der Waechter dabei gruen, ist die
Regel blind.

Verwendung:
    python3 scripts/project/test_check_instructions.py

Exit-Code: 0 = alle Faelle bestanden, 1 = mindestens ein Fall gescheitert.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[2]
WAECHTER = WURZEL / "scripts" / "project" / "check_instructions.py"

FIXTURE_DATEIEN = [
    "PROJECT_SCOPE.md",
    "PROJECT_RULES.md",
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    "README.en.md",
    "Makefile",
]
FIXTURE_VERZEICHNISSE = ["docs", "scripts/project", "spec", "beispiele"]


def waechter(root: Path, *extra: str) -> tuple[int, str]:
    fertig = subprocess.run(
        [sys.executable, str(WAECHTER), "--root", str(root), "--json", *extra],
        capture_output=True,
        text=True,
    )
    return fertig.returncode, fertig.stdout


def gruppen(ausgabe: str) -> set[str]:
    try:
        daten = json.loads(ausgabe)
    except json.JSONDecodeError:
        return set()
    return {f["gruppe"] for f in daten.get("findings", [])}


def baue_fixture(ziel: Path) -> None:
    for rel in FIXTURE_DATEIEN:
        quelle = WURZEL / rel
        if quelle.is_file():
            (ziel / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(quelle, ziel / rel)
    for rel in FIXTURE_VERZEICHNISSE:
        quelle = WURZEL / rel
        if quelle.is_dir():
            shutil.copytree(quelle, ziel / rel, dirs_exist_ok=True)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True)


def git_ausgabe(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


class Lauf:
    def __init__(self) -> None:
        self.gescheitert: list[str] = []
        self.bestanden = 0

    def pruefe(self, name: str, bedingung: bool, hinweis: str = "") -> None:
        if bedingung:
            self.bestanden += 1
            print(f"  ok    {name}")
        else:
            self.gescheitert.append(f"{name}{': ' + hinweis if hinweis else ''}")
            print(f"  FEHLT {name}{': ' + hinweis if hinweis else ''}")


def fall(lauf: Lauf, name: str, mutation, erwartete_gruppe: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ziel = Path(tmp) / "repo"
        ziel.mkdir()
        baue_fixture(ziel)
        mutation(ziel)
        code, ausgabe = waechter(ziel, "--skip-git")
        gefunden = gruppen(ausgabe)
        lauf.pruefe(
            name,
            code == 1 and erwartete_gruppe in gefunden,
            f"exit={code}, Gruppen={sorted(gefunden) or 'keine'}",
        )


# --- Mutationen -------------------------------------------------------------


def m_legacy_satz(root: Path) -> None:
    pfad = root / "README.md"
    pfad.write_text(
        pfad.read_text(encoding="utf-8")
        + "\n## Geschaeft\n\nDas Siegel wird von Treuhaendern verkauft.\n",
        encoding="utf-8",
    )


def m_legacy_in_anweisung(root: Path) -> None:
    pfad = root / "AGENTS.md"
    pfad.write_text(
        pfad.read_text(encoding="utf-8") + "\nDer Reader ist die Leitanwendung.\n",
        encoding="utf-8",
    )


def m_praezedenz_verdreht(root: Path) -> None:
    pfad = root / "CLAUDE.md"
    text = pfad.read_text(encoding="utf-8")
    text = text.replace("1. `PROJECT_SCOPE.md`\n", "", 1)
    text = text.replace(
        "4. betroffene Spezifikation und Konformitätstests",
        "4. betroffene Spezifikation und Konformitätstests\n5. `PROJECT_SCOPE.md`",
        1,
    )
    pfad.write_text(text, encoding="utf-8")


def m_zielbild_entfernt(root: Path) -> None:
    pfad = root / "PROJECT_SCOPE.md"
    text = pfad.read_text(encoding="utf-8")
    pfad.write_text(text.replace("supplier_declaration", "lieferantenaussage"), encoding="utf-8")


def m_proprietaere_kopplung(root: Path) -> None:
    pfad = root / "spec" / "v0.1" / "datenfluss.schema.json"
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    daten["x_evidenzpass_pflichtfeld"] = {"type": "string"}
    pfad.write_text(json.dumps(daten, indent=2, ensure_ascii=False), encoding="utf-8")


def m_kopplung_im_beispiel(root: Path) -> None:
    pfad = root / "beispiele" / "beispiel-deklaration.json"
    text = pfad.read_text(encoding="utf-8")
    pfad.write_text(text.replace("{", '{\n  "erzeugt_von": "EvidenzPass",', 1), encoding="utf-8")


def m_private_quelle(root: Path) -> None:
    pfad = root / "PROJECT_RULES.md"
    pfad.write_text(
        pfad.read_text(encoding="utf-8") + "\nMassgeblich ist ausserdem `EVIDENZPASS.md`.\n",
        encoding="utf-8",
    )


def m_preis_im_standard(root: Path) -> None:
    pfad = root / "README.md"
    pfad.write_text(
        pfad.read_text(encoding="utf-8") + "\nDie Validierung kostet CHF 390 pro Monat.\n",
        encoding="utf-8",
    )


def m_block_feld_fehlt(root: Path) -> None:
    pfad = root / "scripts" / "project" / "block.json"
    daten = json.loads(pfad.read_text(encoding="utf-8"))
    daten.pop("forbidden_paths", None)
    pfad.write_text(json.dumps(daten, indent=2, ensure_ascii=False), encoding="utf-8")


def m_pflichtdatei_fehlt(root: Path) -> None:
    (root / "scripts" / "project" / "handoff.py").unlink()


# --- Git-gestuetzter Scope-Test --------------------------------------------


def scope_test(lauf: Lauf) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        ziel = Path(tmp) / "repo"
        ziel.mkdir()
        baue_fixture(ziel)
        git(ziel, "init", "-q", "-b", "work/W000-foundation")
        git(ziel, "config", "user.email", "test@example.invalid")
        git(ziel, "config", "user.name", "Waechtertest")
        git(ziel, "add", "-A")
        git(ziel, "commit", "-q", "-m", "Basis")
        basis = git_ausgabe(ziel, "rev-parse", "HEAD")

        pfad = ziel / "scripts" / "project" / "block.json"
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        daten["base_sha"] = basis
        pfad.write_text(json.dumps(daten, indent=2, ensure_ascii=False), encoding="utf-8")
        git(ziel, "add", "-A")
        git(ziel, "commit", "-q", "-m", "Block auf lokale Basis")

        code, ausgabe = waechter(ziel)
        lauf.pruefe(
            "Scope: sauberer Baum bleibt gruen",
            code == 0,
            f"exit={code}, Gruppen={sorted(gruppen(ausgabe)) or 'keine'}",
        )

        schema = ziel / "spec" / "v0.1" / "datenfluss.schema.json"
        schema.write_text(
            schema.read_text(encoding="utf-8").replace("\n", "\n", 1) + "\n", encoding="utf-8"
        )
        git(ziel, "add", "-A")
        git(ziel, "commit", "-q", "-m", "Griff in spec/")
        code, ausgabe = waechter(ziel)
        lauf.pruefe(
            "Scope: Aenderung in forbidden_paths wird erkannt",
            code == 1 and "SCOPE" in gruppen(ausgabe),
            f"exit={code}, Gruppen={sorted(gruppen(ausgabe)) or 'keine'}",
        )


def main() -> int:
    lauf = Lauf()

    print("Positiv:")
    with tempfile.TemporaryDirectory() as tmp:
        ziel = Path(tmp) / "repo"
        ziel.mkdir()
        baue_fixture(ziel)
        code, ausgabe = waechter(ziel, "--skip-git")
        lauf.pruefe(
            "unveraenderter Anweisungsbaum besteht",
            code == 0,
            f"exit={code}, Gruppen={sorted(gruppen(ausgabe)) or 'keine'}",
        )

    print("Negativ - Legacy-Rueckfall:")
    fall(lauf, "Siegel/Treuhaender als Geschaeft in README", m_legacy_satz, "LEGACY")
    fall(lauf, "Reader als Leitanwendung in AGENTS.md", m_legacy_in_anweisung, "LEGACY")

    print("Negativ - Praezedenz:")
    fall(lauf, "PROJECT_SCOPE.md nicht mehr an erster Stelle", m_praezedenz_verdreht, "PRAEZEDENZ")
    fall(lauf, "Herkunftsklassen aus dem Scope entfernt", m_zielbild_entfernt, "PRAEZEDENZ")

    print("Negativ - Offenheit:")
    fall(lauf, "proprietaeres Pflichtfeld im Schema", m_proprietaere_kopplung, "OFFENHEIT")
    fall(lauf, "Produktname im Referenzbeispiel", m_kopplung_im_beispiel, "OFFENHEIT")
    fall(lauf, "Verweis auf eine private Projektquelle", m_private_quelle, "OFFENHEIT")
    fall(lauf, "Preisangabe im offenen Standard", m_preis_im_standard, "OFFENHEIT")

    print("Negativ - Block und Struktur:")
    fall(lauf, "Pflichtfeld forbidden_paths fehlt", m_block_feld_fehlt, "SCOPE")
    fall(lauf, "Pflichtskript der Arbeitsmaschine fehlt", m_pflichtdatei_fehlt, "STRUKTUR")

    print("Git-gestuetzt - Scope:")
    scope_test(lauf)

    print()
    if lauf.gescheitert:
        print(
            f"test_check_instructions: FAIL ({len(lauf.gescheitert)} von "
            f"{len(lauf.gescheitert) + lauf.bestanden} Faellen)"
        )
        for eintrag in lauf.gescheitert:
            print(f"  - {eintrag}")
        return 1
    print(f"test_check_instructions: PASS ({lauf.bestanden} Faelle)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

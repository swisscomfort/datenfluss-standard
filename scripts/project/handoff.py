#!/usr/bin/env python3
"""Erzeugt die maschinenlesbare Uebergabe eines Arbeitsblocks.

Ein Handoff behauptet etwas ueber einen bestimmten Stand. Damit die Behauptung
pruefbar ist, muss sie an einen committeten HEAD gebunden sein - aus einem
schmutzigen Arbeitsbaum beschreibt sie einen Stand, den niemand mehr
herstellen kann. Deshalb bricht dieses Skript ab, statt eine unpruefbare
Uebergabe zu schreiben, und fuehrt preflight und verify fuer genau diesen
HEAD selbst aus.

Ein Handoff ist keine Abnahme. Kein ausfuehrender Agent gibt seine eigene
Arbeit final frei; der Blockabschluss wird zentral gefuehrt.

Ablageort ist `docs/handoffs/`. Das ist Absicht: Der Block erlaubt Aenderungen
unter `docs/**`, und eine Uebergabe soll im Repository liegen, das sie
beschreibt.

Verwendung:
    python3 scripts/project/handoff.py
    python3 scripts/project/handoff.py --open-question "Text"

Exit-Codes:
  0 = Handoff geschrieben
  1 = Vorbedingung verletzt oder verify rot
  2 = Aufruf-/Umgebungsfehler
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def git(root: Path, *args: str) -> tuple[int, str]:
    fertig = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return fertig.returncode, fertig.stdout.strip()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--open-question", action="append", default=[])
    parser.add_argument("--known-failure", action="append", default=[])
    parser.add_argument("--tool", default="UNBEKANNT")
    parser.add_argument("--model", default="UNBEKANNT")
    parser.add_argument("--effort", default="UNBEKANNT")
    parser.add_argument("--permission-mode", default="UNBEKANNT")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not (root / ".git").exists():
        print(f"FEHLER: {root} ist kein Git-Repository", file=sys.stderr)
        return 2

    block_pfad = root / "scripts" / "project" / "block.json"
    if not block_pfad.is_file():
        print("FEHLER: scripts/project/block.json fehlt", file=sys.stderr)
        return 2
    block = json.loads(block_pfad.read_text(encoding="utf-8"))

    code, branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if code != 0:
        print("FEHLER: Branch nicht lesbar", file=sys.stderr)
        return 2
    if branch != block.get("branch"):
        print(
            f"FEHLER: Branch {branch} entspricht nicht dem Block ({block.get('branch')})",
            file=sys.stderr,
        )
        return 1

    _, dreck = git(root, "status", "--porcelain")
    if dreck:
        print("FEHLER: Arbeitsbaum ist nicht sauber. Ein Handoff aus einem", file=sys.stderr)
        print("nicht committeten Stand ist ungueltig:", file=sys.stderr)
        for zeile in dreck.splitlines():
            print(f"  {zeile}", file=sys.stderr)
        return 1

    _, head = git(root, "rev-parse", "HEAD")
    base = block["base_sha"]
    code, _ = git(root, "merge-base", "--is-ancestor", base, "HEAD")
    if code != 0:
        print(f"FEHLER: base_sha {base[:12]} ist kein Vorfahr von HEAD", file=sys.stderr)
        return 1

    befehle = [
        ("make preflight", [str(root / "scripts" / "project" / "preflight.sh")]),
        ("make verify", [str(root / "scripts" / "project" / "verify.sh")]),
    ]
    ergebnisse = {}
    for name, kommando in befehle:
        print(f"→ {name}")
        fertig = subprocess.run(kommando, cwd=root)
        ergebnisse[name] = "PASS" if fertig.returncode == 0 else "FAIL"

    if ergebnisse.get("make verify") != "PASS":
        print("\nFEHLER: make verify ist rot. Es wird kein Handoff geschrieben.", file=sys.stderr)
        return 1

    _, diff = git(root, "diff", "--name-only", "--no-renames", base, "HEAD")
    changed = sorted(z for z in diff.splitlines() if z.strip())

    _, commits = git(root, "log", "--format=%H %s", f"{base}..HEAD")
    commit_liste = [
        {"sha": z.split(" ", 1)[0], "subject": z.split(" ", 1)[1] if " " in z else ""}
        for z in commits.splitlines()
        if z.strip()
    ]

    handoff = {
        "work_order": block.get("id"),
        "repository": block.get("repository"),
        "base_sha": base,
        "head_sha": head,
        "branch": branch,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "execution": {
            "tool": args.tool,
            "model": args.model,
            "effort": args.effort,
            "permission_mode": args.permission_mode,
        },
        "changed_files": changed,
        "commits": commit_liste,
        "commands_run": [name for name, _ in befehle],
        "results": ergebnisse,
        "known_failures": args.known_failure,
        "open_questions": args.open_question,
        "approval": "OFFEN — ein Handoff ist keine Abnahme",
        "next_step": "unabhaengige Gegenpruefung durch eine andere Instanz",
    }

    ziel_verzeichnis = root / "docs" / "handoffs"
    ziel_verzeichnis.mkdir(parents=True, exist_ok=True)
    ziel = ziel_verzeichnis / f"{block.get('id')}-{head[:12]}.json"
    ziel.write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print()
    print(json.dumps({
        "command": "handoff",
        "block": block.get("id"),
        "head_sha": head,
        "handoff": ziel.relative_to(root).as_posix(),
        "result": "PASS",
    }, ensure_ascii=False))
    print(f"handoff: {ziel.relative_to(root).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

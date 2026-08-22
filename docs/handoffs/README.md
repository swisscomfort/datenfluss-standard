# docs/handoffs

Maschinenlesbare Uebergaben, erzeugt von `make handoff`.

Eine Uebergabe beschreibt genau einen **committeten** Stand:

```text
work_order
repository
base_sha
head_sha
branch
changed_files
commands_run
results
known_failures
open_questions
```

Bedingungen: sauberer Arbeitsbaum, committeter `head_sha`, Branch entspricht
dem aktiven Block, `make verify` fuer genau diesen Stand erfolgreich, keine
Secrets und keine Kundendaten im Inhalt.

**Eine Uebergabe ist keine Abnahme.** Die Freigabe eines Blocks wird zentral
gefuehrt; kein ausfuehrender Agent gibt seine eigene Arbeit final frei.

Dateiname: `<BLOCK>-<head_sha[:12]>.json`.

Hinweis zur Reihenfolge: Die Uebergabe entsteht fuer den zu diesem Zeitpunkt
committeten HEAD; der Commit, der die Datei selbst versioniert, folgt danach.
Der attestierte Stand ist deshalb der Elternteil des Handoff-Commits.

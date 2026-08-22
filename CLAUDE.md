# CLAUDE.md

Vor jeder Änderung lesen:

1. `PROJECT_SCOPE.md`
2. `PROJECT_RULES.md`
3. aktiven Work Order
4. betroffene Spezifikation und Konformitätstests

Regeln:

- `PROJECT_SCOPE.md` bestimmt die Zielrichtung.
- Technische Tatsachen nur aus Code/Tests ableiten.
- Alte Reader-/Register-/Treuhänder-/Selbstwache-Texte sind keine Produktanforderung.
- Genau einen Work Order bearbeiten.
- Keine proprietäre EvidenzPass-Abhängigkeit in den offenen Standard einbauen.
- Keine bestehende Spezifikationsversion still inkompatibel ändern.
- Neue normative Regeln mit Tests absichern.
- Keine Secrets/Kundendaten.
- Keine destruktiven Git-Befehle.
- Längere Abläufe als Skript/Make-Target.
- Nach Implementierung `make verify` und `make handoff`, sobald W000 diese Targets bereitstellt.
- Claude Code implementiert, entscheidet aber nicht über die finale Abnahme.

# PROJECT_RULES — Datenfluss-Standard

**Status:** verbindlich

## Quellenhierarchie

1. `PROJECT_SCOPE.md` — öffentliche Zielrichtung des Standards.
2. ausgeführter Code und Tests — technische Tatsachen.
3. aktuelle Spezifikation und Konformitätstests — normative Version der jeweils implementierten Standardgeneration.
4. aktuelle Work Orders / ADRs.
5. übrige Texte — nicht autoritativ.

Frühere Geschäfts-, Reader-, Register-, Treuhänder- und Selbstwache-Erzählungen dürfen keine neue Standardentscheidung begründen.

## Arbeitsregeln

- genau ein aktiver Work Order,
- Branch `work/Wxxx-*`, kein direkter Produktbau auf `main`,
- keine Force-Pushes/destruktiven Git-Befehle,
- keine neuen Repositories,
- keine proprietären EvidenzPass-Pflichtfelder im offenen Standard,
- neue Schema-/Semantikregeln erhalten Konformitätstests,
- kritische Regeln möglichst mit Negativ-/Mutationstest,
- keine stille inkompatible Änderung an einer veröffentlichten Spezifikationsversion,
- längere Abläufe als Skript/Make-Target,
- lokale und CI-Prüfung über denselben `make verify`-Pfad, sobald W000 dies bereitstellt,
- keine Secrets oder Kundendaten in diesem öffentlichen Repository.

## v0.1

Der bestehende v0.1-Code ist eine reale implementierte Datenschutz-Spezifikation und bleibt historisch nachvollziehbar. Er ist nicht die fachliche Grenze der neuen modularen Zielgeneration.

## Rolle der Agenten

Claude Code implementiert. Codex prüft unabhängig. Kein ausführender Agent gibt seine eigene Arbeit final frei.

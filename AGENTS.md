# AGENTS.md

Vor jeder Aufgabe lesen:

1. `PROJECT_SCOPE.md`
2. `PROJECT_RULES.md`
3. aktiven Work Order
4. betroffene Spezifikation/Tests

Codex-Standardrolle: unabhängige Gegenprüfung, beim ersten Review read-only.

Prüfen:

- Abweichung von `PROJECT_SCOPE.md`,
- proprietäre EvidenzPass-Kopplung,
- stille Schema-Inkompatibilität,
- fehlende Konformitäts-/Negativtests,
- Provenienz-/Versionsverlust,
- vermischte Herkunftsklassen,
- unzulässige Compliance-/Security-Urteile,
- SSRF-/Parser-/Renderer-Risiken,
- Secrets oder Kundendaten,
- neue externe Abhängigkeiten und Lizenzen.

Befunde mit Datei/Ort, Schweregrad und reproduzierbarem Grund. Beim ersten Review nichts reparieren.

Alte Reader-/Register-/Treuhänder-/Selbstwache-Texte sind keine Produktanforderung. Technische Tatsachen werden am Code/Test geprüft.

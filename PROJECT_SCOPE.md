# Datenfluss — öffentlicher Projektscope

**Status:** verbindlicher öffentlicher Zielscope

**Gültig ab:** 22. August 2026

Datenfluss entwickelt sich vom bisherigen Datenschutz-Deklarationsprototyp zu einem **offenen modularen Standard für B2B-Evidenz**.

Das bestehende v0.1-Datenschutzschema, der Validator, Scanner und weitere Werkzeuge sind technische Ausgangsassets. Ihre vorhandene Implementierung ist real; frühere Geschäfts-, Reader-, Register-, Treuhänder- oder Selbstwache-Erzählungen sind jedoch **keine normative Vorgabe für die Weiterentwicklung des Standards**.

---

## 1. Ziel

Eine Organisation soll Evidenz über sich selbst in einem offenen, maschinenlesbaren, versionierten und quellengebundenen Format veröffentlichen können.

Die kanonische öffentliche Quelle liegt auf der Domain der Organisation.

Der Standard muss ohne einen bestimmten SaaS-Anbieter implementierbar sein.

---

## 2. Stabiler Einstiegspunkt

```text
https://organisation.example/.well-known/datenfluss.json
```

Die nächste Standardgeneration verwendet diesen Pfad als Manifest für unabhängig versionierbare Evidenzmodule.

---

## 3. Evidence Core

Der offene Standard definiert mindestens:

- Manifest,
- Claim-Modell,
- Source-Modell,
- Scope,
- Provenienz/Herkunft,
- Versionierung,
- Integrität/Hashes,
- Sichtbarkeit öffentlicher Claims,
- Modulversionen,
- Konformitätstests.

Normative maschinelle Feldnamen sind englisch.

---

## 4. Herkunftsklassen

Die Zielsemantik unterscheidet mindestens:

```text
supplier_declaration
public_measurement
private_measurement
documented_evidence
internal_assessment
```

Der offene Standard darf Herkunft nicht in einem pauschalen Vertrauensscore verstecken.

Nur öffentlich freigegebene Daten gehören in die öffentliche Standardpublikation. Private Evidenz ist Sache von Anwendungen und Austauschmechanismen; der offene Standard kann Referenzen/Modelle definieren, darf aber keine vertraulichen Inhalte öffentlich erzwingen.

---

## 5. Erste Evidenzdomänen

Die erste modulare Zielgeneration umfasst:

1. `organization.identity`
2. `privacy.processing`
3. `security.certifications`
4. `security.controls`
5. `security.crypto-baseline`

Das bestehende Datenschutzmodell wird damit zu **einem Modul unter mehreren**.

`security.controls` erfindet keinen neuen universellen Control-Katalog. Claims sollen auf bestehende Frameworks referenzieren können.

---

## 6. Interoperabilität

Datenfluss soll vorhandene Standards und Frameworks verbinden, nicht kopieren.

Ein Claim kann über `framework_refs` auf externe Frameworks/Controls verweisen.

Spätere Adapter können z. B. OSCAL, CSA CCM/CAIQ, ISO-Strukturen oder andere etablierte Formate abbilden.

---

## 7. Öffentliche Messung

Messwerkzeuge können öffentliche Evidenz erzeugen.

Messclaims müssen mindestens tragen:

- beobachteten Wert,
- Zeitpunkt,
- Sensorversion,
- Methodikgrenze,
- Rohbeleg soweit sinnvoll.

Messwerkzeuge erzeugen keine pauschalen Aussagen wie „sicher“, „vertrauenswürdig“ oder „rechtskonform“.

---

## 8. Referenzwerkzeuge

Der öffentliche Standard soll weiterhin frei nutzbare Referenzwerkzeuge bereitstellen, insbesondere:

- Validator,
- Conformance Suite,
- Publisher/Generator,
- Renderer,
- Sensoren für klar definierte öffentliche Eigenschaften.

Diese Werkzeuge sind Referenzimplementierungen, keine notwendige Plattformabhängigkeit.

---

## 9. Verhältnis zu EvidenzPass

EvidenzPass ist eine kommerzielle Lieferantenanwendung, die den offenen Standard operationalisiert.

Der Standard selbst bleibt unabhängig:

- kein proprietäres Pflichtfeld für EvidenzPass,
- keine „Powered by“-Pflicht im Protokoll,
- kein Pay-to-Verify,
- keine bessere Standardkonformität durch Zahlung,
- vollständige öffentliche Implementierbarkeit durch Dritte.

Private Geschäftsstrategie, Preise und SaaS-Betriebsdetails gehören nicht in dieses öffentliche Repository.

---

## 10. Nichtziele des Standards

Datenfluss ist keine:

- Zertifizierungsstelle,
- allgemeine Rechtskonformitätsmaschine,
- Lieferantenrisikoscore-Plattform,
- proprietäre Trust-Center-Spezifikation,
- vollständige GRC-Suite,
- neue universelle Security-Control-Ontologie.

---

## 11. Versionierung und Migration

Das vorhandene v0.1 bleibt als historischer implementierter Stand nachvollziehbar.

Die neue modulare Generation wird als neue Spezifikationsversion entwickelt und erhält eigene Konformitätstests. Bestehende v0.1-Dateien werden nicht stillschweigend durch eine inkompatible Schemaänderung umgedeutet.

Migrationen müssen explizit und testbar sein.

---

## 12. Arbeitsgrundsatz

Produkt-/Geschäftsentscheidungen werden nicht aus historischen README-, Kommunikations- oder Strategiepassagen abgeleitet.

Für technische Aussagen gilt der tatsächliche Code/Teststand. Für die Zielrichtung dieses öffentlichen Repositories gilt `PROJECT_SCOPE.md`.

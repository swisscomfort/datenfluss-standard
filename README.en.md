# Datenfluss-Standard v0.1 (draft)

**An open standard for machine-readable privacy transparency. The format is jurisdiction-neutral – the reference implementation and the first legal-check profile are Swiss.**

*This is the English guide to the repository. The normative language of the specification is German ([README.md](README.md)); where the two disagree, the German text prevails. The standard's field names are German by design and identical in every language – the way `robots.txt` is English everywhere.*

Every organisation declares, in one signable JSON file, which personal data it processes, for which purposes, to which recipients it flows, and how long it is retained. The file lives on the organisation's own domain – not on any platform:

```
https://www.example-company.ch/.well-known/datenfluss.json
```

Platforms, browser extensions, fiduciary software and registers can crawl, validate and render these files. The standard belongs to no one and needs no particular vendor to work.

## What is in this package

| File | Content |
|---|---|
| `spec/v0.1/datenfluss.schema.json` | The formal specification as JSON Schema (Draft 2020-12), field descriptions in German |
| `beispiele/beispiel-deklaration.json` | Complete example declaration of the fictional **Alpenkafi GmbH** (web shop, newsletter, analytics, support) |
| `werkzeuge/validator.py` | Validates declarations formally (schema) and semantically (universal rules + one legal-check profile per jurisdiction, today: `ch`) |
| `werkzeuge/renderer.py` | Reference renderer: turns a declaration into the human-readable HTML "data-flow card" |
| `werkzeuge/scanner.py` | Scanner prototype: measures statically embedded third parties of a website and compares them with its declaration (measured ↔ declared) |
| `werkzeuge/konformitaet.py` | Conformance test suite: checks an implementation against the binding test cases |
| `spec/v0.1/konformitaet/` | The test cases themselves plus `erwartungen.json` – the reference every implementation must pass |

## Quick start

```bash
pip install jsonschema
python3 werkzeuge/validator.py beispiele/beispiel-deklaration.json
python3 werkzeuge/renderer.py beispiele/beispiel-deklaration.json   # produces datenfluss-karte.html
python3 werkzeuge/konformitaet.py                                    # 10 test cases, exit 0 = all pass
```

The renderer needs only the Python standard library and produces a fully self-contained HTML page – it loads **zero external resources**, which for a privacy-transparency tool is a feature, not a footnote.

## The validator's two separate verdicts

The validator judges the same file twice, deliberately:

1. **Standard conformance** (stable) – structure, required fields, formats, universal rules (declaration date not in the future, unique IDs, signature notice). This verdict depends only on the file: a file that is conformant today stays conformant until the file itself changes.
2. **Legal findings of a check profile** (time-dependent, `--profil`, default `ch`) – third-country transfers under Art. 16 et seq. of the Swiss FADP, the Swiss–U.S. DPF special case, DPIA notices for high-risk profiling. This verdict depends on the current legal situation and can change without a single byte of the file changing.

This separation is the core of versionability: if Switzerland removes a country from its adequacy list tomorrow, no existing declaration becomes standard-non-conformant – but the validator will surface the new legal issue. Legal logic lives exclusively in check profiles; a further jurisdiction (e.g. `eu` for the GDPR) is added as one more profile, with no change to the schema or to existing declarations.

Exit codes, CI-ready: `0` = conformant with no profile findings · `1` = standard violated · `3` = conformant, but the check profile reports problems. To react to both, test for `!= 0` as usual.

## Conformance: testing your own implementation

The standard is implemented more than once – here in Python, in the browser, tomorrow perhaps by you. Without shared test cases these implementations drift apart until one tool says "valid" and another says "invalid". That must never happen to a standard.

The files in `spec/v0.1/konformitaet/` are therefore a **binding reference**, not mere examples. The naming carries the two-verdict separation: `fehler-*` violates the standard, `profilfehler-*`/`profilwarnung-*` is standard-conformant with a legal finding in profile `ch`. `erwartungen.json` records the expected outcome per case. If your implementation passes all cases, it conforms – you never need to ask us.

One binding rule for registers built on this standard: **a website counts as declared only if its file passes the standard check.** A file that is found but not conformant is shown as exactly that – with the concrete findings as a route description, not a pillory. Without this rule, a successful JSON parse rather than the standard would decide who carries the mark, and the middle level of trust would be worthless.

## Predecessors and related standards

Machine-readable privacy statements are not a new idea – and anyone implementing them should know why the most important predecessor failed:

- **W3C P3P** (2002, officially obsolete today) let websites declare their data practices machine-readably. It failed on two fronts: almost no software consumed the statements – and once Internet Explorer used them for cookie decisions, site operators deployed generic copied policies instead of describing their actual practice. **A standardised claim alone does not create transparency.** That is exactly why this standard confronts the self-declaration with an independent measurement (measured ↔ declared) and keeps the two strictly separate: the declaration is the organisation's statement, the measurement is the outside observation, and the comparison of both is public. A copied courtesy declaration shows up in the measurement.
- **W3C DPV** (Data Privacy Vocabulary) defines a comprehensive vocabulary for purposes, recipients and legal bases. This standard deliberately does not invent its own ontology of that depth; mapping the field semantics to DPV is on the roadmap, keeping declarations internationally interoperable.
- **Apple Privacy Manifests** and **Google Play Data Safety** require structured, machine-readable privacy statements from apps and SDKs – the same shift from prose to verifiable metadata, but inside closed platforms. This standard carries the pattern to the open web, where no platform can force declarations – but anyone can independently re-measure them.

In short: the machine-readable statement is not what is new. What is new is the **public, versioned cross-check** – self-declaration and independent measurement, collected separately and machine-comparable.

## Design principles

1. **Decentralised:** the declaration lives with the organisation. Registers are interchangeable.
2. **Honesty through publicity:** a false public declaration is actionable under unfair-competition law – publicity disciplines.
3. **Extensible but strict:** unknown fields are forbidden unless prefixed `x_` (controlled innovation).
4. **Jurisdiction-neutral format, Swiss-law-informed first profile:** terms follow the Swiss FADP; optional fields (legal bases) bridge to the GDPR. Legal checking is a swappable profile, separate from the format.
5. **Three trust levels** (outside this specification): measured → declared → verified.

## Roadmap towards v1.0

- Mandatory signature (PGP or JWS), including a key convention
- Official French and Italian translations (multilingual declarations)
- EU check profile (`--profil eu`, GDPR logic) as the first non-Swiss profile
- IANA registration of the `/.well-known/` path (RFC 8615), eCH liaison
- Mapping the field semantics to the W3C Data Privacy Vocabulary (DPV)
- Matching recognised providers against the public Swiss–U.S. DPF certification list: turns the externally invisible question "is a safeguard in place?" into a measurable signal
- Badge widget as a tool in this repository
- Headless-browser scanner: also captures dynamically loaded services (today's figures are a lower bound)
- Growing the conformance suite: more edge cases, cases per check profile

## Licence

Code: **MIT** (`LICENSE`) · Specification and texts: **CC BY 4.0** (`spec/LICENSE-CC-BY-4.0.txt`) · Fonts: IBM Plex under **SIL OFL 1.1**. Any person and any company may implement this standard without asking – that is the point.

## Contributing

Issues and pull requests are welcome, in English or German. Discussion is most needed on the purpose vocabulary, the data categories and the signature convention. Security reports: see `SECURITY.md`.

---

*Status: draft v0.1 · August 2026 · Live register and industry report: [datenfluss-standard.ch/en/](https://datenfluss-standard.ch/en/)*

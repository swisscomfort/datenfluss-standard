# Befehlsoberflaeche des offenen Standards.
#
# Kurze, vollstaendige Einstiegspunkte statt einer abgeschriebenen Befehlskette
# aus der Workflow-Datei. Die Logik lebt in scripts/project/; dieses Makefile
# ist nur die Tuer - lokal und in CI dieselbe.
#
#   make preflight   Arbeitsbasis pruefen, bevor etwas geaendert wird
#   make verify      Anweisungs-Waechter, Konformitaets-Testsuite, Selbsttests
#   make handoff     maschinenlesbare Uebergabe fuer einen committeten HEAD

SHELL := /usr/bin/env bash
PYTHON ?= python3

TOOL ?= UNBEKANNT
MODEL ?= UNBEKANNT
EFFORT ?= UNBEKANNT
PERMISSION_MODE ?= UNBEKANNT
HANDOFF_ARGS ?=

.DEFAULT_GOAL := help
.PHONY: help preflight verify handoff

help:
	@echo "Verfuegbare Befehle:"
	@echo "  make preflight                           Arbeitsbasis pruefen"
	@echo "  make verify                              lokale und CI-Pruefung"
	@echo "  make handoff [TOOL= MODEL= EFFORT= ...]  Uebergabe erzeugen"
	@echo
	@echo "Pflichtlektuere: PROJECT_SCOPE.md, PROJECT_RULES.md, aktiver Work Order,"
	@echo "betroffene Spezifikation und Konformitaetstests."

preflight:
	@scripts/project/preflight.sh

verify:
	@scripts/project/verify.sh

handoff:
	@$(PYTHON) scripts/project/handoff.py \
		--tool "$(TOOL)" --model "$(MODEL)" --effort "$(EFFORT)" \
		--permission-mode "$(PERMISSION_MODE)" $(HANDOFF_ARGS)

#!/usr/bin/env python3
"""Zielpruefung fuer Abrufe: nur oeffentliche Adressen, keine internen Netze.

Warum das noetig ist:
  Der Scanner ruft Adressen ab, die von aussen kommen -- aus einer Domainliste,
  aus einem Selbstbedienungs-Vorschlag, aus einer Weiterleitung. Ohne Pruefung
  kann jemand das Werkzeug dazu bringen, *interne* Ziele abzurufen und das
  Ergebnis in ein oeffentliches Profil zu schreiben:

    http://169.254.169.254/...   Metadatendienst der Cloud (Zugangsdaten!)
    http://127.0.0.1:8737/       lokaler Dienst auf demselben Rechner
    http://10.0.0.5/             Nachbarsystem im privaten Netz

  Das ist eine Server-Side Request Forgery. Ein Messwerkzeug, das fuer Fremde
  Abrufe ausfuehrt, muss deshalb *vor* jedem Abruf pruefen, wohin es zeigt --
  und nach jeder Weiterleitung erneut, weil die Umleitung auf eine interne
  Adresse der klassische Umweg ist.

Ehrliche Restluecke (gehoert in die Methodik, nicht ins Kleingedruckte):
  Zwischen Namensaufloesung und Verbindungsaufbau kann ein Angreifer den
  DNS-Eintrag wechseln (DNS-Rebinding). Dagegen hilft nur, die Verbindung an
  die geprueffte IP zu binden. Diese Bindung leistet dieses Modul noch nicht;
  es schliesst die haeufigen Faelle und benennt den verbleibenden.

Nur Python-Standardbibliothek.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, build_opener

ERLAUBTE_SCHEMATA = ("http", "https")

# Ziele, die nie von aussen erreichbar sein sollen. Zusaetzlich zu den Flags
# der ipaddress-Bibliothek, weil diese nicht alles abdeckt, was praktisch
# gefaehrlich ist.
ZUSATZ_GESPERRT = (
    ipaddress.ip_network("169.254.169.254/32"),   # Cloud-Metadaten (IPv4)
    ipaddress.ip_network("fd00:ec2::254/128"),    # Cloud-Metadaten (IPv6)
    ipaddress.ip_network("100.64.0.0/10"),        # Carrier-NAT
)


class ZielAbgelehnt(ValueError):
    """Das Ziel darf nicht abgerufen werden. Die Meldung nennt den Grund."""


def _ist_oeffentlich(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> tuple[bool, str]:
    if ip.is_loopback:
        return False, "Loopback-Adresse"
    if ip.is_private:
        return False, "private Adresse (RFC 1918 / ULA)"
    if ip.is_link_local:
        return False, "Link-local-Adresse"
    if ip.is_multicast:
        return False, "Multicast-Adresse"
    if ip.is_reserved or ip.is_unspecified:
        return False, "reservierte Adresse"
    for netz in ZUSATZ_GESPERRT:
        if ip.version == netz.version and ip in netz:
            return False, f"gesperrter Bereich {netz}"
    # IPv4-in-IPv6 verpackt: die eingebettete Adresse muss ebenfalls halten.
    eingebettet = getattr(ip, "ipv4_mapped", None) or getattr(ip, "sixtofour", None)
    if eingebettet is not None:
        ok, grund = _ist_oeffentlich(eingebettet)
        if not ok:
            return False, f"eingebettete IPv4 ist {grund}"
    return True, ""


def aufloesen(host: str) -> list[str]:
    """Alle IP-Adressen eines Namens. Leere Liste, wenn er nicht aufloest."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, ValueError):
        return []
    return sorted({eintrag[4][0] for eintrag in infos})


def pruefe_ziel(url: str) -> list[str]:
    """Prueft eine URL und gibt die geprueften IP-Adressen zurueck.

    Wirft ZielAbgelehnt, wenn Schema, Name oder *irgendeine* aufgeloeste
    Adresse unzulaessig ist. Bewusst streng: Loest ein Name auf mehrere
    Adressen auf und ist nur eine davon intern, wird der ganze Abruf
    abgelehnt -- sonst entscheidet der Zufall der Adressauswahl darueber,
    ob der Schutz greift.
    """
    teile = urlparse(url)
    if teile.scheme.lower() not in ERLAUBTE_SCHEMATA:
        raise ZielAbgelehnt(f"Schema '{teile.scheme}' ist nicht zugelassen "
                            f"(erlaubt: {', '.join(ERLAUBTE_SCHEMATA)}).")
    host = teile.hostname
    if not host:
        raise ZielAbgelehnt("URL enthaelt keinen Hostnamen.")

    # Direkt notierte IP-Adressen gar nicht erst aufloesen.
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        adressen = aufloesen(host)
        if not adressen:
            raise ZielAbgelehnt(f"Name '{host}' loest nicht auf.")
    else:
        adressen = [str(ip)]

    for a in adressen:
        ok, grund = _ist_oeffentlich(ipaddress.ip_address(a))
        if not ok:
            raise ZielAbgelehnt(f"Ziel '{host}' zeigt auf {a} – {grund}. "
                                f"Interne Adressen werden nicht abgerufen.")
    return adressen


def ziel_erlaubt(url: str) -> bool:
    """Bequeme Ja/Nein-Form fuer Stellen, die den Grund nicht brauchen."""
    try:
        pruefe_ziel(url)
        return True
    except ZielAbgelehnt:
        return False


class GeprueftUmleiten(HTTPRedirectHandler):
    """Prueft jedes Weiterleitungsziel erneut.

    Die Umleitung auf eine interne Adresse ist der Standardumweg um eine
    Eingangspruefung: Der geprueffte Name antwortet mit 302 nach
    http://169.254.169.254/ -- und ohne diese Klasse folgt urllib brav.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        pruefe_ziel(newurl)  # wirft ZielAbgelehnt
        return super().redirect_request(req, fp, code, msg, headers, newurl)


# Ein gemeinsamer Oeffner fuer alle Werkzeuge. Bewusst zentral: Jede Stelle,
# die sich ihren eigenen Abruf baut, ist eine Stelle, an der die Pruefung
# spaeter vergessen wird -- genau so entstand die Luecke im Einwilligungs-Leser.
OEFFNER = build_opener(GeprueftUmleiten)


def oeffne(req, timeout: float):
    """Abruf mit Zielpruefung am Anfang und nach jeder Weiterleitung.

    `req` ist ein urllib-Request oder eine URL. Wirft ZielAbgelehnt, bevor
    ueberhaupt eine Verbindung aufgebaut wird.
    """
    ziel = req if isinstance(req, str) else req.full_url
    pruefe_ziel(ziel)
    return OEFFNER.open(req, timeout=timeout)

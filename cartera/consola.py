"""Utilidades para los comandos de consola."""

from __future__ import annotations

import sys


def salida_utf8() -> None:
    """En Windows la consola no usa UTF-8 por defecto y los textos con acentos o «−» fallarían."""
    for flujo in (sys.stdout, sys.stderr):
        reconfigurar = getattr(flujo, "reconfigure", None)
        if reconfigurar is not None:
            reconfigurar(encoding="utf-8")

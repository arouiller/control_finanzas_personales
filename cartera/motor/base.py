"""Datos de entrada del motor y utilidades de fechas (REQUERIMIENTOS 5, notación)."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from cartera.datos.modelos import Activo, FilaPrecios, Movimiento, Tenencias


@dataclass(frozen=True)
class Datos:
    """Todo lo que el motor necesita: tenencias, movimientos en el orden del archivo y serie de precios."""

    tenencias: Tenencias
    movimientos: list[Movimiento]
    precios: list[FilaPrecios]

    @property
    def activos(self) -> list[Activo]:
        return self.tenencias.activos


def a_fecha(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def dias(a: str, b: str) -> int:
    """Días calendario de `a` a `b`."""
    return (a_fecha(b) - a_fecha(a)).days


def sumar_dias(s: str, n: int) -> str:
    return (a_fecha(s) + dt.timedelta(days=n)).isoformat()


def sumar_anios(s: str, n: int) -> str:
    """Mismo día y mes, `n` años después. El 29/02 pasa al 01/03, como `setUTCFullYear` en el tablero actual."""
    d = a_fecha(s)
    try:
        return d.replace(year=d.year + n).isoformat()
    except ValueError:
        return dt.date(d.year + n, 3, 1).isoformat()


def mes(s: str) -> str:
    return s[:7]


def mes_siguiente(m: str) -> str:
    anio, n = int(m[:4]), int(m[5:7])
    return f"{anio + 1}-01" if n == 12 else f"{anio}-{n + 1:02d}"


def meses_entre(m0: str, m1: str) -> list[str]:
    """Meses `AAAA-MM` de `m0` a `m1` inclusive."""
    out = []
    while m0 <= m1:
        out.append(m0)
        m0 = mes_siguiente(m0)
    return out

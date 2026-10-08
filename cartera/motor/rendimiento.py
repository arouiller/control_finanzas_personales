"""Rendimiento ponderado en el tiempo y períodos de la cabecera (5.8)."""

from __future__ import annotations

from dataclasses import dataclass

from cartera.motor.base import sumar_dias
from cartera.motor.series import Serie
from cartera.motor.valuacion import Fila

DIAS_PERIODO = {"1M": 30, "3M": 91, "6M": 182}


def rendimiento(ini: Fila, fin: Fila, patrimonio: bool = False) -> float:
    """TWR entre dos filas, como fracción (0,05 = 5%)."""
    if patrimonio:
        return fin.idxP / ini.idxP - 1
    return fin.idx / ini.idx - 1


def filas_periodo(serie: Serie) -> dict[str, Fila]:
    """Fila de comparación de cada período: 1D es la anterior; 1A es la fila 0 ("desde el inicio")."""
    f = serie.filas
    ultima = serie.ultima
    out = {"1D": f[-2] if len(f) > 1 else f[0]}
    for k, n in DIAS_PERIODO.items():
        out[k] = serie.hasta(sumar_dias(ultima.t, -n))
    out["1A"] = f[0]
    return out


@dataclass(frozen=True)
class VariacionHoy:
    usd: float
    pct: float | None
    contra: str


def variacion_hoy(serie: Serie) -> VariacionHoy:
    """Variación de los activos financieros contra la fila anterior, sin los flujos del día."""
    ultima = serie.ultima
    ant = filas_periodo(serie)["1D"]
    d1 = ultima.tot - ant.tot - (ultima.cumF - ant.cumF)
    return VariacionHoy(d1, d1 / ant.tot if ant.tot else None, ant.t)


def rendimientos_cabecera(serie: Serie) -> dict[str, float]:
    """TWR de la cartera financiera para 1M, 3M, 6M y desde el inicio (RF-16)."""
    per = filas_periodo(serie)
    return {k: rendimiento(per[k], serie.ultima) for k in ("1M", "3M", "6M", "1A")}

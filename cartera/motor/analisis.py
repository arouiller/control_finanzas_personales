"""Análisis de un período elegido sobre el gráfico de Evolución (5.14)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cartera.motor.series import Serie
from cartera.motor.valuacion import Fila

Modo = Literal["tot", "bie", "pat"]


@dataclass(frozen=True)
class AnalisisPeriodo:
    desde: str
    hasta: str
    modo: str
    activo: str | None
    v0: float
    v1: float
    variacion: float
    variacion_pct: float | None
    # sin flujos (modo bienes) no hay ganancia ni comparación
    neto: float | None = None
    ganancia: float | None = None
    ganancia_spy: float | None = None
    diferencia: float | None = None
    cantidad_0: float | None = None
    cantidad_1: float | None = None


def analizar_periodo(
    serie: Serie, desde: str, hasta: str, modo: Modo = "tot", activo: str | None = None
) -> AnalisisPeriodo:
    r0, r1 = serie.en(desde), serie.en(hasta)
    if r0 is None or r1 is None:
        raise ValueError("las dos fechas tienen que estar en la serie")
    if desde > hasta:
        raise ValueError("`desde` no puede ser posterior a `hasta`")

    flujos: list[tuple[str, float]] | None = None
    q0 = q1 = None
    if activo is not None:
        a = serie.datos.tenencias.activo(activo)
        if a is None:
            raise ValueError(f"no existe el activo {activo}")
        v0, v1 = r0.pos[activo], r1.pos[activo]
        flujos = [
            (o.fecha, ((o.cantidad > 0) - (o.cantidad < 0)) * (o.usd or 0.0))
            for o in serie.datos.movimientos
            if o.activo == activo and o.cambia_saldo and o.tipo != "Interés Nexo" and desde < o.fecha <= hasta
        ]
        if not a.valor_fijo_usd:
            q0, q1 = r0.cant[activo], r1.cant[activo]
    elif modo == "bie":
        v0, v1 = r0.bie, r1.bie
    else:
        patrimonio = modo == "pat"
        v0, v1 = (r0.pat, r1.pat) if patrimonio else (r0.tot, r1.tot)
        flujos = [
            (r.t, r.flowP if patrimonio else r.flow)
            for r in serie.filas
            if desde < r.t <= hasta and abs(r.flowP if patrimonio else r.flow) > 1e-9
        ]

    dv = v1 - v0
    neto = ganancia = g_spy = None
    if flujos is not None:
        neto = sum(f for _, f in flujos)
        ganancia = dv - neto
        g_spy = _ganancia_spy(serie, r0, r1, v0, neto, flujos)
    return AnalisisPeriodo(
        desde=desde,
        hasta=hasta,
        modo=modo if activo is None else "activo",
        activo=activo,
        v0=v0,
        v1=v1,
        variacion=dv,
        variacion_pct=dv / v0 if v0 > 0.5 else None,
        neto=neto,
        ganancia=ganancia,
        ganancia_spy=g_spy,
        diferencia=None if ganancia is None or g_spy is None else ganancia - g_spy,
        cantidad_0=q0,
        cantidad_1=q1,
    )


def _ganancia_spy(
    serie: Serie, r0: Fila, r1: Fila, v0: float, neto: float, flujos: list[tuple[str, float]]
) -> float | None:
    """Lo que habría ganado la misma plata, con los mismos flujos, puesta en SPY."""
    if not r0.spy or not r1.spy:
        return None
    u = v0 / r0.spy
    for d, f in flujos:
        spy = (serie.en(d) or r0).spy
        if not spy:
            return None
        u += f / spy
    return u * r1.spy - v0 - neto

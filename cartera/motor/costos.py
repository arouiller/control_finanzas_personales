"""Costo promedio, resultado realizado (5.10) y valor en USD de los devengos diarios (5.11)."""

from __future__ import annotations

from dataclasses import dataclass, field

from cartera.motor.base import Datos, sumar_dias
from cartera.motor.cantidades import cantidad_en
from cartera.motor.series import Serie

EPS = 1e-9


@dataclass(frozen=True)
class Costo:
    costo: float
    promedio: float
    estimado: bool


@dataclass(frozen=True)
class Realizado:
    usd: float
    estimado: bool


@dataclass
class Costos:
    """Costo de las posiciones abiertas (`por_activo`) y resultado de cada venta, por índice del movimiento."""

    por_activo: dict[str, Costo] = field(default_factory=dict)
    realizados: dict[int, Realizado] = field(default_factory=dict)


def calcular_costos(datos: Datos) -> Costos:
    out = Costos()
    for a in datos.activos:
        if a.valor_fijo_usd:
            continue
        ops = [
            (i, o)
            for i, o in enumerate(datos.movimientos)
            if o.activo == a.ticker and o.cambia_saldo and o.devengo_diario is None
        ]
        ops.sort(key=lambda x: x[1].fecha)  # orden estable: a igual fecha, el del archivo
        if not ops:
            continue
        q = cantidad_en(a, datos.movimientos, sumar_dias(ops[0][1].fecha, -1))
        c = 0.0
        ok = abs(q) < EPS  # el historial está completo si antes del primer movimiento no había tenencia
        est = False
        for i, o in ops:
            if o.cantidad > 0:
                q += o.cantidad
                c += o.usd or 0.0
                est = est or bool(o.estimado)
                continue
            vendida = -o.cantidad
            avg = c / q if q > 0 else 0.0
            if ok and q > 0:
                out.realizados[i] = Realizado(abs(o.usd or 0.0) - avg * vendida, est)
            c -= avg * vendida
            q -= vendida
            if abs(q) < EPS:
                q, c, ok, est = 0.0, 0.0, True, False
        if ok and a.cantidad > 0 and q > 0:
            out.por_activo[a.ticker] = Costo(c, c / q, est)
    return out


def usd_devengos(serie: Serie) -> dict[int, float]:
    """USD de cada movimiento con devengo diario: Σ por_dia × pu(activo, d) entre `desde` y `fecha` (5.11).

    No se usa el `usd` guardado. La clave es el índice del movimiento.
    """
    out: dict[int, float] = {}
    for i, o in enumerate(serie.datos.movimientos):
        dev = o.devengo_diario
        if dev is None:
            continue
        out[i] = sum(dev.por_dia * r.pu.get(o.activo, 0.0) for r in serie.filas if dev.desde <= r.t <= o.fecha)
    return out

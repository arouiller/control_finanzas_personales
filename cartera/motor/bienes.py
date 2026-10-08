"""Bienes (5.5) y pasivos en cuotas (5.6)."""

from __future__ import annotations

from collections.abc import Iterable

from cartera.datos.modelos import Inmueble, Movimiento, Pasivo
from cartera.motor.base import dias


def pagado_hasta(x: Inmueble, movimientos: Iterable[Movimiento], d: str | None = None) -> float:
    """Plata que salió de la cartera con destino al bien (hasta `d` inclusive, o toda si `d` es None)."""
    return sum(-o.flujo for o in movimientos if o.destino == x.nombre and o.flujo and (d is None or o.fecha <= d))


def valor_bien(x: Inmueble, movimientos: Iterable[Movimiento], d: str) -> float:
    """`bval(x, d)`: antes de la compra, lo ya pagado; después, el valor (con depreciación lineal si tiene)."""
    if d < x.fecha_compra:
        return pagado_hasta(x, movimientos, d)
    dep = x.depreciacion_anual_pct or 0
    if dep:
        base = x.valor_nuevo_usd or x.costo_usd
        return max(0.0, base * (1 - dep / 100 * dias(x.fecha_compra, d) / 365.25))
    return x.valor_usd


def valor_bienes(inmuebles: Iterable[Inmueble], movimientos: list[Movimiento], d: str) -> float:
    return sum(valor_bien(x, movimientos, d) for x in inmuebles)


def cuota_usd(p: Pasivo) -> float:
    """`cu`: USD por cuota."""
    return p.alicuota_ars / p.mep_referencia


def pendientes(p: Pasivo, d: str) -> int:
    """Cuotas que faltan: total menos pagas y canceladas con fecha ≤ `d`."""
    pagas = sum(1 for c in p.cuotas_pagas if c.fecha <= d)
    canceladas = sum(1 for c in p.canceladas() if c.fecha <= d)
    return p.cuotas_total - pagas - canceladas


def deuda_pasivo(p: Pasivo, d: str) -> float:
    return 0.0 if d < p.fecha_alta else pendientes(p, d) * cuota_usd(p)


def deuda(pasivos: Iterable[Pasivo], d: str) -> float:
    return sum(deuda_pasivo(p, d) for p in pasivos)


def aporte_por_cuotas(p: Pasivo, d: str) -> float:
    """Aporte al patrimonio del día `d` por cuotas (5.8).

    Cuenta las cuotas pagas y las canceladas que no se pagaron desde la cartera; las pagadas desde la
    cartera no suman porque la plata ya salió con un movimiento con destino al bien.
    """
    if d < p.fecha_alta:
        return 0.0
    n = sum(1 for c in p.cuotas_pagas if c.fecha == d)
    n += sum(1 for c in p.canceladas() if c.fecha == d and not c.pagada_desde_cartera)
    return n * cuota_usd(p)

"""Tabla de movimientos: orden, cantidad acumulada, precio, valor hoy y resultado (5.15)."""

from __future__ import annotations

from dataclasses import dataclass

from cartera.datos.modelos import TIPOS_CONTRAPARTIDA, Movimiento
from cartera.motor.costos import Costos, calcular_costos, usd_devengos
from cartera.motor.series import Serie


@dataclass(frozen=True)
class FilaMovimiento:
    indice: int
    mov: Movimiento
    acumulada: float
    usd: float | None
    precio_usd: float | None
    valor_usd: float | None
    valor_hoy: float | None
    vendido: bool
    resultado: float | None
    resultado_estimado: bool


def orden_tabla(movimientos: list[Movimiento]) -> list[int]:
    """Índices del más nuevo al más viejo, con cada Pago o Cobro pegado a su operación."""
    g = -1
    claves = []
    for i, o in enumerate(movimientos):
        if o.tipo not in TIPOS_CONTRAPARTIDA:
            g += 1
        claves.append((o.fecha, g, i))
    orden = sorted(claves, key=lambda c: c[2])
    orden.sort(key=lambda c: c[1], reverse=True)
    orden.sort(key=lambda c: c[0], reverse=True)
    return [c[2] for c in orden]


def tabla_movimientos(serie: Serie, costos: Costos | None = None) -> list[FilaMovimiento]:
    datos = serie.datos
    movs = datos.movimientos
    costos = costos or calcular_costos(datos)
    devengos = usd_devengos(serie)
    activos = {a.ticker: a for a in datos.activos}
    pu_hoy = serie.ultima.pu
    orden = orden_tabla(movs)

    saldo = {
        t: a.cantidad - sum(o.cantidad for o in movs if o.activo == t and o.cambia_saldo) for t, a in activos.items()
    }
    acumulada: dict[int, float] = {}
    for i in reversed(orden):
        o = movs[i]
        if o.cambia_saldo:
            saldo[o.activo] = round(saldo[o.activo] + o.cantidad, 8)
        acumulada[i] = saldo[o.activo]

    out = []
    for i in orden:
        o = movs[i]
        a = activos[o.activo]
        usd = devengos.get(i, o.usd)
        signo = (o.cantidad > 0) - (o.cantidad < 0)
        valor = signo * usd if usd is not None else (o.cantidad if a.valor_fijo_usd else None)
        precio = abs(usd / o.cantidad) if usd and o.cantidad and not a.valor_fijo_usd else None
        real = costos.realizados.get(i)
        valor_hoy: float | None = None
        vendido = False
        resultado: float | None = None
        est = False
        if o.estimado:
            pass
        elif o.tipo in ("Venta", "Conversión"):
            vendido = a.cantidad == 0
            if real:
                resultado, est = real.usd, real.estimado
        elif not a.valor_fijo_usd and a.cantidad == 0:
            vendido = True
            if real:
                resultado = real.usd
        else:
            valor_hoy = o.cantidad * pu_hoy.get(o.activo, 0.0)
            if valor is not None and abs(valor_hoy - valor) >= 0.005:
                resultado = valor_hoy - valor
        out.append(FilaMovimiento(i, o, acumulada[i], usd, precio, valor, valor_hoy, vendido, resultado, est))
    return out

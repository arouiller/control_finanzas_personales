"""Reglas de integridad entre archivos (REQUERIMIENTOS 4.4).

Se verifican antes de cada escritura y con `scripts/verificar_integridad.py`.
"""

from __future__ import annotations

from collections import Counter
from itertools import pairwise

from cartera.datos.modelos import DESTINO_MINEROS, FilaPrecios, Movimiento, Tenencias
from cartera.motor.base import sumar_dias
from cartera.motor.cantidades import Cantidades

TOLERANCIA = 1e-8
MAX_POR_REGLA = 5


class ErrorIntegridad(Exception):
    """Los datos no cumplen las reglas de 4.4. `errores` trae el detalle, uno por línea."""

    def __init__(self, errores: list[str]) -> None:
        super().__init__("Los datos no pasan la verificación de integridad:\n- " + "\n- ".join(errores))
        self.errores = errores


def _repetidos(valores: list[str]) -> list[str]:
    return [v for v, n in Counter(valores).items() if n > 1]


def verificar(tenencias: Tenencias, movimientos: list[Movimiento], precios: list[FilaPrecios] | None) -> list[str]:
    """Devuelve la lista de problemas (vacía si está todo bien). Sin `precios` se omiten las reglas de la serie."""
    e: list[str] = []
    e += _tenencias(tenencias)
    e += _movimientos(tenencias, movimientos)
    e += _pasivos(tenencias, movimientos)
    if precios is not None:
        e += _precios(tenencias, movimientos, precios)
    return e


def exigir(tenencias: Tenencias, movimientos: list[Movimiento], precios: list[FilaPrecios] | None) -> None:
    errores = verificar(tenencias, movimientos, precios)
    if errores:
        raise ErrorIntegridad(errores)


def _tenencias(ten: Tenencias) -> list[str]:
    e = [f"El ticker {t} está repetido en tenencias.activos." for t in _repetidos([a.ticker for a in ten.activos])]
    e += [f"El bien «{n}» está repetido en tenencias.inmuebles." for n in _repetidos([x.nombre for x in ten.inmuebles])]
    for a in ten.activos:
        # 4.5.1: sin precio en pesos ni valor fijo, el precio sale del par BTCUSDT
        if not a.cotiza_en_pesos and not a.valor_fijo_usd and a.ticker != "BTC":
            e.append(f"{a.ticker} no cotiza en pesos ni es de valor fijo: por ahora eso solo se admite para BTC.")
    return e


def _movimientos(ten: Tenencias, movs: list[Movimiento]) -> list[str]:
    e: list[str] = []
    tickers = {a.ticker for a in ten.activos}
    destinos = {x.nombre for x in ten.inmuebles} | {DESTINO_MINEROS}
    ids = [o.id for o in movs if o.id is not None]
    e += [f"El id de movimiento {i} está repetido." for i in _repetidos(ids)]
    conocidos = set(ids)
    for n, o in enumerate(movs, 1):
        ref = f"Movimiento {o.id or '#' + str(n)} ({o.fecha}, {o.tipo} {o.activo})"
        if o.activo not in tickers:
            e.append(f"{ref}: el activo no existe en tenencias.activos.")
        if o.destino is not None and o.destino not in destinos:
            e.append(f"{ref}: el destino «{o.destino}» no es un bien de tenencias.inmuebles ni «{DESTINO_MINEROS}».")
        if o.contrapartida_de is not None and o.contrapartida_de not in conocidos:
            e.append(f"{ref}: contrapartida_de apunta a {o.contrapartida_de}, que no existe.")
        if o.devengo_diario is not None and o.devengo_diario.desde > o.fecha:
            e.append(f"{ref}: el devengo diario empieza después de la fecha del movimiento.")
    return e


def _pasivos(ten: Tenencias, movs: list[Movimiento]) -> list[str]:
    e: list[str] = []
    bienes = {x.nombre for x in ten.inmuebles}
    for p in ten.pasivos:
        ref = f"Pasivo «{p.nombre}»"
        if p.bien is not None and p.bien not in bienes:
            e.append(f"{ref}: el bien «{p.bien}» no existe en tenencias.inmuebles.")
        pagas = [c.cuota for c in p.cuotas_pagas]
        canceladas = [c.cuota for c in p.canceladas()]
        if len(set(pagas)) != len(pagas):
            e.append(f"{ref}: hay números de cuota repetidos en cuotas_pagas.")
        fechas = [c.fecha for c in p.cuotas_pagas]
        if fechas != sorted(fechas):
            e.append(f"{ref}: las fechas de cuotas_pagas no están ordenadas.")
        if len(set(canceladas)) != len(canceladas):
            e.append(f"{ref}: hay números de cuota repetidos en cuotas_canceladas.")
        ambas = sorted(set(pagas) & set(canceladas))
        if ambas:
            e.append(f"{ref}: las cuotas {ambas} figuran como pagas y como canceladas.")
        if len(pagas) + len(canceladas) > p.cuotas_total:
            e.append(f"{ref}: hay más cuotas pagas y canceladas que cuotas_total.")
        for c in p.canceladas():
            if not c.pagada_desde_cartera:
                continue
            # DECISIÓN: el movimiento de salida tiene que ser de la misma fecha que la cancelación, para que
            # la baja de la deuda y la salida de la plata caigan el mismo día y el rendimiento no se mueva.
            if not any(o.destino == p.bien and o.flujo < 0 and o.fecha == c.fecha for o in movs):
                e.append(
                    f"{ref}: la cuota cancelada {c.cuota} ({c.fecha}) está marcada como pagada desde la cartera, "
                    f"pero no hay un movimiento de salida con destino «{p.bien}» en esa fecha."
                )
    return e


def _precios(ten: Tenencias, movs: list[Movimiento], precios: list[FilaPrecios]) -> list[str]:
    e: list[str] = []
    if not precios:
        return ["La serie de precios está vacía."]
    for ant, act in pairwise(precios):
        if act.fecha != sumar_dias(ant.fecha, 1):
            e.append(f"La serie de precios tiene un hueco o un desorden entre {ant.fecha} y {act.fecha}.")
            if len(e) >= MAX_POR_REGLA:
                break
    tickers = {a.ticker for a in ten.activos}
    cant = Cantidades(ten.activos, [o for o in movs if o.activo in tickers])
    negativos: dict[str, tuple[str, float]] = {}
    sin_precio: dict[str, str] = {}
    for p in precios:
        if p.mep <= 0:
            sin_precio.setdefault("MEP", p.fecha)
        for a in ten.activos:
            q = cant.en(a.ticker, p.fecha)
            if q < -TOLERANCIA:
                negativos.setdefault(a.ticker, (p.fecha, q))
            if q > TOLERANCIA and not a.valor_fijo_usd:
                precio = p.ars.get(a.ticker, 0.0) if a.cotiza_en_pesos else p.btc_usdt
                if not precio or precio <= 0:
                    sin_precio.setdefault(a.ticker, p.fecha)
    for t, (d, q) in negativos.items():
        e.append(f"La cantidad histórica de {t} queda negativa ({q:.8g}) desde el {d}.")
    for t, d in sin_precio.items():
        e.append(f"Falta el precio de {t} el {d} (y hay tenencia en esa fecha).")
    return e

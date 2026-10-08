"""Serie diaria completa (5.3 a 5.8) y serie mensual (5.9)."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property

from cartera.datos.modelos import DESTINO_MINEROS
from cartera.motor.base import Datos, mes
from cartera.motor.bienes import aporte_por_cuotas, deuda, valor_bienes
from cartera.motor.cantidades import Cantidades
from cartera.motor.mineria import valor_mineros
from cartera.motor.valuacion import Fila, precio_usd, precio_usd_ticker

TIPOS_MINERIA = frozenset({"Minería", "Costo minería"})


@dataclass
class Serie:
    datos: Datos
    filas: list[Fila]
    _por_fecha: dict[str, Fila] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._por_fecha = {r.t: r for r in self.filas}

    @property
    def primera(self) -> Fila:
        return self.filas[0]

    @property
    def ultima(self) -> Fila:
        return self.filas[-1]

    def en(self, d: str) -> Fila | None:
        return self._por_fecha.get(d)

    @cached_property
    def mensuales(self) -> list[Fila]:
        """Una fila por mes: el último día de cada mes y, para el mes en curso, la última fecha (5.9)."""
        f = self.filas
        return [r for i, r in enumerate(f) if i == len(f) - 1 or mes(f[i + 1].t) != mes(r.t)]

    @cached_property
    def evolucion(self) -> list[Fila]:
        """Puntos del gráfico de Evolución: la fila 0 más las mensuales."""
        # DECISIÓN: si la fila 0 ya es fin de mes no se repite (el tablero actual la duplicaba).
        m = self.mensuales
        return m if m and m[0] is self.primera else [self.primera, *m]

    def anterior_al_mes(self, puntos: list[Fila], m: str) -> Fila:
        """Último punto anterior al mes `m` (o el primero): inicio de los gráficos para "Gráficos desde" (RF-17)."""
        previos = [r for r in puntos if r.t < m + "-01"]
        return previos[-1] if previos else puntos[0]

    def hasta(self, d: str) -> Fila:
        """Última fila con fecha ≤ `d` (o la primera)."""
        r = self.filas[0]
        for x in self.filas:
            if x.t <= d:
                r = x
            else:
                break
        return r


def calcular_serie(datos: Datos) -> Serie:
    activos = datos.activos
    movs = datos.movimientos
    ten = datos.tenencias
    cant = Cantidades(activos, movs)
    con_destino = [o for o in movs if o.destino and o.flujo]

    flujo: dict[str, float] = defaultdict(float)
    flujo_mineria: dict[str, float] = defaultdict(float)
    flujo_bienes: dict[str, float] = defaultdict(float)
    for o in movs:
        if not o.flujo:
            continue
        flujo[o.fecha] += o.flujo
        if o.tipo in TIPOS_MINERIA:
            flujo_mineria[o.fecha] += o.flujo
        if o.destino and o.destino != DESTINO_MINEROS:
            flujo_bienes[o.fecha] += o.flujo
    tandas: dict[str, float] = defaultdict(float)
    if ten.mineros:
        for t in ten.mineros.tandas():
            tandas[t.fecha] += t.costo_usd
    fechas_cuotas = {c.fecha for p in ten.pasivos for c in p.cuotas_pagas}
    fechas_cuotas |= {c.fecha for p in ten.pasivos for c in p.canceladas()}

    filas: list[Fila] = []
    for p in datos.precios:
        d = p.fecha
        pu = {a.ticker: precio_usd(a, p) for a in activos}
        q = {a.ticker: cant.en(a.ticker, d) for a in activos}
        pos = {t: q[t] * pu[t] for t in pu}
        por_grupo: dict[str, float] = defaultdict(float)
        for a in activos:
            por_grupo[a.grupo] += pos[a.ticker]
        filas.append(
            Fila(
                t=d,
                mep=p.mep,
                btc=p.btc_usdt,
                pu=pu,
                cant=q,
                pos=pos,
                por_grupo=dict(por_grupo),
                tot=sum(pos.values()),
                min=valor_mineros(ten.mineros, d),
                inm=valor_bienes(ten.inmuebles, con_destino, d),
                deu=deuda(ten.pasivos, d),
                spy=precio_usd_ticker("SPY", activos, p),
            )
        )

    idx = idx_p = 1.0
    cum = cum_p = 0.0
    for i, r in enumerate(filas):
        if i:
            d = r.t
            r.flow = flujo.get(d, 0.0)
            r.flowP = r.flow - flujo_mineria.get(d, 0.0) + tandas.get(d, 0.0) - flujo_bienes.get(d, 0.0)
            if d in fechas_cuotas:
                r.flowP += sum(aporte_por_cuotas(pas, d) for pas in ten.pasivos)
            ant = filas[i - 1]
            # DECISIÓN: si el valor anterior es 0 el índice no se mueve (el tablero actual dividía por cero).
            if ant.tot:
                idx *= (r.tot - r.flow) / ant.tot
            if ant.pat:
                idx_p *= (r.pat - r.flowP) / ant.pat
        cum += r.flow
        cum_p += r.flowP
        r.cumF, r.cumFP, r.idx, r.idxP = cum, cum_p, idx, idx_p
        r.capT = filas[0].tot + cum
        r.capP = filas[0].pat + cum_p
    return Serie(datos, filas)

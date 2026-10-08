"""Mineros: valor contable (5.4) y producción mensual (5.13)."""

from __future__ import annotations

from dataclasses import dataclass

from cartera.datos.modelos import Mineros, Movimiento, TandaMineros
from cartera.motor.base import dias, mes, meses_entre, sumar_anios


def fin_vida(m: Mineros, t: TandaMineros) -> str:
    return sumar_anios(t.fecha, m.vida_util_anios)


def valor_tanda(m: Mineros, t: TandaMineros, d: str) -> float:
    """Arranca en `valor_inicial_pct` del costo y baja en línea recta hasta `valor_residual_pct` al fin de su vida."""
    if d < t.fecha:
        return 0.0
    x = min(1.0, dias(t.fecha, d) / dias(t.fecha, fin_vida(m, t)))
    ini, res = m.valor_inicial_pct / 100, m.valor_residual_pct / 100
    return t.costo_usd * (ini - (ini - res) * x)


def valor_mineros(m: Mineros | None, d: str) -> float:
    if m is None:
        return 0.0
    return sum(valor_tanda(m, t, d) for t in m.tandas())


@dataclass(frozen=True)
class MesProduccion:
    mes: str
    btc: float
    usd: float
    cost: float
    net: float
    pagos: int
    acc: float
    recupero: float | None


@dataclass(frozen=True)
class Produccion:
    meses: list[MesProduccion]
    btc_minado: float
    pagos: int
    meses_con_cobro: int
    usd_al_cobrar: float
    valor_hoy: float
    costos_usd: float
    pagos_costos: int
    neto: float
    promedio_mensual: float | None
    recupero: float | None
    amortizacion_anual: float | None


def produccion(
    movimientos: list[Movimiento], mineros: Mineros | None, ultima_fecha: str, pu_btc_hoy: float
) -> Produccion | None:
    """Producción mensual desde el primer mes con Minería o Costo minería hasta el último mes de la serie."""
    mops = [o for o in movimientos if o.tipo == "Minería"]
    cops = [o for o in movimientos if o.tipo == "Costo minería"]
    if not mops and not cops:
        return None
    costo = mineros.costo_usd if mineros else 0.0
    meses: list[MesProduccion] = []
    acc = 0.0
    for k in meses_entre(min(mes(o.fecha) for o in [*mops, *cops]), mes(ultima_fecha)):
        ps = [o for o in mops if mes(o.fecha) == k]
        btc = sum(o.cantidad for o in ps)
        usd = sum(o.usd or 0.0 for o in ps)
        cost = sum(o.usd or 0.0 for o in cops if mes(o.fecha) == k)
        acc += usd - cost
        meses.append(MesProduccion(k, btc, usd, cost, usd - cost, len(ps), acc, acc / costo if costo else None))
    tb = sum(o.cantidad for o in mops)
    tu = sum(o.usd or 0.0 for o in mops)
    tc = sum(o.usd or 0.0 for o in cops)
    activos = [p for p in meses if p.btc > 0 or p.cost > 0]
    amort = None
    if mineros:
        amort = costo * (mineros.valor_inicial_pct - mineros.valor_residual_pct) / 100 / mineros.vida_util_anios
    return Produccion(
        meses=meses,
        btc_minado=tb,
        pagos=len(mops),
        meses_con_cobro=sum(1 for p in meses if p.btc > 0),
        usd_al_cobrar=tu,
        valor_hoy=tb * pu_btc_hoy,
        costos_usd=tc,
        pagos_costos=len(cops),
        neto=tu - tc,
        promedio_mensual=(tu - tc) / len(activos) if activos else None,
        recupero=(tu - tc) / costo if costo else None,
        amortizacion_anual=amort,
    )

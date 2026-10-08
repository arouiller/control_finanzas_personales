"""Clasificación mensual de aportes y retiros (5.12) y capital neto del período elegido."""

from __future__ import annotations

from dataclasses import dataclass

from cartera.datos.modelos import Movimiento
from cartera.motor.base import mes, meses_entre
from cartera.motor.series import Serie
from cartera.motor.valuacion import Fila

# conceptos del detalle mensual, en el orden en que se muestran
APORTE, MINADO, RETIRO, BIENES, LUZ = 1, 2, 3, 4, 5


def concepto(o: Movimiento) -> int:
    if o.tipo == "Costo minería":
        return LUZ
    if o.tipo == "Minería":
        return MINADO
    if o.flujo > 0:
        return APORTE
    return BIENES if o.destino else RETIRO


def etiqueta(c: int, tipo: str) -> str:
    if c == MINADO:
        return "BTC minado"
    if c == LUZ:
        return "Luz y seguro"
    if c == BIENES:
        return "Compra de bienes"
    return {"Venta": "Ventas", "Compra": "Compras"}.get(tipo, tipo)


@dataclass(frozen=True)
class GrupoFlujo:
    concepto: int
    etiqueta: str
    tipo: str
    total: float
    movimientos: int
    por_activo: list[tuple[str, float]]


@dataclass(frozen=True)
class FlujoMes:
    mes: str
    ap: float
    rm: float
    rv: float
    rt: float
    rc: float
    neto: float
    movimientos: int
    grupos: list[GrupoFlujo]
    cierre: Fila | None


def _grupos(ops: list[Movimiento]) -> list[GrupoFlujo]:
    por_clave: dict[tuple[int, str, bool], list[Movimiento]] = {}
    for o in ops:
        por_clave.setdefault((concepto(o), o.tipo, o.flujo > 0), []).append(o)
    out = []
    for (c, tipo, _), g in sorted(por_clave.items(), key=lambda kv: kv[0][0]):
        por_activo: dict[str, float] = {}
        for o in g:
            por_activo[o.activo] = por_activo.get(o.activo, 0.0) + o.flujo
        out.append(
            GrupoFlujo(
                concepto=c,
                etiqueta=etiqueta(c, tipo),
                tipo=tipo,
                total=sum(o.flujo for o in g),
                movimientos=len(g),
                por_activo=sorted(por_activo.items(), key=lambda kv: -abs(kv[1])),
            )
        )
    return out


def flujos_mensuales(serie: Serie) -> list[FlujoMes]:
    """Un elemento por mes de la serie, con los movimientos de flujo posteriores a la primera fecha."""
    primera, ultima = serie.primera.t, serie.ultima.t
    ops = [o for o in serie.datos.movimientos if o.flujo and o.fecha > primera]
    cierre = {mes(r.t): r for r in serie.filas}
    out = []
    for k in meses_entre(mes(primera), mes(ultima)):
        os_ = sorted((o for o in ops if mes(o.fecha) == k), key=lambda o: o.fecha)
        ap = sum(o.flujo for o in os_ if o.flujo > 0 and o.tipo != "Minería")
        rm = sum(o.flujo for o in os_ if o.tipo == "Minería")
        rv = sum(-o.flujo for o in os_ if o.flujo < 0 and o.tipo != "Costo minería" and not o.destino)
        rt = sum(-o.flujo for o in os_ if o.flujo < 0 and o.destino)
        rc = sum(-o.flujo for o in os_ if o.tipo == "Costo minería")
        out.append(FlujoMes(k, ap, rm, rv, rt, rc, ap + rm - rv - rt - rc, len(os_), _grupos(os_), cierre.get(k)))
    return out


@dataclass(frozen=True)
class PeriodoFlujos:
    """Pestaña Aportes y retiros para el período que empieza en el mes elegido (RF-26 a RF-28)."""

    desde_mes: str
    hasta_mes: str
    meses: list[FlujoMes]
    puntos: list[Fila]
    base: float
    valor_inicial: float
    aportes: float
    minado: float
    retiros: float
    a_bienes: float
    luz: float
    capital_neto: float
    valor_final: float
    ganancia: float

    def capital(self, r: Fila) -> float:
        """Capital neto del gráfico: arranca en el valor al inicio del período."""
        return r.capT + self.base


def periodo_flujos(serie: Serie, desde_mes: str | None = None) -> PeriodoFlujos:
    todos = flujos_mensuales(serie)
    a = todos[0].mes if desde_mes is None or desde_mes < todos[0].mes else desde_mes
    previas = [r for r in serie.filas if mes(r.t) < a]
    r0 = previas[-1] if previas else serie.primera
    puntos = [r0, *[r for r in serie.mensuales if r.t > r0.t]]
    meses = [f for f in todos if f.mes >= a]
    rm = sum(f.rm for f in meses)
    ap = sum(f.ap for f in meses) + rm
    rv, rt, rc = sum(f.rv for f in meses), sum(f.rt for f in meses), sum(f.rc for f in meses)
    cap = r0.tot + ap - rv - rt - rc
    return PeriodoFlujos(
        desde_mes=a,
        hasta_mes=todos[-1].mes,
        meses=meses,
        puntos=puntos,
        base=r0.tot - r0.capT,
        valor_inicial=r0.tot,
        aportes=ap,
        minado=rm,
        retiros=rv,
        a_bienes=rt,
        luz=rc,
        capital_neto=cap,
        valor_final=puntos[-1].tot,
        ganancia=puntos[-1].tot - cap,
    )

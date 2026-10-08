"""Tabla de posiciones (RF-24), base 100 (5.16) y composición del patrimonio (5.17)."""

from __future__ import annotations

from dataclasses import dataclass

from cartera.datos.modelos import ORDEN_TIPOS, Activo
from cartera.motor.bienes import cuota_usd, pendientes, valor_bien
from cartera.motor.costos import Costos, calcular_costos
from cartera.motor.rendimiento import filas_periodo, rendimiento
from cartera.motor.series import Serie
from cartera.motor.valuacion import Fila

PERIODOS_TABLA = ("1D", "1M", "1A")

# --- tabla de posiciones


@dataclass(frozen=True)
class Posicion:
    ticker: str
    grupo: str
    valor: float
    peso: float | None
    peso_en_grupo: float | None
    cantidad: float
    costo: float | None
    resultado: float | None
    resultado_estimado: bool
    variacion: dict[str, float | None]


@dataclass(frozen=True)
class GrupoPosiciones:
    grupo: str
    valor: float
    peso: float | None
    costo: float | None
    resultado: float | None
    resultado_estimado: bool
    resultado_parcial: bool
    variacion: dict[str, float | None]
    posiciones: list[Posicion]


@dataclass(frozen=True)
class TablaPosiciones:
    grupos: list[GrupoPosiciones]
    total: float
    costo: float
    resultado: float
    resultado_estimado: bool
    rendimiento: dict[str, float]


def _variacion_grupo(del_grupo: list[Activo], antes: Fila, ult: Fila) -> float | None:
    """Variación de precio del grupo con las cantidades actuales; sin sentido si todos son de valor fijo."""
    if all(a.valor_fijo_usd for a in del_grupo):
        return None
    z = [a for a in del_grupo if antes.pu.get(a.ticker, 0) > 0]
    base = sum(a.cantidad * antes.pu[a.ticker] for a in z)
    return sum(a.cantidad * ult.pu[a.ticker] for a in z) / base - 1 if base else None


def tabla_posiciones(serie: Serie, costos: Costos | None = None) -> TablaPosiciones:
    datos = serie.datos
    costos = costos or calcular_costos(datos)
    ult = serie.ultima
    per = filas_periodo(serie)
    cost = costos.por_activo

    def var_precio(ticker: str, fijo: bool, k: str) -> float | None:
        p0 = per[k].pu.get(ticker)
        return None if fijo or not p0 else ult.pu[ticker] / p0 - 1

    grupos = []
    for g in dict.fromkeys(a.grupo for a in datos.activos):
        del_grupo = [a for a in datos.activos if a.grupo == g]
        con_tenencia = [a for a in del_grupo if a.cantidad > 0]
        if not con_tenencia:
            continue
        sub = ult.por_grupo[g]
        con_costo = [a for a in con_tenencia if a.ticker in cost]
        posiciones = [
            Posicion(
                ticker=a.ticker,
                grupo=g,
                valor=ult.pos[a.ticker],
                peso=ult.pos[a.ticker] / ult.tot if ult.tot else None,
                peso_en_grupo=ult.pos[a.ticker] / sub if sub else None,
                cantidad=a.cantidad,
                costo=cost[a.ticker].costo if a.ticker in cost else None,
                resultado=ult.pos[a.ticker] - cost[a.ticker].costo if a.ticker in cost else None,
                resultado_estimado=a.ticker in cost and cost[a.ticker].estimado,
                variacion={k: var_precio(a.ticker, a.valor_fijo_usd, k) for k in PERIODOS_TABLA},
            )
            for a in sorted(con_tenencia, key=lambda a: -ult.pos[a.ticker])
        ]
        grupos.append(
            GrupoPosiciones(
                grupo=g,
                valor=sub,
                peso=sub / ult.tot if ult.tot else None,
                costo=sum(cost[a.ticker].costo for a in con_costo) if con_costo else None,
                resultado=sum(ult.pos[a.ticker] - cost[a.ticker].costo for a in con_costo) if con_costo else None,
                resultado_estimado=any(cost[a.ticker].estimado for a in con_costo),
                resultado_parcial=any(a.ticker not in cost for a in con_tenencia),
                variacion={k: _variacion_grupo(del_grupo, per[k], ult) for k in PERIODOS_TABLA},
                posiciones=posiciones,
            )
        )
    grupos.sort(key=lambda x: -x.valor)
    return TablaPosiciones(
        grupos=grupos,
        total=ult.tot,
        costo=sum(k.costo for k in cost.values()),
        resultado=sum(ult.pos[t] - k.costo for t, k in cost.items()),
        resultado_estimado=any(k.estimado for k in cost.values()),
        rendimiento={k: rendimiento(per[k], ult) for k in PERIODOS_TABLA},
    )


# --- lista lateral de Evolución (RF-21)


@dataclass(frozen=True)
class ActivoEvolucion:
    ticker: str
    valor: float
    variacion_precio: float | None


def lista_evolucion(serie: Serie, desde: Fila | None = None) -> list[ActivoEvolucion]:
    """Activos con más de 0,5 USD en algún día del mes en curso, con la variación de precio desde `desde`."""
    ult = serie.ultima
    r0 = desde or serie.primera
    del_mes = [r for r in serie.filas if r.t[:7] == ult.t[:7]]
    out = []
    for a in serie.datos.activos:
        if not any(r.pos[a.ticker] > 0.5 for r in del_mes):
            continue
        p0, p1 = r0.pu[a.ticker], ult.pu[a.ticker]
        var = None if a.valor_fijo_usd or not p0 > 0 or not p1 > 0 else p1 / p0 - 1
        out.append(ActivoEvolucion(a.ticker, ult.pos[a.ticker], var))
    return sorted(out, key=lambda x: -x.valor)


# --- base 100 (5.16)


@dataclass(frozen=True)
class SerieBase100:
    ticker: str
    base: str
    puntos: list[tuple[str, float]]


def base_100(serie: Serie, desde_mes: str | None = None) -> list[SerieBase100]:
    """Activos no fijos con tenencia; la base es la primera fila con precio desde el inicio elegido."""
    inicio = serie.primera if desde_mes is None else serie.anterior_al_mes(serie.filas, desde_mes)
    desde = serie.filas.index(inicio)
    out = []
    for a in serie.datos.activos:
        if a.valor_fijo_usd or a.cantidad <= 0:
            continue
        t = a.ticker
        base = next((r for r in serie.filas[desde:] if r.pu[t] > 0), None)
        if base is None:
            out.append(SerieBase100(t, "", []))
            continue
        pts = [base, *[r for r in serie.mensuales if r.t > base.t]]
        out.append(SerieBase100(t, base.t, [(r.t, r.pu[t] / base.pu[t] * 100) for r in pts]))
    return out


# --- composición del patrimonio (5.17)


@dataclass(frozen=True)
class ItemComposicion:
    clave: str
    nombre: str
    valor: float
    estimado: bool = False
    deuda: float = 0.0


@dataclass(frozen=True)
class GrupoComposicion:
    clave: str
    valor: float
    financiero: bool
    items: list[ItemComposicion]


@dataclass(frozen=True)
class Composicion:
    """Treemap. `neto`: cada bien por su parte pagada (valor − deuda de su pasivo); si no, a valor completo."""

    neto: bool
    grupos: list[GrupoComposicion]

    def total(self, financieros: bool = True, no_financieros: bool = True) -> float:
        return sum(g.valor for g in self.grupos if (financieros if g.financiero else no_financieros))


def composicion(serie: Serie, neto: bool = True) -> Composicion:
    datos = serie.datos
    ten = datos.tenencias
    ult = serie.ultima
    grupos = []
    for tipo in ORDEN_TIPOS:
        items = sorted(
            (ItemComposicion(a.ticker, a.nombre, ult.pos[a.ticker]) for a in datos.activos if a.tipo == tipo),
            key=lambda x: -x.valor,
        )
        valor = sum(i.valor for i in items)
        if valor > 0:
            grupos.append(GrupoComposicion(tipo, valor, True, items))

    bienes = []
    for x in ten.inmuebles:
        if ult.t < x.fecha_compra:
            continue
        deuda = sum(
            pendientes(p, ult.t) * cuota_usd(p) for p in ten.pasivos if p.bien == x.nombre and ult.t >= p.fecha_alta
        )
        resta = deuda if neto else 0.0
        bienes.append(
            ItemComposicion(x.nombre, x.nombre, max(0.0, valor_bien(x, datos.movimientos, ult.t) - resta), deuda=resta)
        )
    if ult.min > 0 and ten.mineros:
        bienes.append(ItemComposicion("Mineros", ten.mineros.modelo, ult.min, estimado=True))
    if bienes:
        bienes.sort(key=lambda x: -x.valor)
        grupos.append(GrupoComposicion("Bienes", sum(i.valor for i in bienes), False, bienes))
    return Composicion(neto, grupos)


def composicion_en_el_tiempo(
    serie: Serie, por_activo: bool = False, desde_mes: str | None = None
) -> dict[str, list[tuple[str, float]]]:
    """Valor mensual de cada tipo (o de cada activo que alguna vez tuvo valor), en el orden de los tipos."""
    mensuales = serie.mensuales
    inicio = mensuales[0] if desde_mes is None else serie.anterior_al_mes(mensuales, desde_mes)
    puntos = [r for r in mensuales if r.t >= inicio.t]
    out: dict[str, list[tuple[str, float]]] = {}
    for tipo in ORDEN_TIPOS:
        del_tipo = [a for a in serie.datos.activos if a.tipo == tipo]
        if not del_tipo:
            continue
        if por_activo:
            for a in del_tipo:
                if any(r.pos[a.ticker] > 0 for r in mensuales):
                    out[a.ticker] = [(r.t, r.pos[a.ticker]) for r in puntos]
        else:
            out[tipo] = [(r.t, sum(r.pos[a.ticker] for a in del_tipo)) for r in puntos]
    return out

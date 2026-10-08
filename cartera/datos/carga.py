"""Carga inicial o reemplazo total de los datos (REQUERIMIENTOS 4.3, T-12).

La usan `scripts/cargar_datos.py` y, más adelante, Administración → Cargar datos (RF-48).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cartera.datos import integridad
from cartera.datos.backup import crear_backup
from cartera.datos.colores import COLORES_REFERENCIA, PALETA, clave_color
from cartera.datos.modelos import (
    TIPOS_CONTRAPARTIDA,
    AjusteCantidad,
    AjusteHistorico,
    ColorTicker,
    Config,
    FuenteActivo,
    FuenteRespaldo,
    FuentesPrecios,
    Movimientos,
    PreciosDiarios,
    Tenencias,
)
from cartera.datos.repositorio import (
    CONFIG,
    FUENTES,
    MOVIMIENTOS,
    PRECIOS,
    TENENCIAS,
    ErrorValidacion,
    Repositorio,
    validar,
)
from cartera.motor.base import Datos
from cartera.motor.series import calcular_serie

Json = dict[str, Any]

# DECISIÓN (F1): precios_diarios.json es obligatorio. En F3 pasa a ser opcional: si falta, la historia
# se construye con RF-08 (4.3, paso 3).
OBLIGATORIOS = (TENENCIAS, MOVIMIENTOS, PRECIOS)
OPCIONALES = (FUENTES,)

# Reglas especiales conocidas de precios (tabla de 4.5.4): son datos de mercado, no del usuario.
FUENTES_ESPECIALES: dict[str, FuenteActivo] = {
    "META": FuenteActivo(simbolo_yahoo="META", ratio_ny=24),
    "VIST": FuenteActivo(simbolo_yahoo="VIST", ratio_ny=3),
    "AVGO": FuenteActivo(
        simbolo_yahoo="AVGO.BA", factor=1, respaldo=FuenteRespaldo(simbolo_yahoo="AVGO", ratio_ny=38.5)
    ),
    "YPFD": FuenteActivo(simbolo_yahoo="YPFD.BA", factor=10),
    "NFLX": FuenteActivo(simbolo_yahoo="NFLX.BA", factor=10),
}
AJUSTES_PRECIO: tuple[AjusteHistorico, ...] = (
    AjusteHistorico(activo="AVGO", antes_de="2026-09-29", usar_respaldo=True, motivo="AVGO.BA sin historia en Yahoo"),
    AjusteHistorico(activo="NFLX", antes_de="2024-01-24", multiplicar_precio=1 / 3, motivo="cambio de ratio"),
    AjusteHistorico(activo="AAPL", antes_de="2024-01-24", multiplicar_precio=0.5, motivo="cambio de ratio"),
    AjusteHistorico(activo="MELI", antes_de="2024-01-24", multiplicar_precio=0.5, motivo="cambio de ratio"),
    AjusteHistorico(activo="TM", antes_de="2024-01-24", multiplicar_precio=1 / 3, motivo="cambio de ratio"),
)
# Cambios de ratio y splits para las cantidades del importador de Balanz (4.5.4, RF-52).
AJUSTES_CANTIDAD: tuple[AjusteCantidad, ...] = (
    AjusteCantidad(activo="SPY", antes_de="2026-05-29", multiplicar_cantidad=3),
    AjusteCantidad(activo="AAPL", antes_de="2024-01-24", multiplicar_cantidad=2),
    AjusteCantidad(activo="MELI", antes_de="2024-01-24", multiplicar_cantidad=2),
    AjusteCantidad(activo="NVDA", antes_de="2024-06-10", multiplicar_cantidad=10),
    AjusteCantidad(activo="AVGO", antes_de="2024-07-15", multiplicar_cantidad=10),
)


class ErrorCarga(Exception):
    """La carga se rechaza; `errores` trae el detalle."""

    def __init__(self, errores: list[str]) -> None:
        super().__init__("No se puede cargar:\n- " + "\n- ".join(errores))
        self.errores = errores


@dataclass(frozen=True)
class Resumen:
    activos: int
    movimientos: int
    ids_asignados: int
    contrapartidas_asignadas: int
    primer_movimiento: str | None
    ultimo_movimiento: str | None
    serie_desde: str
    serie_hasta: str
    fecha: str
    activos_financieros: float
    mineros: float
    bienes: float
    pasivos: float
    patrimonio_neto: float


@dataclass
class Carga:
    archivos: dict[str, Json]
    resumen: Resumen
    avisos: list[str] = field(default_factory=list)
    # archivos que no vinieron en la carpeta y se propusieron: no pisan uno que ya exista
    propuestos: set[str] = field(default_factory=set)


def normalizar_movimientos(crudo: Json) -> tuple[Json, int, int]:
    """Completa `id` y `contrapartida_de` (4.3, paso 2). Devuelve los datos y cuántos asignó de cada uno.

    - Sin `id`: se asigna `m-0001`, `m-0002`… en el orden del archivo, salteando los que ya existan.
    - Pago o Cobro sin `contrapartida_de`: el `id` del movimiento anterior que no sea Pago ni Cobro.
    """
    movs = [dict(m) for m in crudo.get("movimientos", [])]
    usados = {m["id"] for m in movs if m.get("id")}
    n = ids = contrapartidas = 0
    anterior: str | None = None
    for m in movs:
        if not m.get("id"):
            n += 1
            while f"m-{n:04d}" in usados:
                n += 1
            m["id"] = f"m-{n:04d}"
            usados.add(m["id"])
            ids += 1
        if m.get("tipo") in TIPOS_CONTRAPARTIDA:
            if not m.get("contrapartida_de") and anterior is not None:
                m["contrapartida_de"] = anterior
                contrapartidas += 1
        else:
            anterior = m["id"]
    return {**crudo, "movimientos": movs}, ids, contrapartidas


def config_por_defecto(tenencias: Tenencias, previa: Config | None = None) -> Config:
    """`config.json` inicial (4.3, paso 5). Si ya había uno, solo se agregan los colores que falten."""
    cfg = previa.model_copy(deep=True) if previa else Config(ajustes_cantidades=list(AJUSTES_CANTIDAD))
    libres = [p for p in PALETA if ColorTicker(claro=p[0], oscuro=p[1], atenuado=p[2]) not in cfg.colores.values()]
    i = 0
    for a in tenencias.activos:
        if a.ticker in cfg.colores:
            continue
        c = COLORES_REFERENCIA.get(clave_color(a.ticker))
        if c is None:
            c = (libres or list(PALETA))[i % len(libres or PALETA)]
            i += 1
        cfg.colores[a.ticker] = ColorTicker(claro=c[0], oscuro=c[1], atenuado=c[2])
    return cfg


def fuentes_propuestas(tenencias: Tenencias) -> FuentesPrecios:
    """`fuentes_precios.json` para revisar: `<TICKER>.BA` con factor 1, más las reglas especiales conocidas."""
    activos = {}
    for a in tenencias.activos:
        if a.cotiza_en_pesos:
            activos[a.ticker] = FUENTES_ESPECIALES.get(a.ticker) or FuenteActivo(
                simbolo_yahoo=f"{a.ticker}.BA", factor=1
            )
    ajustes = [x for x in AJUSTES_PRECIO if x.activo in activos]
    return FuentesPrecios(activos=activos, ajustes_historicos=ajustes)


def _leer(carpeta: Path, nombre: str) -> Json:
    try:
        datos = json.loads((carpeta / nombre).read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise ErrorCarga([f"{nombre} no es un JSON válido: {err}"]) from err
    if not isinstance(datos, dict):
        raise ErrorCarga([f"{nombre}: se esperaba un objeto JSON."])
    return datos


def preparar_carga(carpeta: Path | str) -> Carga:
    """Lee, normaliza y verifica una carpeta de datos sin escribir nada."""
    carpeta = Path(carpeta)
    faltan = [n for n in OBLIGATORIOS if not (carpeta / n).is_file()]
    if faltan:
        raise ErrorCarga([f"Falta {n} en {carpeta}." for n in faltan])

    archivos: dict[str, Json] = {TENENCIAS: _leer(carpeta, TENENCIAS), PRECIOS: _leer(carpeta, PRECIOS)}
    archivos[MOVIMIENTOS], ids, contrapartidas = normalizar_movimientos(_leer(carpeta, MOVIMIENTOS))
    for n in OPCIONALES:
        if (carpeta / n).is_file():
            archivos[n] = _leer(carpeta, n)

    errores: list[str] = []
    for n, d in archivos.items():
        try:
            validar(n, d)
        except ErrorValidacion as err:
            errores += [f"{n}: {linea}" for linea in err.detalle.splitlines()]
    if errores:
        raise ErrorCarga(errores)

    ten = Tenencias.model_validate(archivos[TENENCIAS])
    movs = Movimientos.model_validate(archivos[MOVIMIENTOS]).movimientos
    pre = PreciosDiarios.model_validate(archivos[PRECIOS])
    errores = integridad.verificar(ten, movs, pre.serie)
    if errores:
        raise ErrorCarga(errores)

    avisos = []
    propuestos = set()
    if FUENTES not in archivos:
        archivos[FUENTES] = fuentes_propuestas(ten).a_json()
        propuestos.add(FUENTES)
        avisos.append(
            f"No vino {FUENTES}: si todavía no existe, se crea uno con <TICKER>.BA y factor 1 para que lo revises."
        )
    ult = calcular_serie(Datos(ten, movs, pre.serie)).ultima
    fechas = sorted(o.fecha for o in movs)
    resumen = Resumen(
        activos=len(ten.activos),
        movimientos=len(movs),
        ids_asignados=ids,
        contrapartidas_asignadas=contrapartidas,
        primer_movimiento=fechas[0] if fechas else None,
        ultimo_movimiento=fechas[-1] if fechas else None,
        serie_desde=pre.serie[0].fecha,
        serie_hasta=pre.serie[-1].fecha,
        fecha=ult.t,
        activos_financieros=ult.tot,
        mineros=ult.min,
        bienes=ult.inm,
        pasivos=ult.deu,
        patrimonio_neto=ult.pat,
    )
    return Carga(archivos, resumen, avisos, propuestos)


def aplicar_carga(carga: Carga, repo: Repositorio, carpeta_backups: Path | str) -> Path | None:
    """Escribe la carga como una sola operación. Si ya había datos, antes hace un backup y devuelve su ruta."""
    backup = None
    if repo.dir.is_dir() and any(repo.existe(n) for n in (TENENCIAS, MOVIMIENTOS, PRECIOS)):
        backup = crear_backup(repo.dir, Path(carpeta_backups), prefijo="precarga")
    archivos = {n: d for n, d in carga.archivos.items() if n not in carga.propuestos or not repo.existe(n)}
    previa = repo.config() if repo.existe(CONFIG) else None
    archivos[CONFIG] = config_por_defecto(Tenencias.model_validate(archivos[TENENCIAS]), previa).a_json(completo=True)
    repo.transaccion(archivos, accion="cargar datos")
    return backup

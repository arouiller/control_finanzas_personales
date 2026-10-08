"""Esquemas pydantic de los archivos JSON (REQUERIMIENTOS 4.5).

Las fechas se guardan como texto ISO `AAAA-MM-DD`: el motor las compara en orden lexicográfico (sección 5).
Todos los modelos conservan los campos desconocidos (4.3).
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

TipoActivo = Literal["Acciones argentinas", "CEDEARs", "Cripto", "Liquidez"]
ORDEN_TIPOS: tuple[str, ...] = ("Acciones argentinas", "CEDEARs", "Cripto", "Liquidez")

TipoMovimiento = Literal[
    "Compra",
    "Venta",
    "Cobro",
    "Pago",
    "Conversión",
    "Minería",
    "Costo minería",
    "Interés Nexo",
    "Aporte",
    "Compra de bienes",
    "Saldo inicial",
]
TIPOS_CONTRAPARTIDA: frozenset[str] = frozenset({"Pago", "Cobro"})
DESTINO_MINEROS = "Mineros"


def _fecha_iso(v: str) -> str:
    if len(v) != 10 or dt.date.fromisoformat(v).isoformat() != v:
        raise ValueError("la fecha tiene que ser AAAA-MM-DD")
    return v


def _mes_iso(v: str) -> str:
    _fecha_iso(v + "-01")
    return v


Fecha = Annotated[str, AfterValidator(_fecha_iso)]
Mes = Annotated[str, AfterValidator(_mes_iso)]


class Modelo(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True, validate_assignment=True)

    def a_json(self, completo: bool = False) -> dict[str, Any]:
        """Datos para guardar: solo los campos presentes, más los desconocidos.

        Con `completo` se escriben también los valores por defecto (para `config.json`).
        """
        return self.model_dump(mode="json", exclude_unset=not completo)


# --- tenencias.json (4.5.1)


class Activo(Modelo):
    ticker: str = Field(min_length=1)
    nombre: str
    tipo: TipoActivo
    grupo: str
    cantidad: float
    cotiza_en_pesos: bool
    valor_fijo_usd: bool

    @model_validator(mode="after")
    def _excluyentes(self) -> Activo:
        if self.cotiza_en_pesos and self.valor_fijo_usd:
            raise ValueError("cotiza_en_pesos y valor_fijo_usd no pueden ser los dos true")
        return self


class TandaMineros(Modelo):
    fecha: Fecha
    cantidad: float = 0
    costo_usd: float = Field(ge=0)


class Mineros(Modelo):
    modelo: str
    th_por_equipo: float
    cantidad: float
    fecha_compra: Fecha
    costo_usd: float = Field(ge=0)
    valor_inicial_pct: float
    valor_residual_pct: float
    vida_util_anios: int = Field(gt=0)
    compras: list[TandaMineros] | None = None

    def tandas(self) -> list[TandaMineros]:
        """Sin `compras`, toda la compra es una sola tanda (igual que el tablero actual)."""
        if self.compras:
            return self.compras
        return [TandaMineros(fecha=self.fecha_compra, cantidad=self.cantidad, costo_usd=self.costo_usd)]


class Inmueble(Modelo):
    nombre: str = Field(min_length=1)
    fecha_compra: Fecha
    costo_usd: float
    valor_usd: float
    fecha_valuacion: Fecha | None = None
    depreciacion_anual_pct: float | None = None
    valor_nuevo_usd: float | None = None
    origen: str | None = None


class CuotaPaga(Modelo):
    cuota: int
    fecha: Fecha


class CuotaCancelada(Modelo):
    cuota: int
    fecha: Fecha
    motivo: str | None = None
    pagada_desde_cartera: bool = False


class Pasivo(Modelo):
    nombre: str = Field(min_length=1)
    bien: str | None = None
    tipo: str | None = None
    cuotas_total: int = Field(ge=0)
    alicuota_ars: float = Field(ge=0)
    valor_movil_ars: float | None = None
    fecha_valor_movil: Fecha | None = None
    mep_referencia: float = Field(gt=0)
    fecha_alta: Fecha
    cuotas_pagas: list[CuotaPaga] = Field(default_factory=list)
    cuotas_canceladas: list[CuotaCancelada] | None = None

    def canceladas(self) -> list[CuotaCancelada]:
        return self.cuotas_canceladas or []


class Tenencias(Modelo):
    actualizado: Fecha | None = None
    moneda_valuacion: str | None = None
    activos: list[Activo]
    mineros: Mineros | None = None
    inmuebles: list[Inmueble] = Field(default_factory=list)
    pasivos: list[Pasivo] = Field(default_factory=list)

    def activo(self, ticker: str) -> Activo | None:
        return next((a for a in self.activos if a.ticker == ticker), None)


# --- movimientos.json (4.5.2)


class DevengoDiario(Modelo):
    desde: Fecha
    por_dia: float


class Movimiento(Modelo):
    id: str | None = None
    fecha: Fecha
    tipo: TipoMovimiento
    activo: str
    cantidad: float
    usd: float | None = Field(default=None, ge=0)
    flujo_usd: float | None = None
    estimado: bool | None = None
    sin_efecto_en_saldo: bool | None = None
    devengo_diario: DevengoDiario | None = None
    destino: str | None = None
    contrapartida_de: str | None = None
    nota: str | None = None

    @property
    def flujo(self) -> float:
        return self.flujo_usd or 0.0

    @property
    def cambia_saldo(self) -> bool:
        return not self.sin_efecto_en_saldo


class Movimientos(Modelo):
    movimientos: list[Movimiento]


# --- precios_diarios.json (4.5.3)


class FilaPrecios(Modelo):
    fecha: Fecha
    mep: float
    btc_usdt: float
    ars: dict[str, float] = Field(default_factory=dict)


class PreciosDiarios(Modelo):
    desde: Fecha
    hasta: Fecha
    serie: list[FilaPrecios]


# --- fuentes_precios.json (4.5.4)


class FuenteRespaldo(Modelo):
    simbolo_yahoo: str
    factor: float | None = None
    ratio_ny: float | None = None


class FuenteActivo(Modelo):
    simbolo_yahoo: str
    factor: float | None = None
    ratio_ny: float | None = None
    respaldo: FuenteRespaldo | None = None


class AjusteHistorico(Modelo):
    activo: str
    antes_de: Fecha
    multiplicar_precio: float | None = None
    usar_respaldo: bool | None = None
    motivo: str | None = None


class FuenteBtc(Modelo):
    par: str = "BTCUSDT"


class FuentesPrecios(Modelo):
    activos: dict[str, FuenteActivo] = Field(default_factory=dict)
    ajustes_historicos: list[AjusteHistorico] = Field(default_factory=list)
    btc: FuenteBtc = Field(default_factory=FuenteBtc)


# --- config.json (4.1)


class Umbrales(Modelo):
    """Validaciones del job de precios (RF-05)."""

    mep_min: float = 500
    mep_max: float = 5000
    btc_min: float = 10_000
    btc_max: float = 500_000
    salto_min: float = 0.6
    salto_max: float = 1.6


class AjusteCantidad(Modelo):
    """Cambio de ratio o split: las cantidades anteriores a `antes_de` se multiplican (RF-52)."""

    activo: str
    antes_de: Fecha
    multiplicar_cantidad: float


class ColorTicker(Modelo):
    claro: str
    oscuro: str
    atenuado: str


class Config(Modelo):
    inicio_serie: Fecha = "2023-01-01"
    hora_job: str = "20:45"
    umbrales: Umbrales = Field(default_factory=Umbrales)
    colores: dict[str, ColorTicker] = Field(default_factory=dict)
    orden_tipos: list[str] = Field(default_factory=lambda: list(ORDEN_TIPOS))
    ajustes_cantidades: list[AjusteCantidad] = Field(default_factory=list)

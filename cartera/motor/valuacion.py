"""Precio en USD por unidad (5.1) y fila diaria de valuación (5.3 a 5.8)."""

from __future__ import annotations

from dataclasses import dataclass, field

from cartera.datos.modelos import Activo, FilaPrecios


def precio_usd(a: Activo, p: FilaPrecios) -> float:
    """`pu(activo, d)`: 1 si es de valor fijo; ARS ÷ MEP si cotiza en pesos; si no, el precio del BTC."""
    if a.valor_fijo_usd:
        return 1.0
    if a.cotiza_en_pesos:
        ars = p.ars.get(a.ticker) or 0.0
        return ars / p.mep if p.mep else 0.0
    return p.btc_usdt or 0.0


def precio_usd_ticker(ticker: str, activos: list[Activo], p: FilaPrecios) -> float | None:
    """Precio de un ticker aunque no esté en la cartera (para comparar contra SPY, 5.14)."""
    a = next((x for x in activos if x.ticker == ticker), None)
    if a is not None:
        return precio_usd(a, p) or None
    ars = p.ars.get(ticker)
    return ars / p.mep if ars and p.mep else None


@dataclass
class Fila:
    """Una fecha de la serie diaria. Los nombres siguen la notación de la sección 5."""

    t: str
    mep: float
    btc: float
    pu: dict[str, float]
    cant: dict[str, float]
    pos: dict[str, float]
    por_grupo: dict[str, float]
    tot: float
    min: float
    inm: float
    deu: float
    flow: float = 0.0
    flowP: float = 0.0
    cumF: float = 0.0
    cumFP: float = 0.0
    idx: float = 1.0
    idxP: float = 1.0
    capT: float = 0.0
    capP: float = 0.0
    en_curso: bool = False
    spy: float | None = field(default=None, repr=False)

    @property
    def pat(self) -> float:
        """Patrimonio neto (5.7)."""
        return self.tot + self.min + self.inm - self.deu

    @property
    def bie(self) -> float:
        """Bienes y mineros."""
        return self.min + self.inm

    @property
    def bin(self) -> float:
        """Bienes netos de deuda."""
        return self.bie - self.deu

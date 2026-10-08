"""Cantidad de cada activo en una fecha, reconstruida hacia atrás desde la cantidad actual (5.2)."""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable

from cartera.datos.modelos import Activo, Movimiento
from cartera.motor.base import dias


def efecto(o: Movimiento, d: str) -> float:
    """Parte de la cantidad de `o` que todavía no ocurrió al cierre de `d` (el movimiento del día `d` ya ocurrió)."""
    dev = o.devengo_diario
    if dev is None:
        return o.cantidad if o.fecha > d else 0.0
    if d >= o.fecha:
        return 0.0
    if d < dev.desde:
        return o.cantidad
    return dev.por_dia * dias(d, o.fecha)


def cantidad_en(activo: Activo, movimientos: Iterable[Movimiento], d: str) -> float:
    """`q(a, d)`: definición directa de 5.2. Para muchas fechas conviene `Cantidades`."""
    return activo.cantidad - sum(efecto(o, d) for o in movimientos if o.activo == activo.ticker and o.cambia_saldo)


class Cantidades:
    """Calcula `q(a, d)` sin recorrer todos los movimientos en cada consulta.

    Los movimientos comunes se resuelven con sumas acumuladas por fecha y búsqueda binaria;
    los de devengo diario son pocos y se evalúan uno por uno.
    """

    def __init__(self, activos: Iterable[Activo], movimientos: Iterable[Movimiento]) -> None:
        self._actual = {a.ticker: a.cantidad for a in activos}
        por_fecha: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self._devengos: dict[str, list[Movimiento]] = defaultdict(list)
        for o in movimientos:
            if not o.cambia_saldo or o.activo not in self._actual:
                continue
            if o.devengo_diario is None:
                por_fecha[o.activo][o.fecha] += o.cantidad
            else:
                self._devengos[o.activo].append(o)
        # por activo: fechas ordenadas y, para cada una, la suma de las cantidades con fecha posterior o igual
        self._fechas: dict[str, list[str]] = {}
        self._desde: dict[str, list[float]] = {}
        for t, m in por_fecha.items():
            fechas = sorted(m)
            acum = [0.0] * (len(fechas) + 1)
            for i in range(len(fechas) - 1, -1, -1):
                acum[i] = acum[i + 1] + m[fechas[i]]
            self._fechas[t] = fechas
            self._desde[t] = acum

    def en(self, ticker: str, d: str) -> float:
        q = self._actual[ticker]
        fechas = self._fechas.get(ticker)
        if fechas:
            q -= self._desde[ticker][bisect_right(fechas, d)]
        for o in self._devengos.get(ticker, ()):
            q -= efecto(o, d)
        return q

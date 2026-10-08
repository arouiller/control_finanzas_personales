"""T-03: reconstrucción de cantidades hacia atrás (5.2), incluido el devengo diario del Interés Nexo."""

from __future__ import annotations

import pytest

from cartera.motor.base import Datos
from cartera.motor.cantidades import Cantidades, cantidad_en, efecto
from cartera.motor.series import Serie

POR_DIA = 3.1e-6  # interés de febrero de 2025 en el ejemplo: 28 días, del 01/02 al 28/02


def _interes(datos: Datos):  # type: ignore[no-untyped-def]
    return next(o for o in datos.movimientos if o.tipo == "Interés Nexo")


def test_devengo_diario_del_interes(datos: Datos) -> None:
    o = _interes(datos)
    assert o.fecha == "2025-02-28" and o.devengo_diario is not None
    total = 28 * POR_DIA
    # antes de `desde` falta devengar todo: el 31/01 no hay nada de interés en el saldo
    assert efecto(o, "2025-01-31") == pytest.approx(total)
    # el 01/02 faltan devengar 27 días (ya entró el del día 1)
    assert efecto(o, "2025-02-01") == pytest.approx(27 * POR_DIA)
    assert efecto(o, "2025-02-14") == pytest.approx(14 * POR_DIA)
    assert efecto(o, "2025-02-27") == pytest.approx(1 * POR_DIA)
    # desde la fecha del movimiento está el total
    assert efecto(o, "2025-02-28") == 0
    assert efecto(o, "2025-03-15") == 0


def test_saldo_de_btc_alrededor_del_interes(datos: Datos) -> None:
    btc = datos.tenencias.activo("BTC")
    assert btc is not None

    def q(d: str) -> float:
        return cantidad_en(btc, datos.movimientos, d)

    # 31/01: solo el saldo inicial de 0,05
    assert q("2025-01-31") == pytest.approx(0.05)
    # 01/02: + 0,002 minado + 1 día de interés
    assert q("2025-02-01") == pytest.approx(0.052 + POR_DIA)
    # 05/02: − 0,004 convertidos a USDT, con 5 días de interés
    assert q("2025-02-05") == pytest.approx(0.048 + 5 * POR_DIA)
    # 28/02 en adelante: el interés completo; coincide con la cantidad actual
    assert q("2025-02-28") == pytest.approx(0.048 + 28 * POR_DIA)
    assert q("2025-04-30") == pytest.approx(btc.cantidad) == pytest.approx(0.0480868)


def test_el_movimiento_del_dia_ya_ocurrio(datos: Datos) -> None:
    spy = datos.tenencias.activo("SPY")
    assert spy is not None
    assert cantidad_en(spy, datos.movimientos, "2025-01-09") == 0
    assert cantidad_en(spy, datos.movimientos, "2025-01-10") == 100  # la compra del 10/01 cuenta ese mismo día
    assert cantidad_en(spy, datos.movimientos, "2025-01-25") == 80
    assert cantidad_en(spy, datos.movimientos, "2025-03-10") == 40
    assert cantidad_en(spy, datos.movimientos, "2025-04-10") == 50


def test_sin_efecto_en_saldo_no_cambia_cantidades(datos: Datos) -> None:
    extra = datos.movimientos[2].model_copy(update={"sin_efecto_en_saldo": True, "cantidad": 999.0})
    spy = datos.tenencias.activo("SPY")
    assert spy is not None
    assert cantidad_en(spy, [*datos.movimientos, extra], "2025-01-05") == 0


def test_calculo_rapido_igual_a_la_definicion(datos: Datos, serie: Serie) -> None:
    """`Cantidades` (sumas acumuladas) da lo mismo que la fórmula directa de 5.2 en todas las fechas."""
    rapido = Cantidades(datos.activos, datos.movimientos)
    for r in serie.filas:
        for a in datos.activos:
            directo = cantidad_en(a, datos.movimientos, r.t)
            assert rapido.en(a.ticker, r.t) == pytest.approx(directo, abs=1e-12)
            assert r.cant[a.ticker] == pytest.approx(directo, abs=1e-12)


def test_ninguna_cantidad_historica_negativa(serie: Serie) -> None:
    assert min(q for r in serie.filas for q in r.cant.values()) >= -1e-8

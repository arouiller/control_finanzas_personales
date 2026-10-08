"""T-01: el motor reproduce cada valor de `referencia/ejemplo/valores_control.json`."""

from __future__ import annotations

from typing import Any

import pytest

from cartera.motor.base import Datos
from cartera.motor.costos import calcular_costos
from cartera.motor.mineria import produccion
from cartera.motor.series import Serie
from tests.conftest import EJEMPLO, TOL_PP, TOL_USD, leer_json

CONTROL = leer_json(EJEMPLO / "valores_control.json")
CAMPOS = ("tot", "min", "inm", "deu", "pat", "flow", "flowP", "capT", "capP")


@pytest.mark.parametrize("fecha", sorted(CONTROL["por_fecha"]))
def test_valores_por_fecha(serie: Serie, fecha: str) -> None:
    esperado = CONTROL["por_fecha"][fecha]
    r = serie.en(fecha)
    assert r is not None
    for k in CAMPOS:
        assert getattr(r, k) == pytest.approx(esperado[k], abs=TOL_USD), k
    assert (r.idx - 1) * 100 == pytest.approx(esperado["rend_cartera_pct"], abs=TOL_PP)
    assert (r.idxP - 1) * 100 == pytest.approx(esperado["rend_patrimonio_pct"], abs=TOL_PP)
    # las posiciones del control omiten las que valen menos de medio centavo
    for t, v in r.pos.items():
        assert v == pytest.approx(esperado["posiciones"].get(t, 0.0), abs=TOL_USD), t


def test_costo_posiciones_abiertas(datos: Datos) -> None:
    costos = calcular_costos(datos).por_activo
    esperado = CONTROL["costo_posiciones_abiertas"]
    assert set(costos) == set(esperado)
    for t, v in esperado.items():
        assert costos[t].costo == pytest.approx(v["costo_usd"], abs=TOL_USD)
        assert costos[t].promedio == pytest.approx(v["costo_promedio"], abs=TOL_USD)


def test_mineria(datos: Datos, serie: Serie) -> None:
    p = produccion(datos.movimientos, datos.tenencias.mineros, serie.ultima.t, serie.ultima.pu["BTC"])
    assert p is not None
    esperado: dict[str, Any] = CONTROL["mineria"]
    assert p.btc_minado == pytest.approx(esperado["btc_minado"], abs=1e-8)
    assert p.usd_al_cobrar == pytest.approx(esperado["usd_al_cobrar"], abs=TOL_USD)
    assert p.costos_usd == pytest.approx(esperado["costos_usd"], abs=TOL_USD)


def test_referencias_rapidas_al_30_04_2025(serie: Serie) -> None:
    """Los números que cita T-01 en REQUERIMIENTOS.md."""
    r = serie.ultima
    assert r.t == "2025-04-30"
    assert round(r.tot, 2) == 10999.56
    assert round(r.min, 2) == 4390.46
    assert round(r.inm, 2) == 1875.04
    assert round(r.deu, 2) == 600.00
    assert round(r.pat, 2) == 16665.06
    assert round(r.capT, 2) == 10398.90
    assert round((r.idx - 1) * 100, 2) == 5.75
    assert round((r.idxP - 1) * 100, 2) == -7.11


def test_cuotas_canceladas_del_ejemplo(serie: Serie) -> None:
    """Una cancelada de cada tipo: las dos bajan la deuda en cu = 100; solo la no pagada desde la cartera es aporte."""
    antes, dia = serie.en("2025-03-24"), serie.en("2025-03-25")
    assert antes and dia
    assert antes.deu - dia.deu == pytest.approx(100.0)
    assert dia.flowP == pytest.approx(100.0)  # pagada con plata de afuera: aporte al patrimonio
    assert dia.flow == 0

    antes, dia = serie.en("2025-04-19"), serie.en("2025-04-20")
    assert antes and dia
    assert antes.deu - dia.deu == pytest.approx(100.0)
    assert dia.flow == pytest.approx(-100.0)  # salió de la cartera con destino al auto
    assert dia.flowP == pytest.approx(0.0)  # ni aporte ni retiro del patrimonio

"""T-02: el motor coincide con `calculo_referencia.py` en TODAS las fechas, con el ejemplo y con juegos al azar."""

from __future__ import annotations

import datetime as dt
import time
from pathlib import Path
from typing import Any

import pytest

from cartera.datos import integridad
from cartera.datos.modelos import Movimientos, PreciosDiarios, Tenencias
from cartera.motor.base import Datos
from cartera.motor.costos import calcular_costos
from cartera.motor.series import calcular_serie
from tests.conftest import EJEMPLO, TOL_PP, TOL_USD, correr_referencia, datos_de, escribir_json
from tests.generador import generar

CAMPOS = ("tot", "min", "inm", "deu", "pat", "flow", "flowP", "cumF", "cumFP", "capT", "capP")
SEMILLAS = range(1, 25)


def comparar_con_referencia(carpeta: Path) -> int:
    ref: dict[str, Any] = correr_referencia(carpeta)
    datos = datos_de(carpeta)
    serie = calcular_serie(datos)
    assert [r.t for r in serie.filas] == [r["t"] for r in ref["rows"]]
    for mio, suyo in zip(serie.filas, ref["rows"], strict=True):
        for k in CAMPOS:
            assert getattr(mio, k) == pytest.approx(suyo[k], abs=TOL_USD), (mio.t, k)
        assert (mio.idx - 1) * 100 == pytest.approx((suyo["idx"] - 1) * 100, abs=TOL_PP), mio.t
        assert (mio.idxP - 1) * 100 == pytest.approx((suyo["idxP"] - 1) * 100, abs=TOL_PP), mio.t
        assert set(mio.pos) == set(suyo["pos"])
        for t, v in suyo["pos"].items():
            assert mio.pos[t] == pytest.approx(v, abs=TOL_USD), (mio.t, t)
    costos = calcular_costos(datos).por_activo
    assert set(costos) == set(ref["COST"])
    for t, v in ref["COST"].items():
        assert costos[t].costo == pytest.approx(v["costo_usd"], abs=TOL_USD), t
        assert costos[t].promedio == pytest.approx(v["costo_promedio"], rel=1e-6), t
    return len(serie.filas)


def test_ejemplo_todas_las_fechas() -> None:
    assert comparar_con_referencia(EJEMPLO) == 120


@pytest.mark.parametrize("semilla", SEMILLAS)
def test_juego_aleatorio(semilla: int, tmp_path: Path) -> None:
    for nombre, contenido in generar(semilla).items():
        escribir_json(tmp_path / nombre, contenido)
    datos = datos_de(tmp_path)
    # los juegos generados son datos válidos: pasan las mismas reglas que los del usuario
    assert integridad.verificar(datos.tenencias, datos.movimientos, datos.precios) == []
    assert comparar_con_referencia(tmp_path) >= 100


def test_los_juegos_cubren_todos_los_casos() -> None:
    """Entre todas las semillas aparecen todos los tipos de movimiento y las dos clases de cuota cancelada."""
    tipos: set[str] = set()
    canceladas: set[bool] = set()
    destinos: set[str] = set()
    for s in SEMILLAS:
        juego = generar(s)
        movs = juego["movimientos.json"]["movimientos"]
        tipos |= {m["tipo"] for m in movs}
        destinos |= {m["destino"] for m in movs if m.get("destino")}
        canceladas |= {
            bool(c.get("pagada_desde_cartera")) for c in juego["tenencias.json"]["pasivos"][0]["cuotas_canceladas"]
        }
    assert tipos == {
        "Saldo inicial",
        "Compra",
        "Venta",
        "Pago",
        "Cobro",
        "Minería",
        "Costo minería",
        "Conversión",
        "Aporte",
        "Compra de bienes",
        "Interés Nexo",
    }
    assert canceladas == {True, False}
    assert destinos == {"Mineros", "Terreno Ficticio", "Auto Ficticio"}


def test_rendimiento_rt04() -> None:
    """RT-04: recalcular 1.500 fechas × 30 activos tarda menos de 1 s."""
    juego = generar(7)
    base = juego["precios_diarios.json"]["serie"]
    extra = [f"T{i:02d}" for i in range(24)]
    serie = []
    for i in range(1500):
        fila = dict(base[i % len(base)])
        fila["fecha"] = (dt.date(2021, 1, 1) + dt.timedelta(i)).isoformat()
        fila["ars"] = {**fila["ars"], **{t: 1000.0 + i for t in extra}}
        serie.append(fila)
    ten = juego["tenencias.json"]
    ten["activos"] += [
        {
            "ticker": t,
            "nombre": t,
            "tipo": "CEDEARs",
            "grupo": "CEDEARs · Balanz",
            "cantidad": 10,
            "cotiza_en_pesos": True,
            "valor_fijo_usd": False,
        }
        for t in extra
    ]
    movs = juego["movimientos.json"]["movimientos"]
    movs = [{**m, "fecha": serie[(i * 7) % 1500]["fecha"], "devengo_diario": None} for i, m in enumerate(movs * 20)]
    datos = Datos(
        Tenencias.model_validate({**ten, "pasivos": [], "inmuebles": []}),
        Movimientos.model_validate(
            {"movimientos": [{k: v for k, v in m.items() if v is not None and k != "destino"} for m in movs]}
        ).movimientos,
        PreciosDiarios.model_validate({"desde": serie[0]["fecha"], "hasta": serie[-1]["fecha"], "serie": serie}).serie,
    )
    assert len(datos.activos) >= 30 and len(datos.movimientos) > 500
    t0 = time.perf_counter()
    calcular_serie(datos)
    assert time.perf_counter() - t0 < 1.0

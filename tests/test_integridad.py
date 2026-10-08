"""Reglas de integridad de 4.4, una por una, y validaciones de los esquemas de 4.5."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from cartera.datos import integridad
from cartera.datos.modelos import Movimiento, Movimientos, PreciosDiarios, Tenencias
from cartera.datos.repositorio import MOVIMIENTOS, PRECIOS, TENENCIAS
from tests.conftest import EJEMPLO, RAIZ, leer_json

Json = dict[str, Any]


def verificar(cambio: Callable[[Json, Json, Json], None] | None = None) -> list[str]:
    """Errores de integridad del ejemplo después de aplicarle `cambio(tenencias, movimientos, precios)`."""
    ten, mov, pre = (leer_json(EJEMPLO / n) for n in (TENENCIAS, MOVIMIENTOS, PRECIOS))
    if cambio:
        cambio(ten, mov, pre)
    return integridad.verificar(
        Tenencias.model_validate(ten),
        Movimientos.model_validate(mov).movimientos,
        PreciosDiarios.model_validate(pre).serie,
    )


def un_error(errores: list[str], texto: str) -> None:
    assert len(errores) == 1 and texto in errores[0], errores


def test_el_ejemplo_esta_integro() -> None:
    assert verificar() == []


def test_activo_inexistente() -> None:
    def cambio(_t: Json, m: Json, _p: Json) -> None:
        m["movimientos"][16]["activo"] = "EUR billete"

    un_error(verificar(cambio), "el activo no existe en tenencias.activos")


def test_destino_inexistente() -> None:
    def cambio(_t: Json, m: Json, _p: Json) -> None:
        m["movimientos"][5]["destino"] = "Lancha"

    un_error(verificar(cambio), "el destino «Lancha» no es un bien de tenencias.inmuebles ni «Mineros»")


def test_cantidad_historica_negativa() -> None:
    """Un costo de minería de 6000 USDT el 01/02 deja el saldo en −1000 ese día (había 5000)."""

    def cambio(t: Json, m: Json, _p: Json) -> None:
        m["movimientos"][7]["cantidad"] = -6000.0
        next(a for a in t["activos"] if a["ticker"] == "USDT")["cantidad"] = 5049.29 - 5700

    errores = verificar(cambio)
    assert any("La cantidad histórica de USDT queda negativa (-1000) desde el 2025-02-01" in e for e in errores), (
        errores
    )


def test_cuotas_pagas_repetidas_o_desordenadas() -> None:
    def repetida(t: Json, _m: Json, _p: Json) -> None:
        t["pasivos"][0]["cuotas_pagas"][1]["cuota"] = 1

    un_error(verificar(repetida), "números de cuota repetidos en cuotas_pagas")

    def desordenada(t: Json, _m: Json, _p: Json) -> None:
        t["pasivos"][0]["cuotas_pagas"][3]["fecha"] = "2025-02-20"

    un_error(verificar(desordenada), "las fechas de cuotas_pagas no están ordenadas")


def test_cuota_paga_y_cancelada_a_la_vez() -> None:
    def cambio(t: Json, _m: Json, _p: Json) -> None:
        t["pasivos"][0]["cuotas_canceladas"][0]["cuota"] = 3

    un_error(verificar(cambio), "las cuotas [3] figuran como pagas y como canceladas")


def test_cancelada_desde_la_cartera_exige_el_movimiento() -> None:
    """`pagada_desde_cartera` necesita un movimiento de salida con destino al bien, de la misma fecha."""

    def sin_movimiento(_t: Json, m: Json, _p: Json) -> None:
        del m["movimientos"][18]  # la compra de bienes del 20/04 con destino al auto

    def compensar(t: Json) -> None:
        next(a for a in t["activos"] if a["ticker"] == "USD Balanz")["cantidad"] = 260.0

    def cambio(t: Json, m: Json, p: Json) -> None:
        sin_movimiento(t, m, p)
        compensar(t)

    un_error(verificar(cambio), "la cuota cancelada 11 (2025-04-20) está marcada como pagada desde la cartera")

    def otra_fecha(_t: Json, m: Json, _p: Json) -> None:
        m["movimientos"][18]["fecha"] = "2025-04-21"

    un_error(verificar(otra_fecha), "no hay un movimiento de salida con destino «Auto Ejemplo» en esa fecha")

    def otro_destino(_t: Json, m: Json, _p: Json) -> None:
        m["movimientos"][18]["destino"] = "Terreno Ejemplo"

    un_error(verificar(otro_destino), "pagada desde la cartera")

    # la que se pagó con plata de afuera no necesita ningún movimiento
    def las_dos_de_afuera(t: Json, m: Json, p: Json) -> None:
        cambio(t, m, p)
        t["pasivos"][0]["cuotas_canceladas"][1]["pagada_desde_cartera"] = False

    assert verificar(las_dos_de_afuera) == []


def test_serie_con_hueco() -> None:
    def cambio(_t: Json, _m: Json, p: Json) -> None:
        del p["serie"][40]  # falta el 10/02

    errores = verificar(cambio)
    assert any("hueco o un desorden entre 2025-02-09 y 2025-02-11" in e for e in errores), errores


def test_falta_precio_con_tenencia() -> None:
    def cambio(_t: Json, _m: Json, p: Json) -> None:
        p["serie"][20]["ars"]["SPY"] = 0  # 21/01: hay 100 SPY
        del p["serie"][3]["ars"]["SPY"]  # 04/01: todavía no había SPY, no es un problema

    un_error(verificar(cambio), "Falta el precio de SPY el 2025-01-21")


def test_solo_btc_puede_no_cotizar_en_pesos_ni_ser_fijo() -> None:
    def cambio(t: Json, _m: Json, _p: Json) -> None:
        t["activos"].append(
            {
                "ticker": "ETH",
                "nombre": "Ether",
                "tipo": "Cripto",
                "grupo": "Cripto · Nexo",
                "cantidad": 0,
                "cotiza_en_pesos": False,
                "valor_fijo_usd": False,
            }
        )

    un_error(verificar(cambio), "ETH no cotiza en pesos ni es de valor fijo")


def test_ids_repetidos_y_contrapartida_colgada() -> None:
    def cambio(_t: Json, m: Json, _p: Json) -> None:
        m["movimientos"][0]["id"] = m["movimientos"][1]["id"] = "m-0001"
        m["movimientos"][4]["contrapartida_de"] = "m-9999"

    errores = verificar(cambio)
    assert len(errores) == 2
    assert (
        "El id de movimiento m-0001 está repetido." in errores[0] and "contrapartida_de apunta a m-9999" in errores[1]
    )


# --- esquemas (4.5)


def test_tipo_de_movimiento_invalido() -> None:
    with pytest.raises(ValidationError, match="tipo"):
        Movimiento.model_validate({"fecha": "2025-01-01", "tipo": "Permuta", "activo": "SPY", "cantidad": 1})


def test_usd_no_puede_ser_negativo() -> None:
    with pytest.raises(ValidationError, match="usd"):
        Movimiento.model_validate({"fecha": "2025-01-01", "tipo": "Venta", "activo": "SPY", "cantidad": -1, "usd": -10})


@pytest.mark.parametrize("fecha", ["2025-1-5", "05/01/2025", "2025-02-30", "2025-01-01T10:00"])
def test_fechas_solo_iso(fecha: str) -> None:
    with pytest.raises(ValidationError, match="fecha"):
        Movimiento.model_validate({"fecha": fecha, "tipo": "Compra", "activo": "SPY", "cantidad": 1})


def test_esquema_estricto_no_convierte_tipos() -> None:
    with pytest.raises(ValidationError):
        Movimiento.model_validate({"fecha": "2025-01-01", "tipo": "Compra", "activo": "SPY", "cantidad": "100"})
    with pytest.raises(ValidationError):
        Movimiento.model_validate(
            {"fecha": "2025-01-01", "tipo": "Compra", "activo": "SPY", "cantidad": 1, "estimado": "sí"}
        )


def test_pagada_desde_cartera_vale_false_por_defecto() -> None:
    ten = Tenencias.model_validate(leer_json(EJEMPLO / TENENCIAS))
    assert [(c.cuota, c.pagada_desde_cartera) for c in ten.pasivos[0].canceladas()] == [
        (12, False),
        (11, True),
    ]
    # y al guardar no se inventa el campo donde no estaba
    assert "pagada_desde_cartera" not in ten.a_json()["pasivos"][0]["cuotas_canceladas"][0]


# --- CLI


def _correr(script: str, *args: str, demo: bool = False) -> subprocess.CompletedProcess[str]:
    import os

    env = {**os.environ, "CARTERA_DEMO": "1" if demo else "0"}
    return subprocess.run(
        [sys.executable, *script.split(), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=RAIZ,
        env=env,
        check=False,
    )


def test_script_verificar_integridad(tmp_path: Path) -> None:
    ok = _correr("scripts/verificar_integridad.py", demo=True)
    assert ok.returncode == 0 and "pasan todas las verificaciones" in ok.stdout
    vacio = _correr("scripts/verificar_integridad.py", "--datos", str(tmp_path))
    assert vacio.returncode == 1 and "Todavía no hay datos cargados" in vacio.stderr


def test_cli_resumen_del_motor(tmp_path: Path) -> None:
    """RNF-07: `python -m cartera.motor.resumen --fecha AAAA-MM-DD` imprime los totales."""
    r = _correr("-m cartera.motor.resumen", demo=True)
    assert r.returncode == 0, r.stderr
    assert "Mi cartera en dólares · 30/04/25" in r.stdout
    assert "Patrimonio neto            US$ 16.665,06" in r.stdout
    assert "cartera +5,75% · patrimonio −7,11%" in r.stdout

    r = _correr("-m cartera.motor.resumen", "--fecha", "2025-03-25", "--datos", str(EJEMPLO))
    assert r.returncode == 0 and "Pasivos                      −US$ 800,00" in r.stdout

    fuera = _correr("-m cartera.motor.resumen", "--fecha", "2030-01-01", demo=True)
    assert fuera.returncode == 1 and "no está en la serie" in fuera.stderr
    vacio = _correr("-m cartera.motor.resumen", "--datos", str(tmp_path))
    assert vacio.returncode == 1 and "Todavía no hay datos cargados" in vacio.stderr

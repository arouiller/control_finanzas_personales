"""Fixtures comunes. Ningún test usa la red: todo sale de `referencia/ejemplo/` o de datos generados."""

from __future__ import annotations

import contextlib
import io
import json
import runpy
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from cartera.datos.modelos import Movimientos, PreciosDiarios, Tenencias
from cartera.datos.repositorio import MOVIMIENTOS, PRECIOS, TENENCIAS, Repositorio
from cartera.motor.base import Datos
from cartera.motor.series import Serie, calcular_serie

RAIZ = Path(__file__).resolve().parent.parent
EJEMPLO = RAIZ / "referencia" / "ejemplo"
REFERENCIA = RAIZ / "referencia" / "calculo_referencia.py"
ARCHIVOS = (TENENCIAS, MOVIMIENTOS, PRECIOS)

TOL_USD = 0.02  # tolerancias de 0.3: ±0,02 USD y ±0,01 puntos porcentuales
TOL_PP = 0.01


def leer_json(ruta: Path) -> dict[str, Any]:
    return json.loads(ruta.read_text(encoding="utf-8"))


def escribir_json(ruta: Path, datos: dict[str, Any]) -> None:
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")


def datos_de(carpeta: Path) -> Datos:
    return Datos(
        Tenencias.model_validate(leer_json(carpeta / TENENCIAS)),
        Movimientos.model_validate(leer_json(carpeta / MOVIMIENTOS)).movimientos,
        PreciosDiarios.model_validate(leer_json(carpeta / PRECIOS)).serie,
    )


def correr_referencia(carpeta: Path) -> dict[str, Any]:
    """Ejecuta `calculo_referencia.py` sobre una carpeta y devuelve sus variables (`rows`, `COST`, `mineria`)."""
    argv = [str(REFERENCIA), *(str(carpeta / n) for n in (PRECIOS, TENENCIAS, MOVIMIENTOS))]
    viejo = sys.argv
    sys.argv = argv
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            return runpy.run_path(str(REFERENCIA))
    finally:
        sys.argv = viejo


def copiar_ejemplo(destino: Path) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    for n in ARCHIVOS:
        shutil.copy(EJEMPLO / n, destino / n)
    return destino


@pytest.fixture(scope="session")
def datos() -> Datos:
    return datos_de(EJEMPLO)


@pytest.fixture(scope="session")
def serie(datos: Datos) -> Serie:
    return calcular_serie(datos)


@pytest.fixture(scope="session")
def control() -> dict[str, Any]:
    return leer_json(EJEMPLO / "valores_control.json")


@pytest.fixture(scope="session")
def precios() -> dict[str, dict[str, Any]]:
    """Precios crudos del ejemplo por fecha, para rehacer cuentas a mano en los tests."""
    return {r["fecha"]: r for r in leer_json(EJEMPLO / PRECIOS)["serie"]}


@pytest.fixture
def carpeta_ejemplo(tmp_path: Path) -> Path:
    """Copia del ejemplo en una carpeta temporal (como la que subiría el usuario)."""
    return copiar_ejemplo(tmp_path / "origen")


@pytest.fixture
def repo(tmp_path: Path) -> Repositorio:
    """Repositorio temporal con el ejemplo ya cargado."""
    return Repositorio(copiar_ejemplo(tmp_path / "datos"))

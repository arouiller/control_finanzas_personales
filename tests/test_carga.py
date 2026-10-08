"""T-12: carga de datos (4.3). Normalización, rechazo con detalle y backup antes de reemplazar."""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from cartera.datos.carga import (
    ErrorCarga,
    aplicar_carga,
    config_por_defecto,
    fuentes_propuestas,
    normalizar_movimientos,
    preparar_carga,
)
from cartera.datos.modelos import Tenencias
from cartera.datos.repositorio import CONFIG, FUENTES, MOVIMIENTOS, PRECIOS, TENENCIAS, Repositorio
from tests.conftest import RAIZ, escribir_json, leer_json

# --- normalización (paso 2)


def test_el_ejemplo_no_trae_id_ni_contrapartida(carpeta_ejemplo: Path) -> None:
    movs = leer_json(carpeta_ejemplo / MOVIMIENTOS)["movimientos"]
    assert not any("id" in m or "contrapartida_de" in m for m in movs)


def test_normaliza_ids_y_contrapartidas(carpeta_ejemplo: Path) -> None:
    carga = preparar_carga(carpeta_ejemplo)
    movs = carga.archivos[MOVIMIENTOS]["movimientos"]
    # ids estables, en el orden del archivo
    assert [m["id"] for m in movs] == [f"m-{i:04d}" for i in range(1, len(movs) + 1)]
    assert carga.resumen.ids_asignados == len(movs) == 19
    # cada Pago o Cobro apunta al movimiento anterior que no es Pago ni Cobro
    por_id = {m["id"]: m for m in movs}
    contrapartidas = {m["id"]: m["contrapartida_de"] for m in movs if m["tipo"] in ("Pago", "Cobro")}
    assert contrapartidas == {"m-0005": "m-0004", "m-0010": "m-0009", "m-0013": "m-0012"}
    assert (por_id["m-0004"]["tipo"], por_id["m-0004"]["activo"]) == ("Compra", "XYZ")
    assert (por_id["m-0009"]["tipo"], por_id["m-0009"]["activo"]) == ("Conversión", "BTC")
    assert (por_id["m-0012"]["tipo"], por_id["m-0012"]["activo"]) == ("Venta", "XYZ")
    assert carga.resumen.contrapartidas_asignadas == 3
    # el resto no recibe contrapartida
    assert not any("contrapartida_de" in m for m in movs if m["tipo"] not in ("Pago", "Cobro"))


def test_dos_pagos_seguidos_apuntan_a_la_misma_operacion() -> None:
    crudo = {
        "movimientos": [
            {"tipo": "Compra"},
            {"tipo": "Pago"},
            {"tipo": "Pago"},
            {"tipo": "Venta"},
            {"tipo": "Cobro"},
        ]
    }
    movs = normalizar_movimientos(crudo)[0]["movimientos"]
    assert [m.get("contrapartida_de") for m in movs] == [None, "m-0001", "m-0001", None, "m-0004"]


def test_respeta_ids_y_contrapartidas_existentes() -> None:
    crudo = {
        "movimientos": [
            {"id": "m-0002", "tipo": "Compra"},
            {"tipo": "Venta"},
            {"tipo": "Cobro", "contrapartida_de": "m-0002"},
            {"tipo": "Aporte"},
        ]
    }
    movs, ids, contrapartidas = normalizar_movimientos(crudo)
    assert [m["id"] for m in movs["movimientos"]] == [
        "m-0002",
        "m-0001",
        "m-0003",
        "m-0004",
    ]  # saltea los usados
    assert movs["movimientos"][2]["contrapartida_de"] == "m-0002"
    assert (ids, contrapartidas) == (3, 0)
    assert "id" not in crudo["movimientos"][1]  # no modifica la entrada


def test_conserva_campos_desconocidos_y_columna_precio(carpeta_ejemplo: Path, tmp_path: Path) -> None:
    ten = leer_json(carpeta_ejemplo / TENENCIAS)
    ten["activos"][0]["columna_precio"] = 4  # obsoleto: se conserva y se ignora
    ten["campo_del_usuario"] = {"a": 1}
    escribir_json(carpeta_ejemplo / TENENCIAS, ten)
    mov = leer_json(carpeta_ejemplo / MOVIMIENTOS)
    mov["movimientos"][0]["etiqueta_propia"] = "x"
    escribir_json(carpeta_ejemplo / MOVIMIENTOS, mov)

    repo = Repositorio(tmp_path / "datos")
    aplicar_carga(preparar_carga(carpeta_ejemplo), repo, tmp_path / "backups")
    guardado = repo.leer_crudo(TENENCIAS)[0]
    assert guardado["activos"][0]["columna_precio"] == 4 and guardado["campo_del_usuario"] == {"a": 1}
    assert repo.leer_crudo(MOVIMIENTOS)[0]["movimientos"][0]["etiqueta_propia"] == "x"
    # y pasan por los modelos sin perderse
    assert repo.tenencias().a_json()["activos"][0]["columna_precio"] == 4


# --- resumen y escritura (pasos 4 y 5)


def test_resumen_de_la_carga(carpeta_ejemplo: Path) -> None:
    r = preparar_carga(carpeta_ejemplo).resumen
    assert (r.activos, r.movimientos) == (6, 19)
    assert (r.primer_movimiento, r.ultimo_movimiento) == ("2025-01-01", "2025-04-20")
    assert (r.serie_desde, r.serie_hasta, r.fecha) == ("2025-01-01", "2025-04-30", "2025-04-30")
    assert round(r.patrimonio_neto, 2) == 16665.06
    assert round(r.activos_financieros, 2) == 10999.56


def test_preparar_no_escribe_nada(carpeta_ejemplo: Path) -> None:
    antes = {f.name: f.read_bytes() for f in carpeta_ejemplo.iterdir()}
    preparar_carga(carpeta_ejemplo)
    assert {f.name: f.read_bytes() for f in carpeta_ejemplo.iterdir()} == antes


def test_primera_carga_crea_config_y_fuentes(carpeta_ejemplo: Path, tmp_path: Path) -> None:
    repo = Repositorio(tmp_path / "datos")
    backup = aplicar_carga(preparar_carga(carpeta_ejemplo), repo, tmp_path / "backups")
    assert backup is None and not (tmp_path / "backups").exists()  # no había nada que resguardar
    assert all(repo.existe(n) for n in (TENENCIAS, MOVIMIENTOS, PRECIOS, CONFIG, FUENTES))
    assert repo.movimientos().movimientos[4].contrapartida_de == "m-0004"

    cfg = repo.config()
    assert cfg.inicio_serie == "2023-01-01" and cfg.hora_job == "20:45"
    assert (
        cfg.colores["SPY"].claro == "#e87ba4" and cfg.colores["USD Balanz"].oscuro == "#199e70"
    )  # del HTML de referencia
    assert set(cfg.colores) == {
        "SPY",
        "XYZ",
        "BTC",
        "USDT",
        "USD Balanz",
        "USD billete",
    }  # XYZ recibe uno de la paleta
    assert {a.activo for a in cfg.ajustes_cantidades} == {"SPY", "AAPL", "MELI", "NVDA", "AVGO"}

    fuentes = repo.leer_crudo(FUENTES)[0]
    assert fuentes["activos"] == {
        "SPY": {"simbolo_yahoo": "SPY.BA", "factor": 1.0},
        "XYZ": {"simbolo_yahoo": "XYZ.BA", "factor": 1.0},
    }


def test_con_datos_previos_hace_backup_antes_de_reemplazar(
    carpeta_ejemplo: Path, repo: Repositorio, tmp_path: Path
) -> None:
    previo = repo.ruta(TENENCIAS).read_bytes()
    ten = leer_json(carpeta_ejemplo / TENENCIAS)
    ten["inmuebles"][0]["valor_usd"] = 700
    escribir_json(carpeta_ejemplo / TENENCIAS, ten)

    backup = aplicar_carga(preparar_carga(carpeta_ejemplo), repo, tmp_path / "backups")
    assert backup is not None and backup.parent == tmp_path / "backups" and backup.name.startswith("precarga-")
    with zipfile.ZipFile(backup) as z:
        assert {TENENCIAS, MOVIMIENTOS, PRECIOS} <= set(z.namelist())
        assert z.read(TENENCIAS) == previo  # el backup tiene lo de antes
    assert repo.tenencias().inmuebles[0].valor_usd == 700  # y los datos, lo nuevo
    assert len(repo.versiones(TENENCIAS)) == 1


def test_no_pisa_fuentes_ni_config_existentes(carpeta_ejemplo: Path, repo: Repositorio, tmp_path: Path) -> None:
    repo.escribir(FUENTES, {"activos": {"SPY": {"simbolo_yahoo": "SPY.BA", "factor": 2}}})
    repo.escribir(
        CONFIG,
        {
            "inicio_serie": "2024-06-01",
            "colores": {"SPY": {"claro": "#111111", "oscuro": "#222222", "atenuado": "#333333"}},
        },
    )
    aplicar_carga(preparar_carga(carpeta_ejemplo), repo, tmp_path / "backups")
    assert repo.leer_crudo(FUENTES)[0]["activos"]["SPY"]["factor"] == 2
    cfg = repo.config()
    assert cfg.inicio_serie == "2024-06-01" and cfg.colores["SPY"].claro == "#111111"
    assert "BTC" in cfg.colores  # solo se agregan los colores que faltaban


# --- rechazos


def test_cantidad_negativa_se_rechaza_con_el_detalle(carpeta_ejemplo: Path, tmp_path: Path) -> None:
    # la cantidad actual dice 10 SPY, pero los movimientos suman 50: hacia atrás, el saldo inicial da −40
    ten = leer_json(carpeta_ejemplo / TENENCIAS)
    next(a for a in ten["activos"] if a["ticker"] == "SPY")["cantidad"] = 10
    escribir_json(carpeta_ejemplo / TENENCIAS, ten)

    with pytest.raises(ErrorCarga) as err:
        preparar_carga(carpeta_ejemplo)
    detalle = "\n".join(err.value.errores)
    assert "La cantidad histórica de SPY queda negativa (-40) desde el 2025-01-01" in detalle

    repo = Repositorio(tmp_path / "datos")
    assert repo.vacio()


def test_en_f1_precios_diarios_es_obligatorio(carpeta_ejemplo: Path) -> None:
    (carpeta_ejemplo / PRECIOS).unlink()
    with pytest.raises(ErrorCarga, match=r"Falta precios_diarios\.json"):
        preparar_carga(carpeta_ejemplo)


def test_esquema_invalido_se_rechaza_con_el_campo(carpeta_ejemplo: Path) -> None:
    ten = leer_json(carpeta_ejemplo / TENENCIAS)
    ten["activos"][0]["valor_fijo_usd"] = True  # SPY cotiza en pesos: no puede ser las dos cosas
    ten["activos"][1]["tipo"] = "Bonos"
    escribir_json(carpeta_ejemplo / TENENCIAS, ten)
    with pytest.raises(ErrorCarga) as err:
        preparar_carga(carpeta_ejemplo)
    detalle = "\n".join(err.value.errores)
    assert "activos.0" in detalle and "no pueden ser los dos true" in detalle and "activos.1.tipo" in detalle


def test_json_roto(carpeta_ejemplo: Path) -> None:
    (carpeta_ejemplo / MOVIMIENTOS).write_text('{"movimientos": [', encoding="utf-8")
    with pytest.raises(ErrorCarga, match="no es un JSON válido"):
        preparar_carga(carpeta_ejemplo)


# --- valores por defecto


def test_fuentes_propuestas_con_reglas_especiales() -> None:
    def activo(t: str, ars: bool = True) -> dict[str, object]:
        return {
            "ticker": t,
            "nombre": t,
            "tipo": "CEDEARs",
            "grupo": "CEDEARs · Balanz",
            "cantidad": 1,
            "cotiza_en_pesos": ars,
            "valor_fijo_usd": False,
        }

    ten = Tenencias.model_validate(
        {
            "activos": [
                activo("META"),
                activo("AAPL"),
                activo("YPFD"),
                activo("AVGO"),
                activo("BTC", ars=False),
            ]
        }
    )
    f = fuentes_propuestas(ten)
    assert f.activos["META"].ratio_ny == 24 and f.activos["META"].simbolo_yahoo == "META"
    assert f.activos["AAPL"].simbolo_yahoo == "AAPL.BA" and f.activos["AAPL"].factor == 1
    assert f.activos["YPFD"].factor == 10
    assert f.activos["AVGO"].respaldo is not None and f.activos["AVGO"].respaldo.ratio_ny == 38.5
    assert "BTC" not in f.activos  # el BTC sale de Binance
    assert {(a.activo, a.antes_de) for a in f.ajustes_historicos} == {
        ("AAPL", "2024-01-24"),
        ("AVGO", "2026-09-29"),
    }
    assert config_por_defecto(ten).colores["META"].claro == "#1d4ed8"


# --- CLI


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "cargar_datos.py"), *args],
        capture_output=True, text=True, encoding="utf-8", input="n\n", cwd=RAIZ, check=False,
    )  # fmt: skip


def test_cli_pide_confirmacion_y_no_escribe_si_decis_que_no(carpeta_ejemplo: Path, tmp_path: Path) -> None:
    r = _cli(str(carpeta_ejemplo), "--datos", str(tmp_path / "datos"), "--backups", str(tmp_path / "backups"))
    assert r.returncode == 1
    assert "Patrimonio neto al 30/04/25: US$ 16.665,06" in r.stdout and "No se escribió nada." in r.stdout
    assert not (tmp_path / "datos").exists()


def test_cli_con_si_carga_los_datos(carpeta_ejemplo: Path, tmp_path: Path) -> None:
    destino = tmp_path / "datos"
    r = _cli(str(carpeta_ejemplo), "--datos", str(destino), "--backups", str(tmp_path / "backups"), "--si")
    assert r.returncode == 0, r.stderr
    assert "Movimientos:  19" in r.stdout and "Datos cargados." in r.stdout
    assert Repositorio(destino).movimientos().movimientos[0].id == "m-0001"

    # segunda carga sobre datos existentes: avisa y deja el backup
    r = _cli(str(carpeta_ejemplo), "--datos", str(destino), "--backups", str(tmp_path / "backups"), "--si")
    assert r.returncode == 0, r.stderr
    assert "Backup de los datos anteriores" in r.stdout
    assert len(list((tmp_path / "backups").glob("precarga-*.zip"))) == 1


def test_cli_rechaza_y_explica(carpeta_ejemplo: Path, tmp_path: Path) -> None:
    (carpeta_ejemplo / PRECIOS).unlink()
    r = _cli(str(carpeta_ejemplo), "--datos", str(tmp_path / "datos"), "--si")
    assert r.returncode == 1 and "Falta precios_diarios.json" in r.stderr
    assert not (tmp_path / "datos").exists()

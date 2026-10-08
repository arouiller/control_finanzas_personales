"""T-06: repositorio JSON. Escritura atómica, locks, versionado, conflicto de versión y rollback entre dos archivos."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import pytest

from cartera.datos import repositorio as modulo
from cartera.datos.integridad import ErrorIntegridad
from cartera.datos.repositorio import (
    AUDITORIA,
    MOVIMIENTOS,
    PRECIOS,
    TENENCIAS,
    ConflictoVersion,
    ErrorRepositorio,
    ErrorValidacion,
    Repositorio,
    diferencias,
)

Json = dict[str, Any]


def _con_nota(repo: Repositorio, nota: str) -> Json:
    """`movimientos.json` con la nota del primer movimiento cambiada (un cambio válido cualquiera)."""
    datos, _ = repo.leer_crudo(MOVIMIENTOS)
    datos["movimientos"][0]["nota"] = nota
    return datos


def _sin_temporales(repo: Repositorio) -> bool:
    return not list(repo.dir.glob("*.tmp"))


# --- RT-20: escritura atómica


def test_fallo_a_mitad_de_escritura_deja_el_original_intacto(
    repo: Repositorio, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = repo.ruta(MOVIMIENTOS).read_bytes()

    def fsync_roto(_fd: int) -> None:
        raise OSError("disco lleno")

    monkeypatch.setattr(os, "fsync", fsync_roto)
    with pytest.raises(OSError, match="disco lleno"):
        repo.escribir(MOVIMIENTOS, _con_nota(repo, "cambio que no llega a escribirse"))
    assert repo.ruta(MOVIMIENTOS).read_bytes() == original
    assert _sin_temporales(repo)
    assert repo.versiones(MOVIMIENTOS) == []


def test_fallo_en_el_reemplazo_deja_el_original_intacto(repo: Repositorio, monkeypatch: pytest.MonkeyPatch) -> None:
    original = repo.ruta(MOVIMIENTOS).read_bytes()

    def replace_roto(_a: Any, _b: Any) -> None:
        raise OSError("corte de luz")

    monkeypatch.setattr(os, "replace", replace_roto)
    with pytest.raises(OSError, match="corte de luz"):
        repo.escribir(MOVIMIENTOS, _con_nota(repo, "x"))
    assert repo.ruta(MOVIMIENTOS).read_bytes() == original
    assert _sin_temporales(repo)


def test_escritura_normal_y_formato_rt25(repo: Repositorio) -> None:
    version = repo.escribir(MOVIMIENTOS, _con_nota(repo, "señal con ñ y acentos: minería"))
    texto = repo.ruta(MOVIMIENTOS).read_text(encoding="utf-8")
    assert repo.version(MOVIMIENTOS) == version
    assert "señal con ñ y acentos: minería" in texto  # UTF-8 sin escapar
    assert '\n "movimientos": [\n  {\n   "' in texto  # sangría de 1 espacio
    assert _sin_temporales(repo)

    precios, _ = repo.leer_crudo(PRECIOS)
    repo.escribir(PRECIOS, precios)
    compacto = repo.ruta(PRECIOS).read_text(encoding="utf-8")
    assert compacto.count("\n") == 1 and '"mep":1000.0' in compacto  # la serie de precios va compacta


# --- RT-21: locks


def test_escritores_concurrentes_no_se_pisan(tmp_path: Path) -> None:
    repo = Repositorio(tmp_path)
    repo.escribir("contador.json", {"n": 0})
    hilos, vueltas = 8, 15
    errores: list[BaseException] = []

    def sumar(datos: dict[str, Json]) -> dict[str, Json]:
        return {"contador.json": {"n": datos["contador.json"]["n"] + 1}}

    def trabajar() -> None:
        try:
            for _ in range(vueltas):
                Repositorio(tmp_path).modificar(("contador.json",), sumar)
        except BaseException as err:
            errores.append(err)

    ts = [threading.Thread(target=trabajar) for _ in range(hilos)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert errores == []
    # sin lock, las lecturas-modificaciones-escrituras cruzadas perderían sumas
    assert repo.leer_crudo("contador.json")[0] == {"n": hilos * vueltas}
    assert json.loads(repo.ruta("contador.json").read_bytes())  # nunca queda a medio escribir


def test_el_lock_bloquea_a_otro_escritor(repo: Repositorio, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(modulo, "TIMEOUT_LOCK", 0.2)
    resultado: list[str] = []

    def otro() -> None:
        try:
            Repositorio(repo.dir).escribir(MOVIMIENTOS, _con_nota(repo, "desde otro hilo"))
            resultado.append("escribió")
        except Exception as err:
            resultado.append(type(err).__name__)

    with repo.bloqueo(MOVIMIENTOS):
        t = threading.Thread(target=otro)
        t.start()
        t.join()
    assert resultado == ["Timeout"]


# --- RT-22: versionado


def test_cada_escritura_guarda_la_version_anterior(repo: Repositorio) -> None:
    original, _ = repo.leer_crudo(MOVIMIENTOS)
    repo.escribir(MOVIMIENTOS, _con_nota(repo, "primera"))
    repo.escribir(MOVIMIENTOS, _con_nota(repo, "segunda"))
    versiones = repo.versiones(MOVIMIENTOS)
    assert len(versiones) == 2  # de la más nueva a la más vieja
    assert repo.leer_version(MOVIMIENTOS, versiones[1].id) == original
    assert repo.leer_version(MOVIMIENTOS, versiones[0].id)["movimientos"][0]["nota"] == "primera"
    assert versiones[0].ruta.parent == repo.dir / "_versiones" / MOVIMIENTOS


def test_restaurar_una_version_tambien_queda_versionado(repo: Repositorio) -> None:
    original, _ = repo.leer_crudo(MOVIMIENTOS)
    repo.escribir(MOVIMIENTOS, _con_nota(repo, "cambio a deshacer"))
    repo.restaurar(MOVIMIENTOS, repo.versiones(MOVIMIENTOS)[-1].id)
    assert repo.leer_crudo(MOVIMIENTOS)[0] == original
    assert len(repo.versiones(MOVIMIENTOS)) == 2
    assert (
        repo.leer_version(MOVIMIENTOS, repo.versiones(MOVIMIENTOS)[0].id)["movimientos"][0]["nota"]
        == "cambio a deshacer"
    )


def test_se_conservan_las_ultimas_100_versiones(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(modulo, "MAX_VERSIONES", 5)
    repo = Repositorio(tmp_path)
    for i in range(9):
        repo.escribir("contador.json", {"n": i})
    versiones = repo.versiones("contador.json")
    assert len(versiones) == 5
    # quedan las cinco más nuevas, en orden aunque se hayan escrito en el mismo segundo
    assert [repo.leer_version("contador.json", v.id)["n"] for v in versiones] == [7, 6, 5, 4, 3]


# --- RT-23: concurrencia optimista


def test_conflicto_de_version(repo: Repositorio) -> None:
    _, version_leida = repo.leer_crudo(MOVIMIENTOS)
    mi_cambio = _con_nota(repo, "mi cambio")
    repo.escribir(MOVIMIENTOS, _con_nota(repo, "otro llegó antes"), version_esperada=version_leida)
    with pytest.raises(ConflictoVersion) as err:
        repo.escribir(MOVIMIENTOS, mi_cambio, version_esperada=version_leida)
    assert err.value.archivo == MOVIMIENTOS
    assert repo.leer_crudo(MOVIMIENTOS)[0]["movimientos"][0]["nota"] == "otro llegó antes"
    # con la versión actual sí entra
    repo.escribir(MOVIMIENTOS, mi_cambio, version_esperada=repo.version(MOVIMIENTOS))
    assert repo.leer_crudo(MOVIMIENTOS)[0]["movimientos"][0]["nota"] == "mi cambio"


# --- transacción entre dos archivos


def _compra(repo: Repositorio) -> tuple[Json, Json]:
    """Una compra de 5 SPY: cambia movimientos.json y la cantidad actual en tenencias.json."""
    ten, _ = repo.leer_crudo(TENENCIAS)
    mov, _ = repo.leer_crudo(MOVIMIENTOS)
    mov["movimientos"].append(
        {
            "id": "m-9001",
            "fecha": "2025-04-25",
            "tipo": "Compra",
            "activo": "SPY",
            "cantidad": 5,
            "usd": 60.0,
            "flujo_usd": 60.0,
        }
    )
    next(a for a in ten["activos"] if a["ticker"] == "SPY")["cantidad"] += 5
    return ten, mov


def test_transaccion_escribe_los_dos_archivos(repo: Repositorio) -> None:
    ten, mov = _compra(repo)
    versiones = repo.transaccion({TENENCIAS: ten, MOVIMIENTOS: mov}, accion="alta de movimiento", id_objeto="m-9001")
    assert set(versiones) == {TENENCIAS, MOVIMIENTOS}
    assert repo.tenencias().activo("SPY").cantidad == 55  # type: ignore[union-attr]
    assert repo.movimientos().movimientos[-1].id == "m-9001"
    assert len(repo.versiones(TENENCIAS)) == len(repo.versiones(MOVIMIENTOS)) == 1


def test_rollback_si_falla_el_segundo_archivo(repo: Repositorio, monkeypatch: pytest.MonkeyPatch) -> None:
    antes = {n: repo.ruta(n).read_bytes() for n in (TENENCIAS, MOVIMIENTOS)}
    ten, mov = _compra(repo)
    real = os.replace
    llamadas = 0

    def falla_en_la_segunda(a: Any, b: Any) -> None:
        nonlocal llamadas
        llamadas += 1
        if llamadas == 2:
            raise OSError("falló el segundo reemplazo")
        real(a, b)

    monkeypatch.setattr(os, "replace", falla_en_la_segunda)
    with pytest.raises(OSError, match="segundo reemplazo"):
        repo.transaccion({TENENCIAS: ten, MOVIMIENTOS: mov})
    monkeypatch.undo()
    assert llamadas >= 3  # primer archivo, intento del segundo y restauración del primero
    assert {n: repo.ruta(n).read_bytes() for n in antes} == antes
    assert _sin_temporales(repo)
    assert not repo.existe(AUDITORIA)  # lo que no se escribió no queda auditado


# --- RT-24: validación antes de escribir


def test_esquema_invalido_no_se_escribe(repo: Repositorio) -> None:
    original = repo.ruta(MOVIMIENTOS).read_bytes()
    datos = _con_nota(repo, "x")
    datos["movimientos"][0]["tipo"] = "Trueque"
    datos["movimientos"][1]["usd"] = -5
    with pytest.raises(ErrorValidacion) as err:
        repo.escribir(MOVIMIENTOS, datos)
    assert "movimientos.0.tipo" in err.value.detalle and "movimientos.1.usd" in err.value.detalle
    assert repo.ruta(MOVIMIENTOS).read_bytes() == original
    assert repo.versiones(MOVIMIENTOS) == []


def test_integridad_rota_no_se_escribe(repo: Repositorio) -> None:
    original = repo.ruta(MOVIMIENTOS).read_bytes()
    datos = _con_nota(repo, "x")
    datos["movimientos"][2]["activo"] = "NOEXISTE"
    with pytest.raises(ErrorIntegridad) as err:
        repo.escribir(MOVIMIENTOS, datos)
    assert any("NOEXISTE" in e or "no existe en tenencias.activos" in e for e in err.value.errores)
    assert repo.ruta(MOVIMIENTOS).read_bytes() == original


def test_nombres_de_archivo_fuera_de_la_carpeta(repo: Repositorio) -> None:
    for nombre in ("../afuera.json", "sub/archivo.json", "tenencias.txt"):
        with pytest.raises(ErrorRepositorio):
            repo.escribir(nombre, {})


# --- auditoría


def test_auditoria_registra_el_cambio(repo: Repositorio) -> None:
    repo.escribir(MOVIMIENTOS, _con_nota(repo, "nota nueva"), accion="editar movimiento", id_objeto="m-0001")
    registros = repo.leer_crudo(AUDITORIA)[0]["registros"]
    assert len(registros) == 1
    r = registros[0]
    assert r["accion"] == "editar movimiento" and r["archivo"] == MOVIMIENTOS and r["id"] == "m-0001"
    assert r["cambios"] == 1 and r["diff"][0]["despues"] == "nota nueva"
    assert r["ts"].endswith("-03:00")  # hora de Buenos Aires


def test_diferencias_por_id() -> None:
    antes = {"movimientos": [{"id": "a", "usd": 1}, {"id": "b", "usd": 2}]}
    despues = {"movimientos": [{"id": "a", "usd": 1}, {"id": "b", "usd": 3}, {"id": "c", "usd": 4}]}
    assert diferencias(antes, despues) == [
        {"ruta": "movimientos[b].usd", "antes": 2, "despues": 3},
        {"ruta": "movimientos[c]", "antes": None, "despues": {"id": "c", "usd": 4}},
    ]


def test_repositorio_vacio(tmp_path: Path) -> None:
    """RT-26: sin datos la app arranca igual; no se crea nada de ejemplo."""
    repo = Repositorio(tmp_path / "datos")
    assert repo.vacio()
    assert not (tmp_path / "datos").exists()
    assert repo.config().inicio_serie == "2023-01-01"

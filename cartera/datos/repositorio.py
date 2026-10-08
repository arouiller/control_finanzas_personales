"""Repositorio de archivos JSON (REQUERIMIENTOS 4.2).

Escritura atómica (RT-20), bloqueo por archivo (RT-21), versionado (RT-22), concurrencia optimista
(RT-23), validación antes de escribir (RT-24) y formato (RT-25). Cada cambio queda en `auditoria.json`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from filelock import FileLock
from pydantic import ValidationError

from cartera.datos import integridad
from cartera.datos.modelos import (
    Config,
    FuentesPrecios,
    Modelo,
    Movimientos,
    PreciosDiarios,
    Tenencias,
)

TENENCIAS = "tenencias.json"
MOVIMIENTOS = "movimientos.json"
PRECIOS = "precios_diarios.json"
FUENTES = "fuentes_precios.json"
CONFIG = "config.json"
AUDITORIA = "auditoria.json"

MODELOS: dict[str, type[Modelo]] = {
    TENENCIAS: Tenencias,
    MOVIMIENTOS: Movimientos,
    PRECIOS: PreciosDiarios,
    FUENTES: FuentesPrecios,
    CONFIG: Config,
}
COMPACTOS = frozenset({PRECIOS})
MAX_VERSIONES = 100
MAX_DIFF = 200
TIMEOUT_LOCK = 30.0
ZONA = ZoneInfo("America/Argentina/Buenos_Aires")

Json = dict[str, Any]


class ErrorRepositorio(Exception):
    pass


class ConflictoVersion(ErrorRepositorio):
    """El archivo cambió desde que se leyó (RT-23). La API lo traduce a `409 Conflict`."""

    def __init__(self, archivo: str) -> None:
        super().__init__(f"{archivo} cambió desde que lo leíste. Volvé a cargarlo y repetí el cambio.")
        self.archivo = archivo


class ErrorValidacion(ErrorRepositorio):
    """El contenido no cumple el esquema (RT-24)."""

    def __init__(self, archivo: str, detalle: str) -> None:
        super().__init__(f"{archivo} no es válido:\n{detalle}")
        self.archivo = archivo
        self.detalle = detalle


@dataclass(frozen=True)
class Version:
    id: str
    archivo: str
    ruta: Path
    bytes: int


def ahora() -> dt.datetime:
    return dt.datetime.now(ZONA)


def hash_de(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def serializar(nombre: str, datos: Json) -> bytes:
    """RT-25: UTF-8, sin escapar acentos, sangría de 1 espacio (la serie de precios va compacta)."""
    if nombre in COMPACTOS:
        texto = json.dumps(datos, ensure_ascii=False, separators=(",", ":"))
    else:
        texto = json.dumps(datos, ensure_ascii=False, indent=1)
    return (texto + "\n").encode("utf-8")


def validar(nombre: str, datos: Json) -> Modelo | None:
    """Valida contra el esquema del archivo. Devuelve el modelo, o None si el archivo no tiene esquema."""
    modelo = MODELOS.get(nombre)
    if modelo is None:
        return None
    try:
        return modelo.model_validate(datos)
    except ValidationError as err:
        lineas = [f"{'.'.join(str(p) for p in x['loc']) or '(raíz)'}: {x['msg']}" for x in err.errors()]
        raise ErrorValidacion(nombre, "\n".join(lineas)) from err


def diferencias(antes: Any, despues: Any, ruta: str = "") -> list[Json]:
    """Diff entre dos valores JSON. Las listas de objetos con `id` se comparan por id."""
    if antes == despues:
        return []
    if isinstance(antes, dict) and isinstance(despues, dict):
        out: list[Json] = []
        for k in dict.fromkeys([*antes, *despues]):
            out += diferencias(antes.get(k), despues.get(k), f"{ruta}.{k}" if ruta else str(k))
        return out
    if isinstance(antes, list) and isinstance(despues, list):
        con_id = all(isinstance(x, dict) and x.get("id") is not None for x in [*antes, *despues])
        if con_id and (antes or despues):
            a, d = {x["id"]: x for x in antes}, {x["id"]: x for x in despues}
            out = []
            for k in dict.fromkeys([*a, *d]):
                out += diferencias(a.get(k), d.get(k), f"{ruta}[{k}]")
            return out
        if len(antes) == len(despues):
            out = []
            for i, (x, y) in enumerate(zip(antes, despues, strict=True)):
                out += diferencias(x, y, f"{ruta}[{i}]")
            return out
    return [{"ruta": ruta, "antes": antes, "despues": despues}]


class Repositorio:
    def __init__(self, directorio: Path | str) -> None:
        self.dir = Path(directorio)

    # --- lectura

    def ruta(self, nombre: str) -> Path:
        if Path(nombre).name != nombre or not nombre.endswith(".json"):
            raise ErrorRepositorio(f"Nombre de archivo no permitido: {nombre}")
        return self.dir / nombre

    def existe(self, nombre: str) -> bool:
        return self.ruta(nombre).is_file()

    def vacio(self) -> bool:
        """RT-26: sin tenencias ni movimientos, la app muestra el estado vacío."""
        return not self.existe(TENENCIAS) and not self.existe(MOVIMIENTOS)

    def leer_crudo(self, nombre: str) -> tuple[Json, str]:
        """Contenido y versión (sha256 del archivo, RT-23)."""
        contenido = self.ruta(nombre).read_bytes()
        datos = json.loads(contenido)
        if not isinstance(datos, dict):
            raise ErrorValidacion(nombre, "se esperaba un objeto JSON")
        return datos, hash_de(contenido)

    def version(self, nombre: str) -> str | None:
        ruta = self.ruta(nombre)
        return hash_de(ruta.read_bytes()) if ruta.is_file() else None

    def tenencias(self) -> Tenencias:
        return Tenencias.model_validate(self.leer_crudo(TENENCIAS)[0])

    def movimientos(self) -> Movimientos:
        return Movimientos.model_validate(self.leer_crudo(MOVIMIENTOS)[0])

    def precios(self) -> PreciosDiarios:
        return PreciosDiarios.model_validate(self.leer_crudo(PRECIOS)[0])

    def config(self) -> Config:
        return Config.model_validate(self.leer_crudo(CONFIG)[0]) if self.existe(CONFIG) else Config()

    def marca(self, nombres: tuple[str, ...] = (TENENCIAS, MOVIMIENTOS, PRECIOS)) -> tuple[tuple[int, int], ...]:
        """Fecha de modificación y tamaño de cada archivo: sirve para invalidar la caché del motor (RT-04)."""
        out = []
        for n in nombres:
            try:
                st = self.ruta(n).stat()
                out.append((st.st_mtime_ns, st.st_size))
            except FileNotFoundError:
                out.append((0, 0))
        return tuple(out)

    # --- escritura

    @contextmanager
    def bloqueo(self, *nombres: str) -> Iterator[None]:
        """Lock exclusivo de uno o más archivos, siempre en el mismo orden para no trabarse (RT-21)."""
        carpeta = self.dir / ".locks"
        carpeta.mkdir(parents=True, exist_ok=True)
        with ExitStack() as pila:
            for n in sorted(set(nombres)):
                pila.enter_context(FileLock(carpeta / (n + ".lock"), timeout=TIMEOUT_LOCK))
            yield

    def escribir(
        self,
        nombre: str,
        datos: Json | Modelo,
        *,
        version_esperada: str | None = None,
        accion: str = "escribir",
        id_objeto: str | None = None,
        verificar_integridad: bool = True,
    ) -> str:
        """Escribe un archivo y devuelve su versión nueva."""
        esperadas = {nombre: version_esperada} if version_esperada is not None else None
        return self.transaccion(
            {nombre: datos},
            versiones_esperadas=esperadas,
            accion=accion,
            id_objeto=id_objeto,
            verificar_integridad=verificar_integridad,
        )[nombre]

    def transaccion(
        self,
        cambios: Mapping[str, Json | Modelo],
        *,
        versiones_esperadas: Mapping[str, str | None] | None = None,
        accion: str = "escribir",
        id_objeto: str | None = None,
        verificar_integridad: bool = True,
    ) -> dict[str, str]:
        """Escribe varios archivos como una sola operación: o quedan todos, o no queda ninguno.

        Con los locks tomados: controla versiones, valida esquemas e integridad, guarda la versión
        anterior de cada archivo y recién entonces reemplaza. Si un reemplazo falla, restaura los ya hechos.
        """
        for n in cambios:
            self.ruta(n)
        self.dir.mkdir(parents=True, exist_ok=True)
        with self.bloqueo(*cambios, AUDITORIA):
            return self._transaccion(cambios, versiones_esperadas, accion, id_objeto, verificar_integridad)

    def modificar(
        self,
        nombres: tuple[str, ...],
        cambio: Callable[[dict[str, Json]], Mapping[str, Json | Modelo]],
        *,
        accion: str = "modificar",
        id_objeto: str | None = None,
        verificar_integridad: bool = True,
    ) -> dict[str, str]:
        """Lectura-modificación-escritura con los locks tomados de punta a punta (RT-21).

        `cambio` recibe el contenido actual de `nombres` (los que no existen vienen como `{}`) y devuelve
        los archivos a escribir. Nadie más puede escribirlos entre la lectura y la escritura.
        """
        for n in nombres:
            self.ruta(n)
        self.dir.mkdir(parents=True, exist_ok=True)
        with self.bloqueo(*nombres, AUDITORIA):
            actuales = {n: (self.leer_crudo(n)[0] if self.existe(n) else {}) for n in nombres}
            cambios = cambio(actuales)
            fuera = set(cambios) - set(nombres)
            if fuera:
                raise ErrorRepositorio(f"`cambio` devolvió archivos que no estaban bloqueados: {sorted(fuera)}")
            return self._transaccion(cambios, None, accion, id_objeto, verificar_integridad)

    def _transaccion(
        self,
        cambios: Mapping[str, Json | Modelo],
        versiones_esperadas: Mapping[str, str | None] | None,
        accion: str,
        id_objeto: str | None,
        verificar_integridad: bool,
    ) -> dict[str, str]:
        nuevos = {n: (d.a_json() if isinstance(d, Modelo) else d) for n, d in cambios.items()}
        previos: dict[str, bytes | None] = {}
        for n in nuevos:
            ruta = self.ruta(n)
            previos[n] = ruta.read_bytes() if ruta.is_file() else None
        for n, esperada in (versiones_esperadas or {}).items():
            previo = previos.get(n)
            if esperada is not None and (previo is None or hash_de(previo) != esperada):
                raise ConflictoVersion(n)

        for n, d in nuevos.items():
            validar(n, d)
        if verificar_integridad:
            self._verificar_integridad(nuevos)

        contenidos = {n: serializar(n, d) for n, d in nuevos.items()}
        temporales: dict[str, Path] = {}
        hechos: list[str] = []
        try:
            for n, c in contenidos.items():
                temporales[n] = self.ruta(n).with_name(n + ".tmp")
                self._escribir_temporal(n, c)
            for n in nuevos:
                self._guardar_version(n, previos[n])
            for n, tmp in temporales.items():
                os.replace(tmp, self.ruta(n))
                hechos.append(n)
        except BaseException:
            for n in hechos:
                self._restaurar_previo(n, previos[n])
            for tmp in temporales.values():
                tmp.unlink(missing_ok=True)
            raise
        self._auditar(accion, id_objeto, nuevos, previos)
        return {n: hash_de(c) for n, c in contenidos.items()}

    def _verificar_integridad(self, nuevos: Mapping[str, Json]) -> None:
        """Reglas de 4.4 sobre el estado que quedaría. Se omite hasta que existan tenencias y movimientos."""
        if not {TENENCIAS, MOVIMIENTOS, PRECIOS} & set(nuevos):
            return

        def estado(nombre: str) -> Json | None:
            if nombre in nuevos:
                return nuevos[nombre]
            return self.leer_crudo(nombre)[0] if self.existe(nombre) else None

        ten, mov, pre = estado(TENENCIAS), estado(MOVIMIENTOS), estado(PRECIOS)
        if ten is None or mov is None:
            return
        integridad.exigir(
            Tenencias.model_validate(ten),
            Movimientos.model_validate(mov).movimientos,
            PreciosDiarios.model_validate(pre).serie if pre is not None else None,
        )

    def _escribir_temporal(self, nombre: str, contenido: bytes) -> Path:
        tmp = self.ruta(nombre).with_name(nombre + ".tmp")
        with open(tmp, "wb") as f:
            f.write(contenido)
            f.flush()
            os.fsync(f.fileno())
        return tmp

    def _restaurar_previo(self, nombre: str, previo: bytes | None) -> None:
        ruta = self.ruta(nombre)
        if previo is None:
            ruta.unlink(missing_ok=True)
            return
        tmp = self._escribir_temporal(nombre, previo)
        os.replace(tmp, ruta)

    # --- versiones (RT-22)

    def _carpeta_versiones(self, nombre: str) -> Path:
        return self.dir / "_versiones" / nombre

    def _guardar_version(self, nombre: str, previo: bytes | None) -> None:
        if previo is None:
            return
        carpeta = self._carpeta_versiones(nombre)
        carpeta.mkdir(parents=True, exist_ok=True)
        base = ahora().strftime("%Y%m%d-%H%M%S")
        # dos escrituras en el mismo segundo: sufijo siguiente al mayor que exista, nunca uno ya liberado,
        # para que el orden por nombre siga siendo el orden en que se escribieron
        sufijos = [int(r.stem[16:] or 0) for r in carpeta.glob(f"{base}*.json")]
        destino = carpeta / (f"{base}-{max(sufijos) + 1}.json" if sufijos else f"{base}.json")
        destino.write_bytes(previo)
        for vieja in self._rutas_versiones(nombre)[:-MAX_VERSIONES]:
            vieja.unlink()

    def _rutas_versiones(self, nombre: str) -> list[Path]:
        """De la más vieja a la más nueva. `AAAAMMDD-HHMMSS` va antes que `AAAAMMDD-HHMMSS-1`."""
        carpeta = self._carpeta_versiones(nombre)
        if not carpeta.is_dir():
            return []
        return sorted(carpeta.glob("*.json"), key=lambda r: (r.stem[:15], int(r.stem[16:] or 0)))

    def versiones(self, nombre: str) -> list[Version]:
        """Versiones guardadas, de la más nueva a la más vieja."""
        rutas = reversed(self._rutas_versiones(nombre))
        return [Version(r.stem, nombre, r, r.stat().st_size) for r in rutas]

    def leer_version(self, nombre: str, id_version: str) -> Json:
        ruta = self._carpeta_versiones(nombre) / f"{Path(id_version).name}.json"
        if not ruta.is_file():
            raise ErrorRepositorio(f"No existe la versión {id_version} de {nombre}")
        datos = json.loads(ruta.read_bytes())
        assert isinstance(datos, dict)
        return datos

    def restaurar(self, nombre: str, id_version: str, *, version_esperada: str | None = None) -> str:
        """Vuelve a una versión guardada. La restauración también queda versionada (RF-46)."""
        return self.escribir(
            nombre,
            self.leer_version(nombre, id_version),
            version_esperada=version_esperada,
            accion="restaurar",
            id_objeto=id_version,
        )

    # --- auditoría (4.1)

    def _auditar(
        self, accion: str, id_objeto: str | None, nuevos: Mapping[str, Json], previos: Mapping[str, bytes | None]
    ) -> None:
        momento = ahora()
        ruta = self.ruta(AUDITORIA)
        registros: list[Json] = []
        if ruta.is_file():
            registros = json.loads(ruta.read_bytes()).get("registros", [])
            # rotación anual: lo de años anteriores pasa a auditoria-AAAA.json
            if registros and registros[0]["ts"][:4] != str(momento.year):
                shutil.move(ruta, self.dir / f"auditoria-{registros[0]['ts'][:4]}.json")
                registros = []
        for nombre, datos in nuevos.items():
            previo = previos[nombre]
            cambios = diferencias(json.loads(previo), datos) if previo is not None else []
            entrada: Json = {
                "ts": momento.isoformat(timespec="seconds"),
                "accion": accion if previo is not None else f"{accion} (archivo nuevo)",
                "archivo": nombre,
                "cambios": len(cambios),
            }
            if id_objeto is not None:
                entrada["id"] = id_objeto
            if len(cambios) <= MAX_DIFF:
                entrada["diff"] = cambios
            else:
                entrada["diff_omitido"] = f"más de {MAX_DIFF} cambios; ver _versiones/{nombre}"
            registros.append(entrada)
        tmp = self._escribir_temporal(AUDITORIA, serializar(AUDITORIA, {"registros": registros}))
        os.replace(tmp, ruta)

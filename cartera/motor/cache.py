"""Carga de los datos desde el repositorio y caché en memoria de la serie (RT-04)."""

from __future__ import annotations

from cartera.datos.repositorio import Repositorio
from cartera.motor.base import Datos
from cartera.motor.series import Serie, calcular_serie

_cache: dict[str, tuple[tuple[tuple[int, int], ...], Serie]] = {}


def cargar_datos(repo: Repositorio) -> Datos:
    return Datos(repo.tenencias(), repo.movimientos().movimientos, repo.precios().serie)


def serie_actual(repo: Repositorio) -> Serie:
    """Serie calculada. Se recalcula solo si cambió alguno de los archivos (fecha de modificación o tamaño)."""
    clave = str(repo.dir.resolve())
    marca = repo.marca()
    guardado = _cache.get(clave)
    if guardado and guardado[0] == marca:
        return guardado[1]
    serie = calcular_serie(cargar_datos(repo))
    _cache[clave] = (marca, serie)
    return serie


def invalidar(repo: Repositorio | None = None) -> None:
    if repo is None:
        _cache.clear()
    else:
        _cache.pop(str(repo.dir.resolve()), None)

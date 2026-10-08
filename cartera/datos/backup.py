"""Copia comprimida de la carpeta de datos (RF-65). En F1 la usa la carga de datos antes de reemplazar."""

from __future__ import annotations

import zipfile
from pathlib import Path

from cartera.datos.repositorio import ahora

EXCLUIDOS = (".locks",)


def crear_backup(datos: Path, destino: Path, prefijo: str = "cartera") -> Path:
    """Comprime todo `datos` (incluidas las versiones) en `destino/<prefijo>-AAAAMMDD-HHMMSS.zip`."""
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"{prefijo}-{ahora().strftime('%Y%m%d-%H%M%S')}.zip"
    n = 1
    while ruta.exists():
        ruta = destino / f"{prefijo}-{ahora().strftime('%Y%m%d-%H%M%S')}-{n}.zip"
        n += 1
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(datos.rglob("*")):
            rel = f.relative_to(datos)
            if f.is_file() and rel.parts[0] not in EXCLUIDOS and f.suffix != ".tmp":
                z.write(f, rel.as_posix())
    return ruta

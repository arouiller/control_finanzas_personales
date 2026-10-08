"""Verifica las reglas de integridad de 4.4 sobre la carpeta de datos.

Uso: python scripts/verificar_integridad.py [--datos DIR]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cartera.config import ajustes
from cartera.consola import salida_utf8
from cartera.datos import integridad
from cartera.datos.repositorio import PRECIOS, Repositorio


def main(argv: list[str] | None = None) -> int:
    par = argparse.ArgumentParser(description="Verifica la integridad de los datos.")
    par.add_argument("--datos", help="carpeta de datos (por defecto, CARTERA_DATA_DIR o el ejemplo con CARTERA_DEMO=1)")
    args = par.parse_args(argv)
    salida_utf8()
    repo = Repositorio(args.datos or ajustes().carpeta_datos)
    if repo.vacio():
        print(f"Todavía no hay datos cargados en {repo.dir}.", file=sys.stderr)
        return 1
    precios = repo.precios().serie if repo.existe(PRECIOS) else None
    errores = integridad.verificar(repo.tenencias(), repo.movimientos().movimientos, precios)
    if errores:
        print("Problemas de integridad:", file=sys.stderr)
        for e in errores:
            print(f"- {e}", file=sys.stderr)
        return 1
    print("Los datos pasan todas las verificaciones de integridad.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

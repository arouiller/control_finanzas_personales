"""Carga inicial o reemplazo total de los datos (REQUERIMIENTOS 4.3).

Uso: python scripts/cargar_datos.py <carpeta> [--datos DIR] [--backups DIR] [--si]

La carpeta tiene que traer tenencias.json, movimientos.json y precios_diarios.json;
fuentes_precios.json es opcional. No escribe nada hasta que confirmes.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cartera.config import ajustes
from cartera.consola import salida_utf8
from cartera.datos.carga import ErrorCarga, aplicar_carga, preparar_carga
from cartera.datos.repositorio import ErrorRepositorio, Repositorio
from cartera.motor.resumen import usd


def fecha(d: str | None) -> str:
    return f"{d[8:]}/{d[5:7]}/{d[2:4]}" if d else "—"


def main(argv: list[str] | None = None) -> int:
    par = argparse.ArgumentParser(description="Carga los JSON de una carpeta en la carpeta de datos.")
    par.add_argument("carpeta", help="carpeta con tenencias.json, movimientos.json y precios_diarios.json")
    par.add_argument("--datos", help="carpeta de datos de destino (por defecto, CARTERA_DATA_DIR)")
    par.add_argument("--backups", help="carpeta de backups (por defecto, CARTERA_BACKUP_DIR)")
    par.add_argument("--si", action="store_true", help="no pedir confirmación")
    args = par.parse_args(argv)
    salida_utf8()

    cfg = ajustes()
    repo = Repositorio(args.datos or cfg.data_dir)
    try:
        carga = preparar_carga(args.carpeta)
    except ErrorCarga as err:
        print(err, file=sys.stderr)
        return 1

    r = carga.resumen
    print(f"Datos listos para cargar en {repo.dir.resolve()}")
    print(f"  Activos:      {r.activos}")
    print(f"  Movimientos:  {r.movimientos} (del {fecha(r.primer_movimiento)} al {fecha(r.ultimo_movimiento)})")
    if r.ids_asignados or r.contrapartidas_asignadas:
        print(
            f"                {r.ids_asignados} sin id y {r.contrapartidas_asignadas} sin contrapartida, ya completados"
        )
    print(f"  Precios:      del {fecha(r.serie_desde)} al {fecha(r.serie_hasta)}")
    print(f"  Patrimonio neto al {fecha(r.fecha)}: {usd(r.patrimonio_neto)}")
    print(
        f"    activos financieros {usd(r.activos_financieros)} · mineros {usd(r.mineros)}"
        f" · bienes {usd(r.bienes)} · pasivos {usd(-r.pasivos)}"
    )
    for aviso in carga.avisos:
        print(f"  Aviso: {aviso}")
    if not repo.vacio():
        print("  Ya hay datos cargados: antes de reemplazarlos se hace un backup.")

    if not args.si and input("¿Escribir estos datos? [s/N] ").strip().lower() not in ("s", "si", "sí"):
        print("No se escribió nada.")
        return 1
    try:
        backup = aplicar_carga(carga, repo, args.backups or cfg.backup_dir)
    except ErrorRepositorio as err:
        print(err, file=sys.stderr)
        return 1
    if backup:
        print(f"Backup de los datos anteriores: {backup}")
    print("Datos cargados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

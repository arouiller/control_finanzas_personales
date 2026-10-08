"""Resumen del motor por línea de comandos (RNF-07).

Uso: python -m cartera.motor.resumen [--fecha AAAA-MM-DD] [--datos CARPETA]
"""

from __future__ import annotations

import argparse
import sys

from cartera.config import ajustes
from cartera.consola import salida_utf8
from cartera.datos.repositorio import Repositorio
from cartera.motor.cache import cargar_datos
from cartera.motor.costos import calcular_costos
from cartera.motor.series import Serie, calcular_serie


def num(n: float, decimales: int = 2) -> str:
    """Formato es-AR: miles con punto y decimales con coma."""
    return f"{n:,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def usd(n: float, decimales: int = 2) -> str:
    return ("−" if n < 0 else "") + "US$ " + num(abs(n), decimales)


def pct(n: float) -> str:
    return ("+" if n >= 0 else "−") + num(abs(n) * 100) + "%"


def texto_resumen(serie: Serie, fecha: str | None = None) -> str:
    r = serie.ultima if fecha is None else serie.en(fecha)
    if r is None:
        raise ValueError(f"{fecha} no está en la serie ({serie.primera.t} a {serie.ultima.t})")
    d, m, a = r.t[8:], r.t[5:7], r.t[2:4]
    costos = calcular_costos(serie.datos).por_activo
    lineas = [
        f"Mi cartera en dólares · {d}/{m}/{a}",
        "",
        f"  Activos financieros   {usd(r.tot):>18}",
        f"  Mineros (estimado)    {usd(r.min):>18}",
        f"  Bienes                {usd(r.inm):>18}",
        f"  Pasivos               {usd(-r.deu):>18}",
        f"  Patrimonio neto       {usd(r.pat):>18}",
        "",
        f"  Capital neto          {usd(r.capT):>18}   (patrimonio: {usd(r.capP)})",
        f"  Rendimiento desde el {serie.primera.t[8:]}/{serie.primera.t[5:7]}/{serie.primera.t[2:4]}:"
        f" cartera {pct(r.idx - 1)} · patrimonio {pct(r.idxP - 1)}",
        f"  MEP $ {num(r.mep)} · BTC {usd(r.btc)}",
        "",
        "  Posiciones",
    ]
    for a_ in sorted(serie.datos.activos, key=lambda x: -r.pos[x.ticker]):
        if abs(r.pos[a_.ticker]) < 0.005:
            continue
        cantidad = f"{r.cant[a_.ticker]:.8f}".rstrip("0").rstrip(".")
        extra = ""
        if fecha is None and a_.ticker in costos:
            c = costos[a_.ticker]
            extra = f"   costo {usd(c.costo)}{'*' if c.estimado else ''}"
        lineas.append(f"    {a_.ticker:<12} {usd(r.pos[a_.ticker]):>18}   {cantidad.replace('.', ',')}{extra}")
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    par = argparse.ArgumentParser(description="Totales del motor a una fecha.")
    par.add_argument("--fecha", help="AAAA-MM-DD (por defecto, la última de la serie)")
    par.add_argument("--datos", help="carpeta de datos (por defecto, CARTERA_DATA_DIR o el ejemplo con CARTERA_DEMO=1)")
    args = par.parse_args(argv)
    salida_utf8()
    repo = Repositorio(args.datos or ajustes().carpeta_datos)
    if repo.vacio():
        print(f"Todavía no hay datos cargados en {repo.dir}.", file=sys.stderr)
        return 1
    try:
        print(texto_resumen(calcular_serie(cargar_datos(repo)), args.fecha))
    except ValueError as err:
        print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

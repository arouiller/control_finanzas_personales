"""Juegos de datos FICTICIOS al azar para T-02, con la misma forma que `referencia/ejemplo/generar_ejemplo.py`.

Cada semilla varía el largo de la serie, los precios y los movimientos, y cubre todos los tipos de movimiento:
compras y ventas en pesos (flujo) y contra USD Balanz (contrapartida), ventas con destino, minería, costos,
conversiones, devengo diario, aportes, compras de bienes, mineros en tandas, bienes con y sin depreciación y
un pasivo con cuotas pagas y canceladas de los dos tipos. Los saldos nunca quedan negativos.
"""

from __future__ import annotations

import datetime as dt
import math
import random
from typing import Any

Json = dict[str, Any]
ARS = ("SPY", "XYZ", "ABC", "QQQ")


def generar(semilla: int) -> dict[str, Json]:
    rnd = random.Random(semilla)
    d0 = dt.date(2024, rnd.randint(1, 12), rnd.randint(1, 28))
    n = rnd.randint(100, 420)
    fechas = [(d0 + dt.timedelta(i)).isoformat() for i in range(n)]
    tickers = ["SPY", *rnd.sample(ARS[1:], rnd.randint(1, 3))]

    # precios: tendencia más una onda, distintos por semilla
    par = {
        t: (rnd.uniform(4000, 30000), rnd.uniform(-0.0004, 0.0015), rnd.uniform(0, 0.06), rnd.uniform(4, 15))
        for t in tickers
    }
    btc0, btc_amp, mep0, mep_paso = (
        rnd.uniform(40000, 110000),
        rnd.uniform(0.02, 0.15),
        rnd.uniform(900, 1400),
        rnd.uniform(0.2, 2.5),
    )
    serie = []
    for i, d in enumerate(fechas):
        ars = {t: round(b * (1 + tr * i) * (1 + amp * math.sin(i / per)), 2) for t, (b, tr, amp, per) in par.items()}
        serie.append(
            {
                "fecha": d,
                "mep": round(mep0 + mep_paso * i, 2),
                "btc_usdt": round(btc0 * (1 + btc_amp * math.sin(i / 11)) + 25 * i, 2),
                "ars": ars,
            }
        )
    precio = {r["fecha"]: r for r in serie}

    def pu(t: str, d: str) -> float:
        return precio[d]["btc_usdt"] if t == "BTC" else precio[d]["ars"][t] / precio[d]["mep"]

    bien_a, bien_b = "Terreno Ficticio", "Auto Ficticio"
    compra_a, compra_b = fechas[rnd.randint(n // 3, n // 2)], fechas[rnd.randint(n // 4, n // 2)]
    inicial = {"USD Balanz": rnd.choice([500.0, 1500.0, 4000.0]), "USD billete": 100.0}
    saldo = {t: 0.0 for t in [*tickers, "BTC", "USDT"]} | inicial
    mov: list[Json] = []

    def m(**k: Any) -> None:
        mov.append({kk: v for kk, v in k.items() if v is not None})
        saldo[k["activo"]] = round(saldo[k["activo"]] + (0 if k.get("sin_efecto_en_saldo") else k["cantidad"]), 10)

    m(
        fecha=fechas[0],
        tipo="Saldo inicial",
        activo="USDT",
        cantidad=3000.0,
        usd=3000.0,
        flujo_usd=3000.0,
        estimado=True,
        nota="saldo inicial",
    )
    btc_ini = round(rnd.uniform(0.02, 0.2), 4)
    m(
        fecha=fechas[0],
        tipo="Saldo inicial",
        activo="BTC",
        cantidad=btc_ini,
        usd=round(btc_ini * pu("BTC", fechas[0]), 2),
        flujo_usd=round(btc_ini * pu("BTC", fechas[0]), 2),
        estimado=True,
        nota="saldo inicial",
    )

    cancelada_cartera: str | None = None
    for d in fechas[1:]:
        if rnd.random() > 0.22:
            continue
        ev = rnd.choice(
            [
                "compra",
                "compra",
                "compra_usd",
                "venta",
                "venta",
                "venta_usd",
                "mineria",
                "costo",
                "conversion",
                "aporte",
                "bienes",
                "sin_efecto",
            ]
        )
        t = rnd.choice(tickers)
        if ev == "compra":
            q = rnd.randint(1, 60)
            usd = round(q * pu(t, d) * rnd.uniform(0.97, 1.03), 2)
            m(
                fecha=d,
                tipo="Compra",
                activo=t,
                cantidad=q,
                usd=usd,
                flujo_usd=usd,
                estimado=True if rnd.random() < 0.1 else None,
                nota="compra en pesos",
            )
        elif ev == "compra_usd":
            q = rnd.randint(1, 40)
            usd = round(q * pu(t, d), 2)
            if saldo["USD Balanz"] >= usd:
                m(fecha=d, tipo="Compra", activo=t, cantidad=q, usd=usd, nota="compra con USD Balanz")
                m(fecha=d, tipo="Pago", activo="USD Balanz", cantidad=-usd, usd=usd, nota="contrapartida")
        elif ev in ("venta", "venta_usd") and saldo[t] >= 1:
            q = rnd.randint(1, int(saldo[t]))
            usd = round(q * pu(t, d) * rnd.uniform(0.97, 1.03), 2)
            if ev == "venta":
                destinos = (
                    [None, None, "Mineros"] + ([bien_a] if d <= compra_a else []) + ([bien_b] if d <= compra_b else [])
                )
                m(
                    fecha=d,
                    tipo="Venta",
                    activo=t,
                    cantidad=-q,
                    usd=usd,
                    flujo_usd=-usd,
                    destino=rnd.choice(destinos),
                    nota="venta en pesos",
                )
            else:
                m(fecha=d, tipo="Venta", activo=t, cantidad=-q, usd=usd, nota="venta contra USD Balanz")
                m(fecha=d, tipo="Cobro", activo="USD Balanz", cantidad=usd, usd=usd, nota="contrapartida")
        elif ev == "mineria":
            q = round(rnd.uniform(0.0005, 0.004), 6)
            usd = round(q * pu("BTC", d), 2)
            m(fecha=d, tipo="Minería", activo="BTC", cantidad=q, usd=usd, flujo_usd=usd, nota="producción")
        elif ev == "costo" and saldo["USDT"] >= 400:
            usd = round(rnd.uniform(50, 300), 2)
            m(
                fecha=d,
                tipo="Costo minería",
                activo="USDT",
                cantidad=-usd,
                usd=usd,
                flujo_usd=-usd,
                nota="luz y seguro",
            )
        elif ev == "conversion" and saldo["BTC"] > 0.01:
            q = round(saldo["BTC"] * rnd.uniform(0.05, 0.3), 6)  # nunca se vende todo el BTC
            usd = round(q * pu("BTC", d), 2)
            m(fecha=d, tipo="Conversión", activo="BTC", cantidad=-q, usd=usd, nota="BTC a USDT")
            m(fecha=d, tipo="Cobro", activo="USDT", cantidad=usd, usd=usd, nota="contrapartida")
        elif ev == "aporte":
            usd = float(rnd.randint(50, 800))
            m(
                fecha=d,
                tipo="Aporte",
                activo="USD billete",
                cantidad=usd,
                usd=usd,
                flujo_usd=usd,
                nota="billetes",
            )
        elif ev == "bienes" and saldo["USD Balanz"] >= 150:
            usd = float(rnd.randint(50, 150))
            destino = bien_a if d <= compra_a else bien_b
            m(
                fecha=d,
                tipo="Compra de bienes",
                activo="USD Balanz",
                cantidad=-usd,
                usd=usd,
                flujo_usd=-usd,
                destino=destino,
                nota="pago del bien",
            )
            if destino == bien_b and d > compra_b and cancelada_cartera is None:
                cancelada_cartera = d
        elif ev == "sin_efecto":
            m(
                fecha=d,
                tipo="Compra",
                activo=t,
                cantidad=5,
                usd=10.0,
                sin_efecto_en_saldo=True,
                nota="no cambia el saldo",
            )

    # interés con devengo diario: un mes completo que cae dentro de la serie
    desde = next(d for d in fechas[10:] if d.endswith("-01"))
    hasta = (dt.date.fromisoformat(desde) + dt.timedelta(27)).isoformat()
    por_dia = round(rnd.uniform(1e-6, 6e-6), 8)
    m(
        fecha=hasta,
        tipo="Interés Nexo",
        activo="BTC",
        cantidad=round(28 * por_dia, 10),
        usd=0.0,
        devengo_diario={"desde": desde, "por_dia": por_dia},
        nota="interés diario",
    )

    def activo(t: str, tipo: str, ars: bool, fijo: bool) -> Json:
        plataforma = " · Nexo" if tipo == "Cripto" else " · USD" if tipo == "Liquidez" else " · Balanz"
        return {
            "ticker": t,
            "nombre": t,
            "tipo": tipo,
            "grupo": tipo + plataforma,
            "cantidad": saldo[t],
            "cotiza_en_pesos": ars,
            "valor_fijo_usd": fijo,
        }

    alta = fechas[rnd.randint(n // 4, n // 2)]
    pagas = [{"cuota": i + 1, "fecha": d} for i, d in enumerate(d for d in fechas if d.endswith("-10"))][:9]
    canceladas = [{"cuota": 24, "fecha": fechas[rnd.randint(n // 2, n - 1)], "motivo": "anticipada"}]
    if cancelada_cartera:
        canceladas.append({"cuota": 23, "fecha": cancelada_cartera, "motivo": "licitada", "pagada_desde_cartera": True})
    tandas = [
        {"fecha": fechas[rnd.randint(0, n - 1)], "cantidad": 1, "costo_usd": float(rnd.randint(1500, 4000))}
        for _ in range(rnd.randint(1, 3))
    ]
    tandas.sort(key=lambda t: t["fecha"])
    tenencias = {
        "actualizado": fechas[-1],
        "moneda_valuacion": "USD",
        "activos": [
            *[activo(t, "CEDEARs", True, False) for t in tickers],
            activo("BTC", "Cripto", False, False),
            activo("USDT", "Cripto", False, True),
            activo("USD Balanz", "Liquidez", False, True),
            activo("USD billete", "Liquidez", False, True),
        ],
        "mineros": {
            "modelo": "Minero Z",
            "th_por_equipo": 100,
            "cantidad": len(tandas),
            "fecha_compra": tandas[0]["fecha"],
            "costo_usd": sum(t["costo_usd"] for t in tandas),
            "valor_inicial_pct": rnd.choice([70, 75, 80]),
            "valor_residual_pct": rnd.choice([10, 25]),
            "vida_util_anios": rnd.choice([4, 6]),
            "compras": tandas,
        },
        "inmuebles": [
            {
                "nombre": bien_a,
                "fecha_compra": compra_a,
                "costo_usd": 900,
                "valor_usd": float(rnd.randint(800, 1500)),
                "fecha_valuacion": compra_a,
                "origen": "Ficticio",
            },
            {
                "nombre": bien_b,
                "fecha_compra": compra_b,
                "costo_usd": 400,
                "valor_usd": 400,
                "fecha_valuacion": compra_b,
                "depreciacion_anual_pct": rnd.choice([10, 15, 20]),
                "valor_nuevo_usd": float(rnd.randint(1000, 3000)),
                "origen": "Ficticio",
            },
        ],
        "pasivos": [
            {
                "nombre": "Plan Ficticio",
                "bien": bien_b,
                "tipo": "Plan de ahorro",
                "cuotas_total": 24,
                "alicuota_ars": float(rnd.randint(80000, 200000)),
                "valor_movil_ars": 5000000,
                "fecha_valor_movil": alta,
                "mep_referencia": rnd.choice([1000, 1150, 1300]),
                "fecha_alta": alta,
                "cuotas_pagas": pagas,
                "cuotas_canceladas": canceladas,
            }
        ],
    }
    return {
        "tenencias.json": tenencias,
        "movimientos.json": {"movimientos": mov},
        "precios_diarios.json": {"desde": fechas[0], "hasta": fechas[-1], "serie": serie},
    }

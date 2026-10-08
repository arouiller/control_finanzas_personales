"""Genera un juego de datos FICTICIO (no son datos del usuario) que cubre todos los tipos de movimiento,
mineros, bienes con y sin depreciación y un pasivo en cuotas. Sirve para los tests del motor.
Uso: python3 generar_ejemplo.py  (escribe tenencias.json, movimientos.json, precios_diarios.json en esta carpeta)"""
import json, math, datetime as dt
d0 = dt.date(2025, 1, 1); N = 120
serie = []
for i in range(N):
    d = (d0 + dt.timedelta(i)).isoformat()
    finde = (d0 + dt.timedelta(i)).weekday() >= 5
    j = i if not finde else max(k for k in range(i + 1) if (d0 + dt.timedelta(k)).weekday() < 5) if i >= 2 else 0
    mep = round(1000 + 1.5 * j, 2)
    serie.append({"fecha": d, "mep": mep, "btc_usdt": round(90000 + 6000 * math.sin(i / 9) + 40 * i, 2),
                  "ars": {"SPY": round(11000 * (1 + 0.0012 * j) + 150 * math.sin(j / 5), 2),
                          "XYZ": round(12500 * (1 + 0.0008 * j) + 400 * math.cos(j / 7), 2)}})
P = {r["fecha"]: r for r in serie}
btc = lambda d: P[d]["btc_usdt"]
mov = []
def m(**k): mov.append({kk: v for kk, v in k.items() if v is not None})
m(fecha="2025-01-01", tipo="Saldo inicial", activo="USDT", cantidad=5000, usd=5000, flujo_usd=5000, estimado=True, nota="Ficticio: saldo inicial estimado")
m(fecha="2025-01-01", tipo="Saldo inicial", activo="BTC", cantidad=0.05, usd=round(0.05 * btc("2025-01-01"), 2), flujo_usd=round(0.05 * btc("2025-01-01"), 2), estimado=True, nota="Ficticio: saldo inicial estimado")
m(fecha="2025-01-10", tipo="Compra", activo="SPY", cantidad=100, usd=1000.0, flujo_usd=1000.0, nota="Ficticio: compra en pesos (aporte)")
m(fecha="2025-01-15", tipo="Compra", activo="XYZ", cantidad=50, usd=500.0, nota="Ficticio: compra con USD Balanz (pase interno)")
m(fecha="2025-01-15", tipo="Pago", activo="USD Balanz", cantidad=-500.0, usd=500.0, nota="Contrapartida de la compra de XYZ")
m(fecha="2025-01-25", tipo="Venta", activo="SPY", cantidad=-20, usd=230.0, flujo_usd=-230.0, destino="Mineros", nota="Ficticio: venta en pesos para pagar mineros")
u = round(0.002 * btc("2025-02-01"), 2)
m(fecha="2025-02-01", tipo="Minería", activo="BTC", cantidad=0.002, usd=u, flujo_usd=u, nota="Ficticio: producción minera (aporte)")
m(fecha="2025-02-01", tipo="Costo minería", activo="USDT", cantidad=-300.0, usd=300.0, flujo_usd=-300.0, nota="Ficticio: luz y seguro (retiro)")
u = round(0.004 * btc("2025-02-05"), 2)
m(fecha="2025-02-05", tipo="Conversión", activo="BTC", cantidad=-0.004, usd=u, nota="Ficticio: BTC a USDT (pase interno)")
m(fecha="2025-02-05", tipo="Cobro", activo="USDT", cantidad=u, usd=u, nota="Contrapartida de la conversión")
m(fecha="2025-02-10", tipo="Venta", activo="SPY", cantidad=-10, usd=115.0, flujo_usd=-115.0, destino="Auto Ejemplo", nota="Ficticio: venta para el adelanto del auto")
m(fecha="2025-02-20", tipo="Venta", activo="XYZ", cantidad=-30, usd=360.0, nota="Ficticio: venta contra USD Balanz")
m(fecha="2025-02-20", tipo="Cobro", activo="USD Balanz", cantidad=360.0, usd=360.0, nota="Contrapartida de la venta de XYZ")
m(fecha="2025-02-28", tipo="Interés Nexo", activo="BTC", cantidad=round(28 * 3.1e-6, 10), usd=0.0, devengo_diario={"desde": "2025-02-01", "por_dia": 3.1e-6}, nota="Ficticio: interés diario de febrero")
m(fecha="2025-03-10", tipo="Venta", activo="SPY", cantidad=-30, usd=360.0, flujo_usd=-360.0, destino="Terreno Ejemplo", nota="Ficticio: venta para el terreno")
m(fecha="2025-03-15", tipo="Compra de bienes", activo="USD Balanz", cantidad=-200.0, usd=200.0, flujo_usd=-200.0, destino="Terreno Ejemplo", nota="Ficticio: pago del terreno con USD Balanz")
m(fecha="2025-04-01", tipo="Aporte", activo="USD billete", cantidad=300.0, usd=300.0, flujo_usd=300.0, nota="Ficticio: billetes que entran a la cartera")
m(fecha="2025-04-10", tipo="Compra", activo="SPY", cantidad=10, usd=125.0, flujo_usd=125.0, nota="Ficticio: compra en pesos")
m(fecha="2025-04-20", tipo="Compra de bienes", activo="USD Balanz", cantidad=-100.0, usd=100.0, flujo_usd=-100.0, destino="Auto Ejemplo", nota="Ficticio: licitación de la cuota 11 pagada con USD Balanz")
def act(t, n, tipo, q, ars, fijo):
    return {"ticker": t, "nombre": n, "tipo": tipo, "grupo": tipo + (" · Nexo" if tipo == "Cripto" else " · Balanz" if tipo != "Liquidez" else " · USD"), "cantidad": q, "cotiza_en_pesos": ars, "valor_fijo_usd": fijo}
cant = lambda t: round(sum(x["cantidad"] for x in mov if x["activo"] == t), 10)
ten = {"_descripcion": "DATOS FICTICIOS para tests. Mismo esquema que tenencias.json real.", "actualizado": serie[-1]["fecha"], "moneda_valuacion": "USD",
 "activos": [act("SPY", "ETF S&P 500", "CEDEARs", cant("SPY"), True, False), act("XYZ", "Empresa XYZ (ficticia)", "CEDEARs", cant("XYZ"), True, False),
             act("BTC", "Bitcoin", "Cripto", cant("BTC"), False, False), act("USDT", "Tether", "Cripto", cant("USDT"), False, True),
             act("USD Balanz", "Dólar MEP en cuenta", "Liquidez", round(600 + cant("USD Balanz"), 2), False, True), act("USD billete", "Efectivo", "Liquidez", cant("USD billete"), False, True)],
 "mineros": {"modelo": "Minero X", "th_por_equipo": 100, "cantidad": 2, "fecha_compra": "2025-01-20", "costo_usd": 6000, "valor_inicial_pct": 75, "valor_residual_pct": 25, "vida_util_anios": 6,
             "compras": [{"fecha": "2025-01-20", "cantidad": 1, "costo_usd": 3000}, {"fecha": "2025-03-01", "cantidad": 1, "costo_usd": 3000}]},
 "inmuebles": [{"nombre": "Terreno Ejemplo", "fecha_compra": "2025-03-20", "costo_usd": 560, "valor_usd": 600, "fecha_valuacion": "2025-03-20", "origen": "Ficticio"},
               {"nombre": "Auto Ejemplo", "fecha_compra": "2025-02-15", "costo_usd": 115, "valor_usd": 115, "fecha_valuacion": "2025-02-15", "depreciacion_anual_pct": 15, "valor_nuevo_usd": 1315, "origen": "Ficticio"}],
 "pasivos": [{"nombre": "Plan Ejemplo", "bien": "Auto Ejemplo", "tipo": "Plan de ahorro (12 cuotas)", "cuotas_total": 12, "alicuota_ars": 100000, "valor_movil_ars": 5000000, "fecha_valor_movil": "2025-04-01", "mep_referencia": 1000, "fecha_alta": "2025-02-15",
              "cuotas_pagas": [{"cuota": 1, "fecha": "2025-01-10"}, {"cuota": 2, "fecha": "2025-02-10"}, {"cuota": 3, "fecha": "2025-03-10"}, {"cuota": 4, "fecha": "2025-04-10"}],
              # una cancelada de cada tipo: la 12 se pagó con plata de afuera (aporte al patrimonio); la 11, desde la cartera (movimiento del 20/04 con destino al auto)
              "cuotas_canceladas": [{"cuota": 12, "fecha": "2025-03-25", "motivo": "anticipada"},
                                    {"cuota": 11, "fecha": "2025-04-20", "motivo": "licitada", "pagada_desde_cartera": True}]}]}
W = dict(encoding="utf-8", newline="\n")
json.dump(ten, open("tenencias.json", "w", **W), ensure_ascii=False, indent=1)
json.dump({"_descripcion": "DATOS FICTICIOS para tests. Mismo esquema que movimientos.json real.", "movimientos": mov}, open("movimientos.json", "w", **W), ensure_ascii=False, indent=1)
json.dump({"_descripcion": "DATOS FICTICIOS para tests.", "desde": serie[0]["fecha"], "hasta": serie[-1]["fecha"], "serie": serie}, open("precios_diarios.json", "w", **W), ensure_ascii=False, indent=1)
print({a["ticker"]: a["cantidad"] for a in ten["activos"]})

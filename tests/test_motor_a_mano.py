"""Reglas del motor que los valores de control no cubren (5.8 a 5.17).

No hay Node en la máquina de desarrollo, así que no se pudo ejecutar el JS de `referencia/tablero_actual.html`.
Los valores esperados están calculados a mano siguiendo ese JS: cada test deja la cuenta escrita, partiendo
de los movimientos del ejemplo ficticio y, cuando hacen falta precios, de `precios_diarios.json` crudo
(fixture `precios`), sin pasar por las funciones del motor que se están probando.

Movimientos del ejemplo (en el orden del archivo, índice desde 0):
  0  01/01 Saldo inicial USDT +5000 (estimado, flujo +5000)
  1  01/01 Saldo inicial BTC +0,05 por 4500 (estimado, flujo +4500)
  2  10/01 Compra SPY +100 por 1000 (flujo +1000)
  3  15/01 Compra XYZ +50 por 500, con USD Balanz      4  15/01 Pago USD Balanz −500
  5  25/01 Venta SPY −20 por 230 (flujo −230, destino Mineros)
  6  01/02 Minería BTC +0,002 por 178,90 (flujo +178,90)
  7  01/02 Costo minería USDT −300 (flujo −300)
  8  05/02 Conversión BTC −0,004 por 349,29           9  05/02 Cobro USDT +349,29
 10  10/02 Venta SPY −10 por 115 (flujo −115, destino Auto Ejemplo)
 11  20/02 Venta XYZ −30 por 360, contra USD Balanz   12  20/02 Cobro USD Balanz +360
 13  28/02 Interés Nexo BTC +0,0000868 (devengo diario de 0,0000031 desde el 01/02)
 14  10/03 Venta SPY −30 por 360 (flujo −360, destino Terreno Ejemplo)
 15  15/03 Compra de bienes USD Balanz −200 (flujo −200, destino Terreno Ejemplo)
 16  01/04 Aporte USD billete +300 (flujo +300)
 17  10/04 Compra SPY +10 por 125 (flujo +125)
 18  20/04 Compra de bienes USD Balanz −100 (flujo −100, destino Auto Ejemplo)
"""

from __future__ import annotations

from typing import Any

import pytest

from cartera.motor.analisis import analizar_periodo
from cartera.motor.base import Datos
from cartera.motor.composicion import (
    base_100,
    composicion,
    composicion_en_el_tiempo,
    lista_evolucion,
    tabla_posiciones,
)
from cartera.motor.costos import calcular_costos, usd_devengos
from cartera.motor.flujos import periodo_flujos
from cartera.motor.mineria import produccion
from cartera.motor.movimientos import orden_tabla, tabla_movimientos
from cartera.motor.rendimiento import filas_periodo, rendimiento, rendimientos_cabecera, variacion_hoy
from cartera.motor.series import Serie

Precios = dict[str, dict[str, Any]]
C = 0.005  # medio centavo: las cuentas a mano son exactas


def pu_spy(precios: Precios, d: str) -> float:
    return precios[d]["ars"]["SPY"] / precios[d]["mep"]


# --- 5.8: períodos de la cabecera


def test_filas_de_cada_periodo(serie: Serie) -> None:
    """Última fecha 30/04/25. 1D = fila anterior; 1M, 3M, 6M = última fila con fecha ≤ 30/04 − 30, 91 y 182 días.

    30/04 − 30 = 31/03; 30/04 − 91 = 29/01; 30/04 − 182 = 30/10/24, anterior al inicio → fila 0. 1A = fila 0.
    """
    assert {k: r.t for k, r in filas_periodo(serie).items()} == {
        "1D": "2025-04-29", "1M": "2025-03-31", "3M": "2025-01-29", "6M": "2025-01-01", "1A": "2025-01-01",
    }  # fmt: skip
    r = rendimientos_cabecera(serie)
    assert r["1A"] == r["6M"] == pytest.approx(serie.ultima.idx - 1)
    assert r["1M"] == pytest.approx(serie.ultima.idx / serie.en("2025-03-31").idx - 1)  # type: ignore[union-attr]


def test_rendimiento_no_cambia_por_un_aporte(serie: Serie, precios: Precios) -> None:
    """El 01/04 entran 300 USD en billetes: el valor sube 300 pero el TWR del día solo refleja precios.

    Ese día solo cambian de precio SPY (40 nominales al 01/04), XYZ (20) y BTC (0,0480868); USDT y USD no se mueven.
    """
    ayer, hoy = serie.en("2025-03-31"), serie.en("2025-04-01")
    assert ayer and hoy
    delta_precios = sum(
        q
        * (
            precios["2025-04-01"]["ars"][t] / precios["2025-04-01"]["mep"]
            - precios["2025-03-31"]["ars"][t] / precios["2025-03-31"]["mep"]
        )
        for t, q in (("SPY", 40), ("XYZ", 20))
    ) + 0.0480868 * (precios["2025-04-01"]["btc_usdt"] - precios["2025-03-31"]["btc_usdt"])
    assert hoy.tot - ayer.tot == pytest.approx(300 + delta_precios, abs=C)
    assert rendimiento(ayer, hoy) == pytest.approx(delta_precios / ayer.tot)


def test_variacion_hoy(serie: Serie) -> None:
    """El 30/04 no hay flujos: la variación es tot(30/04) − tot(29/04)."""
    v = variacion_hoy(serie)
    ayer = serie.en("2025-04-29")
    assert ayer and v.contra == "2025-04-29"
    assert v.usd == pytest.approx(serie.ultima.tot - ayer.tot)
    assert v.pct == pytest.approx(v.usd / ayer.tot)


# --- 5.9: serie mensual


def test_serie_mensual_y_puntos_de_evolucion(serie: Serie) -> None:
    assert [r.t for r in serie.mensuales] == ["2025-01-31", "2025-02-28", "2025-03-31", "2025-04-30"]
    assert [r.t for r in serie.evolucion] == [
        "2025-01-01",
        "2025-01-31",
        "2025-02-28",
        "2025-03-31",
        "2025-04-30",
    ]
    # "Gráficos desde marzo": el primer punto es el cierre del mes anterior (RF-17)
    assert serie.anterior_al_mes(serie.evolucion, "2025-03").t == "2025-02-28"
    assert serie.anterior_al_mes(serie.evolucion, "2025-01").t == "2025-01-01"


# --- 5.10: costo promedio y resultado realizado


def test_resultados_realizados(datos: Datos) -> None:
    """SPY: compra 100 por 1000 → promedio 10.
         25/01 vende 20 por 230 → 230 − 10×20 = +30      (quedan 80, costo 800)
         10/02 vende 10 por 115 → 115 − 10×10 = +15      (quedan 70, costo 700)
         10/03 vende 30 por 360 → 360 − 10×30 = +60      (quedan 40, costo 400)
         10/04 compra 10 por 125 → 50 nominales, costo 525, promedio 10,50
    XYZ: compra 50 por 500 → promedio 10; 20/02 vende 30 por 360 → +60 (quedan 20, costo 200).
    BTC: saldo inicial 0,05 por 4500 (estimado) + minado 0,002 por 178,90 → 0,052 por 4678,90,
         promedio 89.978,846. 05/02 convierte 0,004 por 349,29 → 349,29 − 359,915 = −10,625, marcado estimado.
         Queda costo 4678,90 − 359,915 = 4318,985 sobre 0,048 (el interés no entra en el costo).
    """
    c = calcular_costos(datos)
    assert {i: (round(r.usd, 3), r.estimado) for i, r in c.realizados.items()} == {
        5: (30.0, False), 10: (15.0, False), 14: (60.0, False), 11: (60.0, False), 8: (-10.625, True),
    }  # fmt: skip
    assert c.por_activo["SPY"].costo == pytest.approx(525) and c.por_activo["SPY"].promedio == pytest.approx(10.5)
    assert c.por_activo["XYZ"].costo == pytest.approx(200) and not c.por_activo["XYZ"].estimado
    assert c.por_activo["BTC"].costo == pytest.approx(4678.90 - 4678.90 / 0.052 * 0.004)
    assert c.por_activo["BTC"].estimado  # incluye el saldo inicial estimado
    assert "USDT" not in c.por_activo  # los activos de valor fijo no tienen costo


def test_historial_incompleto_no_da_costo(datos: Datos) -> None:
    """Sin el saldo inicial de BTC, antes del primer movimiento ya había 0,05: no se conoce el costo."""
    sin_inicial = Datos(datos.tenencias, [o for i, o in enumerate(datos.movimientos) if i != 1], datos.precios)
    c = calcular_costos(sin_inicial)
    assert "BTC" not in c.por_activo
    # la conversión queda sin resultado; las ventas de SPY y XYZ siguen teniéndolo
    assert sorted(sin_inicial.movimientos[i].activo for i in c.realizados) == ["SPY", "SPY", "SPY", "XYZ"]


# --- 5.11: USD de los devengos diarios


def test_usd_del_interes_nexo(serie: Serie, precios: Precios) -> None:
    """Σ 0,0000031 × precio del BTC de cada día, del 01/02 al 28/02 (28 días). El `usd` guardado (0) no se usa."""
    dias = [f"2025-02-{d:02d}" for d in range(1, 29)]
    a_mano = sum(3.1e-6 * precios[d]["btc_usdt"] for d in dias)
    assert usd_devengos(serie) == {13: pytest.approx(a_mano)}
    assert a_mano == pytest.approx(7.64, abs=C)


# --- 5.12: aportes y retiros


def test_clasificacion_mensual(serie: Serie) -> None:
    """Flujos posteriores al 01/01 (los saldos iniciales son de la primera fecha y no cuentan):

    ene: +1000 compra SPY (aporte) · −230 venta con destino Mineros (a la compra de bienes)   → neto +770
    feb: +178,90 minería (BTC minado) · −300 costo (luz y seguro) · −115 venta con destino    → neto −236,10
    mar: −360 venta con destino · −200 compra de bienes                                       → neto −560
    abr: +300 aporte · +125 compra SPY (aportes 425) · −100 compra de bienes                  → neto +325
    """
    p = periodo_flujos(serie)
    assert [(f.mes, f.ap, f.rm, f.rv, f.rt, f.rc) for f in p.meses] == [
        ("2025-01", 1000, 0, 0, 230, 0),
        ("2025-02", 0, pytest.approx(178.9), 0, 115, 300),
        ("2025-03", 0, 0, 0, 560, 0),
        ("2025-04", 425, 0, 0, 100, 0),
    ]
    assert [round(f.neto, 2) for f in p.meses] == [770, -236.1, -560, 325]
    assert [f.cierre.t for f in p.meses if f.cierre] == [
        "2025-01-31",
        "2025-02-28",
        "2025-03-31",
        "2025-04-30",
    ]


def test_kpis_del_periodo_completo(serie: Serie) -> None:
    """Valor inicial 10.100 (fila 0). Aportes = 1000 + 425 + 178,90 minado = 1603,90.
    Retiros: ventas 0 · a bienes 230+115+560+100 = 1005 · luz 300.
    Capital neto = 10.100 + 1603,90 − 1005 − 300 = 10.398,90 (coincide con capT del control).
    Ganancia = valor final 10.999,56 − 10.398,90 = 600,66.
    """
    p = periodo_flujos(serie)
    assert (p.desde_mes, p.hasta_mes, p.base) == ("2025-01", "2025-04", 0)
    assert p.valor_inicial == pytest.approx(10100)
    assert p.aportes == pytest.approx(1603.90) and p.minado == pytest.approx(178.90)
    assert (p.retiros, p.a_bienes, p.luz) == (0, 1005, 300)
    assert p.capital_neto == pytest.approx(10398.90) == pytest.approx(serie.ultima.capT)
    assert p.ganancia == pytest.approx(600.66, abs=C)


def test_periodo_desde_marzo(serie: Serie) -> None:
    """Desde marzo: arranca en el cierre de febrero (10.982,30). El capital del gráfico arranca en ese valor:
    base = tot − capT del 28/02 = 10.982,30 − 10.633,90 = 348,40.
    Aportes 425 · a bienes 560 + 100 = 660 → capital neto 10.982,30 + 425 − 660 = 10.747,30.
    """
    p = periodo_flujos(serie, "2025-03")
    assert [r.t for r in p.puntos] == ["2025-02-28", "2025-03-31", "2025-04-30"]
    assert p.valor_inicial == pytest.approx(10982.30, abs=C) and p.base == pytest.approx(348.40, abs=C)
    assert (p.aportes, p.a_bienes, p.luz) == (425, 660, 0)
    assert p.capital_neto == pytest.approx(10747.30, abs=C)
    assert p.capital(p.puntos[0]) == pytest.approx(p.valor_inicial)  # el capital arranca en el valor inicial
    assert p.capital(p.puntos[-1]) == pytest.approx(p.capital_neto)


def test_detalle_de_un_mes(serie: Serie) -> None:
    """Abril, agrupado por concepto (aportes primero) y tipo: Aporte +300, Compras +125, Compra de bienes −100."""
    abril = periodo_flujos(serie).meses[-1]
    assert [(g.etiqueta, g.total, g.movimientos, g.por_activo) for g in abril.grupos] == [
        ("Aporte", 300, 1, [("USD billete", 300)]),
        ("Compras", 125, 1, [("SPY", 125)]),
        ("Compra de bienes", -100, 1, [("USD Balanz", -100)]),
    ]
    # la venta de enero con destino Mineros también figura como "Compra de bienes"
    enero = periodo_flujos(serie).meses[0]
    assert [(g.etiqueta, g.tipo, g.total) for g in enero.grupos] == [
        ("Compras", "Compra", 1000),
        ("Compra de bienes", "Venta", -230),
    ]


# --- 5.13: producción minera


def test_produccion_minera(datos: Datos, serie: Serie, precios: Precios) -> None:
    """Un solo mes con actividad: febrero, 0,002 BTC por 178,90 y 300 de luz → neto −121,10.
    Marzo y abril van en cero y arrastran el acumulado. Recupero = −121,10 ÷ 6000 (costo de los equipos).
    Amortización anual = 6000 × (75% − 25%) ÷ 6 años = 500. Promedio mensual sobre 1 mes con cobro o costo.
    """
    p = produccion(datos.movimientos, datos.tenencias.mineros, serie.ultima.t, serie.ultima.pu["BTC"])
    assert p is not None
    assert [(m.mes, m.btc, m.pagos) for m in p.meses] == [
        ("2025-02", 0.002, 1),
        ("2025-03", 0, 0),
        ("2025-04", 0, 0),
    ]
    assert [round(m.net, 2) for m in p.meses] == [-121.1, 0, 0]
    assert [round(m.acc, 2) for m in p.meses] == [-121.1, -121.1, -121.1]
    assert p.neto == pytest.approx(-121.1) == pytest.approx(p.promedio_mensual)
    assert p.recupero == pytest.approx(-121.1 / 6000)
    assert p.amortizacion_anual == pytest.approx(500)
    assert p.valor_hoy == pytest.approx(0.002 * precios["2025-04-30"]["btc_usdt"])
    assert (p.pagos, p.meses_con_cobro, p.pagos_costos) == (1, 1, 1)


# --- 5.14: análisis de un período


def test_analisis_de_la_cartera(serie: Serie, precios: Precios) -> None:
    """31/01 → 30/04, cartera financiera. Flujos del período (31/01 < fecha ≤ 30/04):
    01/02 −121,10 (178,90 − 300) · 10/02 −115 · 10/03 −360 · 15/03 −200 · 01/04 +300 · 10/04 +125 · 20/04 −100
    neto = −471,10. Ganancia = (V1 − V0) − neto.
    Lo mismo en SPY: se compran V0/spy(31/01) unidades y cada flujo compra o vende al precio de su día.
    """
    a = analizar_periodo(serie, "2025-01-31", "2025-04-30", "tot")
    flujos = {
        "2025-02-01": 178.9 - 300,
        "2025-02-10": -115,
        "2025-03-10": -360,
        "2025-03-15": -200,
        "2025-04-01": 300,
        "2025-04-10": 125,
        "2025-04-20": -100,
    }
    neto = sum(flujos.values())
    assert neto == pytest.approx(-471.10)
    assert a.v0 == pytest.approx(11076.56, abs=C) and a.v1 == pytest.approx(10999.56, abs=C)
    assert a.neto == pytest.approx(neto)
    assert a.ganancia == pytest.approx(10999.56 - 11076.56 + 471.10, abs=0.02)
    unidades = a.v0 / pu_spy(precios, "2025-01-31") + sum(f / pu_spy(precios, d) for d, f in flujos.items())
    assert a.ganancia_spy == pytest.approx(unidades * pu_spy(precios, "2025-04-30") - a.v0 - neto)
    assert a.diferencia == pytest.approx(a.ganancia - a.ganancia_spy)  # type: ignore[operator]
    assert a.variacion_pct == pytest.approx((a.v1 - a.v0) / a.v0)


def test_analisis_del_patrimonio(serie: Serie) -> None:
    """Mismo período, patrimonio: los flujos son flowP.
    01/02: 0 (minería y costo se neutralizan) · 10/02: 0 (venta con destino al auto) · 01/03: +3000 (2ª tanda)
    10/03: +100 (cuota 3; la venta va al terreno) · 15/03: 0 · 25/03: +100 (cuota 12 cancelada con plata de afuera)
    01/04: +300 · 10/04: +125 + 100 (cuota 4) · 20/04: 0 (cuota 11 cancelada desde la cartera)   → neto 3725
    """
    a = analizar_periodo(serie, "2025-01-31", "2025-04-30", "pat")
    assert a.neto == pytest.approx(3000 + 100 + 100 + 300 + 225)
    assert a.ganancia == pytest.approx(a.v1 - a.v0 - 3725)


def test_analisis_de_bienes_no_tiene_flujos(serie: Serie) -> None:
    a = analizar_periodo(serie, "2025-01-31", "2025-04-30", "bie")
    assert a.v0 == pytest.approx(serie.en("2025-01-31").min) and a.v1 == pytest.approx(4390.46 + 1875.04, abs=C)  # type: ignore[union-attr]
    assert a.neto is None and a.ganancia is None and a.ganancia_spy is None


def test_analisis_de_un_activo(serie: Serie, precios: Precios) -> None:
    """SPY: compras − ventas = signo(cantidad) × usd → −115 (10/02) − 360 (10/03) + 125 (10/04) = −350.
    Posición: 80 nominales al 31/01 y 50 al 30/04. Valor: 80 × pu(31/01) → 50 × pu(30/04).
    """
    a = analizar_periodo(serie, "2025-01-31", "2025-04-30", activo="SPY")
    assert (a.modo, a.cantidad_0, a.cantidad_1) == ("activo", 80, 50)
    assert a.v0 == pytest.approx(80 * pu_spy(precios, "2025-01-31")) and a.v1 == pytest.approx(
        50 * pu_spy(precios, "2025-04-30")
    )
    assert a.neto == pytest.approx(-350)
    assert a.ganancia == pytest.approx(a.v1 - a.v0 + 350)
    # el interés de Nexo no cuenta como compra de BTC: quedan la conversión (−349,29) y el minado (+178,90)
    btc = analizar_periodo(serie, "2025-01-31", "2025-04-30", activo="BTC")
    assert btc.neto == pytest.approx(178.90 - 349.29)


def test_analisis_valida_las_fechas(serie: Serie) -> None:
    with pytest.raises(ValueError, match="tienen que estar en la serie"):
        analizar_periodo(serie, "2024-12-31", "2025-04-30")
    with pytest.raises(ValueError, match="posterior"):
        analizar_periodo(serie, "2025-04-30", "2025-01-31")
    with pytest.raises(ValueError, match="no existe el activo"):
        analizar_periodo(serie, "2025-01-31", "2025-04-30", activo="NADA")


# --- 5.15: tabla de movimientos


def test_orden_de_la_tabla(datos: Datos) -> None:
    """Del más nuevo al más viejo. A igual fecha va primero el grupo más nuevo, y cada Pago o Cobro queda
    pegado debajo de su operación: 20/02 venta XYZ (11) y su cobro (12); 05/02 conversión (8) y su cobro (9);
    01/02 primero el costo (7) y después la minería (6); 15/01 compra XYZ (3) y su pago (4);
    01/01 primero el saldo de BTC (1) y después el de USDT (0).
    """
    assert orden_tabla(datos.movimientos) == [
        18,
        17,
        16,
        15,
        14,
        13,
        11,
        12,
        10,
        8,
        9,
        7,
        6,
        5,
        3,
        4,
        2,
        1,
        0,
    ]


def test_cantidad_acumulada(serie: Serie) -> None:
    """Tenencia después de cada movimiento. Arranca en cantidad_actual − Σ cantidades:
    USD Balanz 160 − (−500 + 360 − 200 − 100) = 600 → 100 → 460 → 260 → 160.
    SPY 0 → 100 → 80 → 70 → 40 → 50.   BTC 0 → 0,05 → 0,052 → 0,048 → 0,0480868.
    """
    acum: dict[str, list[float]] = {}
    for f in reversed(tabla_movimientos(serie)):
        acum.setdefault(f.mov.activo, []).append(f.acumulada)
    assert acum["USD Balanz"] == [100, 460, 260, 160]
    assert acum["SPY"] == [100, 80, 70, 40, 50]
    assert acum["BTC"] == [0.05, 0.052, 0.048, 0.0480868]
    assert acum["USDT"] == [5000, 4700, 5049.29]


def test_precio_valor_hoy_y_resultado(serie: Serie, precios: Precios) -> None:
    filas = {f.indice: f for f in tabla_movimientos(serie)}
    hoy = pu_spy(precios, "2025-04-30")
    # compra de 100 SPY por 1000: precio 10; hoy vale 100 × pu; resultado = valor hoy − 1000
    compra = filas[2]
    assert compra.precio_usd == 10 and compra.valor_usd == 1000
    assert compra.valor_hoy == pytest.approx(100 * hoy) and compra.resultado == pytest.approx(100 * hoy - 1000)
    # venta de 20 SPY por 230: valor −230, precio 11,50; como todavía hay SPY no dice "vendido"; resultado realizado +30
    venta = filas[5]
    assert (venta.valor_usd, venta.precio_usd, venta.valor_hoy, venta.vendido, venta.resultado) == (
        -230,
        11.5,
        None,
        False,
        30,
    )
    # conversión de BTC: resultado realizado con marca de estimado (viene del saldo inicial)
    assert filas[8].resultado == pytest.approx(-10.625, abs=C) and filas[8].resultado_estimado
    # movimientos estimados: sin valor hoy ni resultado
    assert (filas[0].valor_usd, filas[0].valor_hoy, filas[0].resultado) == (5000, None, None)
    assert (filas[1].valor_usd, filas[1].valor_hoy, filas[1].resultado) == (4500, None, None)
    # activos de valor fijo: sin precio; valor hoy = cantidad; resultado "—" porque no cambia
    pago = filas[4]
    assert (pago.precio_usd, pago.valor_usd, pago.valor_hoy, pago.resultado) == (None, -500, -500, None)
    # el interés usa el USD calculado por el motor (5.11), no el 0 guardado
    interes = filas[13]
    assert interes.usd == pytest.approx(7.64, abs=C) and interes.valor_usd == pytest.approx(interes.usd)
    assert interes.valor_hoy == pytest.approx(0.0000868 * precios["2025-04-30"]["btc_usdt"])


def test_activo_vendido_por_completo(datos: Datos, serie: Serie) -> None:
    """Si la tenencia actual de XYZ fuera 0 (se vendieron también los 20 que quedan), sus filas dicen "vendido"."""
    from cartera.motor.series import calcular_serie

    ten = datos.tenencias.model_copy(deep=True)
    ten.activo("XYZ").cantidad = 0  # type: ignore[union-attr]
    venta = datos.movimientos[11].model_copy(update={"fecha": "2025-04-25", "cantidad": -20.0, "usd": 230.0})
    s = calcular_serie(Datos(ten, [*datos.movimientos, venta], datos.precios))
    filas = {f.indice: f for f in tabla_movimientos(s)}
    assert filas[3].vendido and filas[3].valor_hoy is None and filas[3].resultado is None  # la compra
    assert filas[11].vendido and filas[11].resultado == 60  # venta anterior: 360 − 10×30
    assert filas[19].vendido and filas[19].resultado == 30  # la venta final: 230 − 10×20


# --- 5.16 y 5.17, tabla de posiciones


def test_base_100(serie: Serie, precios: Precios) -> None:
    """Solo activos no fijos con tenencia. Base = primera fila; puntos mensuales: precio ÷ precio base × 100."""
    b = {s.ticker: s for s in base_100(serie)}
    assert set(b) == {"SPY", "XYZ", "BTC"}
    assert [d for d, _ in b["SPY"].puntos] == [
        "2025-01-01",
        "2025-01-31",
        "2025-02-28",
        "2025-03-31",
        "2025-04-30",
    ]
    assert b["SPY"].puntos[0][1] == 100
    assert b["SPY"].puntos[-1][1] == pytest.approx(pu_spy(precios, "2025-04-30") / pu_spy(precios, "2025-01-01") * 100)
    assert b["BTC"].puntos[-1][1] == pytest.approx(precios["2025-04-30"]["btc_usdt"] / 90000 * 100)
    # desde marzo: la base es el cierre de febrero
    desde_marzo = {s.ticker: s for s in base_100(serie, "2025-03")}
    assert desde_marzo["SPY"].base == "2025-02-28" and len(desde_marzo["SPY"].puntos) == 3
    assert desde_marzo["SPY"].puntos[-1][1] == pytest.approx(
        pu_spy(precios, "2025-04-30") / pu_spy(precios, "2025-02-28") * 100
    )


def test_composicion_parte_pagada_y_valor_completo(serie: Serie) -> None:
    """Al 30/04: auto = 1315 × (1 − 15% × 74 días ÷ 365,25) = 1275,04; terreno 600; mineros 4390,46 (estimado).
    Deuda del plan: 12 − 4 pagas − 2 canceladas = 6 cuotas × 100 = 600.
    Parte pagada: el auto figura por 1275,04 − 600 = 675,04 y el total da el patrimonio neto.
    Valor completo: el auto figura por 1275,04 y el total da los activos totales (patrimonio + deuda).
    """
    auto = 1315 * (1 - 0.15 * 74 / 365.25)
    neto, bruto = composicion(serie, neto=True), composicion(serie, neto=False)
    assert [g.clave for g in neto.grupos] == [
        "CEDEARs",
        "Cripto",
        "Liquidez",
        "Bienes",
    ]  # sin "Acciones argentinas": no hay
    assert [i.clave for i in neto.grupos[1].items] == ["USDT", "BTC"]  # de mayor a menor
    bienes = {i.clave: i for i in neto.grupos[-1].items}
    assert list(bienes) == ["Mineros", "Auto Ejemplo", "Terreno Ejemplo"]
    assert bienes["Auto Ejemplo"].valor == pytest.approx(auto - 600) and bienes["Auto Ejemplo"].deuda == 600
    assert bienes["Terreno Ejemplo"].valor == 600 and bienes["Mineros"].estimado
    assert neto.total() == pytest.approx(serie.ultima.pat) == pytest.approx(16665.06, abs=C)
    assert {i.clave: i.valor for i in bruto.grupos[-1].items}["Auto Ejemplo"] == pytest.approx(auto)
    assert bruto.total() == pytest.approx(serie.ultima.pat + serie.ultima.deu)
    assert neto.total(no_financieros=False) == pytest.approx(serie.ultima.tot)
    assert neto.total(financieros=False) == pytest.approx(4390.46 + 675.04 + 600, abs=C)


def test_composicion_en_el_tiempo(serie: Serie) -> None:
    """Por tipo, mensual. Liquidez (USD Balanz + billetes): 100 · 460 · 260 · 160 + 300."""
    por_tipo = composicion_en_el_tiempo(serie)
    assert list(por_tipo) == ["CEDEARs", "Cripto", "Liquidez"]
    assert por_tipo["Liquidez"] == [
        ("2025-01-31", 100),
        ("2025-02-28", 460),
        ("2025-03-31", 260),
        ("2025-04-30", 460),
    ]
    for i, r in enumerate(serie.mensuales):
        assert sum(v[i][1] for v in por_tipo.values()) == pytest.approx(r.tot)
    por_activo = composicion_en_el_tiempo(serie, por_activo=True, desde_mes="2025-04")
    assert list(por_activo) == ["SPY", "XYZ", "BTC", "USDT", "USD Balanz", "USD billete"]
    assert por_activo["USD billete"] == [("2025-03-31", 0), ("2025-04-30", 300)]


def test_tabla_de_posiciones(serie: Serie, precios: Precios) -> None:
    t = tabla_posiciones(serie)
    assert [g.grupo for g in t.grupos] == ["Cripto · Nexo", "CEDEARs · Balanz", "Liquidez · USD"]  # por valor
    cedears = t.grupos[1]
    spy, xyz = cedears.posiciones
    assert (spy.ticker, spy.cantidad, spy.costo) == ("SPY", 50, 525)
    # resultado de la posición = valor − costo; peso sobre el total y sobre el grupo
    assert spy.resultado == pytest.approx(50 * pu_spy(precios, "2025-04-30") - 525)
    assert spy.peso == pytest.approx(spy.valor / serie.ultima.tot)
    assert spy.peso_en_grupo == pytest.approx(spy.valor / (spy.valor + xyz.valor))
    # variaciones de precio: 1D contra el 29/04, 1M contra el 31/03, "1A" contra la fila 0
    assert spy.variacion["1M"] == pytest.approx(pu_spy(precios, "2025-04-30") / pu_spy(precios, "2025-03-31") - 1)
    assert spy.variacion["1A"] == pytest.approx(pu_spy(precios, "2025-04-30") / pu_spy(precios, "2025-01-01") - 1)
    # grupo: costo 525 + 200; resultado completo (los dos tienen costo)
    assert cedears.costo == 725 and not cedears.resultado_parcial and not cedears.resultado_estimado
    # la variación del grupo usa las cantidades actuales a los dos precios
    antes = 50 * pu_spy(precios, "2025-03-31") + 20 * precios["2025-03-31"]["ars"]["XYZ"] / precios["2025-03-31"]["mep"]
    assert cedears.variacion["1M"] == pytest.approx(cedears.valor / antes - 1)
    # cripto: USDT no tiene costo → resultado parcial; BTC viene de un saldo estimado
    cripto = t.grupos[0]
    assert cripto.resultado_parcial and cripto.resultado_estimado
    assert [p.ticker for p in cripto.posiciones] == ["USDT", "BTC"]
    assert cripto.posiciones[0].variacion == {"1D": None, "1M": None, "1A": None}
    # liquidez: todos de valor fijo → sin resultado ni variaciones
    assert t.grupos[2].costo is None and t.grupos[2].variacion["1M"] is None
    # fila Total: suma de costos conocidos y TWR
    assert t.costo == pytest.approx(525 + 200 + 4318.985, abs=C)
    assert t.rendimiento["1A"] == pytest.approx(serie.ultima.idx - 1)


def test_lista_lateral_de_evolucion(serie: Serie, precios: Precios) -> None:
    """Activos con más de 0,5 USD en abril, de mayor a menor, con la variación de precio desde el inicio elegido."""
    lista = lista_evolucion(serie)
    assert [a.ticker for a in lista] == ["USDT", "BTC", "SPY", "USD billete", "XYZ", "USD Balanz"]
    por_ticker = {a.ticker: a for a in lista}
    assert por_ticker["USDT"].variacion_precio is None
    assert por_ticker["SPY"].variacion_precio == pytest.approx(
        pu_spy(precios, "2025-04-30") / pu_spy(precios, "2025-01-01") - 1
    )
    desde_feb = {a.ticker: a for a in lista_evolucion(serie, serie.en("2025-02-28"))}
    assert desde_feb["BTC"].variacion_precio == pytest.approx(
        precios["2025-04-30"]["btc_usdt"] / precios["2025-02-28"]["btc_usdt"] - 1
    )

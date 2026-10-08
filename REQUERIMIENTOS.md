# Mi cartera en dólares: requerimientos para la versión en servidor (Python + JSON en Hostinger)

Versión 1.2 · 07/10/2026 (sin datos del usuario) · Documento para Claude Code

Cambios de la 1.2: `pagada_desde_cartera` en las cuotas canceladas (4.4, 4.5.1, 5.6, 5.8, 6.12, RF-43) y valores de control regenerados (T-01).

---

## 0. Cómo usar este documento (leer primero)

Este documento especifica una aplicación web de un solo usuario. La aplicación reemplaza el tablero actual "Mi cartera en dólares", que hoy es una página HTML con toda la lógica en JavaScript. El objetivo es reproducir **exactamente** los mismos cálculos y la misma experiencia, con estas diferencias:

- Los cálculos se hacen en un backend Python.
- Los datos se guardan en archivos `.json` en el servidor.
- Los precios se actualizan solos con un job diario en el servidor.
- Hay un módulo de administración para cargar movimientos sin editar JSON a mano.
- Todo se despliega en un VPS de Hostinger.

### 0.1 Contenido del paquete

```
REQUERIMIENTOS.md                     ← este documento
referencia/
  tablero_actual.html                 ← tablero actual (HTML + CSS + JS) como referencia visual y de lógica.
                                         No incluye datos: la serie de precios fue vaciada y los textos con montos se volvieron genéricos.
  calculo_referencia.py               ← port mínimo en Python de la valuación (no es código de producción)
  ejemplo/                            ← juego de datos FICTICIO para desarrollo y tests
    generar_ejemplo.py                ← genera los tres JSON de abajo
    tenencias.json · movimientos.json · precios_diarios.json
    valores_control.json              ← resultados esperados (golden values) de calculo_referencia.py sobre estos datos
```

**El paquete no contiene datos reales del usuario.** La app se construye y se prueba solo con el ejemplo ficticio. El usuario carga sus datos reales en el servidor después del despliegue (sección 4.3). **No pedir ni inventar datos reales.**

### 0.2 Reglas de precedencia

1. **Lógica de negocio.** Si este documento y el JavaScript de `referencia/tablero_actual.html` no coinciden, manda el JavaScript, salvo los cambios que este documento pide en forma explícita (marcados **[CAMBIO]**). Ante una ambigüedad, replicar el comportamiento del JS y dejar un comentario en el código.
2. **Interfaz.** Replicar el diseño, los textos, las pestañas, los colores (variables CSS de los temas claro, atenuado y oscuro) y las interacciones de `tablero_actual.html`. Se puede reutilizar su CSS y su JS de presentación casi tal cual.
3. **Datos.** Los esquemas de la sección 4.5 y el ejemplo ficticio de `referencia/ejemplo/` definen el formato. Los datos reales los carga el usuario; el código no debe asumir tickers, montos ni fechas particulares (todo sale de los JSON y de `config.json`).
4. **Idioma.** Interfaz en español rioplatense. Formato numérico `es-AR` (separador de miles `.`, decimal `,`). Fechas `dd/mm/aa` en la UI e ISO `AAAA-MM-DD` en datos y API.

### 0.3 Definición de terminado (global)

- Todos los tests de la sección 11 pasan, incluidos los golden values de `referencia/ejemplo/valores_control.json` (tolerancia ±0,02 USD y ±0,01 puntos porcentuales).
- La app corre en el VPS con HTTPS, login, job diario activo y backups funcionando (sección 10).
- Hay un `README.md` con instalación, carga de datos (4.3), operación, restauración de backups y procedimientos mensuales.

---

## 1. Objetivo y alcance

### 1.1 Objetivo

Seguir en dólares el patrimonio personal del usuario:
- Activos financieros: CEDEARs y acciones argentinas en Balanz, BTC y USDT en Nexo, y dólares (en Balanz y en billetes).
- Otros activos no financieros: equipos de minería de BTC.
- Bienes: terreno y auto.
- Pasivos: el plan de ahorro del auto.

Para todo lo anterior, la app muestra la evolución diaria, el rendimiento ponderado en el tiempo, los aportes y retiros, los resultados por posición y la producción minera.

### 1.2 Dentro del alcance

- Backend Python que guarda los datos en JSON, calcula todo y expone una API.
- Frontend web que replica el tablero actual.
- Job diario de precios: Yahoo Finance, Binance y ArgentinaDatos.
- Botón "Actualizar ahora" con precios en vivo, resuelto desde el servidor.
- Módulo de administración: alta, edición y baja de movimientos y de tenencias, bienes, mineros, plan de ahorro y activos nuevos.
- Importación del export de operaciones de Balanz.
- Exportación y backup de los JSON.
- Login de un único usuario.
- Despliegue en un VPS de Hostinger.

### 1.3 Fuera del alcance

- El registro de gastos personales ("Mis gastos"). Es otra aplicación.
- Multiusuario, registro de cuentas y roles.
- Recomendaciones de inversión.
- Conexión directa a cuentas de brokers o exchanges con credenciales del usuario. No se guardan claves de Balanz, Nexo ni Binance.
- Fase 2 (opcional, sección 12): lectura automática del PDF de FIAT Plan y 2FA.

---

## 2. Glosario

| Término | Significado |
|---|---|
| CEDEAR | Certificado que cotiza en pesos en BYMA y representa una fracción (ratio) de una acción extranjera. |
| MEP | Dólar bolsa, valor de venta del día (ARS por USD). Fuente: ArgentinaDatos. |
| Nominal | Unidad de CEDEAR o acción. Las cantidades se expresan en **nominales actuales** (ajustadas por cambios de ratio y splits). |
| Activos financieros (`tot`) | Suma de las posiciones de la cartera valuadas a mercado. |
| Mineros (`min`) | Equipos de minería de BTC valuados a valor contable. |
| Bienes (`inm`) | Inmuebles y vehículos (`tenencias.inmuebles`). |
| Pasivos (`deu`) | Deudas en cuotas, por ejemplo un plan de ahorro de un auto (`tenencias.pasivos`). |
| Patrimonio neto (`pat`) | `tot + min + inm − deu`. |
| Flujo (`flujo_usd`) | Aporte (+) o retiro (−) de plata de afuera de la cartera financiera. |
| Pase interno | Movimiento entre activos de la cartera (compra con USD Balanz, conversión BTC↔USDT). No es flujo. |
| TWR | Rendimiento ponderado en el tiempo (time-weighted return), diario, que descuenta flujos. |
| Capital neto | Valor inicial + aportes − retiros acumulados. |
| En curso | Último punto de la serie con precios del momento (no es un cierre). |

---

## 3. Arquitectura y stack (requerimientos técnicos generales)

| ID | Requerimiento |
|---|---|
| RT-01 | Python 3.12. Backend con **FastAPI**, servido por **uvicorn** detrás de **nginx** (reverse proxy y TLS). |
| RT-02 | Persistencia **exclusivamente en archivos `.json`** (sección 4). Sin base de datos. |
| RT-03 | Validación de esquemas con **pydantic v2**. Ningún archivo se escribe sin validar primero. |
| RT-04 | Cálculos en Python puro o con **pandas/numpy** (a elección). Recalcular toda la serie (del orden de 1.500 fechas × 30 activos) debe tardar menos de 1 s. Se cachea en memoria y se invalida cuando cambia cualquier JSON (por mtime o hash). |
| RT-05 | Frontend: HTML + CSS + JavaScript sin framework, igual que el actual, con **Lightweight Charts 4.2.0** (`https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js`), o una copia local en `static/vendor/` (preferido, para no depender del CDN). Los templates pueden ser Jinja2 o archivos estáticos. |
| RT-06 | **[CAMBIO]** El frontend **no** contiene lógica de negocio. Pide a la API los datos ya calculados y solo dibuja. Solo puede hacer cálculos de presentación: formatos, filtros, ordenamientos y colocación de etiquetas. |
| RT-07 | HTTP saliente con `httpx`, timeouts de 15 s, 3 reintentos con backoff y `User-Agent` explícito. Precios de Yahoo con **`yfinance`** (o la API `query1.finance.yahoo.com` vía httpx como respaldo). |
| RT-08 | Tareas programadas con **systemd timers** (no cron de usuario ni threads dentro de la app). |
| RT-09 | Configuración por variables de entorno en `.env` (cargado con `pydantic-settings`): `CARTERA_DATA_DIR`, `CARTERA_BACKUP_DIR`, `CARTERA_USER`, `CARTERA_PASSWORD_HASH`, `CARTERA_SECRET_KEY`, `TZ=America/Argentina/Buenos_Aires`, `NOTIF_*` (sección 6.10). |
| RT-10 | Logging estructurado (JSON lines) a `logs/app.log` y `logs/job_precios.log`, rotados con `logging.handlers.RotatingFileHandler` (5 × 5 MB). |
| RT-11 | Dependencias fijadas en `requirements.txt` (o `pyproject.toml` + `uv.lock`). Formato y lint con `ruff`; tipos con `mypy --strict` en `cartera/motor` y `cartera/datos`. |
| RT-12 | Tests con `pytest`. Ningún test usa la red: las respuestas de Yahoo, Binance y ArgentinaDatos se graban como fixtures. |

### 3.1 Estructura de repositorio sugerida

```
cartera/
  app/            main.py (FastAPI), auth.py, api/ (routers), templates/, static/ (css, js, vendor)
  cartera/
    datos/        modelos pydantic, repositorio JSON (lectura, escritura atómica, locks, versiones, backups)
    motor/        cantidades.py, valuacion.py, flujos.py, rendimiento.py, costos.py, bienes.py, mineria.py, series.py
    precios/      yahoo.py, binance.py, argentinadatos.py, actualizar.py (job diario), en_vivo.py
    importar/     balanz.py
  scripts/        cargar_datos.py, backup.py, restaurar.py, verificar_integridad.py
  deploy/         nginx.conf, cartera.service, cartera-precios.service/.timer, cartera-backup.service/.timer, deploy.sh
  tests/
  referencia/       (copiado de este paquete; ejemplo/ se usa como fixture de tests)
```

---

## 4. Almacenamiento de datos en JSON

### 4.1 Archivos

Todos viven en `CARTERA_DATA_DIR` (por ejemplo `/srv/cartera/datos`), **fuera del repositorio git**.

| Archivo | Contenido | Quién escribe |
|---|---|---|
| `tenencias.json` | Activos (cantidad actual), mineros, inmuebles, pasivos (esquema en 4.5). | Admin, importador |
| `movimientos.json` | Lista de movimientos. Esquema en 4.5, con los campos `id` y `contrapartida_de`. | Admin, importador |
| `precios_diarios.json` | Serie diaria `{fecha, mep, btc_usdt, ars:{ticker: precio}}`, calendario completo. | Job diario, admin |
| `fuentes_precios.json` | Cómo obtener el precio de cada activo (símbolo de Yahoo, factor, ratio NY, ajustes). | Admin |
| `precios_en_vivo.json` | Último resultado de "Actualizar ahora" `{fecha, ts, mep, btc, ars:{}}`. | Endpoint en vivo |
| `config.json` | Parámetros de la app: inicio de la serie (`2023-01-01`), hora del job, umbrales de validación, colores por ticker, orden de tipos. | Admin |
| `estado_jobs.json` | Últimas 60 ejecuciones del job de precios y de backup (inicio, fin, resultado, filas tocadas, errores). | Jobs |
| `auditoria.json` | Registro de cambios en datos: fecha y hora, acción, archivo, id, valores antes y después (diff). Se rota a `auditoria-AAAA.json` por año. | Repositorio |

### 4.2 Requerimientos del repositorio JSON

| ID | Requerimiento |
|---|---|
| RT-20 | **Escritura atómica.** Escribir en `archivo.json.tmp` en el mismo directorio, hacer `fsync` y luego `os.replace`. Nunca dejar un archivo a medio escribir. |
| RT-21 | **Bloqueo.** Lock exclusivo por archivo (`filelock` o `fcntl.flock`) durante cada lectura-modificación-escritura. El job y la web no pueden pisarse. |
| RT-22 | **Versionado.** Antes de cada escritura, copiar la versión anterior a `datos/_versiones/<archivo>/<AAAAMMDD-HHMMSS>.json`, conservando las últimas 100 por archivo. Desde la administración se puede restaurar una versión. |
| RT-23 | **Concurrencia optimista.** Cada lectura que hace la UI de administración devuelve un `version` (hash sha256 del archivo). Las escrituras lo envían y, si cambió, la API responde `409 Conflict`. |
| RT-24 | **Validación.** Esquemas pydantic estrictos y verificación de integridad (sección 4.4) antes de escribir. Si falla, no se escribe y se devuelve el detalle del error. |
| RT-25 | JSON en UTF-8, `ensure_ascii=False`, indentado con 1 espacio (salvo `precios_diarios.json`, compacto), números con `.` decimal y fechas ISO. |
| RT-26 | Si `CARTERA_DATA_DIR` está vacío, la app arranca igual: muestra un estado vacío ("Todavía no hay datos cargados") con un enlace a Administración → Cargar datos. Nunca crea datos de ejemplo en producción. `CARTERA_DEMO=1` carga el ejemplo ficticio (solo para desarrollo). |

### 4.3 Carga de datos (la hace el usuario)

1. **Formas de carga** (ambas obligatorias):
   - CLI: `python scripts/cargar_datos.py <carpeta>`.
   - Web: Administración → Cargar datos (RF-48).

   Las dos aceptan `tenencias.json` y `movimientos.json` con el esquema de 4.5. El usuario los exporta del tablero actual, que hoy publica `datos/tenencias.json` y `datos/movimientos.json` con ese mismo formato. Opcionalmente aceptan también `precios_diarios.json` y `fuentes_precios.json`.
2. **Normalización al cargar:**
   - Si un movimiento no tiene `id`, se le asigna uno estable (`"m-0001"`, `"m-0002"`…) en el **orden del archivo**.
   - Si un `Pago` o `Cobro` no tiene `contrapartida_de`, se le asigna el `id` del movimiento **anterior en el orden del archivo** que no sea `Pago` ni `Cobro`. Es la regla implícita del tablero actual: cada Pago/Cobro es la contrapartida del movimiento anterior.
   - El campo `columna_precio` de los activos queda obsoleto: se conserva pero se ignora.
   - Se conservan los campos desconocidos (`model_config = extra="allow"`).
3. **Precios:** si no se cargó `precios_diarios.json`, se construye la historia completa desde `config.inicio_serie` con RF-08, aplicando `fuentes_precios.json`. Si falta `fuentes_precios.json`, la pantalla de carga lo arma a partir de los activos, proponiendo `<TICKER>.BA` con factor 1, y el usuario lo revisa. Las reglas especiales conocidas están en la tabla de 4.5.4.
4. **Al final de la carga:**
   - Se corren las verificaciones de integridad de 4.4.
   - Se muestra un resumen: activos, cantidad de movimientos, primera y última fecha, y patrimonio neto a la última fecha.
   - Se pide confirmación antes de escribir.
5. Se crea `config.json` con los valores por defecto. Los colores por ticker se toman de las variables CSS `--c-<ticker>` del HTML de referencia; los activos sin color reciben uno de una paleta categórica.

### 4.4 Reglas de integridad (verificar en cada escritura y en `scripts/verificar_integridad.py`)

- Todo `activo` de un movimiento existe en `tenencias.activos`.
- `tipo` de movimiento ∈ {Compra, Venta, Cobro, Pago, Conversión, Minería, Costo minería, Interés Nexo, Aporte, Compra de bienes, Saldo inicial}.
- `destino`, si existe, es el `nombre` de un inmueble o `"Mineros"`.
- Las cantidades históricas reconstruidas (sección 5.2) nunca son negativas en ninguna fecha de la serie para BTC, USDT, USD Balanz y USD billete (tolerancia 1e-8). En CEDEARs y acciones, tampoco son negativas.
- `cuotas_pagas` sin números repetidos y con fechas ordenadas.
- `cuotas_canceladas` sin números repetidos entre sí ni con `cuotas_pagas`. Toda cancelada con `pagada_desde_cartera = true` tiene un movimiento con `flujo_usd < 0`, `destino` = `bien` del pasivo y su misma fecha.
- La serie de precios no tiene huecos de fechas y tiene precio > 0 para todo activo con cantidad > 0 en esa fecha.

### 4.5 Esquemas

Los ejemplos de abajo son **ficticios** y están completos en `referencia/ejemplo/`.

#### 4.5.1 `tenencias.json`

```json
{
 "actualizado": "2025-04-30",
 "moneda_valuacion": "USD",
 "activos": [
  {"ticker": "SPY", "nombre": "ETF S&P 500", "tipo": "CEDEARs", "grupo": "CEDEARs · Balanz",
   "cantidad": 50, "cotiza_en_pesos": true, "valor_fijo_usd": false},
  {"ticker": "BTC", "nombre": "Bitcoin", "tipo": "Cripto", "grupo": "Cripto · Nexo",
   "cantidad": 0.0480868, "cotiza_en_pesos": false, "valor_fijo_usd": false},
  {"ticker": "USDT", "nombre": "Tether", "tipo": "Cripto", "grupo": "Cripto · Nexo",
   "cantidad": 5049.29, "cotiza_en_pesos": false, "valor_fijo_usd": true},
  {"ticker": "USD Balanz", "nombre": "Dólar MEP en cuenta", "tipo": "Liquidez", "grupo": "Liquidez · USD",
   "cantidad": 260, "cotiza_en_pesos": false, "valor_fijo_usd": true}
 ],
 "mineros": {"modelo": "Minero X", "th_por_equipo": 100, "cantidad": 2, "fecha_compra": "2025-01-20",
   "costo_usd": 6000, "valor_inicial_pct": 75, "valor_residual_pct": 25, "vida_util_anios": 6,
   "compras": [{"fecha": "2025-01-20", "cantidad": 1, "costo_usd": 3000},
               {"fecha": "2025-03-01", "cantidad": 1, "costo_usd": 3000}]},
 "inmuebles": [
  {"nombre": "Terreno Ejemplo", "fecha_compra": "2025-03-20", "costo_usd": 560, "valor_usd": 600,
   "fecha_valuacion": "2025-03-20", "origen": "texto libre"},
  {"nombre": "Auto Ejemplo", "fecha_compra": "2025-02-15", "costo_usd": 115, "valor_usd": 115,
   "fecha_valuacion": "2025-02-15", "depreciacion_anual_pct": 15, "valor_nuevo_usd": 1315, "origen": "texto libre"}
 ],
 "pasivos": [
  {"nombre": "Plan Ejemplo", "bien": "Auto Ejemplo", "tipo": "Plan de ahorro (12 cuotas)", "cuotas_total": 12,
   "alicuota_ars": 100000, "valor_movil_ars": 5000000, "fecha_valor_movil": "2025-04-01", "mep_referencia": 1000,
   "fecha_alta": "2025-02-15", "cuotas_pagas": [{"cuota": 1, "fecha": "2025-01-10"}],
   "cuotas_canceladas": [{"cuota": 12, "fecha": "2025-03-25", "motivo": "anticipada"},
                         {"cuota": 11, "fecha": "2025-04-20", "motivo": "licitada", "pagada_desde_cartera": true}]}
 ]
}
```

- `tipo` de activo ∈ {Acciones argentinas, CEDEARs, Cripto, Liquidez} (es el orden de los grupos en la UI).
- `grupo` = "tipo · plataforma".
- `cotiza_en_pesos` y `valor_fijo_usd` no pueden ser los dos `true`.
- Un activo que no cotiza en pesos ni es fijo solo puede ser BTC. **[CAMBIO]** Para soportar otras cripto en el futuro, agregar `fuente_precio` en `fuentes_precios.json` con el par de Binance, por ejemplo `ETHUSDT`.
- `cuotas_canceladas` es opcional (ver RF-43). Cada elemento tiene `cuota`, `fecha`, `motivo` y `pagada_desde_cartera` (bool, por defecto `false`):
  - `false`: la cancelación se pagó con plata de afuera de la cartera. Es un aporte al patrimonio por `cu` (5.8), igual que una cuota paga.
  - `true`: se pagó con plata de la cartera. No suma a `flowP`, y tiene que existir un movimiento de salida (`flujo_usd < 0`) con `destino` = `bien` del pasivo y la misma fecha; ese movimiento ya queda fuera de los flujos del patrimonio (5.8).
  - En los dos casos la cuota se resta de las pendientes desde su fecha (5.6).

#### 4.5.2 `movimientos.json`

```json
{"movimientos": [
 {"id": "m-0003", "fecha": "2025-01-10", "tipo": "Compra", "activo": "SPY", "cantidad": 100,
  "usd": 1000.0, "flujo_usd": 1000.0, "nota": "compra en pesos (aporte)"},
 {"id": "m-0004", "fecha": "2025-01-15", "tipo": "Compra", "activo": "XYZ", "cantidad": 50, "usd": 500.0,
  "nota": "compra con USD Balanz"},
 {"id": "m-0005", "fecha": "2025-01-15", "tipo": "Pago", "activo": "USD Balanz", "cantidad": -500.0, "usd": 500.0,
  "contrapartida_de": "m-0004", "nota": "contrapartida"},
 {"id": "m-0014", "fecha": "2025-02-28", "tipo": "Interés Nexo", "activo": "BTC", "cantidad": 0.0000868, "usd": 0,
  "devengo_diario": {"desde": "2025-02-01", "por_dia": 0.0000031}, "nota": "interés diario de febrero"},
 {"id": "m-0015", "fecha": "2025-03-10", "tipo": "Venta", "activo": "SPY", "cantidad": -30, "usd": 360.0,
  "flujo_usd": -360.0, "destino": "Terreno Ejemplo", "nota": "venta para pagar el terreno"}
]}
```

| Campo | Regla |
|---|---|
| `cantidad` | Lleva signo: + entra, − sale. |
| `usd` | Monto en USD, siempre ≥ 0 y neto de comisiones. |
| `flujo_usd` | Solo si es un flujo externo (+ aporte / − retiro). |
| `estimado` | Opcional; marca saldos iniciales u operaciones supuestas. |
| `sin_efecto_en_saldo` | Opcional; el movimiento no cambia cantidades. |
| `devengo_diario` | Opcional. |
| `destino` | Opcional; `nombre` de un inmueble o `"Mineros"`. |

#### 4.5.3 `precios_diarios.json`

```json
{"desde": "2025-01-01", "hasta": "2025-04-30", "serie": [
 {"fecha": "2025-01-01", "mep": 1000.0, "btc_usdt": 90000.0, "ars": {"SPY": 11000.0, "XYZ": 12900.0}}
]}
```

- Calendario completo, sin huecos.
- `ars` = precio en pesos por nominal, ya corregido por ratios y splits (en nominales actuales).
- `mep` = MEP venta. `btc_usdt` = BTCUSDT a las 17:00 AR.

#### 4.5.4 `fuentes_precios.json`

```json
{"activos": {
  "SPY":  {"simbolo_yahoo": "SPY.BA", "factor": 1},
  "META": {"simbolo_yahoo": "META", "ratio_ny": 24},
  "AVGO": {"simbolo_yahoo": "AVGO.BA", "factor": 1, "respaldo": {"simbolo_yahoo": "AVGO", "ratio_ny": 38.5}}},
 "ajustes_historicos": [
  {"activo": "AAPL", "antes_de": "2024-01-24", "multiplicar_precio": 0.5, "motivo": "cambio de ratio no ajustado por Yahoo"},
  {"activo": "AVGO", "antes_de": "2026-09-29", "usar_respaldo": true, "motivo": "AVGO.BA sin historia en Yahoo"}],
 "btc": {"par": "BTCUSDT"}}
```

**Reglas especiales conocidas** (datos de mercado; precargar como valores por defecto cuando el ticker aparezca):

| Ticker | Regla |
|---|---|
| META | Sin historia del CEDEAR en Yahoo: precio NY ÷ 24 × MEP. |
| VIST | Sin historia del CEDEAR en Yahoo: precio NY ÷ 3 × MEP. |
| AVGO | Antes del 29/09/2026: precio NY ÷ 38,5 × MEP. |
| YPFD.BA | Factor 10. |
| NFLX.BA | Factor 10 (split de nov-2025), y además ×1/3 antes del 24/01/2024. |
| AAPL, MELI | ×1/2 antes del 24/01/2024. |
| TM | ×1/3 antes del 24/01/2024. |

**Cambios de ratio y splits para las cantidades** (importador de Balanz, `config.json`):

| Ticker | Ajuste |
|---|---|
| SPY | ×3 antes del 29/05/2026 |
| AAPL, MELI | ×2 antes del 24/01/2024 |
| NVDA | ×10 antes del 10/06/2024 |
| AVGO | ×10 antes del 15/07/2024 |

---

## 5. Reglas de cálculo (motor)

Todo lo que sigue debe implementarse en `cartera/motor` y es lo que verifican los golden values. Notación: `d` es una fecha ISO; las comparaciones de fechas son lexicográficas sobre ISO; `días(a,b)` es la cantidad de días calendario entre `a` y `b`.

### 5.1 Precio en USD por unidad, `pu(activo, d)`

- `valor_fijo_usd = true` (USDT, USD Balanz, USD billete): **1**.
- `cotiza_en_pesos = true`: `precios_diarios[d].ars[ticker] ÷ precios_diarios[d].mep`.
- BTC: `precios_diarios[d].btc_usdt`.
- Si no hay precio, se toma 0. La integridad garantiza que no pase con tenencia > 0.

### 5.2 Cantidad en una fecha, `q(activo, d)`

La cantidad se reconstruye **hacia atrás desde la cantidad actual** (`tenencias.activos[].cantidad`):

```
q(a, d) = cantidad_actual(a) − Σ efecto(o, d)   para o en movimientos con o.activo = a y sin sin_efecto_en_saldo
efecto(o, d):
  si o no tiene devengo_diario:  o.cantidad si o.fecha > d, si no 0     (el movimiento del día d YA ocurrió en d)
  si tiene devengo_diario {desde, por_dia}:
     d ≥ o.fecha        → 0
     d < desde          → o.cantidad
     desde ≤ d < fecha  → por_dia × días(d, o.fecha)
```

### 5.3 Valor diario

- `pos(a,d) = q(a,d) × pu(a,d)`
- `tot(d) = Σ pos`
- `por_grupo(d)`: suma por `grupo`.

### 5.4 Mineros, `min(d)`

Cada tanda de `mineros.compras[]` (`fecha`, `costo_usd`) se valúa por separado:

```
si d < fecha: 0
fin = fecha + vida_util_anios (mismo día y mes)
x = min(1, días(fecha, d) / días(fecha, fin))
valor = costo × (ini − (ini − res) × x)      ini = valor_inicial_pct/100, res = valor_residual_pct/100
```

### 5.5 Bienes, `inm(d) = Σ bval(x, d)`

```
si d < x.fecha_compra:
    Σ (−flujo_usd) de movimientos con destino = x.nombre, flujo_usd ≠ 0 y fecha ≤ d     (se suma lo ya pagado)
si no, si x.depreciacion_anual_pct:
    max(0, (x.valor_nuevo_usd o x.costo_usd) × (1 − dep/100 × días(x.fecha_compra, d)/365,25))
si no:
    x.valor_usd
```

### 5.6 Pasivos, `deu(d)`

Para cada pasivo `p`:
- `cu = alicuota_ars ÷ mep_referencia` (USD por cuota).
- `pendientes(d) = cuotas_total − #(cuotas_pagas con fecha ≤ d) − #(cuotas_canceladas con fecha ≤ d)`. Las canceladas se restan siempre, valga lo que valga `pagada_desde_cartera` (4.5.1).
- `deu(d) = 0` si `d < fecha_alta`; si no, `pendientes(d) × cu`.

### 5.7 Patrimonio

`pat(d) = tot + min + inm − deu`. En la cabecera, los porcentajes de cada bloque se calculan sobre `pat + deu` (activos totales).

### 5.8 Flujos y rendimiento (para cada fila i > 0 de la serie diaria; en la fila 0 los flujos valen 0)

```
flow_i  = Σ flujo_usd de movimientos con fecha = d_i
flowP_i = flow_i
        − Σ flujo_usd de movimientos tipo Minería o Costo minería con fecha = d_i
        + Σ costo_usd de tandas de mineros con fecha = d_i
        + (#cuotas_pagas con fecha = d_i) × cu        (solo si d_i ≥ fecha_alta del pasivo)
        + (#cuotas_canceladas con fecha = d_i y pagada_desde_cartera = false) × cu   (misma condición)
        − Σ flujo_usd de movimientos con destino ≠ "Mineros" (y destino definido) con fecha = d_i
idx_i  = idx_{i−1}  × (tot_i − flow_i)  / tot_{i−1}       idx_0 = 1
idxP_i = idxP_{i−1} × (pat_i − flowP_i) / pat_{i−1}       idxP_0 = 1
capT_i = tot_0 + Σ_{k≤i} flow_k         capP_i = pat_0 + Σ_{k≤i} flowP_k
```

- **Rendimiento entre dos fechas** = `idx_fin / idx_ini − 1`.
- **Períodos de la cabecera.** `1D` = fila anterior. `1M`, `3M` y `6M` = última fila con fecha ≤ (última fecha − 30, 91 y 182 días). `1A` se muestra como "desde 01/01/23": es la fila 0. **[CAMBIO opcional]** Agregar un "12M" real (365 días); el "1A" actual queda como "Desde el inicio".
- **Variación "hoy" de activos financieros** = `tot_L − tot_1D − (cumF_L − cumF_1D)`.

### 5.9 Serie mensual

Una fila por mes: el último día de cada mes y, para el mes en curso, la última fecha disponible. La usan todos los gráficos de historia, salvo el de Evolución, que además incluye la fila 0.

### 5.10 Costo promedio y resultado realizado (por activo no fijo)

1. Tomar los movimientos del activo sin `sin_efecto_en_saldo` y sin `devengo_diario`, ordenados por fecha.
2. `q0 = q(a, día anterior al primero)`. El historial está completo (`ok`) si `|q0| < 1e-9`.
3. Recorrerlos en orden:
   - **Compra** (cantidad > 0): `q += cantidad`, `c += usd`, y marcar `est` si el movimiento es `estimado`.
   - **Venta**: `avg = c/q`. Si `ok`, el resultado realizado es `|usd| − avg × cantidad_vendida` (con marca `*` si `est`). Después `c −= avg × vendida` y `q −= vendida`. Si `q` vuelve a 0: `c = 0`, `ok = true`, `est = false`.
4. Si `ok` y la cantidad actual > 0: `costo = c`, `costo_promedio = c/q`. Resultado de la posición = `pos_actual − costo`.
5. Valores de control con el ejemplo ficticio: SPY costo 525,00 (promedio 10,50), XYZ 200,00 (10,00), BTC 4.318,98 (ver `referencia/ejemplo/valores_control.json`).

### 5.11 Valor en USD de los movimientos con devengo diario

`usd = Σ por_dia × pu(activo, d)` para cada fecha `d` entre `desde` y `fecha` inclusive. Se calcula en el motor; no se usa el `usd` guardado.

### 5.12 Clasificación mensual de flujos (pestaña Aportes y retiros)

Se consideran los movimientos con `flujo_usd ≠ 0` y fecha > primera fecha de la serie. Por mes:

| Concepto | Regla |
|---|---|
| `ap` (aportes) | flujo > 0 y tipo ≠ Minería |
| `rm` (BTC minado) | tipo = Minería |
| `rv` (retiros) | flujo < 0, tipo ≠ Costo minería y sin destino |
| `rt` (a la compra de bienes) | flujo < 0 y con destino |
| `rc` (luz y seguro) | tipo = Costo minería |

`neto = ap + rm − rv − rt − rc`. En un período elegido, el capital del gráfico "Capital neto contra valor" es `capT + (tot_ini − capT_ini)` (arranca en el valor al inicio del período).

### 5.13 Producción minera mensual

Desde el primer mes con Minería o Costo minería hasta hoy, por mes:
- `btc` = Σ cantidad de Minería.
- `usd` = Σ usd de Minería.
- `cost` = Σ usd de Costo minería.
- `net = usd − cost`.
- `acc` = neto acumulado; recupero neto = `acc ÷ costo total de los mineros`.

Indicadores:
- Total de BTC minado, producción al cobrar y su valor hoy (`btc × pu BTC`).
- Luz y seguro.
- Resultado neto y promedio mensual (sobre los meses con cobro o costo).
- Recupero neto.
- Amortización anual de los equipos: `costo × (ini − res) / vida`.

### 5.14 Análisis de un período (arrastre sobre el gráfico de Evolución)

Para el rango `[d0, d1]` y el modo elegido (cartera, bienes, patrimonio o un activo):

- `V0`, `V1` = valor en cada punta.
- `variación = V1 − V0` (y en %).
- `net` = flujos del período (`d0 < fecha ≤ d1`):
  - Cartera: `flow`.
  - Patrimonio: `flowP`.
  - Activo: `signo(cantidad) × usd` de sus movimientos sin Interés Nexo.
- `ganancia = variación − net`.
- **Comparación con SPY:**

  ```
  u = V0/spy(d0) + Σ flujo/spy(fecha)
  ganancia_SPY = u × spy(d1) − V0 − net
  diferencia = ganancia − ganancia_SPY
  ```

  Con `spy = pu(SPY)`.
- Con un activo elegido se muestra además la posición en nominales al inicio y al final, y su diferencia.

**[CAMBIO]** Lo calcula el backend: `GET /api/analisis-periodo?desde=&hasta=&modo=&activo=`.

### 5.15 Tabla de movimientos

**Orden.** Del más nuevo al más viejo; cada Pago o Cobro va pegado a su operación (usar `contrapartida_de`). Equivale a la regla del JS:
1. Asignar un número de grupo `g` que aumenta con cada movimiento que no es Pago ni Cobro, en el orden del archivo.
2. Ordenar por fecha descendente, luego por `g` descendente y luego por el índice original ascendente.

**Cantidad acumulada.** Es la tenencia después de cada movimiento:
- Arranca en `cantidad_actual − Σ cantidades del activo`.
- Se recorre del más viejo al más nuevo, sumando, con redondeo a 8 decimales.

**Precio USD** = `|usd / cantidad|` (no aplica a los activos fijos).

**Valor hoy y resultado:**

| Caso | Valor hoy | Resultado |
|---|---|---|
| Estimado | — | — |
| Venta o Conversión | "vendido" si la tenencia actual es 0 | El resultado realizado (5.10) |
| Activo con tenencia actual 0 | "vendido" | — |
| Resto | `cantidad × pu_hoy` | `cantidad × pu_hoy − valor original` |

### 5.16 Base 100

Activos no fijos con cantidad actual > 0. Base = primera fila con precio > 0 desde el mes elegido en "Gráficos desde". Valor = `pu / pu_base × 100`, con puntos mensuales.

### 5.17 Composición

**Treemap.** Grupos por tipo, en el orden Acciones argentinas, CEDEARs, Cripto, Liquidez, más el bloque "Bienes":
- Inmuebles cuya fecha de compra ya pasó.
- Mineros, marcados "estimado".

Modo "Parte pagada" (por defecto): a cada bien se le resta la deuda de su pasivo asociado (`pasivo.bien = nombre`). Modo "Valor completo": sin restar.

**Composición en el tiempo** (mensual): por tipo o por activo, en área 100% o en líneas (USD), con selección de series. En área, la base es la suma de lo elegido; en líneas, el valor absoluto.

---

## 6. Requerimientos funcionales

Prioridad: **M** = obligatorio en la v1, **D** = deseable en la v1, **F2** = fase 2.

### 6.1 Ingesta diaria de precios (job)

| ID | Prioridad | Requerimiento |
|---|---|---|
| RF-01 | M | Un systemd timer corre `python -m cartera.precios.actualizar` **todos los días a las 20:45 hora argentina**. Si falla, reintenta a las 22:00 y a las 08:00 del día siguiente. |
| RF-02 | M | **Fuentes:** <br>• **Yahoo**: cierres diarios de cada símbolo de `fuentes_precios.json` (`.BA` en ARS; símbolos de NY en USD). <br>• **ArgentinaDatos**: `GET https://api.argentinadatos.com/v1/cotizaciones/dolares/bolsa` (histórico, campo `venta`) o `/bolsa/AAAA/MM/DD`. <br>• **Binance**: `GET /api/v3/klines?symbol=BTCUSDT&interval=1h&startTime=…`; precio del día = **cierre de la vela que abre a las 19:00 UTC** (17:00 AR). Host `api.binance.com` con respaldo `data-api.binance.vision`. |
| RF-03 | M | **Conversión a ARS por activo:** <br>• Si tiene `ratio_ny`: `precio_ars = precio_NY ÷ ratio_ny × MEP del día`. <br>• Si no: `precio_ars = precio .BA × factor`. <br>Los `ajustes_historicos` se aplican solo al recargar historia (RF-08). |
| RF-04 | M | **Calendario completo**, con la misma lógica que `actualizar_precios.py`: <br>• Repasar desde **7 días antes de hoy** (corrige cierres provisorios) hasta hoy y agregar las fechas faltantes. <br>• Día con rueda en BYMA (hay algún cierre `.BA` ese día): actualizar MEP y cierres. <br>• Fin de semana o feriado: repetir el último cierre y el MEP; solo cambia el BTC. <br>• Si un activo no trae dato, conserva el valor anterior. |
| RF-05 | M | **Validaciones antes de escribir** (umbrales en `config.json`): <br>• Ningún valor vacío. <br>• MEP entre 500 y 5000. <br>• BTC entre 10.000 y 500.000. <br>• Para cada activo, `0,6 < precio / precio_día_anterior < 1,6`. <br>Si alguna falla, **no se escribe nada**, se registra en `estado_jobs.json` y se notifica (RF-60). |
| RF-06 | M | Actualiza todos los activos de `fuentes_precios.json`, no solo los que tienen tenencia. Registra cuántas filas agregó o recalculó y la hora (`ultima_actualizacion`, equivalente al `UPD` actual). |
| RF-07 | M | Al terminar con éxito, invalida la caché del motor. Al día siguiente, el punto "en curso" pasa a ser cierre. |
| RF-08 | M | Comando `python -m cartera.precios.recargar --desde AAAA-MM-DD [--activo X]` que vuelve a bajar historia y aplica `ajustes_historicos`. Muestra un diff antes de escribir y pide confirmación (`--si` para no interactivo). Es también la forma de construir la historia en la carga inicial (4.3), por eso es obligatorio. |
| RF-09 | M | **Activo nuevo:** al agregarlo desde la administración (RF-45), se carga su historia desde el inicio de la serie y se suma al job sin tocar código. |

### 6.2 Precios en vivo ("Actualizar ahora")

| ID | Prioridad | Requerimiento |
|---|---|---|
| RF-10 | M | Botón "↻ Actualizar ahora" en la cabecera. Llama a `POST /api/precios/en-vivo`, que consulta en el servidor: <br>• Yahoo con cotización del momento: `regularMarketPrice` de los activos con tenencia, más SPY siempre. <br>• Binance `ticker/price` para BTC. <br>• El MEP del día. |
| RF-11 | M | El resultado se guarda en `precios_en_vivo.json` y se usa como fila "en curso" (`en_curso = true`) **solo si**: <br>• Su fecha ≥ la última fecha de la serie. <br>• Tiene menos de 18 h. <br>• Es más nuevo que la última actualización del job. <br>Si es de un día posterior al último de la serie, se rellenan los días intermedios repitiendo la última fila. **Nunca** se escribe en `precios_diarios.json`. |
| RF-12 | M | La cabecera muestra "Precios en vivo dd/mm/aa hh:mm · último cierre guardado …" o "Última actualización de la información … · precios automáticos todos los días cerca de las 21 h". Los errores se muestran en rojo junto al botón. |

### 6.3 Cabecera (fija arriba al hacer scroll en escritorio)

| ID | Prioridad | Requerimiento |
|---|---|---|
| RF-15 | M | **Patrimonio neto** en grande. <br>**Desglose en tarjetas, en este orden:** <br>• **Bienes**: valor; nombres de los bienes vigentes · % del total. <br>• **Pasivos**: −valor; "nombre del pasivo · N cuotas". Se muestra solo si hay deuda. <br>• **Otros no financieros**: valor con etiqueta "estimado"; "mineros <modelo> · %". <br>• **Activos financieros**: valor; variación "hoy" en USD y % contra el cierre anterior; "%". |
| RF-16 | M | **Línea de rendimiento de los activos financieros:** 1M, 3M, 6M y "desde dd/mm/aa" (TWR, 5.8), más el MEP y el precio del BTC del último punto. |
| RF-17 | M | **Control deslizante "Gráficos desde"**, por mes con marcas por año. <br>• Define el inicio de Evolución, Composición en el tiempo, Base 100, Producción y Aportes y retiros. <br>• El primer punto es el cierre del mes anterior al mes elegido. <br>• El máximo es 3 meses antes del último. <br>• Se recuerda la elección (en `localStorage` del navegador; es preferencia de UI, no dato). |
| RF-18 | M | **Temas** Claro, Atenuado y Oscuro, con la paleta exacta del HTML de referencia. Por defecto, según `prefers-color-scheme`. Se recuerdan en `localStorage`. |
| RF-19 | M | **Menú lateral de pestañas** (en móvil pasa arriba como tira desplazable): <br>• Evolución y composición. <br>• Aportes y retiros. <br>• Cada activo, base 100. <br>• Movimientos. <br>• Producción minera. <br>• Otros activos. <br>• Botón ⓘ "Cómo se calcula", que abre un diálogo con el texto del HTML de referencia, actualizado a la nueva arquitectura. <br>La pestaña activa se recuerda y acepta `#hash`. Se navega con flechas del teclado. |

### 6.4 Pestaña "Evolución y composición"

| ID | Prioridad | Requerimiento |
|---|---|---|
| RF-20 | M | **Gráfico de evolución** (área, puntos mensuales más el último), con tres modos: <br>• Cartera financiera (`tot`). <br>• Bienes (`min + inm`). <br>• Patrimonio total (`pat`), con un área apilada de "bienes netos" (`min + inm − deu`). <br>El eje Y arranca en 0. Sin zoom ni scroll. Etiquetas de valor sin colisiones (algoritmo de `placeLbl` del HTML de referencia). Leyenda como hint junto al mouse. |
| RF-21 | M | **Lista lateral** de activos financieros con valor > 0,5 USD en el mes en curso: "Toda la cartera" más cada activo, con su valor y la variación de precio desde el inicio elegido. Un clic muestra solo ese activo: valor en USD (eje derecho) y cantidad (línea, eje izquierdo). Otro clic vuelve a toda la cartera. |
| RF-22 | M | **Arrastrar sobre el gráfico** selecciona un período. Se resalta la franja y se muestra una tarjeta con los datos de 5.14. Se cierra con ×, con Escape o con un clic afuera. En pantallas táctiles, se activa con una pulsación larga de 350 ms. |
| RF-23 | M | **Composición del patrimonio:** <br>• Treemap squarified en dos bloques, activos financieros arriba y no financieros abajo, con alturas proporcionales acotadas entre 30% y 75%. Cada grupo ocupa al menos el 7% del área. <br>• Selectores "Parte pagada / Valor completo" y "Activos financieros / Activos no financieros" (al menos uno activo). <br>• Rótulo "% sobre US$ X · patrimonio neto / activos totales". <br>• Bloque de leyenda con la explicación de la deuda. |
| RF-24 | M | **Tabla de posiciones**, "Por grupo y activo" (grupos colapsables, estado recordado) o "Solo por activo". <br>• Columnas: Activo, Valor USD, Peso (con barra), Cantidad, Resultado (5.10, con % y `*` si es estimado; "—" si falta costo), Hoy, 1M, 1A (variación de precio en USD; ojo: en el tablero actual la columna "1A" compara contra la fila 0, es decir, desde el inicio de la serie; mantenerlo y rotularlo "Desde el inicio", salvo que se adopte el "12M" de 5.8). <br>• Fila Total con los TWR. <br>• Debajo, el peso de cada clase. |
| RF-25 | M | **Cómo cambió la composición:** mensual, "Por tipo / Por activo", "Área 100% / Líneas", con botones para elegir series y "Todos". Hint con el valor y el % de la serie bajo el mouse. |

### 6.5 Pestaña "Aportes y retiros"

| ID | Prioridad | Requerimiento |
|---|---|---|
| RF-26 | M | **KPIs del período** (desde "Gráficos desde" hasta hoy): <br>• Valor inicial. <br>• Aportes (compras y billetes, más BTC minado). <br>• Retiros (ventas, a la compra de bienes, luz y seguro). <br>• Capital neto. <br>• Valor final. <br>• Ganancia. |
| RF-27 | M | **Barras mensuales** apiladas: aportes, BTC minado, retiros, a la compra de bienes, luz y seguro, con los colores del HTML de referencia. Gráfico **Capital neto contra valor de la cartera** (5.12). |
| RF-28 | M | **Tabla mensual** de los meses con movimientos: aportes, retiros, neto, capital neto al cierre y valor al cierre. Cada mes se despliega con sus movimientos agrupados por concepto y activo. Debajo va el texto explicativo. |

### 6.6 Otras pestañas

| ID | Prioridad | Requerimiento |
|---|---|---|
| RF-30 | M | **Cada activo, base 100** (5.16), con hint del activo más cercano al mouse (distancia de hasta 40 px). |
| RF-31 | M | **Movimientos** (5.15). <br>• Filtros por activo y por operación, recordados, con el contador "n de N". <br>• Columnas: Fecha, Movimiento (tipo y nota; etiqueta "estimado"), Activo, Cantidad, Cantidad acumulada, Precio USD, Valor USD, Valor hoy, Resultado. |
| RF-32 | M | **Producción minera** (5.13). <br>• Gráfico mensual en USD (producción, costos negativos y línea de recupero acumulado en el eje izquierdo) o en BTC. <br>• KPIs y tabla mensual. |
| RF-33 | M | **Otros activos.** <br>• **Mineros**: KPIs (costo, valor contable, pérdida de valor, amortización anual, resultado neto de la minería, recupero), tabla por tanda y textos. <br>• **Bienes**: una ficha por inmueble. El auto muestra valor, deuda, parte propia, cuotas y lo pagado desde la cartera; el terreno muestra valor, costo, resultado, peso y lo pagado. Los textos se generan a partir de los datos (`origen`). |

### 6.7 Administración de datos ([CAMBIO]: reemplaza la edición manual de JSON)

Sección `/admin`, que requiere login. Formularios simples con el mismo estilo visual. **Toda alta, edición o baja actualiza los JSON afectados en una sola operación atómica** (los dos archivos con lock, escritura de ambos y rollback si falla el segundo) y queda en `auditoria.json`.

| ID | Prioridad | Requerimiento |
|---|---|---|
| RF-40 | M | **Alta de movimiento.** <br>• **Campos:** fecha, tipo, activo, cantidad (con signo, guiado por el tipo), usd, flujo_usd (opcional), destino (opcional), estimado, sin_efecto_en_saldo, devengo_diario (desde y por_dia), nota. <br>• **Ayudas según el tipo:** <br>&nbsp;&nbsp;– *Compra o Venta en pesos*: `usd = monto_ars ÷ MEP del día` (se ingresa el monto en ARS y se muestra el MEP usado); propone `flujo_usd = +usd` en compra y `−usd` en venta. <br>&nbsp;&nbsp;– *Compra o Venta contra USD Balanz*: sin flujo; crea automáticamente la contrapartida Pago (compra) o Cobro (venta) sobre `USD Balanz` con `contrapartida_de`. <br>&nbsp;&nbsp;– *Conversión BTC→USDT*: crea la contrapartida sobre USDT; sin flujo. <br>&nbsp;&nbsp;– *Minería*: `usd = cantidad × precio BTC del día`; `flujo_usd = +usd`. <br>&nbsp;&nbsp;– *Costo minería*: activo USDT, cantidad negativa, `flujo_usd = −usd`. <br>&nbsp;&nbsp;– *Interés Nexo*: pide el mes y el BTC por día; arma el `devengo_diario` del mes. <br>• **Al guardar:** `tenencias.activos[activo].cantidad += cantidad` (también la de la contrapartida). <br>• Muestra la vista previa del impacto (cantidad antes y después; patrimonio antes y después) antes de confirmar. |
| RF-41 | M | **Edición y baja de movimiento.** Recalcula la cantidad actual con el delta (o revierte en una baja). Una baja pregunta si también se borra la contrapartida. Valida la integridad de 4.4. |
| RF-42 | M | **Ajuste directo de cantidad actual** (conciliación). Pide un motivo que queda en auditoría. Advierte si deja cantidades históricas negativas. |
| RF-43 | M | **Plan de ahorro** (procedimiento mensual del resumen de FIAT Plan). Formulario con: valor móvil, alícuota, número de cuota emitida, fecha de emisión, Pagas, Anticipadas, Licitadas, Impagas y A vencer. Al guardar: <br>• Agrega a `cuotas_pagas` las cuotas faltantes hasta llegar a "Pagas" (pidiendo la fecha de cada una, con el día de vencimiento como valor por defecto). <br>• Actualiza `alicuota_ars`, `valor_movil_ars`, `fecha_valor_movil` y `mep_referencia` (MEP venta de la fecha de emisión, traído solo pero editable). <br>• Anticipadas y licitadas → `cuotas_canceladas`, preguntando por cada una si se pagó desde la cartera (`pagada_desde_cartera`, 4.5.1). <br>• Impagas > 0 → aviso visible. <br>• Recalcula `valor_nuevo_usd` del auto = valor móvil ÷ MEP de referencia. <br>• Muestra la deuda y el patrimonio antes y después. |
| RF-44 | M | **Bienes:** editar valor_usd y fecha_valuacion (revaluación), depreciación, valor_nuevo_usd, origen; alta de un bien nuevo. **Mineros:** editar tandas y parámetros. |
| RF-45 | M | **Activo nuevo:** ticker, nombre, tipo, grupo, cotiza_en_pesos, valor_fijo_usd, fuente de precio (símbolo de Yahoo, factor o ratio NY) y color. Valida que Yahoo devuelva datos y carga la historia (RF-09). |
| RF-46 | M | **Versiones:** listar las versiones guardadas de cada JSON (RT-22), ver el diff y restaurar una (la restauración también queda versionada). |
| RF-47 | M | **Descargar** cada JSON y un `.zip` con todos. **Subir** un JSON completo para reemplazar uno, con validación, diff previo y confirmación. |
| RF-48 | M | **Cargar datos** (primera vez o reemplazo total): subir `tenencias.json` y `movimientos.json` (y opcionalmente `precios_diarios.json` y `fuentes_precios.json`) y aplicar el proceso de 4.3, con resumen y confirmación. Si ya hay datos, primero se hace un backup automático. |

### 6.8 Importación de operaciones de Balanz

| ID | Prioridad | Requerimiento |
|---|---|---|
| RF-50 | M | Subir el export de operaciones de Balanz (CSV o XLSX), con las columnas: Operación, Estado, id Orden, Ticker, Moneda, Fecha, Hora, Cantidad, Precio, Monto, Precio Operado, Cantidad Operada. |
| RF-51 | M | Considerar solo las órdenes en estado ejecutado. Detectar duplicados contra los movimientos existentes por (fecha, ticker, cantidad, monto ±1%) y mostrarlos como "ya cargado". |
| RF-52 | M | **Conversión de cada operación nueva:** <br>• En pesos: `usd = |Monto| ÷ MEP venta del día`, con flujo = aporte (compra) o retiro (venta). <br>• En dólares: sin flujo y con contrapartida Pago o Cobro sobre USD Balanz. Una casilla permite marcarla como flujo (retiro o aporte), porque hay ventas en USD que salieron de Balanz. <br>• Cantidades en nominales actuales: aplicar los cambios de ratio y splits de `config.json` (SPY ×3 antes del 29/05/2026; AAPL y MELI ×2 antes del 24/01/2024; NVDA ×10 antes del 10/06/2024; AVGO ×10 antes del 15/07/2024). |
| RF-53 | M | Muestra una vista previa en tabla (editable: tipo de flujo, destino, nota) antes de confirmar. Al confirmar, aplica RF-40 a cada fila en una sola transacción. |

### 6.9 Autenticación y seguridad funcional

| ID | Prioridad | Requerimiento |
|---|---|---|
| RF-55 | M | Login con usuario y contraseña de un único usuario (hash **argon2** en `.env`). Sesión en cookie firmada `HttpOnly`, `Secure`, `SameSite=Strict`, de 30 días deslizantes. Botón "Salir". |
| RF-56 | M | Todas las rutas (HTML, API y estáticos con datos) requieren sesión, salvo `/login` y `/salud`. |
| RF-57 | M | Límite de intentos de login: 5 por 15 minutos por IP; luego, bloqueo temporal. |
| RF-58 | M | Protección CSRF (token por sesión) en todo POST, PUT, PATCH o DELETE. |
| RF-59 | F2 | 2FA TOTP opcional. |

### 6.10 Notificaciones y monitoreo

| ID | Prioridad | Requerimiento |
|---|---|---|
| RF-60 | M | Si el job de precios o el de backup fallan (validación, red o excepción), avisar por **email (SMTP)** o por **Telegram (bot)**, según `NOTIF_*` en `.env`. Ambos son opcionales; si no hay ninguno configurado, se avisa con un banner en el tablero. |
| RF-61 | M | Banner en el tablero si los precios tienen más de 2 días hábiles de atraso o si la última ejecución del job falló. |
| RF-62 | M | `GET /salud` (sin login) responde 200 con `{"ok":true}` y sin datos sensibles. `GET /api/estado` (con login) devuelve la última ejecución de los jobs, la última fecha de precios, el tamaño de los archivos y el último backup. |
| RF-63 | D | Recordatorio mensual (el día 1, por el mismo canal de notificación) de cargar: minería del mes, interés de Nexo, luz y seguro, conversiones y el resumen de FIAT Plan. |

### 6.11 Backups

| ID | Prioridad | Requerimiento |
|---|---|---|
| RF-65 | M | Timer diario (03:30 AR) que comprime `CARTERA_DATA_DIR` en `backups/cartera-AAAAMMDD.zip`. Conserva 30 diarios y 12 mensuales (el del día 1). |
| RF-66 | D | Copia externa opcional del zip: a un repositorio **privado** de GitHub, por `git` con deploy key, o a un remoto `rclone`, según `.env`. |
| RF-67 | M | `scripts/restaurar.py <zip>` valida el contenido antes de reemplazar y deja versionado lo anterior. |

### 6.12 Casos especiales que hay que respetar (con cualquier dato)

- **Movimientos `estimado`** (saldos iniciales sin origen conocido, ventas supuestas): se muestran con la etiqueta "estimado" y con `*` en los resultados que los incluyen.
- **Destinos:**
  - Destino = nombre de un inmueble: retiro "a la compra de bienes". En el patrimonio, el bien se suma a medida que sale la plata (5.5) y esos retiros no cuentan como flujo del patrimonio (5.8).
  - `destino = "Mineros"`: en el patrimonio, **sí** cuentan como retiro. La compra de los mineros entra como aporte por el costo de cada tanda.
- **Minería e Interés Nexo:** el BTC minado es aporte a la cartera y la luz y el seguro son retiro. En el patrimonio esos flujos se neutralizan. El Interés Nexo es ingreso, sin flujo.
- **Pasivo en cuotas:** desde `fecha_alta`, cada cuota paga es aporte al patrimonio por `cu`. Las `cuotas_canceladas` (anticipadas o licitadas) se restan de las pendientes desde su fecha. Si `pagada_desde_cartera` es `false` (valor por defecto), la cancelación es aporte al patrimonio por `cu`, como una cuota paga. Si es `true`, no suma a `flowP`: la plata salió de la cartera con un movimiento cuyo `destino` es el bien, que ya no cuenta como flujo del patrimonio. Así, en ninguno de los dos casos la baja de la deuda aparece como ganancia.
- **Ajustes históricos de precios:** se aplican una sola vez, al bajar historia (RF-08). Un `precios_diarios.json` cargado por el usuario ya viene corregido: **no volver a aplicarlos**.

---

## 7. API (JSON, todas con sesión salvo `/salud`)

| Método y ruta | Descripción |
|---|---|
| `GET /api/tablero?desde=AAAA-MM` | Todo lo que necesita el frontend para pintar, ya calculado (ver 7.1). |
| `GET /api/analisis-periodo?desde&hasta&modo=tot\|bie\|pat&activo=` | Tarjeta de 5.14. |
| `POST /api/precios/en-vivo` | RF-10/11. Devuelve la fila en curso o un error con código. |
| `GET /api/estado` | RF-62. |
| `GET/POST/PUT/DELETE /api/admin/movimientos[/{id}]` | RF-40/41 (con `version`, RT-23). |
| `POST /api/admin/movimientos/preview` | Vista previa del impacto. |
| `GET/PUT /api/admin/tenencias` · `PATCH /api/admin/activos/{ticker}` · `POST /api/admin/activos` | RF-42/45. |
| `PUT /api/admin/pasivos/{nombre}/resumen` | RF-43. |
| `PUT /api/admin/inmuebles/{nombre}` · `PUT /api/admin/mineros` | RF-44. |
| `GET /api/admin/versiones/{archivo}` · `POST /api/admin/versiones/{archivo}/{id}/restaurar` | RF-46. |
| `GET /api/admin/exportar[.zip]` · `POST /api/admin/importar/{archivo}` | RF-47. |
| `POST /api/admin/balanz/preview` · `POST /api/admin/balanz/confirmar` | RF-50–53. |

### 7.1 Contenido de `/api/tablero`

- `meta`: última actualización, si hay precios en vivo y su timestamp, primera y última fecha, banner de estado.
- `cabecera`: total, desglose, rendimientos por período, MEP y BTC, variación "hoy".
- `activos`: ticker, nombre, tipo, grupo, color, cantidad, valor, peso, costo, resultado y variaciones 1D/1M/1A.
- `serie_mensual`: puntos de 5.9 con `t`, `tot`, `min`, `inm`, `deu`, `pat`, `bie`, `bin`, `capT`, `capP`, `idx`, `idxP`, `por_grupo`, `pos` y `pu` por activo, `cantidad` por activo, `mep`, `en_curso`.
- `composicion`: datos del treemap en los dos modos.
- `flujos_mensuales`: 5.12, con el detalle agrupado por mes.
- `produccion_mensual`: 5.13, con sus KPIs.
- `mineros`, `bienes`, `pasivos`: fichas de RF-33.
- `movimientos`: ya ordenados (5.15), con la cantidad acumulada, el precio USD, el valor hoy, el resultado y las marcas.

Respuesta comprimida con gzip (`GZipMiddleware`). Objetivo: menos de 1,5 MB sin comprimir. Si se necesita la serie diaria (por ejemplo, para el análisis de un período), se pide aparte.

---

## 8. Requerimientos no funcionales

| ID | Requerimiento |
|---|---|
| RNF-01 | **Rendimiento:** `/api/tablero` responde en menos de 300 ms con la caché caliente y en menos de 1,5 s con la caché fría, en un VPS de 1 vCPU. La primera pintura del tablero tarda menos de 2 s en una conexión 4G. |
| RNF-02 | **Responsive:** funciona a 360 px de ancho sin scroll horizontal de la página (las tablas sí pueden desplazarse dentro de su contenedor), con los breakpoints del HTML de referencia (900, 760 y 700 px). |
| RNF-03 | **Accesibilidad:** roles ARIA de pestañas, `aria-pressed` en los botones de segmento, foco visible y navegación por teclado en las pestañas y en las filas desplegables. |
| RNF-04 | **Privacidad:** los datos son personales. No exponer los JSON por URL pública. Las notas de los movimientos no deben incluir CBU, CUIT, números de cuenta o tarjeta, ni datos de terceros (se usan iniciales). No mandar analytics ni telemetría a terceros. |
| RNF-05 | **Seguridad:** encabezados `Strict-Transport-Security`, `Content-Security-Policy` (scripts propios más el CDN de jsdelivr si no se usa copia local), `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options: DENY`. Dependencias actualizadas y `pip-audit` en CI. |
| RNF-06 | **Disponibilidad:** reinicio automático del servicio (`Restart=always`). Si el job no corre, la app sigue funcionando con los últimos precios. |
| RNF-07 | **Mantenibilidad:** el motor está separado de la API y de los clientes de precios, y se puede usar por línea de comandos: `python -m cartera.motor.resumen --fecha 2026-09-30` imprime los totales. |
| RNF-08 | **Zona horaria:** todo en `America/Argentina/Buenos_Aires`. Las fechas de la serie no tienen hora. |
| RNF-09 | **Exactitud:** los totales se muestran sin decimales y los precios y movimientos con 2. BTC con 8 decimales, como en el tablero actual. |

---

## 9. Interfaz: requisitos de fidelidad

- Reutilizar del HTML de referencia:
  - Variables CSS y temas (`--bg`, `--panel`, `--ink`… y colores `--c-<ticker>`, `--t-<tipo>`).
  - Tipografía `system-ui`.
  - Componentes `.panel`, `.bar`, `.seg`, `.kgrid`, `.tm`, `.hint`, `.selband`, `.selcard`, `.desde`.
  - Layout de cabecera fija más menú lateral.
- Textos: copiar los textos explicativos de cada pestaña y del diálogo "Cómo se calcula". Donde mencionan "la app de Claude", "datos/tenencias.json" o "editar a mano", adaptarlos a la nueva app ("Administración").
- Gráficos: Lightweight Charts con `handleScroll` y `handleScale` desactivados, sin cuadrícula vertical, eje de tiempo y leyendas como hint junto al mouse (función `legendHint` del HTML de referencia).
- Los colores por ticker vienen de `config.json`, para que un activo nuevo tenga color sin tocar el CSS.
- Agregar en la cabecera un enlace a **Administración** y un botón **Salir**.

---

## 10. Despliegue en Hostinger

### 10.1 Plan requerido

- Usar un **VPS de Hostinger (KVM)**, por ejemplo KVM 1 (1 vCPU, 4 GB RAM), con **Ubuntu 24.04 LTS**.
- El hosting compartido de Hostinger no sirve: no permite procesos Python persistentes como un servidor FastAPI.
- El "Cloud hosting" tiene soporte limitado de Python y no se usa.

### 10.2 Ubicación del servidor

Elegir un data center **fuera de EE.UU.** (por ejemplo Brasil o Europa), porque `api.binance.com` rechaza IPs de EE.UU. Igual se implementa el respaldo `data-api.binance.vision`.

### 10.3 Pasos de aprovisionamiento (documentar en `README.md` y automatizar en `deploy/`)

1. **Seguridad del servidor:**
   - Crear el usuario `cartera` sin privilegios.
   - SSH solo con clave (deshabilitar root y password).
   - `ufw allow 22,80,443`.
   - `fail2ban`.
   - `unattended-upgrades`.
2. **Instalación:**
   - `timedatectl set-timezone America/Argentina/Buenos_Aires`.
   - Python 3.12 y `uv` (o venv).
   - Clonar el repo (privado en GitHub) en `/srv/cartera/app`.
   - Datos en `/srv/cartera/datos` y backups en `/srv/cartera/backups`, con permisos `700` y dueño `cartera`.
3. **Servicios systemd:**
   - `cartera.service`: uvicorn en `127.0.0.1:8000`, 2 workers, `Restart=always`, `EnvironmentFile=/srv/cartera/.env`.
   - `cartera-precios.timer`: 20:45 con reintentos a las 22:00 y 08:00, `Persistent=true`.
   - `cartera-backup.timer`: 03:30.
4. **nginx y dominio:**
   - nginx como reverse proxy con gzip, `client_max_body_size 10m` (para las importaciones) y caché de estáticos.
   - Dominio o subdominio del usuario apuntando al VPS (registro A, gestionable desde hPanel).
   - Certificado TLS con **certbot** (Let's Encrypt) y renovación automática.
5. **Script `deploy/deploy.sh`:** `git pull` → instalar dependencias → tests rápidos → migraciones de datos si hacen falta → `systemctl restart cartera`. Nunca toca `/srv/cartera/datos`.
6. **Primera carga:** el usuario sube sus JSON (4.3, RF-48, o `scripts/cargar_datos.py` por SSH). Después se corre el job de precios a mano para empalmar la serie hasta hoy, o se construye la historia con RF-08.
7. **Backups de Hostinger:** activar las instantáneas semanales del VPS, si el plan las incluye, como capa adicional.

### 10.4 Transición desde el tablero actual

Durante 2 semanas conviven los dos sistemas:
- Comparar a diario los precios de los dos sistemas: deben coincidir con una diferencia de ±0,5% (BTC: misma hora). Si no, revisar.
- Después, apagar la tarea programada actual. Esto lo hace el usuario.

---

## 11. Pruebas y criterios de aceptación

| ID | Prueba |
|---|---|
| T-01 | **Golden values:** con `referencia/ejemplo/`, el motor reproduce cada valor de `referencia/ejemplo/valores_control.json` (`por_fecha`: `tot`, `min`, `inm`, `deu`, `pat`, `flow`, `flowP`, `capT`, `capP`, `rend_cartera_pct`, `rend_patrimonio_pct` y `posiciones`; `costo_posiciones_abiertas`; `mineria`) con tolerancia de ±0,02 USD y ±0,01 pp. Referencias rápidas al 30/04/2025: activos financieros **10.999,56**, mineros 4.390,46, bienes 1.875,04, pasivos 600,00, **patrimonio neto 16.665,06**, capital neto 10.398,90, rendimiento de la cartera **+5,75%** y del patrimonio **−7,11%**. El ejemplo incluye una cuota cancelada de cada tipo (4.5.1): el 25/03/2025 `flowP` suma `cu` (100,00) y el 20/04/2025 no suma nada; en las dos fechas la deuda baja 100,00. |
| T-02 | `calculo_referencia.py` y el motor dan los mismos números para **todas** las fechas de la serie, no solo las del archivo de control. Es un test de propiedad sobre todas las fechas. Además se generan al menos 20 juegos aleatorios (semilla fija) variando precios y movimientos con `generar_ejemplo.py` como base, y el motor tiene que coincidir con la referencia en todos. |
| T-03 | **Cantidades:** reconstrucción hacia atrás (5.2), incluido el devengo diario del Interés Nexo del ejemplo (febrero de 2025): el 31/01/2025 no tiene interés, el 01/02 tiene 27 días por devengar y desde el 28/02 tiene el total. |
| T-04 | **Job de precios con fixtures:** día hábil, fin de semana, feriado, cierre provisorio corregido dentro de los 7 días, activo sin dato y validaciones que bloquean la escritura (MEP 0, salto de +70%). |
| T-05 | **Binance:** toma el cierre de la vela que abre a las 19:00 UTC; si el host principal falla, usa el de respaldo. |
| T-06 | **Repositorio JSON:** escritura atómica (simulando un fallo a mitad de escritura, el archivo original queda intacto), lock con escritores concurrentes, versionado, conflicto 409 y rollback de una transacción entre dos archivos. |
| T-07 | **Admin:** una compra en pesos con flujo y una compra con USD Balanz con contrapartida actualizan la cantidad actual. La baja revierte. La integridad rechaza un movimiento que deja USDT negativo en el pasado. |
| T-08 | **Plan Fiat:** con el ejemplo, cargar un resumen con 5 cuotas pagas baja la deuda en exactamente `cu` desde la fecha de la cuota 5. Ese día `flowP` suma `cu`, así que el rendimiento del patrimonio no cambia por la cuota (es un aporte, no una ganancia). |
| T-09 | **Importador de Balanz:** detecta duplicados con el historial existente. Una compra en pesos se convierte con el MEP del día. Aplica los ratios. |
| T-12 | **Carga de datos (4.3):** <br>• Un `movimientos.json` sin `id` ni `contrapartida_de` se normaliza bien. <br>• Una carga que deja una cantidad negativa se rechaza con el detalle. <br>• Con datos previos, se hace backup antes de reemplazar. |
| T-10 | **API:** sin sesión responde 401 o redirige al login. CSRF en mutaciones. Límite de intentos de login. `/salud` sin datos. |
| T-11 | **E2E (Playwright, con el ejemplo ficticio y `CARTERA_DEMO=1`):** <br>• La cabecera muestra los cuatro bloques en orden. <br>• Las pestañas cambian. <br>• Un arrastre en Evolución muestra la tarjeta con la comparación con SPY. <br>• Los filtros de Movimientos cuentan bien. <br>• Funciona a 360 px y a 1280 px, en los tres temas. |

---

## 12. Plan de entrega por fases

| Fase | Contenido | Criterio de salida |
|---|---|---|
| F1 | Modelos, repositorio JSON, carga de datos por CLI (4.3) y motor completo. CLI `resumen`. | T-01, T-02, T-03, T-06 y T-12 en verde. |
| F2 | API `/api/tablero` y frontend de solo lectura, réplica visual completa. | T-10 y T-11 en verde. Revisión visual contra `tablero_actual.html`. |
| F3 | Job diario, precios en vivo, notificaciones, banner y `/api/estado`. | T-04 y T-05 en verde. Corrida real en el servidor. |
| F4 | Administración (RF-40 a RF-47) e importador de Balanz. | T-07, T-08 y T-09 en verde. |
| F5 | Despliegue en Hostinger, TLS, backups y documentación. | Checklist de 10.3 completo y restauración de backup probada. |
| F2+ (opcional) | Lectura del PDF de FIAT Plan (`pdfplumber`: valor móvil, alícuota, cuota, emisión, estado de cuenta) para precompletar RF-43. 2FA TOTP. Recordatorio mensual. | — |

---

## 13. Decisiones abiertas (confirmar con el usuario antes de F5; no bloquean F1–F4)

1. El dominio o subdominio que se va a usar y el canal de notificación preferido (email o Telegram).
2. Si la copia externa de backups va a un repositorio privado de GitHub o a otro destino.
3. Si se agrega el período "12M" real (5.8) además del "desde el inicio".
4. Si se soportan otras cripto además de BTC (4.5.1).

# Mi cartera en dólares (versión servidor)

Aplicación web de un solo usuario para seguir en USD un patrimonio personal: CEDEARs y acciones argentinas, BTC/USDT, dólares, mineros de BTC, bienes y pasivos. Reemplaza un tablero HTML existente con la misma lógica y la misma interfaz. Backend en Python, datos en archivos JSON, despliegue en un VPS de Hostinger.

## Fuente de verdad

- **`REQUERIMIENTOS.md`** es la especificación completa. Leé la sección relevante antes de implementar cualquier cosa y citá los IDs (RF-xx, RT-xx, T-xx) en commits y comentarios cuando corresponda.
- **`referencia/tablero_actual.html`** es el tablero actual (HTML + CSS + JS). Ante una duda de lógica o de interfaz, manda su comportamiento, salvo lo marcado **[CAMBIO]** en los requerimientos. Es un archivo grande: leé solo las partes que necesites (con `grep` u offsets).
- **`referencia/calculo_referencia.py`** es un port mínimo de la valuación. No es código de producción; es la referencia de los tests.
- **`referencia/ejemplo/`** contiene datos FICTICIOS para desarrollo y tests, y `valores_control.json` con los resultados esperados.

## Reglas

- **No hay datos reales del usuario en este repositorio, y no tiene que haberlos.** No pidas datos reales ni los inventes. No asumas tickers, montos ni fechas particulares: todo sale de los JSON y de `config.json`. El usuario carga sus datos en el servidor después del despliegue.
- La persistencia es **solo en archivos `.json`**: sin bases de datos. Las escrituras son atómicas, con lock, versionado y validación pydantic (sección 4 de los requerimientos).
- El frontend **no** tiene lógica de negocio: pide los datos ya calculados a la API y solo los dibuja (RT-06).
- Los tests **no usan la red**: las respuestas de Yahoo, Binance y ArgentinaDatos se graban como fixtures.
- La interfaz va en español rioplatense, con formato numérico `es-AR`. Fechas: `dd/mm/aa` en la UI e ISO `AAAA-MM-DD` en datos y API. Zona horaria `America/Argentina/Buenos_Aires`.
- No commitear `datos/`, `backups/`, `logs/` ni `.env`.
- Si los requerimientos son ambiguos o se contradicen, preguntá antes de decidir algo que cambie un cálculo. En detalles menores, decidí, dejá un comentario `# DECISIÓN:` y mencionalo al terminar.

## Forma de trabajo

- Se trabaja **por fases**, en el orden de la sección 12 (F1 → F5). No avances a la fase siguiente sin aprobación del usuario.
- Al empezar una fase, presentá un plan breve (archivos, orden, tests que la cierran) y esperá el OK.
- Al terminar una fase:
  - correr todos los tests y el lint, y mostrar el resultado;
  - actualizar la sección "Estado" de este archivo;
  - proponer un commit.
- Cambios chicos y verificables. Después de cada módulo del motor, correr sus tests.

## Stack

Python 3.12 · FastAPI + uvicorn (detrás de nginx) · pydantic v2 + pydantic-settings · httpx · yfinance · pytest · ruff · mypy (strict en `cartera/motor` y `cartera/datos`) · frontend HTML/CSS/JS sin framework con Lightweight Charts 4.2.0 · systemd timers para los jobs.

## Comandos

Todo corre con `uv`, que usa el Python 3.12 de `.python-version` y el entorno `.venv/` del proyecto.

```bash
# entorno (crea .venv e instala dependencias)
uv sync

# tests
uv run pytest

# lint, formato y tipos
uv run ruff check .
uv run ruff format --check .
uv run mypy

# resumen del motor por CLI (con el ejemplo ficticio: CARTERA_DEMO=1)
CARTERA_DEMO=1 uv run python -m cartera.motor.resumen --fecha 2025-04-30
uv run python -m cartera.motor.resumen --datos <carpeta>

# carga de datos (4.3) y verificación de integridad (4.4)
uv run python scripts/cargar_datos.py <carpeta> --datos <destino> --backups <carpeta> [--si]
uv run python scripts/verificar_integridad.py --datos <carpeta>

# regenerar el ejemplo ficticio y sus valores de control
cd referencia/ejemplo && python generar_ejemplo.py && cd .. \
  && python calculo_referencia.py ejemplo/precios_diarios.json ejemplo/tenencias.json ejemplo/movimientos.json > ejemplo/valores_control.json

# app en modo demo: todavía no existe (F2)
```

## Estado

- [x] F1 — Modelos, repositorio JSON, carga de datos por CLI y motor (T-01, T-02, T-03, T-06, T-12). Terminada el 07/10/2026: 141 tests, ruff y mypy en verde. Falta tu revisión y el commit.
- [ ] F2 — API `/api/tablero` y frontend de solo lectura (T-10, T-11)
- [ ] F3 — Job diario de precios, precios en vivo, notificaciones (T-04, T-05)
  - Pendiente de F1: en F1 `scripts/cargar_datos.py` exige `precios_diarios.json`. En F3 pasa a ser opcional: si falta, la historia se construye con RF-08 (4.3, paso 3).
- [ ] F4 — Administración e importador de Balanz (T-07, T-08, T-09)
- [ ] F5 — Despliegue en Hostinger, TLS y backups

Decisiones tomadas:

1. **Cuotas canceladas (07/10/2026).** Cada elemento de `cuotas_canceladas` lleva `pagada_desde_cartera` (bool, por defecto `false`). Si es `false`, suma `cu` a `flowP` como una cuota paga. Si es `true`, no suma y tiene que existir un movimiento de salida con `destino` = nombre del bien. En los dos casos se resta de las pendientes desde su fecha. Está en REQUERIMIENTOS 4.4, 4.5.1, 5.6, 5.8 y 6.12, en `calculo_referencia.py` y en el ejemplo ficticio (una cancelada de cada tipo).
2. **Carga por CLI en F1.** `scripts/cargar_datos.py` exige `precios_diarios.json`. En F3 pasa a ser opcional con RF-08.
3. **Motor completo en F1 (5.1 a 5.17).** Lo que no cubren los valores de control se verifica contra el JS de `referencia/tablero_actual.html`: ejecutándolo con Node si está disponible; si no, con valores calculados a mano y el cálculo explicado en el test.
4. **Python 3.12 con `uv`**, fijado en `.python-version`, sin tocar el Python del sistema.

Decisiones menores de F1 (marcadas `# DECISIÓN:` en el código):

- **Cancelada desde la cartera:** el movimiento de salida con destino al bien tiene que ser de la misma fecha que la cancelación (`cartera/datos/integridad.py`). Así la baja de la deuda y la salida de la plata caen el mismo día.
- **Índices con valor anterior 0:** si `tot` o `pat` del día anterior es 0, el índice no se mueve; el tablero actual dividía por cero (`cartera/motor/series.py`).
- **Puntos de Evolución:** si la fila 0 ya es fin de mes no se repite (`cartera/motor/series.py`).
- **Sin pandas:** motor en Python puro; 1.500 fechas × 30 activos se recalculan en menos de 1 s (test `test_rendimiento_rt04`).
- **Conflicto de versión:** el repositorio levanta `ConflictoVersion`; la API lo traducirá a 409 en F2/F4.
- **Colores:** `config.json` guarda por ticker los tres temas (claro, oscuro, atenuado) tomados del HTML de referencia; no se precargan los de los bienes del tablero actual.
- **`tzdata`:** dependencia solo en Windows, que no trae la base de zonas horarias.
- **Sin Node en la máquina:** lo que no cubren los valores de control está calculado a mano en `tests/test_motor_a_mano.py`.

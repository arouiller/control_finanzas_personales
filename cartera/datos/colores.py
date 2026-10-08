"""Colores por ticker de `referencia/tablero_actual.html` (variables CSS `--c-<ticker>`), por tema.

Son los valores por defecto de `config.json` (4.3, paso 5). La clave es el ticker en minúsculas y sin
símbolos. Los activos que no están acá reciben un color de `PALETA`.
"""

from __future__ import annotations

import re

# clave: (claro, oscuro, atenuado)
COLORES_REFERENCIA: dict[str, tuple[str, str, str]] = {
    "aapl": ("#64748b", "#94a3b8", "#b4c0cf"),
    "amd": ("#059669", "#34d399", "#6ee7b7"),
    "amzn": ("#d97706", "#fbbf24", "#fcd34d"),
    "avgo": ("#13998a", "#2bb3a3", "#3fc4b3"),
    "brkb": ("#4d7c0f", "#bef264", "#d9f99d"),
    "btc": ("#eb6834", "#d95926", "#ef7d44"),
    "ggal": ("#c2410c", "#fb923c", "#fdba74"),
    "googl": ("#2a78d6", "#3987e5", "#5ea3f2"),
    "ko": ("#dc2626", "#f87171", "#fca5a5"),
    "mcd": ("#ca8a04", "#facc15", "#fde047"),
    "meli": ("#eda100", "#c98500", "#e3a414"),
    "meta": ("#1d4ed8", "#60a5fa", "#93c5fd"),
    "msft": ("#4a3aa7", "#9085e9", "#aea5f3"),
    "nflx": ("#b91c1c", "#ef4444", "#f87171"),
    "nke": ("#f97316", "#fb923c", "#fdba74"),
    "nvda": ("#65a30d", "#a3e635", "#bef264"),
    "qqq": ("#7c3aed", "#a78bfa", "#c4b5fd"),
    "spot": ("#16a34a", "#4ade80", "#86efac"),
    "spy": ("#e87ba4", "#d55181", "#ee7ba3"),
    "tm": ("#64748b", "#94a3b8", "#cbd5e1"),
    "tsla": ("#b91c1c", "#f87171", "#fca5a5"),
    "usdbalanz": ("#1baf7a", "#199e70", "#2dbd8a"),
    "usdbillete": ("#86c7a4", "#7fbf9b", "#9fd3b5"),
    "usdt": ("#a9a79f", "#85837c", "#a2a19a"),
    "vist": ("#0e7490", "#22d3ee", "#67e8f9"),
    "ypfd": ("#0369a1", "#38bdf8", "#7dd3fc"),
}

# paleta categórica para activos sin color propio: (claro, oscuro, atenuado)
PALETA: tuple[tuple[str, str, str], ...] = (
    ("#0f766e", "#2dd4bf", "#5eead4"),
    ("#9d174d", "#f472b6", "#f9a8d4"),
    ("#3f6212", "#a3e635", "#bef264"),
    ("#6d28d9", "#a78bfa", "#c4b5fd"),
    ("#b45309", "#fbbf24", "#fcd34d"),
    ("#0e7490", "#22d3ee", "#67e8f9"),
    ("#be123c", "#fb7185", "#fda4af"),
    ("#475569", "#94a3b8", "#cbd5e1"),
)


def clave_color(ticker: str) -> str:
    """`USD Balanz` → `usdbalanz`, igual que en el CSS de referencia."""
    return re.sub(r"[^a-z0-9]", "", ticker.lower())

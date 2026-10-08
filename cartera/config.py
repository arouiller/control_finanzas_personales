"""Configuración por variables de entorno o `.env` (RT-09)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parent.parent
EJEMPLO = RAIZ / "referencia" / "ejemplo"


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CARTERA_", env_file=".env", extra="ignore")

    data_dir: Path = Path("datos")
    backup_dir: Path = Path("backups")
    demo: bool = False

    @property
    def carpeta_datos(self) -> Path:
        """Con `CARTERA_DEMO=1` se lee el ejemplo ficticio (solo desarrollo, RT-26)."""
        return EJEMPLO if self.demo else self.data_dir


def ajustes() -> Ajustes:
    return Ajustes()

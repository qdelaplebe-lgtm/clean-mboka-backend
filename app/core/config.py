from pydantic_settings import BaseSettings
from pathlib import Path
import os

class Settings(BaseSettings):
    """
    Paramètres globaux de l'application
    """

    # --- DATABASE ---
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost:5432/cleanmboka"  # Valeur par défaut locale
    )

    # --- JWT ---
    SECRET_KEY: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 jours

    # --- Uploads ---
    UPLOAD_DIR: str = "/app/uploads"

    class Config:
        env_file = ".env"
        case_sensitive = True

    @property
    def upload_path(self) -> Path:
        """Retourne le chemin absolu vers le dossier d'upload"""
        path = Path(self.UPLOAD_DIR)
        if not path.is_absolute():
            path = Path("/app") / path
        return path

    def ensure_upload_dir(self):
        """Crée le dossier d'upload s'il n'existe pas"""
        upload_path = self.upload_path
        upload_path.mkdir(parents=True, exist_ok=True)
        return str(upload_path)

# --- INSTANCE DES SETTINGS ---
settings = Settings()
settings.ensure_upload_dir()

# Pour compatibilité avec le code existant
STATIC_URL = "/static"

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Paramètres globaux de l'application Clean Mboka
    Compatible Render Free + Cloudinary
    """

    # ------------------------------------------------------------------
    # DATABASE
    # ------------------------------------------------------------------
    DATABASE_URL: str

    # ------------------------------------------------------------------
    # CLOUDINARY (OBLIGATOIRE - Render Free n'a pas de disque persistant)
    # ------------------------------------------------------------------
    CLOUDINARY_URL: str

    # ------------------------------------------------------------------
    # JWT / SÉCURITÉ
    # ------------------------------------------------------------------
    SECRET_KEY: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 jours

    class Config:
        case_sensitive = True


# ----------------------------------------------------------------------
# INSTANCE GLOBALE DES SETTINGS
# ----------------------------------------------------------------------
settings = Settings()

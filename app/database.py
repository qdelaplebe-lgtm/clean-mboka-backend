from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from core.config import settings
# --- CONNEXION À LA BASE DE DONNÉES ---
DATABASE_URL = settings.DATABASE_URL

# Création du moteur SQLAlchemy
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True  # Vérifie la connexion avant utilisation
)

# Création d'une session locale
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base pour les modèles
Base = declarative_base()

# --- IMPORT DES MODÈLES ---
# Indispensable pour que Base.metadata.create_all sache quelles tables créer
from .models import user, report, subscription

# --- GESTIONNAIRE DE SESSION ---
def get_db():
    """
    Fonction à utiliser avec Depends() dans FastAPI
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

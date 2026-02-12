from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .core.config import settings

# --- CONNEXION DB ---
# On utilise les settings depuis le fichier de config
DATABASE_URL = settings.DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# --- IMPORT DES MODÈLES ---
# Indispensable pour que Base.metadata.create_all sache ce qu'il doit créer
from .models import user, report, subscription

# --- GESTIONNAIRE DE SESSION (CE QUI MANQUAIT) ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from .core.config import settings  # <-- import relatif corrigé

# --- CONNEXION DB ---
DATABASE_URL = settings.DATABASE_URL

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- IMPORT DES MODÈLES ---
from .models import user, report, subscription

# --- GESTIONNAIRE DE SESSION ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

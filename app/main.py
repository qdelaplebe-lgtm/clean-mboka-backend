from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

# Imports Internes de l'application
from .database import engine, Base
from .models import user, report, subscription
from .api import auth, reports, users, geo, tasks, subscriptions  # AJOUT
from .core.config import settings

# Création des tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Clean Mboka API",
    description="API de gestion de salubrité urbaine à Kinshasa",
    version="1.1.0"  # ✅ Mise à jour mineure pour refléter les nouvelles fonctionnalités
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === CONFIGURATION STATIC FILES - ORDRE CORRIGÉ ===

# 1. D'ABORD : Photos de profil (sous-dossier spécifique)
PROFILE_PICTURES_DIR = "static/profile_pictures"
os.makedirs(PROFILE_PICTURES_DIR, exist_ok=True)
print(f"✅ Montage profile_pictures: {os.path.abspath(PROFILE_PICTURES_DIR)}")
app.mount("/static/profile_pictures", StaticFiles(directory=PROFILE_PICTURES_DIR), name="profile_pictures")

# 2. ENSUITE : Photos des signalements (dossier général)
print(f"✅ Montage uploads: {settings.UPLOAD_DIR}")
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.UPLOAD_DIR), name="static")

# Routes API - EXISTANTES
app.include_router(auth.router, prefix="/api/auth", tags=["Authentification"])
app.include_router(reports.router, prefix="/api/reports", tags=["Signalements"])
app.include_router(users.router, prefix="/api/users", tags=["Utilisateurs"])
app.include_router(geo.router, prefix="/api/geo", tags=["Géographie"])
app.include_router(subscriptions.router, prefix="/api/subscriptions", tags=["Abonnements"])

# ✅ NOUVEAU: Routes pour tâches planifiées (cron)
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tâches Planifiées"])

@app.get("/")
def read_root():
    return {
        "message": "Bienvenue sur Clean Mboka API",
        "status": "Opérationnel",
        "version": "1.1.0",  # ✅ Version mise à jour
        "features": {
            "points_citoyens": "Actif - Critères: description, poids, abonnement",
            "tirage_au_sort": "Actif - Seuils de récompense configurés",
            "confirmation_photo": "Actif - Code unique + deadline 48h"
        },
        "static_files": {
            "reports": "/static/[filename]",
            "profile_pictures": "/static/profile_pictures/[filename]"
        }
    }

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()  # ✅ Ajout timestamp
    }

# ✅ Pour éviter l'erreur NameError: datetime
from datetime import datetime

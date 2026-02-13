from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from datetime import datetime
import os

from app.services.database import engine, Base
from models import user, report, subscription
from api import auth, reports, users, geo, tasks, subscriptions
from core.config import settings

app = FastAPI(
    title="Clean Mboka API",
    description="API de gestion de salubrité urbaine à Kinshasa",
    version="1.1.0"
)

@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROFILE_PICTURES_DIR = "static/profile_pictures"
os.makedirs(PROFILE_PICTURES_DIR, exist_ok=True)
app.mount(
    "/static/profile_pictures",
    StaticFiles(directory=PROFILE_PICTURES_DIR),
    name="profile_pictures"
)

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.UPLOAD_DIR), name="static")

app.include_router(auth.router, prefix="/api/auth", tags=["Authentification"])
app.include_router(reports.router, prefix="/api/reports", tags=["Signalements"])
app.include_router(users.router, prefix="/api/users", tags=["Utilisateurs"])
app.include_router(geo.router, prefix="/api/geo", tags=["Géographie"])
app.include_router(subscriptions.router, prefix="/api/subscriptions", tags=["Abonnements"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tâches Planifiées"])

@app.get("/")
def read_root():
    return {"status": "Clean Mboka API opérationnelle"}

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

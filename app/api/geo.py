# app/api/geo.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta

from ..database import get_db
from ..models.commune import Commune, Quartier
from ..models.report import Report, ReportStatus
from ..models.user import User
# CORRECTION : deps.py est dans le même dossier (app/api/)
from .deps import get_current_user  # Point important : .deps (même niveau)

router = APIRouter()

@router.get("/commune/{commune_name}/map-data")
async def get_commune_map_data(
    commune_name: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Récupère les données pour afficher la carte d'une commune
    avec les quartiers et les signalements
    """
    # Trouver la commune
    commune = db.query(Commune).filter(
        func.lower(Commune.name) == func.lower(commune_name)
    ).first()

    if not commune:
        raise HTTPException(status_code=404, detail="Commune non trouvée")

    # Récupérer les quartiers de cette commune
    quartiers = db.query(Quartier).filter(
        Quartier.commune_id == commune.id
    ).all()

    # Pour chaque quartier, compter les signalements
    quartiers_data = []
    for quartier in quartiers:
        # Compter les signalements par statut
        reports_count = db.query(Report).filter(
            Report.quartier_id == quartier.id
        ).count()

        active_reports = db.query(Report).filter(
            Report.quartier_id == quartier.id,
            Report.status.in_([ReportStatus.PENDING, ReportStatus.IN_PROGRESS])
        ).count()

        quartiers_data.append({
            "id": quartier.id,
            "name": quartier.name,
            "latitude": quartier.latitude,
            "longitude": quartier.longitude,
            "boundaries": quartier.boundaries,
            "reports_count": reports_count,
            "active_reports": active_reports,
            "has_waste": active_reports > 0,
            "reports": []
        })

    # Récupérer tous les signalements de la commune
    commune_reports = db.query(Report).filter(
        Report.commune_id == commune.id
    ).all()

    reports_data = []
    for report in commune_reports:
        reports_data.append({
            "id": report.id,
            "latitude": report.latitude,
            "longitude": report.longitude,
            "status": report.status,
            "description": report.description,
            "created_at": report.created_at.isoformat() if report.created_at else None,
            "image_url": report.image_url,
            "user_name": report.user.full_name if report.user else "Anonyme",
            "quartier_id": report.quartier_id
        })

    return {
        "commune": {
            "id": commune.id,
            "name": commune.name,
            "postal_code": commune.postal_code,
            "latitude": commune.latitude,
            "longitude": commune.longitude,
            "boundaries": commune.boundaries,
            "quartiers_count": len(quartiers_data)
        },
        "quartiers": quartiers_data,
        "reports": reports_data,
        "stats": {
            "total_reports": len(reports_data),
            "active_reports": sum(q["active_reports"] for q in quartiers_data),
            "completed_reports": len([r for r in reports_data if r["status"] == "COMPLETED"])
        }
    }

@router.get("/quartier/{quartier_id}/details")
async def get_quartier_details(
    quartier_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Détails d'un quartier spécifique avec ses signalements"""
    quartier = db.query(Quartier).filter(Quartier.id == quartier_id).first()

    if not quartier:
        raise HTTPException(status_code=404, detail="Quartier non trouvé")

    # Récupérer les signalements de ce quartier
    reports = db.query(Report).filter(
        Report.quartier_id == quartier_id
    ).order_by(Report.created_at.desc()).limit(50).all()

    reports_data = []
    for report in reports:
        reports_data.append({
            "id": report.id,
            "latitude": report.latitude,
            "longitude": report.longitude,
            "status": report.status,
            "description": report.description,
            "created_at": report.created_at,
            "image_url": report.image_url,
            "user_name": report.user.full_name if report.user else "Anonyme",
            "address": report.address_description,
            "collector_name": report.collector.full_name if report.collector else None
        })

    # Statistiques par statut
    stats = {
        "pending": len([r for r in reports if r.status == "PENDING"]),
        "in_progress": len([r for r in reports if r.status == "IN_PROGRESS"]),
        "completed": len([r for r in reports if r.status == "COMPLETED"]),
        "total": len(reports)
    }

    return {
        "quartier": {
            "id": quartier.id,
            "name": quartier.name,
            "commune": quartier.commune.name if quartier.commune else None,
            "latitude": quartier.latitude,
            "longitude": quartier.longitude
        },
        "reports": reports_data,
        "stats": stats
    }

@router.get("/user-location")
async def get_user_location_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retourne les données géographiques basées sur la commune de l'utilisateur"""
    if not current_user.commune:
        raise HTTPException(status_code=400, detail="Commune non définie")

    return await get_commune_map_data(current_user.commune, current_user, db)

# Ajoutons un endpoint simple pour tester
@router.get("/test")
async def test_endpoint():
    return {"message": "API Geo fonctionne", "status": "ok"}

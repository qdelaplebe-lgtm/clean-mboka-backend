# app/api/tasks.py
"""
Tâches planifiées (cron) pour Clean Mboka.
À exécuter quotidiennement/mensuellement via cron ou celery.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Dict

from ..database import get_db
from .. import models
from ..services.scoring_service import ScoringService
from .deps import get_current_user

router = APIRouter()


@router.post("/cron/monthly-subscription-points")
def monthly_subscription_points(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)  # Admin requis
):
    """
    Tâche à exécuter le 1er de chaque mois.
    Attribue les points d'abonnement à tous les citoyens abonnés.
    PRÉSERVE toutes les données existantes.
    """
    # Vérifier que l'utilisateur est admin
    from ..api.reports import get_user_role
    user_role = get_user_role(current_user)
    
    if user_role not in ["admin", "administrateur"]:
        raise HTTPException(
            status_code=403,
            detail="Accès réservé à l'administrateur"
        )

    # Récupérer tous les citoyens avec abonnement actif
    users = db.query(models.User).filter(
        models.User.subscription_active == True,
        models.User.role == models.RoleEnum.CITOYEN
    ).all()

    total_points = 0
    count = 0
    errors = []

    for user in users:
        try:
            points = ScoringService.attribuer_points_abonnement(user, db)
            if points > 0:
                total_points += points
                count += 1
        except Exception as e:
            errors.append(f"User {user.id}: {str(e)}")

    return {
        "message": f"{count} citoyens ont reçu {total_points} points d'abonnement",
        "total_eligible": len(users),
        "processed": count,
        "total_points": total_points,
        "errors": errors if errors else None,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.post("/cron/daily-auto-confirm")
def daily_auto_confirm(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)  # Admin requis
):
    """
    Tâche quotidienne pour auto-confirmer les signalements expirés.
    Complète la route existante dans reports.py.
    """
    from ..api.reports import get_user_role
    
    user_role = get_user_role(current_user)
    if user_role not in ["admin", "administrateur"]:
        raise HTTPException(status_code=403, detail="Accès réservé à l'administrateur")

    # Récupérer les signalements expirés
    expired_reports = db.query(models.Report)\
        .filter(
            models.Report.status == models.ReportStatus.AWAITING_CONFIRMATION,
            models.Report.confirmation_deadline < datetime.utcnow(),
            models.Report.citizen_confirmed == False,
            models.Report.auto_confirmed == False
        )\
        .all()

    auto_confirmed_count = 0

    for report in expired_reports:
        report.auto_confirmed = True
        report.status = models.ReportStatus.COMPLETED
        report.resolved_at = datetime.utcnow()
        report.last_action = "auto_confirmed"
        report.last_action_at = datetime.utcnow()
        auto_confirmed_count += 1

    db.commit()

    return {
        "message": f"{auto_confirmed_count} signalements auto-confirmés",
        "auto_confirmed_count": auto_confirmed_count,
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/cron/status")
def get_cron_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Vérifie l'état des tâches planifiées.
    """
    from ..api.reports import get_user_role
    
    user_role = get_user_role(current_user)
    if user_role not in ["admin", "administrateur", "coordinator", "coordinateur"]:
        raise HTTPException(status_code=403, detail="Accès réservé")

    # Stats pour le rapport
    today = datetime.utcnow().date()
    
    # Nombre d'abonnements actifs
    active_subs = db.query(models.Subscription)\
        .filter(
            models.Subscription.is_active == True,
            models.Subscription.end_date > datetime.utcnow()
        ).count()
    
    # Signalements en attente de confirmation
    awaiting = db.query(models.Report)\
        .filter(models.Report.status == models.ReportStatus.AWAITING_CONFIRMATION)\
        .count()
    
    # Signalements expirés aujourd'hui
    expired_today = db.query(models.Report)\
        .filter(
            models.Report.status == models.ReportStatus.AWAITING_CONFIRMATION,
            models.Report.confirmation_deadline < datetime.utcnow(),
            models.Report.auto_confirmed == False
        ).count()

    return {
        "date": today.isoformat(),
        "active_subscriptions": active_subs,
        "awaiting_confirmation": awaiting,
        "expired_today": expired_today,
        "next_monthly_run": f"{today.year}-{today.month+1}-01 00:00:00" if today.day == 1 else f"{today.year}-{today.month}-01 00:00:00 (déjà exécuté)" if today.day > 1 else "Aujourd'hui",
        "daily_auto_confirm": "Exécuté" if today else "Planifié",
        "timestamp": datetime.utcnow().isoformat()
    }

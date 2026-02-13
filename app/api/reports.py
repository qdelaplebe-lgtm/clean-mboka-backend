# app/api/reports.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, func, case, update
from typing import List, Optional
from datetime import datetime, timedelta
import os
import shutil
import uuid

from .. import models, schemas
from ..database import get_db
from ..api.deps import get_current_user
from ..core.config import settings
from ..services.scoring_service import ScoringService  # NOUVEAU SERVICE

router = APIRouter()


# ==================== FONCTIONS UTILITAIRES ====================

def get_user_role(user):
    """Extrait la valeur du rôle de l'utilisateur."""
    if not user or not user.role:
        return ""

    if hasattr(user.role, 'value'):
        return user.role.value.lower()

    role_str = str(user.role).lower()
    if role_str.startswith('roleenum.'):
        role_str = role_str[9:]

    return role_str


def can_view_all_reports(current_user: models.User) -> bool:
    """
    Vérifie si l'utilisateur peut voir tous les signalements de sa commune.
    """
    user_role = get_user_role(current_user)

    # Tous les agents (ramasseur, superviseur, coordinateur) peuvent voir leur commune
    return user_role in [
        "ramasseur", "collector",
        "superviseur", "supervisor",
        "coordinateur", "coordinator",
        "administrateur", "admin"
    ]


# Assurons-nous que le dossier d'upload existe
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)


# ==================== NOUVELLES ROUTES POUR CONFIRMATION PHOTO ====================

@router.post("/{report_id}/submit-cleanup-photo", response_model=schemas.ReportDetail)
def submit_cleanup_photo(
    report_id: int,
    photo: UploadFile = File(...),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Permet au ramasseur de soumettre une photo prouvant le ramassage.
    Met le statut en AWAITING_CONFIRMATION.
    """
    # Vérifier que le signalement existe
    db_report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not db_report:
        raise HTTPException(status_code=404, detail="Signalement non trouvé")

    # Vérifier les permissions (ramasseur assigné)
    user_role = get_user_role(current_user)
    if user_role not in ["ramasseur", "collector"]:
        raise HTTPException(
            status_code=403,
            detail="Seuls les ramasseurs peuvent soumettre des photos de confirmation"
        )

    if db_report.collector_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Vous n'êtes pas le ramasseur assigné à ce signalement"
        )

    # Vérifier que le statut permet la soumission
    if db_report.status not in [models.ReportStatus.IN_PROGRESS, models.ReportStatus.ASSIGNED]:
        raise HTTPException(
            status_code=400,
            detail=f"Impossible de soumettre une photo pour un signalement au statut {db_report.status}"
        )

    # Sauvegarder la photo
    file_extension = photo.filename.split('.')[-1] if '.' in photo.filename else 'jpg'
    unique_filename = f"cleanup_{uuid.uuid4()}.{file_extension}"
    file_location = os.path.join(settings.UPLOAD_DIR, unique_filename)

    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(photo.file, buffer)

    cleanup_photo_url = f"/static/{unique_filename}"

    # Mettre à jour le signalement
    db_report.cleanup_photo_url = cleanup_photo_url
    db_report.cleanup_photo_submitted_at = datetime.utcnow()
    db_report.status = models.ReportStatus.AWAITING_CONFIRMATION

    # Générer un code de confirmation unique
    confirmation_code = str(uuid.uuid4())[:8].upper()  # Code à 8 caractères
    db_report.confirmation_code = confirmation_code

    # Définir une deadline (48h)
    db_report.confirmation_deadline = datetime.utcnow() + timedelta(hours=48)

    # Mettre à jour les logs
    db_report.last_action = "photo_submitted"
    db_report.last_action_at = datetime.utcnow()

    if notes:
        # Ajouter les notes à la description existante
        existing_desc = db_report.description or ""
        separator = "\n\n" if existing_desc else ""
        db_report.description = f"{existing_desc}{separator}📸 Notes du ramasseur: {notes}"

    db.commit()
    db.refresh(db_report)

    return db_report


@router.post("/{report_id}/confirm-cleanup", response_model=schemas.ReportDetail)
def confirm_cleanup_by_citizen(
    report_id: int,
    confirmation: schemas.CitizenConfirmation,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Permet au citoyen de confirmer ou refuser la confirmation.
    MODIFIÉ: Ajout du calcul des points via ScoringService.
    """
    from ..services.scoring_service import ScoringService

    db_report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not db_report:
        raise HTTPException(status_code=404, detail="Signalement non trouvé")

    # Vérifier l'authentification ou le code
    is_authenticated = False
    is_owner = False

    if current_user:
        # Utilisateur connecté
        user_role = get_user_role(current_user)
        is_owner = db_report.user_id == current_user.id

        # Vérifier si c'est un citoyen ou le propriétaire
        if user_role not in ["citoyen", "citizen"] and not is_owner:
            raise HTTPException(
                status_code=403,
                detail="Seuls les citoyens propriétaires peuvent confirmer le nettoyage"
            )
        is_authenticated = True
    else:
        # Vérification par code (pour liens externes/sans login)
        if not confirmation.confirmation_code:
            raise HTTPException(
                status_code=400,
                detail="Code de confirmation requis pour les utilisateurs non connectés"
            )

        if db_report.confirmation_code != confirmation.confirmation_code:
            raise HTTPException(
                status_code=403,
                detail="Code de confirmation invalide"
            )

    # Pour les utilisateurs connectés, vérifier qu'ils sont propriétaires (sauf admin)
    if is_authenticated and not is_owner:
        user_role = get_user_role(current_user)
        if user_role not in ["admin", "administrateur", "coordinator", "coordinateur"]:
            raise HTTPException(
                status_code=403,
                detail="Vous ne pouvez confirmer que vos propres signalements"
            )

    # Vérifier que le signalement est en attente de confirmation
    if db_report.status != models.ReportStatus.AWAITING_CONFIRMATION:
        raise HTTPException(
            status_code=400,
            detail=f"Ce signalement n'est pas en attente de confirmation. Statut: {db_report.status}"
        )

    # Vérifier que la deadline n'est pas passée
    if db_report.confirmation_deadline and datetime.utcnow() > db_report.confirmation_deadline:
        # Auto-confirmation si délai expiré
        db_report.auto_confirmed = True
        db_report.status = models.ReportStatus.COMPLETED
        db_report.resolved_at = datetime.utcnow()
        db_report.last_action = "auto_confirmed"
        db.commit()
        db.refresh(db_report)

        raise HTTPException(
            status_code=400,
            detail="Le délai de confirmation est expiré. Signalement auto-confirmé."
        )

    # Traiter la confirmation ou le refus
    if confirmation.confirmed:
        # Confirmation positive
        db_report.citizen_confirmed = True
        db_report.citizen_confirmed_at = datetime.utcnow()
        db_report.status = models.ReportStatus.COMPLETED
        db_report.resolved_at = datetime.utcnow()
        db_report.last_action = "confirmed"

        # ========== NOUVEAU: Calcul des points avec ScoringService ==========
        if is_authenticated and is_owner:
            # 1. Vérifier que le score de description existe
            if db_report.description_quality_score is None and db_report.description:
                db_report.description_quality_score = ScoringService.calculer_score_description(
                    db_report.description or ""
                )
            
            # 2. Calculer les points pour ce signalement (inclut poids, description, bonus)
            points_calcules = ScoringService.calculer_points_signalement(db_report, db_report.user)
            
            # 3. Ajouter les points au citoyen
            if points_calcules['total'] > 0:
                citoyen = db_report.user
                citoyen.points = (citoyen.points or 0) + points_calcules['total']
                db.add(citoyen)
                
                message = f"Collecte confirmée ! +{points_calcules['total']} points gagnés"
                db_report.confirmation_message = message
                
                # Log pour debug
                print(f"POINTS CONFIRMATION - User {citoyen.id}: +{points_calcules['total']} pts")
            else:
                # Fallback sur l'ancien système si aucun point calculé
                current_user.points = (current_user.points or 0) + 100
                db.add(current_user)
                message = "Collecte confirmée ! +100 points de récompense"
        else:
            message = "Collecte confirmée !"
        # ===================================================================
    else:
        # Refus avec raison obligatoire
        if not confirmation.reason or len(confirmation.reason.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="Veuillez fournir une raison détaillée (minimum 10 caractères) pour votre refus"
            )

        db_report.citizen_confirmed = False
        db_report.dispute_reason = confirmation.reason
        db_report.status = models.ReportStatus.DISPUTED
        db_report.last_action = "disputed"

        message = "Confirmation refusée. Le superviseur a été notifié."

    db_report.last_action_at = datetime.utcnow()
    db.commit()
    db.refresh(db_report)

    # Ajouter un message personnalisé pour l'utilisateur
    db_report.confirmation_message = message

    return db_report


@router.get("/{report_id}/cleanup-status", response_model=schemas.CleanupStatusResponse)
def get_cleanup_status(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)  # Optionnel
):
    """
    Récupère le statut de confirmation d'un signalement.
    Accessible publiquement avec code ou par utilisateur connecté.
    MODIFIÉ: Ajout des informations de poids et score.
    """
    db_report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not db_report:
        raise HTTPException(status_code=404, detail="Signalement non trouvé")

    # Déterminer si l'utilisateur peut confirmer
    can_confirm = False
    accessible_via_code = False

    if current_user:
        user_role = get_user_role(current_user)
        # Le propriétaire peut confirmer
        if db_report.user_id == current_user.id:
            can_confirm = db_report.status == models.ReportStatus.AWAITING_CONFIRMATION and not db_report.citizen_confirmed
        # Les admins peuvent aussi voir/confirmer
        elif user_role in ["admin", "administrateur", "coordinator", "coordinateur", "superviseur", "supervisor"]:
            can_confirm = db_report.status == models.ReportStatus.AWAITING_CONFIRMATION

    # Vérifier si accessible via code
    accessible_via_code = (
        db_report.status == models.ReportStatus.AWAITING_CONFIRMATION and
        db_report.confirmation_code is not None and
        not db_report.citizen_confirmed
    )

    response_data = {
        "report_id": db_report.id,
        "status": db_report.status,
        "has_cleanup_photo": bool(db_report.cleanup_photo_url),
        "cleanup_photo_url": db_report.cleanup_photo_url,
        "photo_submitted_at": db_report.cleanup_photo_submitted_at,
        "citizen_confirmed": db_report.citizen_confirmed,
        "citizen_confirmed_at": db_report.citizen_confirmed_at,
        "confirmation_deadline": db_report.confirmation_deadline,
        "awaiting_confirmation": db_report.status == models.ReportStatus.AWAITING_CONFIRMATION,
        "can_confirm": can_confirm,
        "confirmation_code": db_report.confirmation_code if accessible_via_code else None,
        # ========== NOUVEAUX CHAMPS ==========
        "weight_kg": db_report.weight_kg,
        "description_quality_score": db_report.description_quality_score,
        "points_estimated": ScoringService.calculer_points_signalement(db_report, db_report.user)['total'] if db_report.user else 0
        # ======================================
    }

    # Ajouter la raison du litige si applicable
    if db_report.dispute_reason:
        response_data["dispute_reason"] = db_report.dispute_reason

    return response_data


@router.get("/awaiting-confirmation", response_model=List[schemas.ReportList])
def get_reports_awaiting_confirmation(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Liste des signalements en attente de confirmation.
    Utile pour les superviseurs.
    """
    user_role = get_user_role(current_user)

    # Seuls les agents peuvent voir cette liste
    if user_role not in ["ramasseur", "collector", "superviseur", "supervisor",
                         "coordinateur", "coordinator", "admin", "administrateur"]:
        raise HTTPException(status_code=403, detail="Accès réservé aux agents")

    # Construire la requête
    query = db.query(models.Report)\
        .options(joinedload(models.Report.user))\
        .filter(models.Report.status == models.ReportStatus.AWAITING_CONFIRMATION)\
        .order_by(models.Report.confirmation_deadline.asc())  # Plus urgent d'abord

    # Filtre géographique pour non-admins
    if user_role in ["ramasseur", "collector", "superviseur", "supervisor"]:
        if current_user.commune:
            query = query.filter(
                models.Report.user.has(commune=current_user.commune)
            )

    reports = query.offset(skip).limit(limit).all()

    return reports


@router.get("/disputed", response_model=List[schemas.ReportList])
def get_disputed_reports(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Liste des signalements en litige.
    Utile pour les superviseurs.
    """
    user_role = get_user_role(current_user)

    # Seuls les agents peuvent voir cette liste
    if user_role not in ["superviseur", "supervisor", "coordinateur", "coordinator",
                         "admin", "administrateur"]:
        raise HTTPException(status_code=403, detail="Accès réservé aux superviseurs")

    query = db.query(models.Report)\
        .options(joinedload(models.Report.user))\
        .filter(models.Report.status == models.ReportStatus.DISPUTED)\
        .order_by(models.Report.last_action_at.desc())

    # Filtre géographique pour non-admins
    if user_role in ["superviseur", "supervisor"]:
        if current_user.commune:
            query = query.filter(
                models.Report.user.has(commune=current_user.commune)
            )

    reports = query.offset(skip).limit(limit).all()

    return reports


@router.put("/{report_id}/resolve-dispute", response_model=schemas.ReportDetail)
def resolve_dispute(
    report_id: int,
    resolution: str = Form(...),  # "accept" ou "reject"
    admin_notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Permet à un superviseur/admin de résoudre un litige.
    """
    user_role = get_user_role(current_user)

    if user_role not in ["superviseur", "supervisor", "coordinateur", "coordinator",
                         "admin", "administrateur"]:
        raise HTTPException(status_code=403, detail="Accès réservé aux superviseurs")

    db_report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not db_report:
        raise HTTPException(status_code=404, detail="Signalement non trouvé")

    if db_report.status != models.ReportStatus.DISPUTED:
        raise HTTPException(
            status_code=400,
            detail="Ce signalement n'est pas en état de litige"
        )

    # Vérifier les permissions géographiques
    if user_role in ["superviseur", "supervisor"]:
        if current_user.commune and db_report.user.commune:
            if current_user.commune.lower() != db_report.user.commune.lower():
                raise HTTPException(
                    status_code=403,
                    detail="Ce signalement n'est pas dans votre zone de responsabilité"
                )

    # Appliquer la résolution
    if resolution.lower() == "accept":
        # Accepter la photo, marquer comme complété
        db_report.status = models.ReportStatus.COMPLETED
        db_report.resolved_at = datetime.utcnow()
        db_report.citizen_confirmed = True  # Forcé par le superviseur
        db_report.last_action = "dispute_resolved_accepted"
        message = "Litige résolu: Photo acceptée par le superviseur"
    elif resolution.lower() == "reject":
        # Rejeter, remettre en IN_PROGRESS pour nouvelle tentative
        db_report.status = models.ReportStatus.IN_PROGRESS
        db_report.cleanup_photo_url = None  # Supprimer la photo refusée
        db_report.cleanup_photo_submitted_at = None
        db_report.confirmation_code = None
        db_report.confirmation_deadline = None
        db_report.dispute_reason = f"{db_report.dispute_reason}\n\nRésolution superviseur: {admin_notes or 'Rejeté sans commentaire'}"
        db_report.last_action = "dispute_resolved_rejected"
        message = "Litige résolu: Photo rejetée, retour en traitement"
    else:
        raise HTTPException(status_code=400, detail="Résolution invalide. Utilisez 'accept' ou 'reject'")

    db_report.last_action_at = datetime.utcnow()

    if admin_notes:
        existing_desc = db_report.description or ""
        separator = "\n\n" if existing_desc else ""
        db_report.description = f"{existing_desc}{separator}👨‍💼 Notes du superviseur: {admin_notes}"

    db.commit()
    db.refresh(db_report)

    # Ajouter un message
    db_report.resolution_message = message

    return db_report


# Tâche cron pour auto-confirmation (à appeler quotidiennement)
@router.post("/tasks/auto-confirm-expired")
def auto_confirm_expired_reports(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)  # Authentification admin
):
    """
    Tâche à exécuter quotidiennement pour auto-confirmer les signalements expirés.
    """
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


# ==================== ROUTES EXISTANTES (PRÉSERVÉES) ====================

@router.get("/", response_model=List[schemas.ReportList])
def read_reports(
    skip: int = 0,
    limit: int = 100,
    commune: Optional[str] = Query(None),
    quartier: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    # ========== NOUVEAUX FILTRES ==========
    min_weight: Optional[float] = Query(None, description="Poids minimum (kg)"),
    max_weight: Optional[float] = Query(None, description="Poids maximum (kg)"),
    has_weight: Optional[bool] = Query(None, description="Filtrer les signalements avec/sans poids"),
    min_score: Optional[int] = Query(None, description="Score description minimum (0-30)"),
    # ======================================
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Récupère la liste des signalements avec filtrage hiérarchique.
    MODIFIÉ: Ajout des filtres poids et score.
    """
    user_role = get_user_role(current_user)

    print(f"=== DEBUG read_reports ===")
    print(f"User: {current_user.full_name}")
    print(f"Role: {user_role}")
    print(f"Commune: {current_user.commune}")

    # Construction de la requête de base avec jointure
    query = db.query(models.Report).options(joinedload(models.Report.user))

    # ========== LOGIQUE DE FILTRAGE HIÉRARCHIQUE ==========

    if user_role in ["citoyen", "citizen"]:
        # CITOYEN : seulement ses propres signalements
        print("DEBUG - CITOYEN: voir seulement ses propres signalements")
        query = query.filter(models.Report.user_id == current_user.id)

    elif user_role in ["ramasseur", "collector", "superviseur", "supervisor"]:
        # RAMASSEUR & SUPERVISEUR : voient les signalements de leur commune seulement
        if not current_user.commune:
            print("DEBUG - Agent sans commune!")
            return []

        print(f"DEBUG - AGENT ({user_role}): voir les signalements de la commune {current_user.commune}")
        query = query.filter(
            models.Report.user.has(commune=current_user.commune)
        )

        # Filtres avancés pour les agents
        if quartier:
            query = query.filter(models.Report.user.has(quartier=quartier))

    elif user_role in ["coordinateur", "coordinator"]:
        # MODIFICATION: COORDINATEUR voit TOUS les signalements (comme l'administrateur)
        print("DEBUG - COORDINATEUR: voir tous les signalements (même privilèges que admin)")

        # Filtres avancés pour le coordinateur
        if commune:
            query = query.filter(models.Report.user.has(commune=commune))
        if quartier:
            query = query.filter(models.Report.user.has(quartier=quartier))

    elif user_role in ["administrateur", "admin"]:
        # ADMINISTRATEUR : voit TOUS les signalements de la ville
        print("DEBUG - ADMINISTRATEUR: voir tous les signalements de Kinshasa")

        # Filtres avancés pour l'admin
        if commune:
            query = query.filter(models.Report.user.has(commune=commune))
        if quartier:
            query = query.filter(models.Report.user.has(quartier=quartier))

    else:
        print(f"DEBUG - Rôle inconnu: {user_role}")
        return []

    # Appliquer les filtres communs à tous
    if status:
        query = query.filter(models.Report.status == status)

    if start_date:
        query = query.filter(models.Report.created_at >= start_date)

    if end_date:
        query = query.filter(models.Report.created_at <= end_date)
    
    # ========== NOUVEAUX FILTRES POIDS ET SCORE ==========
    if min_weight is not None:
        query = query.filter(models.Report.weight_kg >= min_weight)
    
    if max_weight is not None:
        query = query.filter(models.Report.weight_kg <= max_weight)
    
    if has_weight is not None:
        if has_weight:
            query = query.filter(models.Report.weight_kg.isnot(None))
        else:
            query = query.filter(models.Report.weight_kg.is_(None))
    
    if min_score is not None:
        query = query.filter(models.Report.description_quality_score >= min_score)
    # ====================================================

    # Tri du plus récent au plus ancien
    query = query.order_by(models.Report.created_at.desc())

    # Exécuter avec pagination
    reports = query.offset(skip).limit(limit).all()
    print(f"DEBUG - Nombre de rapports trouvés: {len(reports)}")

    return reports


@router.get("/all", response_model=List[schemas.ReportList])
def read_all_reports(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Récupère TOUS les signalements (admin ET coordinateur).
    """
    user_role = get_user_role(current_user)

    # MODIFICATION: Admin ET Coordinateur peuvent voir tous les signalements
    if user_role not in ["admin", "administrateur", "coordinator", "coordinateur"]:
        raise HTTPException(
            status_code=403,
            detail="Accès administrateur ou coordinateur seulement"
        )

    query = db.query(models.Report)\
        .options(joinedload(models.Report.user))\
        .order_by(models.Report.created_at.desc())

    reports = query.offset(skip).limit(limit).all()

    return reports


@router.get("/stats/global", response_model=schemas.ReportStatistics)
def get_global_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Statistiques globales sur les signalements (admin ET coordinateur).
    MODIFIÉ: Ajout des statistiques de poids et points.
    """
    user_role = get_user_role(current_user)

    # MODIFICATION: Admin ET Coordinateur peuvent voir les statistiques globales
    if user_role not in ["admin", "administrateur", "coordinator", "coordinateur"]:
        raise HTTPException(
            status_code=403,
            detail="Accès administrateur ou coordinateur seulement"
        )

    # Compter tous les signalements
    total = db.query(models.Report).count()

    # Par statut (incluant les nouveaux statuts)
    pending = db.query(models.Report).filter(models.Report.status == "PENDING").count()
    assigned = db.query(models.Report).filter(models.Report.status == "ASSIGNED").count()
    in_progress = db.query(models.Report).filter(models.Report.status == "IN_PROGRESS").count()
    awaiting_confirmation = db.query(models.Report).filter(models.Report.status == "AWAITING_CONFIRMATION").count()
    completed = db.query(models.Report).filter(models.Report.status == "COMPLETED").count()
    disputed = db.query(models.Report).filter(models.Report.status == "DISPUTED").count()
    rejected = 0  # CORRECTION: Pas de statut REJECTED dans la base

    # Dernières 24 heures
    last_24h = datetime.utcnow() - timedelta(hours=24)
    recent_24h = db.query(models.Report)\
        .filter(models.Report.created_at >= last_24h)\
        .count()

    # ========== NOUVEAU: Statistiques de poids ==========
    total_weight = db.query(
            func.coalesce(func.sum(models.Report.weight_kg), 0)
        ).scalar() or 0.0
    
    reports_with_weight = db.query(models.Report)\
        .filter(models.Report.weight_kg.isnot(None))\
        .count()
    
    average_weight = total_weight / reports_with_weight if reports_with_weight > 0 else 0
    
    # ========== NOUVEAU: Estimation des points distribués ==========
    # Approximation basée sur les signalements complétés avec poids
    total_points_estimate = db.query(
        func.sum(
            func.coalesce(models.Report.description_quality_score, 0) +
            func.coalesce(models.Report.weight_kg * 2, 0)
        )
    ).filter(
        models.Report.status == "COMPLETED"
    ).scalar() or 0
    # ============================================================

    # Par commune (top 10)
    commune_stats = db.query(
        models.User.commune,
        func.count(models.Report.id).label('count'),
        func.coalesce(func.sum(models.Report.weight_kg), 0).label('weight')  # NOUVEAU
    )\
    .join(models.Report, models.Report.user_id == models.User.id)\
    .group_by(models.User.commune)\
    .order_by(func.count(models.Report.id).desc())\
    .limit(10)\
    .all()

    # Évolution mensuelle (derniers 6 mois)
    six_months_ago = datetime.utcnow() - timedelta(days=180)
    monthly_stats = db.query(
        func.date_trunc('month', models.Report.created_at).label('month'),
        func.count(models.Report.id).label('count'),
        func.coalesce(func.sum(models.Report.weight_kg), 0).label('weight')  # NOUVEAU
    )\
    .filter(models.Report.created_at >= six_months_ago)\
    .group_by(func.date_trunc('month', models.Report.created_at))\
    .order_by(func.date_trunc('month', models.Report.created_at))\
    .all()

    return {
        "total": total,
        "pending": pending,
        "assigned": assigned,
        "in_progress": in_progress,
        "awaiting_confirmation": awaiting_confirmation,
        "completed": completed,
        "disputed": disputed,
        "rejected": rejected,
        "recent_24h": recent_24h,
        # ========== NOUVEAUX CHAMPS ==========
        "total_weight_kg": float(total_weight),
        "average_weight_kg": float(average_weight),
        "total_points_awarded": int(total_points_estimate),
        "reports_with_weight": reports_with_weight,
        # ======================================
        "commune_stats": {
            commune: {
                "count": count,
                "weight_kg": float(weight)
            } 
            for commune, count, weight in commune_stats
        },
        "monthly_stats": {
            month.strftime('%Y-%m'): {
                "count": count,
                "weight_kg": float(weight)
            }
            for month, count, weight in monthly_stats
        }
    }


@router.get("/stats/by-commune")
def get_stats_by_commune(
    commune: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Statistiques par commune.
    MODIFIÉ: Ajout du poids total par commune.
    """
    user_role = get_user_role(current_user)

    # Construire la requête de base avec syntaxe SQLAlchemy correcte
    query = db.query(
        models.User.commune,
        func.count(models.Report.id).label('total'),
        func.sum(
            case(
                (models.Report.status == "PENDING", 1),
                else_=0
            )
        ).label('pending'),
        func.sum(
            case(
                (models.Report.status == "ASSIGNED", 1),
                else_=0
            )
        ).label('assigned'),
        func.sum(
            case(
                (models.Report.status == "IN_PROGRESS", 1),
                else_=0
            )
        ).label('in_progress'),
        func.sum(
            case(
                (models.Report.status == "AWAITING_CONFIRMATION", 1),
                else_=0
            )
        ).label('awaiting_confirmation'),
        func.sum(
            case(
                (models.Report.status == "COMPLETED", 1),
                else_=0
            )
        ).label('completed'),
        func.sum(
            case(
                (models.Report.status == "DISPUTED", 1),
                else_=0
            )
        ).label('disputed'),
        # ========== NOUVEAU: Poids total par commune ==========
        func.coalesce(func.sum(models.Report.weight_kg), 0).label('total_weight'),
        func.avg(models.Report.weight_kg).label('average_weight'),
        func.sum(
            func.coalesce(models.Report.description_quality_score, 0)
        ).label('total_score')
        # ====================================================
    )\
    .join(models.Report, models.Report.user_id == models.User.id)\
    .group_by(models.User.commune)

    # Appliquer le filtrage hiérarchique
    if user_role in ["ramasseur", "collector", "superviseur", "supervisor"]:
        # Agents voient seulement leur commune
        if not current_user.commune:
            return []
        query = query.filter(models.User.commune == current_user.commune)

    elif user_role in ["admin", "administrateur", "coordinator", "coordinateur"]:
        # Admin ET Coordinateur peuvent filtrer par commune spécifique ou voir toutes
        if commune:
            query = query.filter(models.User.commune == commune)
        # Sinon, voir toutes les communes

    else:
        # Citoyens ne peuvent pas voir ces stats
        raise HTTPException(status_code=403, detail="Permission refusée")

    results = query.all()

    return [
        {
            "commune": result.commune,
            "total": result.total or 0,
            "pending": result.pending or 0,
            "assigned": result.assigned or 0,
            "in_progress": result.in_progress or 0,
            "awaiting_confirmation": result.awaiting_confirmation or 0,
            "completed": result.completed or 0,
            "disputed": result.disputed or 0,
            # ========== NOUVEAUX CHAMPS ==========
            "total_weight_kg": float(result.total_weight or 0),
            "average_weight_kg": float(result.average_weight or 0),
            "total_description_score": int(result.total_score or 0),
            # ======================================
            "completion_rate": ((result.completed or 0) / (result.total or 1)) * 100
        }
        for result in results
    ]


@router.get("/stats/by-role")
def get_stats_by_role(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Statistiques des signalements par rôle de l'utilisateur.
    """
    user_role = get_user_role(current_user)

    # MODIFICATION: Admin ET Coordinateur peuvent voir ces statistiques
    if user_role not in ["admin", "administrateur", "coordinator", "coordinateur"]:
        raise HTTPException(status_code=403, detail="Accès administrateur ou coordinateur seulement")

    stats_by_role = {}

    for role in models.RoleEnum:
        # Signalements créés par les utilisateurs de ce rôle
        reports_by_role = db.query(models.Report)\
            .join(models.User, models.Report.user_id == models.User.id)\
            .filter(models.User.role == role)\
            .count()

        # Signalements assignés aux utilisateurs de ce rôle
        reports_assigned_to_role = db.query(models.Report)\
            .join(models.User, models.Report.collector_id == models.User.id)\
            .filter(models.User.role == role)\
            .count()
        
        # ========== NOUVEAU: Poids collecté par rôle ==========
        weight_by_role = db.query(
                func.coalesce(func.sum(models.Report.weight_kg), 0)
            )\
            .join(models.User, models.Report.user_id == models.User.id)\
            .filter(models.User.role == role)\
            .scalar() or 0
        # ====================================================

        stats_by_role[role.value] = {
            "reports_created": reports_by_role,
            "reports_assigned": reports_assigned_to_role,
            "total_weight_kg": float(weight_by_role)  # NOUVEAU
        }

    return stats_by_role


@router.get("/history", response_model=List[schemas.ReportList])
def read_reports_history(
    days: int = 30,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Récupère l'historique des signalements (tous statuts confondus).
    """
    from datetime import datetime, timedelta

    user_role = get_user_role(current_user)

    # Date de début (il y a X jours)
    start_date = datetime.utcnow() - timedelta(days=days)

    # Construction de la requête de base avec jointure
    query = db.query(models.Report).options(joinedload(models.Report.user))

    # Filtrer par date
    query = query.filter(models.Report.created_at >= start_date)

    # LOGIQUE DE FILTRAGE HIÉRARCHIQUE
    if user_role in ["citizen", "citoyen"]:
        query = query.filter(models.Report.user_id == current_user.id)

    elif user_role in ["ramasseur", "collector", "superviseur", "supervisor"]:
        # Agents voient leur commune
        if not current_user.commune:
            return []

        query = query.filter(
            models.Report.user.has(commune=current_user.commune)
        )

    elif user_role in ["coordinateur", "coordinator"]:
        # MODIFICATION: Coordinateur voit TOUS les signalements
        # Pas de restriction géographique
        pass

    elif user_role in ["admin", "administrateur"]:
        # Admin : pas de filtre géographique
        pass

    else:
        return []

    # Tri du plus récent au plus ancien
    query = query.order_by(models.Report.created_at.desc())

    return query.offset(skip).limit(limit).all()


@router.get("/admin/dashboard")
def get_admin_dashboard(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Données pour le tableau de bord admin (admin ET coordinateur).
    MODIFIÉ: Ajout des métriques de poids et points.
    """
    user_role = get_user_role(current_user)

    # MODIFICATION: Admin ET Coordinateur peuvent voir le dashboard admin
    if user_role not in ["admin", "administrateur", "coordinator", "coordinateur"]:
        raise HTTPException(status_code=403, detail="Accès administrateur ou coordinateur seulement")

    # Statistiques utilisateurs
    total_users = db.query(models.User).count()
    users_by_role = {}
    for role in models.RoleEnum:
        count = db.query(models.User).filter(models.User.role == role).count()
        users_by_role[role.value] = count

    # Statistiques signalements
    total_reports = db.query(models.Report).count()
    reports_by_status = {
        "PENDING": db.query(models.Report).filter(models.Report.status == "PENDING").count(),
        "ASSIGNED": db.query(models.Report).filter(models.Report.status == "ASSIGNED").count(),
        "IN_PROGRESS": db.query(models.Report).filter(models.Report.status == "IN_PROGRESS").count(),
        "AWAITING_CONFIRMATION": db.query(models.Report).filter(models.Report.status == "AWAITING_CONFIRMATION").count(),
        "COMPLETED": db.query(models.Report).filter(models.Report.status == "COMPLETED").count(),
        "DISPUTED": db.query(models.Report).filter(models.Report.status == "DISPUTED").count()
    }

    # Signalements récents (dernières 24h)
    last_24h = datetime.utcnow() - timedelta(hours=24)
    recent_reports = db.query(models.Report)\
        .filter(models.Report.created_at >= last_24h)\
        .count()

    # Utilisateurs actifs récents (connectés dans les dernières 24h)
    recent_active_users = db.query(models.User)\
        .filter(models.User.updated_at >= last_24h)\
        .count()

    # ========== NOUVELLES MÉTRIQUES POIDS ==========
    total_weight = db.query(
            func.coalesce(func.sum(models.Report.weight_kg), 0)
        ).scalar() or 0.0
    
    avg_weight_per_report = db.query(
            func.avg(models.Report.weight_kg)
        ).filter(models.Report.weight_kg.isnot(None)).scalar() or 0
    
    reports_with_weight = db.query(models.Report)\
        .filter(models.Report.weight_kg.isnot(None))\
        .count()
    # ===============================================

    # ========== NOUVELLES MÉTRIQUES POINTS ==========
    top_citizens = db.query(
        models.User.id,
        models.User.full_name,
        models.User.commune,
        models.User.points,
        func.coalesce(func.sum(models.Report.weight_kg), 0).label('total_weight')
    )\
    .join(models.Report, models.Report.user_id == models.User.id, isouter=True)\
    .filter(models.User.role == models.RoleEnum.CITOYEN)\
    .group_by(models.User.id)\
    .order_by(models.User.points.desc())\
    .limit(5)\
    .all()
    # ================================================

    # Top communes avec le plus de signalements
    top_communes = db.query(
        models.User.commune,
        func.count(models.Report.id).label('count'),
        func.coalesce(func.sum(models.Report.weight_kg), 0).label('weight')  # NOUVEAU
    )\
    .join(models.Report, models.Report.user_id == models.User.id)\
    .group_by(models.User.commune)\
    .order_by(func.count(models.Report.id).desc())\
    .limit(5)\
    .all()

    # Top agents (ramasseurs) les plus actifs
    top_collectors = db.query(
        models.User.full_name,
        func.count(models.Report.id).label('completed_reports'),
        func.coalesce(func.sum(models.Report.weight_kg), 0).label('total_weight')  # NOUVEAU
    )\
    .join(models.Report, models.Report.collector_id == models.User.id)\
    .filter(models.Report.status == "COMPLETED")\
    .group_by(models.User.id, models.User.full_name)\
    .order_by(func.count(models.Report.id).desc())\
    .limit(5)\
    .all()

    # Signalements par commune (détail)
    reports_by_commune = db.query(
        models.User.commune,
        func.count(models.Report.id).label('total'),
        func.sum(
            case(
                (models.Report.status == "PENDING", 1),
                else_=0
            )
        ).label('pending'),
        func.sum(
            case(
                (models.Report.status == "COMPLETED", 1),
                else_=0
            )
        ).label('completed'),
        func.sum(
            case(
                (models.Report.status == "AWAITING_CONFIRMATION", 1),
                else_=0
            )
        ).label('awaiting_confirmation'),
        func.sum(
            case(
                (models.Report.status == "DISPUTED", 1),
                else_=0
            )
        ).label('disputed'),
        # ========== NOUVEAU: Poids total par commune pour dashboard ==========
        func.coalesce(func.sum(models.Report.weight_kg), 0).label('total_weight')
        # ===================================================================
    )\
    .join(models.Report, models.Report.user_id == models.User.id)\
    .group_by(models.User.commune)\
    .order_by(func.count(models.Report.id).desc())\
    .all()

    return {
        "user_stats": {
            "total": total_users,
            "by_role": users_by_role,
            "recent_active": recent_active_users
        },
        "report_stats": {
            "total": total_reports,
            "by_status": reports_by_status,
            "recent": recent_reports,
            # ========== NOUVEAUX CHAMPS ==========
            "total_weight_kg": float(total_weight),
            "avg_weight_per_report": float(avg_weight_per_report or 0),
            "reports_with_weight": reports_with_weight
            # ======================================
        },
        "top_communes": [
            {
                "commune": commune, 
                "count": count,
                "total_weight_kg": float(weight)  # NOUVEAU
            }
            for commune, count, weight in top_communes
        ],
        "top_collectors": [
            {
                "name": name, 
                "completed_reports": count,
                "total_weight_kg": float(weight)  # NOUVEAU
            }
            for name, count, weight in top_collectors
        ],
        # ========== NOUVEAU: Top citoyens ==========
        "top_citizens": [
            {
                "id": c.id,
                "name": c.full_name,
                "commune": c.commune,
                "points": c.points or 0,
                "total_weight_kg": float(c.total_weight or 0)
            }
            for c in top_citizens
        ],
        # ===========================================
        "reports_by_commune": [
            {
                "commune": commune,
                "total": total or 0,
                "pending": pending or 0,
                "completed": completed or 0,
                "awaiting_confirmation": awaiting_confirmation or 0,
                "disputed": disputed or 0,
                "total_weight_kg": float(total_weight or 0),  # NOUVEAU
                "completion_rate": ((completed or 0) / (total or 1)) * 100
            }
            for commune, total, pending, completed, awaiting_confirmation, disputed, total_weight in reports_by_commune
        ],
        "timestamp": datetime.utcnow().isoformat()
    }


# ==================== ROUTES EXISTANTES POUR CITOYENS ====================

@router.get("/my-reports", response_model=List[schemas.ReportList])
def read_my_reports(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Récupère les signalements de l'utilisateur connecté (pour les citoyens).
    """
    user_role = get_user_role(current_user)

    # Seuls les citoyens peuvent utiliser cette route
    if user_role not in ["citizen", "citoyen"]:
        raise HTTPException(
            status_code=403,
            detail="Cette route est réservée aux citoyens"
        )

    reports = db.query(models.Report)\
        .options(joinedload(models.Report.user))\
        .filter(models.Report.user_id == current_user.id)\
        .order_by(models.Report.created_at.desc())\
        .offset(skip).limit(limit).all()

    return reports


@router.delete("/{report_id}/citizen")
def delete_report_by_citizen(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Permet à un citoyen de supprimer son propre signalement.
    """
    # Vérifier que le signalement existe
    db_report = db.query(models.Report)\
        .filter(models.Report.id == report_id)\
        .first()

    if not db_report:
        raise HTTPException(status_code=404, detail="Signalement non trouvé")

    # Vérifier que l'utilisateur est le propriétaire
    user_role = get_user_role(current_user)
    if user_role not in ["citizen", "citoyen"]:
        raise HTTPException(
            status_code=403,
            detail="Seuls les citoyens peuvent supprimer leurs propres signalements"
        )

    if db_report.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Vous ne pouvez supprimer que vos propres signalements"
        )

    # Vérifier que le signalement n'est pas déjà en cours ou terminé
    if db_report.status not in ["PENDING"]:
        raise HTTPException(
            status_code=400,
            detail="Vous ne pouvez supprimer que les signalements en attente"
        )

    # Supprimer le signalement
    db.delete(db_report)
    db.commit()

    return {
        "message": "Signalement supprimé avec succès",
        "report_id": report_id
    }


@router.put("/{report_id}/confirm-collection")
def confirm_collection_by_citizen(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Permet à un citoyen de confirmer que les déchets ont été ramassés.
    (Ancienne route - conservée pour compatibilité)
    """
    # Vérifier que le signalement existe
    db_report = db.query(models.Report)\
        .filter(models.Report.id == report_id)\
        .first()

    if not db_report:
        raise HTTPException(status_code=404, detail="Signalement non trouvé")

    # Vérifier que l'utilisateur est le propriétaire
    user_role = get_user_role(current_user)
    if user_role not in ["citizen", "citoyen"]:
        raise HTTPException(
            status_code=403,
            detail="Seuls les citoyens peuvent confirmer la collecte"
        )

    if db_report.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Vous ne pouvez confirmer que vos propres signalements"
        )

    # Vérifier que le signalement est en cours
    if db_report.status != "IN_PROGRESS":
        # Si le signalement est en attente de confirmation, rediriger vers le nouveau système
        if db_report.status == models.ReportStatus.AWAITING_CONFIRMATION:
            raise HTTPException(
                status_code=400,
                detail="Ce signalement nécessite une confirmation avec photo. Utilisez le nouveau endpoint /confirm-cleanup"
            )
        raise HTTPException(
            status_code=400,
            detail="Vous ne pouvez confirmer que les signalements en cours de traitement"
        )

    # Mettre à jour le statut (ancienne méthode)
    db_report.status = "COMPLETED"
    db_report.resolved_at = datetime.utcnow()

    # Ajouter des points de récompense
    current_user.points = (current_user.points or 0) + 100
    db.add(current_user)

    db.commit()
    db.refresh(db_report)

    return {
        "message": "Collecte confirmée ! +100 points de récompense",
        "report_id": report_id,
        "new_status": db_report.status,
        "points_earned": 100
    }


@router.get("/{report_id}/can-confirm")
def can_confirm_collection(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Vérifie si un citoyen peut confirmer la collecte d'un signalement.
    MODIFIÉ: Ajout des informations de poids et points.
    """
    db_report = db.query(models.Report)\
        .filter(models.Report.id == report_id)\
        .first()

    if not db_report:
        return {"can_confirm": False, "reason": "Signalement non trouvé"}

    user_role = get_user_role(current_user)

    # Seuls les citoyens propriétaires peuvent confirmer
    if user_role not in ["citizen", "citoyen"]:
        return {"can_confirm": False, "reason": "Réservé aux citoyens"}

    if db_report.user_id != current_user.id:
        return {"can_confirm": False, "reason": "Vous n'êtes pas le propriétaire"}

    # Vérifier le statut
    if db_report.status == models.ReportStatus.AWAITING_CONFIRMATION:
        # Nouveau système avec photo
        points_estimate = ScoringService.calculer_points_signalement(db_report, db_report.user)['total'] if db_report.user else 0
        
        return {
            "can_confirm": True,
            "reason": "Signalement avec photo en attente de confirmation",
            "requires_photo_confirmation": True,
            "has_cleanup_photo": bool(db_report.cleanup_photo_url),
            "confirmation_code": db_report.confirmation_code,
            # ========== NOUVEAUX CHAMPS ==========
            "weight_kg": db_report.weight_kg,
            "description_score": db_report.description_quality_score,
            "points_estimated": points_estimate
            # ======================================
        }
    elif db_report.status == "IN_PROGRESS":
        # Ancien système (sans photo)
        return {
            "can_confirm": True, 
            "reason": "OK", 
            "requires_photo_confirmation": False,
            "points_estimated": 100  # NOUVEAU
        }
    else:
        return {
            "can_confirm": False,
            "reason": f"Le signalement est {db_report.status}"
        }


# ==================== NOUVEL ENDPOINT POIDS DÉCHETS ====================

@router.put("/{report_id}/weight", response_model=schemas.ReportResponse)
def update_report_weight(
    report_id: int,
    weight_data: schemas.ReportWeightUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    NOUVEAU - Permet au ramasseur d'ajouter le poids vérifié des déchets.
    DÉCLENCHE LE CALCUL DES POINTS CITOYENS (critère #3).
    """
    # Vérifier que le signalement existe
    db_report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not db_report:
        raise HTTPException(status_code=404, detail="Signalement non trouvé")

    # Vérifier les permissions (ramasseur assigné ou superviseur)
    user_role = get_user_role(current_user)
    if user_role not in ["ramasseur", "collector", "superviseur", "supervisor", "admin", "administrateur", "coordinator", "coordinateur"]:
        raise HTTPException(status_code=403, detail="Seuls les agents peuvent enregistrer un poids")

    # Si c'est un ramasseur, vérifier qu'il est assigné
    if user_role in ["ramasseur", "collector"] and db_report.collector_id != current_user.id:
        raise HTTPException(status_code=403, detail="Vous n'êtes pas assigné à ce signalement")

    # Vérifier que le poids n'a pas déjà été enregistré
    if db_report.weight_kg is not None:
        raise HTTPException(status_code=400, detail="Un poids a déjà été enregistré pour ce signalement")

    # Enregistrer le poids
    db_report.weight_kg = weight_data.weight_kg
    db_report.weight_verified_at = datetime.utcnow()
    db_report.weight_verified_by = current_user.id
    db_report.last_action = "weight_recorded"
    db_report.last_action_at = datetime.utcnow()

    # --- CALCUL DES POINTS CITOYENS ---
    # 1. S'assurer que le score de description existe
    if db_report.description_quality_score is None and db_report.description:
        db_report.description_quality_score = ScoringService.calculer_score_description(
            db_report.description or ""
        )
    elif db_report.description_quality_score is None:
        db_report.description_quality_score = 0

    # 2. Calculer les points pour ce signalement
    points_calcules = ScoringService.calculer_points_signalement(db_report, db_report.user)
    
    # 3. Ajouter les points au citoyen (uniquement si > 0)
    if points_calcules['total'] > 0:
        citoyen = db_report.user
        citoyen.points = (citoyen.points or 0) + points_calcules['total']
        
        # Log pour debug
        print(f"POINTS POIDS - User {citoyen.id}: +{points_calcules['total']} pts "
              f"(report {db_report.id})")
        print(f"  Détail: {points_calcules['details']}")

    db.commit()
    db.refresh(db_report)

    # Ajouter les points calculés à la réponse (non stocké, juste pour feedback)
    setattr(db_report, '_points_earned', points_calcules['total'])
    setattr(db_report, '_points_details', points_calcules['details'])

    return db_report


@router.post("/", response_model=schemas.ReportResponse)
def create_report(
    latitude: float = Form(...),
    longitude: float = Form(...),
    description: Optional[str] = Form(None),
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Signaler un déchet.
    MODIFIÉ: Upload sur Cloudinary et calcul automatique du score de qualité de description.
    """
    import cloudinary.uploader

    # Générer un nom unique pour l'image
    file_extension = photo.filename.split('.')[-1] if '.' in photo.filename else 'jpg'
    unique_public_id = f"reports/{uuid.uuid4()}"

    try:
        # Upload sur Cloudinary
        upload_result = cloudinary.uploader.upload(
            photo.file,
            public_id=unique_public_id,
            folder="reports"
        )
        image_url = upload_result['secure_url']  # URL publique Cloudinary
        public_id = upload_result.get('public_id')  # Pour suppression future si nécessaire
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Échec de l'upload de l'image: {str(e)}")

    if not image_url:
        raise HTTPException(status_code=400, detail="L'image est requise")

    # Créer l'objet Report
    db_report = models.Report(
        latitude=latitude,
        longitude=longitude,
        description=description,
        image_url=image_url,
        cloudinary_public_id=public_id,  # nouveau champ optionnel pour Cloudinary
        user_id=current_user.id,
        status=models.ReportStatus.PENDING
    )

    db.add(db_report)
    db.commit()
    db.refresh(db_report)

    # ========== NOUVEAU: Calcul du score de description ==========
    if description:
        score = ScoringService.calculer_score_description(description)
        db_report.description_quality_score = score
        db.add(db_report)
        db.commit()
        db.refresh(db_report)
        print(f"SCORE DESCRIPTION - Report {db_report.id}: {score}/30")
    # ============================================================

    return db_report



@router.put("/{report_id}", response_model=schemas.ReportResponse)
def update_report_status(
    report_id: int,
    status_update: schemas.ReportStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Permet au ramasseur de prendre la mission ou de marquer "Terminé".
    """
    db_report = db.query(models.Report).filter(models.Report.id == report_id).first()

    if not db_report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")

    # Vérification des permissions : Seuls les agents peuvent modifier
    user_role = get_user_role(current_user)
    agent_roles = ["collector", "ramasseur", "supervisor", "superviseur",
                   "coordinator", "coordinateur", "admin", "administrateur"]

    if user_role not in agent_roles:
        raise HTTPException(
            status_code=403,
            detail="Seuls les agents peuvent modifier le statut d'un signalement"
        )

    # Vérification du périmètre géographique
    # Exception pour l'administrateur et le coordinateur qui peuvent modifier partout
    if user_role not in ["admin", "administrateur", "coordinator", "coordinateur"]:
        if current_user.commune and db_report.user.commune:
            if current_user.commune.lower() != db_report.user.commune.lower():
                raise HTTPException(
                    status_code=403,
                    detail="Ce signalement n'est pas dans votre zone de responsabilité"
                )

    # Mise à jour du statut
    new_status = status_update.status.value

    # Si on passe à IN_PROGRESS sans collector_id, utiliser l'utilisateur courant
    if new_status == "IN_PROGRESS" and not status_update.collector_id:
        db_report.collector_id = current_user.id

    # Si on passe un collector_id, on l'assigne
    if status_update.collector_id:
        db_report.collector_id = status_update.collector_id

    # Gestion spéciale pour ASSIGNED
    if new_status == "ASSIGNED":
        if not status_update.collector_id:
            raise HTTPException(
                status_code=400,
                detail="Un collector_id est requis pour assigner un signalement"
            )
        db_report.collector_id = status_update.collector_id

    # Si on marque comme COMPLETED via l'ancienne méthode
    if new_status == "COMPLETED":
        # Pour compatibilité avec l'ancien système
        db_report.resolved_at = datetime.utcnow()
        # Note: Pas de photo de confirmation dans l'ancien système

    db_report.status = new_status

    # Mettre à jour le last_action
    db_report.last_action = "status_updated"
    db_report.last_action_at = datetime.utcnow()

    db.commit()
    db.refresh(db_report)
    return db_report


@router.get("/{report_id}", response_model=schemas.ReportResponse)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Récupère un signalement spécifique.
    """
    db_report = db.query(models.Report)\
        .filter(models.Report.id == report_id)\
        .first()

    if not db_report:
        raise HTTPException(status_code=404, detail="Signalement non trouvé")

    # Vérification des permissions selon la hiérarchie
    user_role = get_user_role(current_user)

    if user_role in ["citizen", "citoyen"]:
        # Citoyen ne peut voir que ses propres signalements
        if db_report.user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Vous n'avez pas le droit de voir ce signalement"
            )

    elif user_role in ["ramasseur", "collector", "superviseur", "supervisor"]:
        # Agents ne peuvent voir que les signalements de leur commune
        if current_user.commune and db_report.user.commune:
            if current_user.commune.lower() != db_report.user.commune.lower():
                raise HTTPException(
                    status_code=403,
                    detail="Ce signalement n'est pas dans votre zone de responsabilité"
                )

    elif user_role in ["coordinateur", "coordinator"]:
        # MODIFICATION: Coordinateur peut voir TOUS les signalements
        # Pas de restriction géographique
        pass

    # Administrateur peut tout voir

    return db_report


# ==================== NOUVELLES ROUTES UTILITAIRES ====================

@router.get("/{report_id}/details", response_model=schemas.ReportDetail)
def get_report_details(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Récupère les détails complets d'un signalement (incluant les nouvelles données).
    MODIFIÉ: Ajout de weight_verifier dans les relations.
    """
    db_report = db.query(models.Report)\
        .options(
            joinedload(models.Report.user),
            joinedload(models.Report.collector),
            joinedload(models.Report.weight_verifier)  # NOUVEAU
        )\
        .filter(models.Report.id == report_id)\
        .first()

    if not db_report:
        raise HTTPException(status_code=404, detail="Signalement non trouvé")

    # Vérification des permissions selon la hiérarchie
    user_role = get_user_role(current_user)

    if user_role in ["citizen", "citoyen"]:
        # Citoyen ne peut voir que ses propres signalements
        if db_report.user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Vous n'avez pas le droit de voir ce signalement"
            )

    elif user_role in ["ramasseur", "collector", "superviseur", "supervisor"]:
        # Agents ne peuvent voir que les signalements de leur commune
        if current_user.commune and db_report.user.commune:
            if current_user.commune.lower() != db_report.user.commune.lower():
                raise HTTPException(
                    status_code=403,
                    detail="Ce signalement n'est pas dans votre zone de responsabilité"
                )

    elif user_role in ["coordinateur", "coordinator"]:
        # Coordinateur peut voir TOUS les signalements
        pass

    # Administrateur peut tout voir

    return db_report


@router.get("/collector/{collector_id}/stats")
def get_collector_stats(
    collector_id: int,
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Statistiques pour un ramasseur spécifique.
    MODIFIÉ: Ajout du poids total collecté.
    """
    user_role = get_user_role(current_user)

    # Vérifier les permissions
    if user_role not in ["ramasseur", "collector", "superviseur", "supervisor",
                         "coordinateur", "coordinator", "admin", "administrateur"]:
        raise HTTPException(status_code=403, detail="Accès réservé")

    # Si c'est un ramasseur, vérifier qu'il consulte ses propres stats
    if user_role in ["ramasseur", "collector"] and collector_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Vous ne pouvez voir que vos propres statistiques"
        )

    # Calculer la date de début
    start_date = datetime.utcnow() - timedelta(days=days)

    # Requête pour les statistiques
    stats = db.query(
        func.count(models.Report.id).label('total'),
        func.sum(
            case(
                (models.Report.status == "COMPLETED", 1),
                else_=0
            )
        ).label('completed'),
        func.sum(
            case(
                (models.Report.status == "AWAITING_CONFIRMATION", 1),
                else_=0
            )
        ).label('awaiting_confirmation'),
        func.sum(
            case(
                (models.Report.status == "DISPUTED", 1),
                else_=0
            )
        ).label('disputed'),
        func.sum(
            case(
                (models.Report.status == "IN_PROGRESS", 1),
                else_=0
            )
        ).label('in_progress'),
        # ========== NOUVEAU: Poids total collecté ==========
        func.coalesce(func.sum(models.Report.weight_kg), 0).label('total_weight')
        # =================================================
    )\
    .filter(
        models.Report.collector_id == collector_id,
        models.Report.created_at >= start_date
    )\
    .first()

    # Récupérer le dernier signalement traité
    last_report = db.query(models.Report)\
        .filter(models.Report.collector_id == collector_id)\
        .order_by(models.Report.last_action_at.desc())\
        .first()

    return {
        "collector_id": collector_id,
        "period_days": days,
        "stats": {
            "total": stats.total or 0,
            "completed": stats.completed or 0,
            "awaiting_confirmation": stats.awaiting_confirmation or 0,
            "disputed": stats.disputed or 0,
            "in_progress": stats.in_progress or 0,
            # ========== NOUVEAU CHAMP ==========
            "total_weight_kg": float(stats.total_weight or 0),
            # ===================================
            "completion_rate": ((stats.completed or 0) / (stats.total or 1)) * 100,
            "confirmation_rate": ((stats.completed or 0) / ((stats.completed or 0) + (stats.disputed or 0) + 1)) * 100
        },
        "last_action": {
            "report_id": last_report.id if last_report else None,
            "status": last_report.status if last_report else None,
            "last_action": last_report.last_action if last_report else None,
            "last_action_at": last_report.last_action_at if last_report else None
        },
        "timestamp": datetime.utcnow().isoformat()
    }


# ==================== NOUVEAUX ENDPOINTS ANALYTIQUES ====================

@router.get("/analytics/citizen-ranking")
def get_citizen_ranking(
    commune: Optional[str] = Query(None),
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    NOUVEAU - Classement des citoyens par points et poids collecté.
    Accessible aux superviseurs, coordinateurs et admins.
    """
    user_role = get_user_role(current_user)
    
    if user_role not in ["superviseur", "supervisor", "coordinateur", "coordinator", "admin", "administrateur"]:
        raise HTTPException(status_code=403, detail="Accès réservé aux superviseurs et supérieurs")
    
    query = db.query(
        models.User.id,
        models.User.full_name,
        models.User.commune,
        models.User.quartier,
        models.User.points,
        func.count(models.Report.id).label('total_reports'),
        func.coalesce(func.sum(models.Report.weight_kg), 0).label('total_weight'),
        func.avg(models.Report.description_quality_score).label('avg_description_score')
    )\
    .join(models.Report, models.Report.user_id == models.User.id, isouter=True)\
    .filter(models.User.role == models.RoleEnum.CITOYEN)\
    .group_by(models.User.id)\
    .order_by(models.User.points.desc())
    
    if commune:
        query = query.filter(models.User.commune == commune)
    elif user_role in ["superviseur", "supervisor", "coordinateur", "coordinator"] and current_user.commune:
        query = query.filter(models.User.commune == current_user.commune)
    
    results = query.limit(limit).all()
    
    ranking = []
    for idx, row in enumerate(results, 1):
        ranking.append({
            "rank": idx,
            "user_id": row.id,
            "full_name": row.full_name,
            "commune": row.commune,
            "quartier": row.quartier,
            "points": row.points or 0,
            "total_reports": int(row.total_reports or 0),
            "total_weight_kg": float(row.total_weight or 0),
            "avg_description_score": float(row.avg_description_score or 0),
            "estimated_brouettes": int((row.total_weight or 0) / 15)  # 15kg par brouette
        })
    
    return ranking


@router.get("/analytics/weight-trends")
def get_weight_trends(
    days: int = 30,
    commune: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    NOUVEAU - Tendances du poids collecté par jour.
    Accessible aux coordinateurs et admins.
    """
    user_role = get_user_role(current_user)
    
    if user_role not in ["coordinateur", "coordinator", "admin", "administrateur"]:
        raise HTTPException(status_code=403, detail="Accès réservé aux coordinateurs et admins")
    
    start_date = datetime.utcnow() - timedelta(days=days)
    
    query = db.query(
        func.date(models.Report.created_at).label('date'),
        func.coalesce(func.sum(models.Report.weight_kg), 0).label('daily_weight'),
        func.count(models.Report.id).label('report_count')
    )\
    .filter(
        models.Report.created_at >= start_date,
        models.Report.weight_kg.isnot(None)
    )
    
    if commune:
        query = query.join(models.User, models.Report.user_id == models.User.id)\
                     .filter(models.User.commune == commune)
    elif user_role in ["coordinateur", "coordinator"] and current_user.commune:
        query = query.join(models.User, models.Report.user_id == models.User.id)\
                     .filter(models.User.commune == current_user.commune)
    
    query = query.group_by(func.date(models.Report.created_at))\
                 .order_by(func.date(models.Report.created_at))
    
    results = query.all()
    
    return [
        {
            "date": str(row.date),
            "daily_weight_kg": float(row.daily_weight),
            "report_count": int(row.report_count),
            "avg_weight_per_report": float(row.daily_weight / row.report_count) if row.report_count > 0 else 0
        }
        for row in results
    ]


@router.get("/analytics/commune-performance")
def get_commune_performance(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    NOUVEAU - Performance des communes (poids, points, taux de résolution).
    Accessible aux coordinateurs et admins.
    """
    user_role = get_user_role(current_user)
    
    if user_role not in ["coordinateur", "coordinator", "admin", "administrateur"]:
        raise HTTPException(status_code=403, detail="Accès réservé aux coordinateurs et admins")
    
    query = db.query(
        models.User.commune,
        func.count(models.Report.id).label('total_reports'),
        func.sum(
            case(
                (models.Report.status == "COMPLETED", 1),
                else_=0
            )
        ).label('completed_reports'),
        func.coalesce(func.sum(models.Report.weight_kg), 0).label('total_weight'),
        func.sum(models.User.points).label('total_points'),
        func.count(func.distinct(models.User.id)).label('citizen_count')
    )\
    .join(models.Report, models.Report.user_id == models.User.id)\
    .filter(
        models.User.role == models.RoleEnum.CITOYEN,
        models.User.commune.isnot(None)
    )\
    .group_by(models.User.commune)\
    .order_by(func.sum(models.Report.weight_kg).desc())
    
    results = query.all()
    
    performance = []
    for row in results:
        completion_rate = (row.completed_reports or 0) / (row.total_reports or 1) * 100
        weight_per_citizen = (row.total_weight or 0) / (row.citizen_count or 1)
        points_per_citizen = (row.total_points or 0) / (row.citizen_count or 1)
        
        performance.append({
            "commune": row.commune,
            "total_reports": int(row.total_reports or 0),
            "completed_reports": int(row.completed_reports or 0),
            "completion_rate": float(completion_rate),
            "total_weight_kg": float(row.total_weight or 0),
            "total_points": int(row.total_points or 0),
            "citizen_count": int(row.citizen_count or 0),
            "weight_per_citizen_kg": float(weight_per_citizen),
            "points_per_citizen": int(points_per_citizen),
            "estimated_brouettes": int((row.total_weight or 0) / 15)
        })
    
    return performance

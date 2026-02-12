# app/api/users.py
from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import os
import uuid
import aiofiles

from .. import crud, models
from ..schemas.user import (
    User, 
    UserUpdate, 
    RoleAssignment, 
    ZoneAssignment, 
    UserStats, 
    ProfilePictureUpdate,
    # ========== NOUVEAUX SCHÉMAS ==========
    UserPointsResponse,
    RewardThreshold,
    NextReward,
    UserExtendedStats,
    PaginatedUserResponse
)
from ..database import get_db
from ..api.deps import get_current_user
from ..services.scoring_service import ScoringService  # NOUVEAU SERVICE

router = APIRouter()


def can_manage_users(current_user: models.User, target_user: models.User = None) -> bool:
    """
    Vérifie si l'utilisateur courant peut gérer d'autres utilisateurs.
    """
    # Si pas de target_user, on vérifie juste si l'utilisateur a des permissions de gestion
    if target_user is None:
        return current_user.role in [
            models.RoleEnum.SUPERVISEUR,
            models.RoleEnum.COORDINATEUR,
            models.RoleEnum.ADMINISTRATEUR
        ]

    # Même utilisateur
    if current_user.id == target_user.id:
        return True

    # Hiérarchie des rôles
    hierarchy = {
        models.RoleEnum.CITOYEN: 0,
        models.RoleEnum.RAMASSEUR: 1,
        models.RoleEnum.SUPERVISEUR: 2,
        models.RoleEnum.COORDINATEUR: 3,
        models.RoleEnum.ADMINISTRATEUR: 4
    }

    current_level = hierarchy.get(current_user.role, 0)
    target_level = hierarchy.get(target_user.role, 0)

    # L'utilisateur doit avoir un niveau supérieur
    if current_level <= target_level:
        return False

    # Vérifications géographiques selon le rôle
    if current_user.role == models.RoleEnum.SUPERVISEUR:
        # Superviseur peut gérer les RAMASSEURS de sa commune
        return (
            current_user.commune == target_user.commune and
            target_user.role == models.RoleEnum.RAMASSEUR
        )

    elif current_user.role == models.RoleEnum.COORDINATEUR:
        # MODIFICATION: Coordinateur peut gérer TOUS les utilisateurs de sa commune (sauf admins)
        return (
            current_user.commune == target_user.commune and
            target_user.role != models.RoleEnum.ADMINISTRATEUR
        )

    elif current_user.role == models.RoleEnum.ADMINISTRATEUR:
        # Administrateur peut gérer tout le monde
        return True

    return False


def can_view_users(current_user: models.User) -> bool:
    """
    Vérifie si l'utilisateur peut voir d'autres utilisateurs.
    """
    return current_user.role in [
        models.RoleEnum.SUPERVISEUR,
        models.RoleEnum.COORDINATEUR,
        models.RoleEnum.ADMINISTRATEUR
    ]


def get_user_role(user):
    """Extrait la valeur du rôle de l'utilisateur - Compatibilité avec reports.py"""
    if not user or not user.role:
        return ""

    if hasattr(user.role, 'value'):
        return user.role.value.lower()

    role_str = str(user.role).lower()
    if role_str.startswith('roleenum.'):
        role_str = role_str[9:]

    return role_str


# Configuration du service de fichiers
UPLOAD_DIR = "static/profile_pictures"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE_MB = 5

# Créer le dossier s'il n'existe pas
os.makedirs(UPLOAD_DIR, exist_ok=True)


def validate_file(file: UploadFile) -> tuple[bool, str]:
    """Valider le fichier uploadé"""
    # Vérifier la taille (max 5MB)
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    if file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        return False, f"Fichier trop volumineux. Maximum: {MAX_FILE_SIZE_MB}MB"

    # Vérifier l'extension
    filename = file.filename or ""
    file_ext = os.path.splitext(filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return False, f"Extension non autorisée. Permises: {', '.join(ALLOWED_EXTENSIONS)}"

    return True, ""


async def save_profile_picture(file: UploadFile, user_id: int) -> str:
    """Sauvegarder la photo de profil et retourner le chemin relatif"""
    filename = file.filename or ""
    file_ext = os.path.splitext(filename)[1].lower()
    unique_filename = f"user_{user_id}_{uuid.uuid4().hex}{file_ext}"
    filepath = os.path.join(UPLOAD_DIR, unique_filename)

    async with aiofiles.open(filepath, 'wb') as out_file:
        content = await file.read()
        await out_file.write(content)

    return f"/{filepath}"


def delete_old_picture(current_picture_url: Optional[str]) -> bool:
    """Supprimer l'ancienne photo de profil"""
    if current_picture_url and current_picture_url.startswith(f"/{UPLOAD_DIR}/"):
        try:
            filepath = current_picture_url[1:]
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
        except Exception:
            pass
    return False


# ==================== ENDPOINTS EXISTANTS PRÉSERVÉS ====================

@router.get("/me", response_model=User)
def read_user_me(current_user: models.User = Depends(get_current_user)):
    """
    Get current user.
    """
    return current_user


@router.get("/me/profile-picture", response_model=User)
def get_profile_picture(
    current_user: models.User = Depends(get_current_user)
):
    """
    Récupérer les informations de l'utilisateur courant, incluant la photo de profil.
    Compatible avec l'endpoint existant /me.
    """
    return current_user


@router.patch("/me/profile-picture", response_model=User)
def update_profile_picture(
    update_data: ProfilePictureUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Mettre à jour uniquement la photo de profil de l'utilisateur connecté.
    """
    if update_data.profile_picture is not None:
        if update_data.profile_picture and not update_data.profile_picture.startswith(('http://', 'https://', '/')):
            raise HTTPException(
                status_code=400,
                detail="L'URL de la photo de profil doit être une URL valide"
            )

        current_user.profile_picture = update_data.profile_picture
        current_user.updated_at = datetime.utcnow()

    elif update_data.profile_picture is None:
        current_user.profile_picture = None
        current_user.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(current_user)

    return current_user


@router.delete("/me/profile-picture", response_model=User)
def delete_profile_picture(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Supprimer la photo de profil de l'utilisateur connecté.
    """
    if current_user.profile_picture:
        delete_old_picture(current_user.profile_picture)

    current_user.profile_picture = None
    current_user.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(current_user)

    return current_user


@router.post("/me/upload-profile-picture", response_model=User)
async def upload_profile_picture(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Uploader une nouvelle photo de profil.
    """
    is_valid, error_msg = validate_file(file)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    if current_user.profile_picture:
        delete_old_picture(current_user.profile_picture)

    try:
        picture_url = await save_profile_picture(file, current_user.id)

        current_user.profile_picture = picture_url
        current_user.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(current_user)

        return current_user

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Erreur lors du traitement de l'image: {str(e)}"
        )


@router.get("/", response_model=List[User])
def read_users(
    skip: int = 0,
    limit: int = 100,
    commune: Optional[str] = Query(None),
    quartier: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Retrieve users with hierarchical filtering.
    """
    if not can_view_users(current_user):
        query = db.query(models.User).filter(models.User.id == current_user.id)
        users = query.all()
        return users

    query = db.query(models.User)

    if search:
        search_filter = or_(
            models.User.full_name.ilike(f"%{search}%"),
            models.User.phone.ilike(f"%{search}%"),
            models.User.email.ilike(f"%{search}%")
        )
        query = query.filter(search_filter)

    if commune:
        query = query.filter(models.User.commune == commune)

    if quartier:
        query = query.filter(models.User.quartier == quartier)

    if role:
        try:
            role_enum = models.RoleEnum(role)
            query = query.filter(models.User.role == role_enum)
        except ValueError:
            pass

    if is_active is not None:
        query = query.filter(models.User.is_active == is_active)

    # ========== FILTRAGE HIÉRARCHIQUE SELON LE RÔLE ==========
    if current_user.role == models.RoleEnum.CITOYEN:
        query = query.filter(models.User.id == current_user.id)

    elif current_user.role == models.RoleEnum.RAMASSEUR:
        query = query.filter(models.User.id == current_user.id)

    elif current_user.role == models.RoleEnum.SUPERVISEUR:
        if not current_user.commune:
            query = query.filter(models.User.id == current_user.id)
        else:
            query = query.filter(
                models.User.commune == current_user.commune,
                models.User.role == models.RoleEnum.RAMASSEUR
            )

    elif current_user.role == models.RoleEnum.COORDINATEUR:
        if not current_user.commune:
            query = query.filter(models.User.id == current_user.id)
        else:
            query = query.filter(
                models.User.commune == current_user.commune
            )

    elif current_user.role == models.RoleEnum.ADMINISTRATEUR:
        pass

    else:
        query = query.filter(models.User.id == current_user.id)

    query = query.order_by(models.User.created_at.desc())
    users = query.offset(skip).limit(limit).all()

    return users


@router.get("/stats", response_model=UserStats)
def get_user_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Get user statistics.
    """
    if not can_view_users(current_user):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de voir les statistiques"
        )

    query = db.query(models.User)

    if current_user.role == models.RoleEnum.SUPERVISEUR:
        if current_user.commune:
            query = query.filter(
                models.User.commune == current_user.commune,
                models.User.role == models.RoleEnum.RAMASSEUR
            )
        else:
            query = query.filter(models.User.id == current_user.id)

    elif current_user.role == models.RoleEnum.COORDINATEUR:
        if current_user.commune:
            query = query.filter(
                models.User.commune == current_user.commune
            )
        else:
            query = query.filter(models.User.id == current_user.id)

    elif current_user.role == models.RoleEnum.ADMINISTRATEUR:
        pass

    else:
        query = query.filter(models.User.id == current_user.id)

    total = query.count()

    by_role = {}
    for role in models.RoleEnum:
        count = query.filter(models.User.role == role).count()
        by_role[role.value] = count

    by_commune = {}
    communes = db.query(models.User.commune).distinct().all()
    for (commune,) in communes:
        if commune:
            count = query.filter(models.User.commune == commune).count()
            by_commune[commune] = count

    active_count = query.filter(models.User.is_active == True).count()
    inactive_count = query.filter(models.User.is_active == False).count()
    verified_count = query.filter(models.User.is_verified == True).count()
    unverified_count = query.filter(models.User.is_verified == False).count()

    by_status = {
        "active": active_count,
        "inactive": inactive_count,
        "verified": verified_count,
        "unverified": unverified_count
    }

    return {
        "total": total,
        "by_role": by_role,
        "by_commune": by_commune,
        "by_status": by_status
    }


@router.put("/{user_id}/role", response_model=User)
def update_user_role(
    user_id: int,
    role_update: RoleAssignment,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Update a user's role (admin/coordinator/supervisor only).
    """
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    if not can_manage_users(current_user, target_user):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de modifier le rôle de cet utilisateur"
        )

    try:
        new_role = models.RoleEnum(role_update.role)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Rôle invalide: {role_update.role}"
        )

    hierarchy = {
        models.RoleEnum.CITOYEN: 0,
        models.RoleEnum.RAMASSEUR: 1,
        models.RoleEnum.SUPERVISEUR: 2,
        models.RoleEnum.COORDINATEUR: 3,
        models.RoleEnum.ADMINISTRATEUR: 4
    }

    current_level = hierarchy.get(current_user.role, 0)
    target_current_level = hierarchy.get(target_user.role, 0)
    new_level = hierarchy.get(new_role, 0)

    if current_user.id == user_id:
        raise HTTPException(
            status_code=400,
            detail="Vous ne pouvez pas changer votre propre rôle"
        )

    if current_level <= target_current_level:
        raise HTTPException(
            status_code=403,
            detail="Vous ne pouvez pas modifier un utilisateur de rang égal ou supérieur"
        )

    if current_level <= new_level:
        raise HTTPException(
            status_code=403,
            detail="Vous ne pouvez pas attribuer un rôle égal ou supérieur au vôtre"
        )

    if current_user.role == models.RoleEnum.SUPERVISEUR:
        if new_role not in [models.RoleEnum.CITOYEN, models.RoleEnum.RAMASSEUR]:
            raise HTTPException(
                status_code=403,
                detail="Le superviseur ne peut que modifier les rôles citoyen ↔ ramasseur"
            )

        if current_user.commune != target_user.commune:
            raise HTTPException(
                status_code=403,
                detail="Vous ne pouvez modifier que les utilisateurs de votre commune"
            )

    elif current_user.role == models.RoleEnum.COORDINATEUR:
        if new_role in [models.RoleEnum.COORDINATEUR, models.RoleEnum.ADMINISTRATEUR]:
            raise HTTPException(
                status_code=403,
                detail="Le coordinateur ne peut pas créer d'autres coordinateurs ou administrateurs"
            )

        if current_user.commune != target_user.commune:
            raise HTTPException(
                status_code=403,
                detail="Vous ne pouvez modifier que les utilisateurs de votre commune"
            )

    elif current_user.role == models.RoleEnum.ADMINISTRATEUR:
        if new_role == models.RoleEnum.ADMINISTRATEUR and current_user.id != 1:
            raise HTTPException(
                status_code=403,
                detail="Seul le super administrateur peut créer d'autres administrateurs"
            )

    target_user.role = new_role
    target_user.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(target_user)

    return target_user


@router.put("/{user_id}/status", response_model=User)
def update_user_status(
    user_id: int,
    status_update: UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Activate/deactivate a user (admin/coordinator/supervisor).
    """
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    if not can_manage_users(current_user, target_user):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de modifier cet utilisateur"
        )

    if current_user.id == user_id:
        raise HTTPException(
            status_code=400,
            detail="Vous ne pouvez pas vous désactiver vous-même"
        )

    if status_update.is_active is not None:
        target_user.is_active = status_update.is_active

    if status_update.is_verified is not None:
        target_user.is_verified = status_update.is_verified

    target_user.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(target_user)

    return target_user


@router.put("/{user_id}/zone", response_model=User)
def update_user_zone(
    user_id: int,
    zone_update: ZoneAssignment,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Update a user's assigned zone (commune/quartier).
    """
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    if not can_manage_users(current_user, target_user):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas la permission de modifier la zone de cet utilisateur"
        )

    if current_user.role == models.RoleEnum.SUPERVISEUR:
        if zone_update.commune != current_user.commune:
            raise HTTPException(
                status_code=403,
                detail="Le superviseur ne peut assigner que sa propre commune"
            )

    elif current_user.role == models.RoleEnum.COORDINATEUR:
        if zone_update.commune != current_user.commune:
            raise HTTPException(
                status_code=403,
                detail="Le coordinateur ne peut assigner que sa propre commune"
            )

    if zone_update.commune:
        target_user.commune = zone_update.commune

    if zone_update.quartier is not None:
        target_user.quartier = zone_update.quartier

    target_user.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(target_user)

    return target_user


@router.get("/search", response_model=List[User])
def search_users(
    q: str = Query(..., min_length=2, description="Terme de recherche"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Rechercher des utilisateurs par nom, téléphone, ou email.
    """
    if not can_view_users(current_user):
        query = db.query(models.User).filter(
            models.User.id == current_user.id,
            or_(
                models.User.full_name.ilike(f"%{q}%"),
                models.User.phone.ilike(f"%{q}%"),
                models.User.email.ilike(f"%{q}%")
            )
        )
        return query.limit(1).all()

    query = db.query(models.User).filter(
        or_(
            models.User.full_name.ilike(f"%{q}%"),
            models.User.phone.ilike(f"%{q}%"),
            models.User.email.ilike(f"%{q}%")
        )
    )

    if current_user.role == models.RoleEnum.SUPERVISEUR:
        if current_user.commune:
            query = query.filter(
                models.User.commune == current_user.commune,
                models.User.role == models.RoleEnum.RAMASSEUR
            )
        else:
            query = query.filter(models.User.id == current_user.id)

    elif current_user.role == models.RoleEnum.COORDINATEUR:
        if current_user.commune:
            query = query.filter(
                models.User.commune == current_user.commune
            )
        else:
            query = query.filter(models.User.id == current_user.id)

    return query.limit(20).all()


@router.get("/by-commune/{commune}", response_model=List[User])
def get_users_by_commune(
    commune: str,
    role: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Obtenir les utilisateurs d'une commune spécifique.
    """
    if current_user.role not in [models.RoleEnum.ADMINISTRATEUR, models.RoleEnum.COORDINATEUR]:
        raise HTTPException(
            status_code=403,
            detail="Seul l'administrateur ou le coordinateur peut voir les utilisateurs d'autres communes"
        )

    if current_user.role == models.RoleEnum.COORDINATEUR and commune != current_user.commune:
        raise HTTPException(
            status_code=403,
            detail="Le coordinateur ne peut voir que les utilisateurs de sa propre commune"
        )

    query = db.query(models.User).filter(models.User.commune == commune)

    if role:
        try:
            role_enum = models.RoleEnum(role)
            query = query.filter(models.User.role == role_enum)
        except ValueError:
            pass

    return query.order_by(models.User.created_at.desc()).all()


# ==================== NOUVEAUX ENDPOINTS POINTS & RÉCOMPENSES ====================

@router.get("/me/points", response_model=UserPointsResponse)
def get_my_points_and_rewards(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    NOUVEAU - Retourne les points du citoyen, les seuils de récompense atteints,
    l'éligibilité au tirage au sort, et le poids total collecté.
    """
    points_actuels = current_user.points or 0
    
    total_reports = db.query(models.Report)\
        .filter(models.Report.user_id == current_user.id)\
        .count()
    
    total_weight = db.query(
            func.coalesce(func.sum(models.Report.weight_kg), 0)
        )\
        .filter(models.Report.user_id == current_user.id)\
        .scalar() or 0.0

    seuils_atteints = ScoringService.get_seuils_atteints(points_actuels)
    prochain_seuil = ScoringService.get_prochain_seuil(points_actuels)
    eligible = ScoringService.is_eligible_for_lottery(current_user)

    return {
        "user_id": current_user.id,
        "full_name": current_user.full_name,
        "points": points_actuels,
        "subscription_active": current_user.subscription_active,
        "eligible_lottery": eligible,
        "rewards_unlocked": seuils_atteints,
        "next_reward": prochain_seuil,
        "total_reports": total_reports,
        "total_weight_kg": float(total_weight)
    }


@router.get("/me/stats/extended", response_model=UserExtendedStats)
def get_my_extended_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    NOUVEAU - Statistiques détaillées pour le citoyen (graphiques, historique).
    """
    from sqlalchemy import extract
    
    total_reports = db.query(models.Report)\
        .filter(models.Report.user_id == current_user.id)\
        .count()
    
    completed_reports = db.query(models.Report)\
        .filter(
            models.Report.user_id == current_user.id,
            models.Report.status == models.ReportStatus.COMPLETED
        )\
        .count()
    
    pending_reports = db.query(models.Report)\
        .filter(
            models.Report.user_id == current_user.id,
            models.Report.status == models.ReportStatus.PENDING
        )\
        .count()
    
    total_weight = db.query(
            func.coalesce(func.sum(models.Report.weight_kg), 0)
        )\
        .filter(models.Report.user_id == current_user.id)\
        .scalar() or 0.0
    
    subscription_months = db.query(models.Subscription)\
        .filter(
            models.Subscription.user_id == current_user.id,
            models.Subscription.is_active == True
        )\
        .count()
    
    reports_by_month = db.query(
        extract('year', models.Report.created_at).label('year'),
        extract('month', models.Report.created_at).label('month'),
        func.count(models.Report.id).label('count'),
        func.coalesce(func.sum(models.Report.weight_kg), 0).label('weight')
    )\
    .filter(models.Report.user_id == current_user.id)\
    .group_by('year', 'month')\
    .order_by('year', 'month')\
    .limit(12)\
    .all()
    
    return {
        "total_reports": total_reports,
        "completed_reports": completed_reports,
        "pending_reports": pending_reports,
        "points_earned": current_user.points or 0,
        "total_weight_collected": float(total_weight),
        "subscription_months": subscription_months,
        "reports_by_month": [
            {
                "month": f"{int(m)}-{int(y)}",
                "reports": int(c),
                "weight_kg": float(w)
            }
            for y, m, c, w in reports_by_month
        ]
    }


@router.get("/top/citizens")
def get_top_citizens(
    limit: int = 10,
    commune: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    NOUVEAU - Classement des citoyens par points (pour dashboard admin/superviseur).
    """
    user_role = get_user_role(current_user)
    
    if user_role not in ["admin", "administrateur", "coordinator", "coordinateur", "superviseur", "supervisor"]:
        raise HTTPException(
            status_code=403, 
            detail="Accès réservé aux superviseurs et supérieurs"
        )
    
    query = db.query(models.User)\
        .filter(models.User.role == models.RoleEnum.CITOYEN)\
        .order_by(models.User.points.desc())
    
    if commune:
        query = query.filter(models.User.commune == commune)
    elif user_role in ["coordinator", "coordinateur", "superviseur", "supervisor"] and current_user.commune:
        query = query.filter(models.User.commune == current_user.commune)
    
    top_citizens = query.limit(limit).all()
    
    result = []
    for idx, citizen in enumerate(top_citizens, 1):
        total_weight = db.query(
                func.coalesce(func.sum(models.Report.weight_kg), 0)
            )\
            .filter(models.Report.user_id == citizen.id)\
            .scalar() or 0.0
        
        result.append({
            "rank": idx,
            "id": citizen.id,
            "full_name": citizen.full_name,
            "commune": citizen.commune,
            "points": citizen.points or 0,
            "total_weight_kg": float(total_weight),
            "subscription_active": citizen.subscription_active,
            "is_verified": citizen.is_verified
        })
    
    return result


@router.get("/{user_id}/points/history")
def get_user_points_history(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    NOUVEAU - Historique des points gagnés par un citoyen.
    """
    user_role = get_user_role(current_user)
    
    if current_user.id != user_id and user_role not in ["admin", "administrateur", "coordinator", "coordinateur", "superviseur", "supervisor"]:
        raise HTTPException(
            status_code=403, 
            detail="Vous ne pouvez voir que votre propre historique"
        )
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    reports = db.query(models.Report)\
        .filter(models.Report.user_id == user_id)\
        .order_by(models.Report.created_at.desc())\
        .limit(50)\
        .all()
    
    history = []
    
    for report in reports:
        if report.weight_kg is not None or report.description_quality_score is not None:
            points_data = ScoringService.calculer_points_signalement(report, user)
            if points_data['total'] > 0:
                history.append({
                    "date": report.created_at,
                    "report_id": report.id,
                    "points": points_data['total'],
                    "details": points_data['details'],
                    "weight_kg": report.weight_kg,
                    "description_score": report.description_quality_score,
                    "status": report.status,
                    "type": "signalement"
                })
    
    subscriptions = db.query(models.Subscription)\
        .filter(
            models.Subscription.user_id == user_id,
            models.Subscription.is_active == True
        )\
        .order_by(models.Subscription.start_date.desc())\
        .all()
    
    for sub in subscriptions:
        history.append({
            "date": sub.start_date,
            "type": "abonnement",
            "points": ScoringService.POINTS_ABONNEMENT_MENSUEL,
            "details": {"abonnement": ScoringService.POINTS_ABONNEMENT_MENSUEL},
            "subscription_id": sub.id
        })
    
    history.sort(key=lambda x: x['date'], reverse=True)
    
    return {
        "user_id": user_id,
        "full_name": user.full_name,
        "total_points": user.points or 0,
        "history": history[:50]
    }


@router.get("/citizens/eligible-lottery")
def get_citizens_eligible_for_lottery(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    NOUVEAU - Liste des citoyens éligibles au tirage au sort (admin/coordinateur).
    """
    user_role = get_user_role(current_user)
    
    if user_role not in ["admin", "administrateur", "coordinator", "coordinateur"]:
        raise HTTPException(
            status_code=403, 
            detail="Accès réservé à l'administrateur et au coordinateur"
        )
    
    seuil_minimum = min(ScoringService.SEUILS_TIRAGE.keys())
    
    query = db.query(models.User)\
        .filter(
            models.User.role == models.RoleEnum.CITOYEN,
            models.User.points >= seuil_minimum
        )\
        .order_by(models.User.points.desc())
    
    if user_role in ["coordinator", "coordinateur"] and current_user.commune:
        query = query.filter(models.User.commune == current_user.commune)
    
    citizens = query.all()
    
    result = []
    for citizen in citizens:
        total_weight = db.query(
                func.coalesce(func.sum(models.Report.weight_kg), 0)
            )\
            .filter(models.Report.user_id == citizen.id)\
            .scalar() or 0.0
        
        result.append({
            "id": citizen.id,
            "full_name": citizen.full_name,
            "commune": citizen.commune,
            "points": citizen.points or 0,
            "total_weight_kg": float(total_weight),
            "subscription_active": citizen.subscription_active,
            "rewards_unlocked": ScoringService.get_seuils_atteints(citizen.points or 0)
        })
    
    return {
        "total_eligible": len(result),
        "seuil_minimum": seuil_minimum,
        "citizens": result[:100]  # Limiter à 100 pour performance
    }


@router.post("/{user_id}/points/add")
def add_manual_points(
    user_id: int,
    points_data: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    NOUVEAU - Ajouter manuellement des points à un citoyen (admin/coordinateur uniquement).
    """
    user_role = get_user_role(current_user)
    
    if user_role not in ["admin", "administrateur", "coordinator", "coordinateur"]:
        raise HTTPException(
            status_code=403, 
            detail="Accès réservé à l'administrateur et au coordinateur"
        )
    
    points = points_data.get("points", 0)
    reason = points_data.get("reason", "Ajustement manuel")
    
    if points <= 0:
        raise HTTPException(
            status_code=400, 
            detail="Le nombre de points doit être positif"
        )
    
    target_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    if target_user.role != models.RoleEnum.CITOYEN:
        raise HTTPException(
            status_code=400, 
            detail="Seuls les citoyens peuvent recevoir des points"
        )
    
    target_user.points = (target_user.points or 0) + points
    target_user.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(target_user)
    
    return {
        "message": f"{points} points ajoutés à {target_user.full_name}",
        "user_id": user_id,
        "points_added": points,
        "total_points": target_user.points,
        "reason": reason
    }


@router.get("/communes/ranking")
def get_communes_ranking(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    NOUVEAU - Classement des communes par points citoyens cumulés et poids collecté.
    """
    user_role = get_user_role(current_user)
    
    if user_role not in ["admin", "administrateur", "coordinator", "coordinateur"]:
        raise HTTPException(
            status_code=403, 
            detail="Accès réservé à l'administrateur et au coordinateur"
        )
    
    ranking = db.query(
        models.User.commune,
        func.sum(models.User.points).label('total_points'),
        func.count(models.User.id).label('citizen_count'),
        func.sum(
            func.coalesce(func.sum(models.Report.weight_kg), 0)
        ).label('total_weight')
    )\
    .join(models.Report, models.Report.user_id == models.User.id, isouter=True)\
    .filter(
        models.User.role == models.RoleEnum.CITOYEN,
        models.User.commune.isnot(None)
    )\
    .group_by(models.User.commune)\
    .order_by(func.sum(models.User.points).desc())\
    .all()
    
    result = []
    for idx, (commune, points, count, weight) in enumerate(ranking, 1):
        result.append({
            "rank": idx,
            "commune": commune,
            "total_points": int(points or 0),
            "citizen_count": int(count or 0),
            "total_weight_kg": float(weight or 0),
            "average_points_per_citizen": int((points or 0) / (count or 1))
        })
    
    return result

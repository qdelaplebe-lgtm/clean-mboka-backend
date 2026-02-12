# app/schemas/report.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict
from enum import Enum

# Enum pour les statuts - doit correspondre à votre modèle
class ReportStatusEnum(str, Enum):
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    COMPLETED = "COMPLETED"
    DISPUTED = "DISPUTED"

# ========== NOUVEAU SCHÉMA POUR POIDS ==========
class ReportWeightUpdate(BaseModel):
    """Schéma pour mettre à jour le poids d'un signalement"""
    weight_kg: float = Field(
        ..., 
        gt=0, 
        le=1000, 
        example=15.5, 
        description="Poids en kg vérifié par balance"
    )
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "weight_kg": 15.5
            }
        }
# ================================================

# --- NOUVEAUX SCHÉMAS POUR CONFIRMATION PHOTO ---

class ReportPhotoSubmit(BaseModel):
    """Schéma pour soumettre une photo de confirmation"""
    notes: Optional[str] = Field(
        None,
        example="Zone entièrement nettoyée",
        description="Notes optionnelles du ramasseur"
    )

    class Config:
        from_attributes = True

class CitizenConfirmation(BaseModel):
    """Schéma pour confirmation/refus par le citoyen"""
    confirmed: bool = Field(
        ...,
        example=True,
        description="True si confirmé, False si refusé"
    )
    reason: Optional[str] = Field(
        None,
        example="La zone n'a pas été entièrement nettoyée",
        description="Raison obligatoire en cas de refus"
    )
    confirmation_code: Optional[str] = Field(
        None,
        description="Code de confirmation (optionnel si authentifié)"
    )

    class Config:
        from_attributes = True

class CleanupStatusResponse(BaseModel):
    """Schéma pour réponse de statut de confirmation"""
    report_id: int = Field(..., example=1)
    status: str = Field(..., example="AWAITING_CONFIRMATION")
    has_cleanup_photo: bool = Field(..., example=True)
    cleanup_photo_url: Optional[str] = Field(None, example="/static/cleanup_123.jpg")
    photo_submitted_at: Optional[datetime] = None
    citizen_confirmed: bool = Field(default=False)
    citizen_confirmed_at: Optional[datetime] = None
    dispute_reason: Optional[str] = Field(None, example="Raison du refus")
    confirmation_deadline: Optional[datetime] = None
    awaiting_confirmation: bool = Field(..., example=True)
    can_confirm: bool = Field(..., example=True)
    confirmation_code: Optional[str] = Field(None, example="ABC123")

    class Config:
        from_attributes = True

# --- SCHÉMAS EXISTANTS MODIFIÉS AVEC NOUVEAUX CHAMPS ---

class ReportCreate(BaseModel):
    latitude: float = Field(..., example=-4.4419, description="Latitude GPS")
    longitude: float = Field(..., example=15.2663, description="Longitude GPS")
    description: Optional[str] = Field(None, example="Déchets plastiques", description="Description des déchets")

class ReportStatusUpdate(BaseModel):
    status: ReportStatusEnum = Field(..., example="PENDING", description="Nouveau statut du signalement")
    collector_id: Optional[int] = Field(None, example=1, description="ID du collecteur assigné")

class ReportUpdate(BaseModel):
    """Schéma pour mettre à jour un signalement"""
    latitude: Optional[float] = Field(None, example=-4.4419)
    longitude: Optional[float] = Field(None, example=15.2663)
    description: Optional[str] = Field(None, example="Déchets plastiques mis à jour")
    address_description: Optional[str] = Field(None, example="Nouvelle description d'adresse")
    status: Optional[ReportStatusEnum] = Field(None, example="PENDING")
    collector_id: Optional[int] = Field(None, example=1)
    # ========== NOUVEAUX CHAMPS ==========
    weight_kg: Optional[float] = Field(
        None, 
        example=15.5, 
        description="Poids en kg vérifié par balance",
        gt=0,
        le=1000
    )
    description_quality_score: Optional[int] = Field(
        None,
        example=25,
        description="Score de qualité de la description (0-30)",
        ge=0,
        le=30
    )
    # ======================================

    class Config:
        from_attributes = True

# Schéma pour les informations utilisateur simplifiées
class UserSimple(BaseModel):
    id: int
    full_name: Optional[str] = None
    phone: Optional[str] = None
    commune: Optional[str] = None
    # ========== NOUVEAUX CHAMPS ==========
    points: Optional[int] = Field(None, example=1250)
    profile_picture: Optional[str] = Field(None, example="/static/profile_pictures/user123.jpg")
    # ======================================

    class Config:
        from_attributes = True

# Schéma principal pour la liste des rapports
class ReportList(BaseModel):
    id: int = Field(..., example=1)
    latitude: float = Field(..., example=-4.4419)
    longitude: float = Field(..., example=15.2663)
    description: Optional[str] = Field(None, example="Déchets plastiques")
    address_description: Optional[str] = Field(None, example="Devant l'église Sainte-Anne")
    image_url: str = Field(..., example="/static/image.jpg")

    # ========== NOUVEAUX CHAMPS POIDS ET SCORE ==========
    weight_kg: Optional[float] = Field(None, example=15.5)
    weight_verified_at: Optional[datetime] = None
    weight_verified_by: Optional[int] = Field(None, example=2)
    description_quality_score: Optional[int] = Field(None, example=25, ge=0, le=30)
    # ===================================================

    # NOUVEAUX CHAMPS CONFIRMATION
    cleanup_photo_url: Optional[str] = Field(None, example="/static/cleanup_123.jpg")
    citizen_confirmed: bool = Field(default=False)
    citizen_confirmed_at: Optional[datetime] = None
    confirmation_code: Optional[str] = Field(None, example="ABC123")
    auto_confirmed: bool = Field(default=False)
    last_action: Optional[str] = Field(None, example="weight_recorded")
    last_action_at: Optional[datetime] = None

    status: str = Field(..., example="PENDING")
    created_at: datetime = Field(..., example="2024-01-15T10:30:00")
    resolved_at: Optional[datetime] = None
    user_id: Optional[int] = Field(None, example=1)
    collector_id: Optional[int] = Field(None, example=2)

    # Relations optionnelles
    user: Optional[UserSimple] = None
    collector: Optional[UserSimple] = None

    # Champs calculés
    @property
    def awaiting_confirmation(self):
        return self.status == "AWAITING_CONFIRMATION"

    @property
    def can_confirm(self):
        return self.status == "AWAITING_CONFIRMATION" and not self.citizen_confirmed
    
    # ========== NOUVEAU CHAMP CALCULÉ ==========
    @property
    def points_earned(self):
        """Estimation des points gagnés (calcul côté client)"""
        points = 0
        if self.description_quality_score:
            points += self.description_quality_score
        if self.weight_kg:
            points += int(self.weight_kg * 2)
        if self.citizen_confirmed and self.cleanup_photo_url:
            points += 20  # Bonus confirmation rapide
        return points
    # ===========================================

    class Config:
        from_attributes = True

# Schéma simplifié pour /my-reports
class MyReport(BaseModel):
    id: int
    latitude: float
    longitude: float
    description: Optional[str]
    address_description: Optional[str]
    image_url: str
    status: str
    created_at: datetime
    user_id: Optional[int] = None

    # ========== NOUVEAUX CHAMPS ==========
    weight_kg: Optional[float] = Field(None, example=15.5)
    description_quality_score: Optional[int] = Field(None, example=25)
    cleanup_photo_url: Optional[str] = None
    citizen_confirmed: bool = False
    citizen_confirmed_at: Optional[datetime] = None
    # ======================================

    class Config:
        from_attributes = True

class ReportResponse(BaseModel):
    id: int = Field(..., example=1)
    latitude: float = Field(..., example=-4.4419)
    longitude: float = Field(..., example=15.2663)
    description: Optional[str] = Field(None, example="Déchets plastiques")
    address_description: Optional[str] = Field(None, example="Devant l'église Sainte-Anne")
    image_url: str = Field(..., example="/static/image.jpg")
    status: str = Field(..., example="PENDING")
    created_at: datetime = Field(..., example="2024-01-15T10:30:00")
    user_id: Optional[int] = Field(None, example=1)
    collector_id: Optional[int] = Field(None, example=2)
    
    # ========== NOUVEAUX CHAMPS ==========
    weight_kg: Optional[float] = Field(None, example=15.5)
    description_quality_score: Optional[int] = Field(None, example=25)
    # ======================================

    class Config:
        from_attributes = True

class ReportStatistics(BaseModel):
    total: int = Field(..., example=100)
    pending: int = Field(..., example=30)
    assigned: int = Field(0, example=10)  # NOUVEAU
    in_progress: int = Field(..., example=20)
    completed: int = Field(..., example=40)
    rejected: int = Field(..., example=10)
    recent_24h: int = Field(..., example=5)

    # NOUVEAUX CHAMPS EXISTANTS
    awaiting_confirmation: int = Field(0, example=15)
    disputed: int = Field(0, example=5)
    
    # ========== NOUVEAUX CHAMPS STATISTIQUES ==========
    total_weight_kg: Optional[float] = Field(0, example=1250.5)
    average_weight_kg: Optional[float] = Field(0, example=12.5)
    total_points_awarded: Optional[int] = Field(0, example=2500)
    # =================================================

    class Config:
        from_attributes = True

class ReportDetail(BaseModel):
    """Schéma pour les détails complets d'un signalement"""
    id: int
    latitude: float
    longitude: float
    description: Optional[str]
    address_description: Optional[str]
    image_url: str
    status: str
    created_at: datetime
    resolved_at: Optional[datetime]
    user_id: Optional[int]
    collector_id: Optional[int]

    # ========== NOUVEAUX CHAMPS POIDS ==========
    weight_kg: Optional[float] = None
    weight_verified_at: Optional[datetime] = None
    weight_verified_by: Optional[int] = None
    description_quality_score: Optional[int] = None
    # ============================================

    # NOUVEAUX CHAMPS CONFIRMATION
    cleanup_photo_url: Optional[str] = None
    cleanup_photo_submitted_at: Optional[datetime] = None
    citizen_confirmed: bool = False
    citizen_confirmed_at: Optional[datetime] = None
    dispute_reason: Optional[str] = None
    confirmation_code: Optional[str] = None
    confirmation_deadline: Optional[datetime] = None
    auto_confirmed: bool = False
    last_action: Optional[str] = None
    last_action_at: Optional[datetime] = None

    # Relations
    user: Optional[UserSimple] = None
    collector: Optional[UserSimple] = None
    # ========== NOUVELLE RELATION ==========
    weight_verifier: Optional[UserSimple] = Field(None, description="Ramasseur qui a pesé les déchets")
    # ========================================

    class Config:
        from_attributes = True

class ReportFilter(BaseModel):
    commune: Optional[str] = Field(None, example="Gombe")
    quartier: Optional[str] = Field(None, example="Salongo")  # NOUVEAU
    status: Optional[ReportStatusEnum] = Field(None, example="PENDING")
    start_date: Optional[datetime] = Field(None, example="2024-01-01T00:00:00")
    end_date: Optional[datetime] = Field(None, example="2024-01-31T23:59:59")
    user_id: Optional[int] = Field(None, example=1)
    collector_id: Optional[int] = Field(None, example=2)
    
    # ========== NOUVEAUX FILTRES ==========
    min_weight_kg: Optional[float] = Field(None, example=10, gt=0)
    max_weight_kg: Optional[float] = Field(None, example=100, gt=0)
    has_weight: Optional[bool] = Field(None, example=True, description="Filtrer les signalements avec/sans poids")
    min_description_score: Optional[int] = Field(None, example=15, ge=0, le=30)
    # ======================================

    class Config:
        from_attributes = True

class PaginatedReportResponse(BaseModel):
    items: List[ReportList]
    total: int
    page: int
    size: int
    pages: int

    class Config:
        from_attributes = True

# Nouveau schéma pour le rapport de confirmation
class ConfirmationReport(BaseModel):
    """Rapport de confirmation pour dashboard superviseur"""
    report_id: int
    citizen_name: Optional[str]
    collector_name: Optional[str]
    submitted_at: datetime
    confirmed_at: Optional[datetime]
    status: str
    has_dispute: bool = False
    dispute_reason: Optional[str] = None
    
    # ========== NOUVEAUX CHAMPS ==========
    weight_kg: Optional[float] = Field(None, example=15.5)
    description_score: Optional[int] = Field(None, example=25)
    points_earned: Optional[int] = Field(None, example=70)
    # ======================================

    class Config:
        from_attributes = True

# ========== NOUVEAUX SCHÉMAS POUR STATISTIQUES AVANCÉES ==========

class ReportCommuneStats(BaseModel):
    """Statistiques par commune"""
    commune: str
    total: int
    pending: int
    assigned: int
    in_progress: int
    awaiting_confirmation: int
    completed: int
    disputed: int
    total_weight_kg: float
    completion_rate: float
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "commune": "Lemba",
                "total": 150,
                "pending": 30,
                "assigned": 10,
                "in_progress": 20,
                "awaiting_confirmation": 15,
                "completed": 70,
                "disputed": 5,
                "total_weight_kg": 1250.5,
                "completion_rate": 46.67
            }
        }

class ReportMonthlyStats(BaseModel):
    """Statistiques mensuelles"""
    month: str
    year: int
    reports: int
    weight_kg: float
    completed: int
    
    class Config:
        from_attributes = True

class CollectorPerformanceStats(BaseModel):
    """Statistiques de performance pour un ramasseur"""
    collector_id: int
    collector_name: str
    total_missions: int
    completed_missions: int
    awaiting_confirmation: int
    disputed: int
    total_weight_kg: float
    average_weight_per_mission: float
    completion_rate: float
    confirmation_rate: float
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "collector_id": 5,
                "collector_name": "Pierre Kabongo",
                "total_missions": 45,
                "completed_missions": 38,
                "awaiting_confirmation": 4,
                "disputed": 3,
                "total_weight_kg": 567.8,
                "average_weight_per_mission": 12.6,
                "completion_rate": 84.44,
                "confirmation_rate": 92.68
            }
        }

class CitizenImpactStats(BaseModel):
    """Statistiques d'impact pour un citoyen"""
    user_id: int
    full_name: str
    total_reports: int
    total_weight_kg: float
    total_points: int
    average_description_score: float
    subscription_months: int
    reports_by_status: Dict[str, int]
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "full_name": "Jean Mutombo",
                "total_reports": 25,
                "total_weight_kg": 312.5,
                "total_points": 1250,
                "average_description_score": 22.5,
                "subscription_months": 3,
                "reports_by_status": {
                    "COMPLETED": 18,
                    "PENDING": 5,
                    "DISPUTED": 2
                }
            }
        }
# ================================================================

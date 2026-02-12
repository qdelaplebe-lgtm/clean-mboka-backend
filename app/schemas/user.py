# app/schemas/user.py
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class RoleEnum(str, Enum):
    citoyen = "citoyen"
    ramasseur = "ramasseur"
    superviseur = "superviseur"
    coordinateur = "coordinateur"
    administrateur = "administrateur"

# ========== NOUVEAUX SCHÉMAS POUR POINTS ET RÉCOMPENSES ==========
class RewardThreshold(BaseModel):
    """Seuil de récompense atteint"""
    seuil: int = Field(..., example=1000)
    cadeau: str = Field(..., example="Kit scolaire")
    eligible: bool = Field(default=True)

    class Config:
        json_schema_extra = {
            "example": {
                "seuil": 1000,
                "cadeau": "Kit scolaire",
                "eligible": True
            }
        }

class NextReward(BaseModel):
    """Prochaine récompense à atteindre"""
    seuil: int = Field(..., example=2000)
    cadeau: str = Field(..., example="Sac de riz 25kg")
    points_manquants: int = Field(..., example=500)

    class Config:
        json_schema_extra = {
            "example": {
                "seuil": 2000,
                "cadeau": "Sac de riz 25kg",
                "points_manquants": 500
            }
        }

class UserPointsResponse(BaseModel):
    """Réponse complète pour les points et récompenses"""
    user_id: int
    full_name: str
    points: int
    subscription_active: bool
    eligible_lottery: bool
    rewards_unlocked: List[RewardThreshold] = []
    next_reward: Optional[NextReward] = None
    total_reports: int
    total_weight_kg: float
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "full_name": "Jean Mutombo",
                "points": 1250,
                "subscription_active": True,
                "eligible_lottery": True,
                "rewards_unlocked": [
                    {"seuil": 1000, "cadeau": "Kit scolaire", "eligible": True}
                ],
                "next_reward": {
                    "seuil": 2000,
                    "cadeau": "Sac de riz 25kg",
                    "points_manquants": 750
                },
                "total_reports": 15,
                "total_weight_kg": 125.5
            }
        }

class PointsHistoryEntry(BaseModel):
    """Entrée d'historique des points"""
    date: datetime
    report_id: Optional[int] = None
    subscription_id: Optional[int] = None
    points: int
    details: Dict[str, int]
    type: str = Field(..., description="signalement, subscription, bonus")
    
    class Config:
        from_attributes = True
# ================================================================

class UserBase(BaseModel):
    phone: str = Field(..., example="+243810000001")
    email: Optional[EmailStr] = Field(None, example="user@example.com")
    full_name: str = Field(..., example="Jean Mutombo")

    # Adresse
    province: Optional[str] = Field(None, example="Kinshasa")
    commune: str = Field(..., example="Lemba")
    quartier: Optional[str] = Field(None, example="Salongo")
    avenue: Optional[str] = Field(None, example="Mangobo")

    # Photo de profil (NOUVEAU)
    profile_picture: Optional[str] = Field(
        None,
        description="URL de la photo de profil",
        example="https://storage.example.com/profiles/user123.jpg"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "phone": "+243810000001",
                "email": "user@example.com",
                "full_name": "Jean Mutombo",
                "province": "Kinshasa",
                "commune": "Lemba",
                "quartier": "Salongo",
                "avenue": "Mangobo",
                "profile_picture": "https://storage.example.com/profiles/user123.jpg"
            }
        }

class UserCreate(UserBase):
    password: str = Field(..., min_length=6, example="Password123")
    role: RoleEnum = Field(default=RoleEnum.citoyen)
    id_card_url: Optional[str] = Field(None, description="URL de la pièce d'identité")

    class Config:
        json_schema_extra = {
            "example": {
                "phone": "+243810000001",
                "email": "user@example.com",
                "full_name": "Jean Mutombo",
                "province": "Kinshasa",
                "commune": "Lemba",
                "quartier": "Salongo",
                "avenue": "Mangobo",
                "profile_picture": "https://storage.example.com/profiles/user123.jpg",
                "password": "Password123",
                "role": "citoyen",
                "id_card_url": "https://example.com/id_card.jpg"
            }
        }

class UserLogin(BaseModel):
    username: str = Field(..., example="+243810000001")
    password: str = Field(..., example="Password123")

    class Config:
        json_schema_extra = {
            "example": {
                "username": "+243810000001",
                "password": "Password123"
            }
        }

class User(UserBase):
    id: int
    role: RoleEnum
    is_active: bool
    is_verified: bool
    points: int = Field(default=0, ge=0)
    subscription_active: bool = Field(default=False)
    profile_picture: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "phone": "+243810000001",
                "email": "user@example.com",
                "full_name": "Jean Mutombo",
                "province": "Kinshasa",
                "commune": "Lemba",
                "quartier": "Salongo",
                "avenue": "Mangobo",
                "profile_picture": "https://storage.example.com/profiles/user123.jpg",
                "role": "citoyen",
                "is_active": True,
                "is_verified": False,
                "points": 0,
                "subscription_active": False,
                "created_at": "2024-01-07T10:00:00Z",
                "updated_at": "2024-01-07T10:00:00Z"
            }
        }

# Alias pour compatibilité
UserResponse = User

class UserInDB(User):
    hashed_password: str

    class Config:
        from_attributes = True

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = None
    province: Optional[str] = None
    commune: Optional[str] = None
    quartier: Optional[str] = None
    avenue: Optional[str] = None
    profile_picture: Optional[str] = None
    role: Optional[RoleEnum] = None
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None
    id_card_url: Optional[str] = None
    points: Optional[int] = Field(None, ge=0)
    subscription_active: Optional[bool] = None

    class Config:
        json_schema_extra = {
            "example": {
                "email": "newemail@example.com",
                "full_name": "Jean NouvNom",
                "province": "Kinshasa",
                "commune": "Kintambo",
                "quartier": "Binza",
                "avenue": "Lubumbashi",
                "profile_picture": "https://storage.example.com/profiles/new_photo.jpg",
                "role": "citoyen"
            }
        }

class ProfilePictureUpdate(BaseModel):
    profile_picture: Optional[str] = Field(
        None,
        description="URL de la nouvelle photo de profil. Passer null pour supprimer.",
        example="https://storage.example.com/profiles/new_photo.jpg"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "profile_picture": "https://storage.example.com/profiles/user123_updated.jpg"
            }
        }

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user": {
                    "id": 1,
                    "phone": "+243810000001",
                    "email": "user@example.com",
                    "full_name": "Jean Mutombo",
                    "province": "Kinshasa",
                    "commune": "Lemba",
                    "quartier": "Salongo",
                    "avenue": "Mangobo",
                    "profile_picture": "https://storage.example.com/profiles/user123.jpg",
                    "role": "citoyen",
                    "is_active": True,
                    "is_verified": False,
                    "points": 0,
                    "subscription_active": False,
                    "created_at": "2024-01-07T10:00:00Z",
                    "updated_at": "2024-01-07T10:00:00Z"
                }
            }
        }

# Pour compatibilité avec l'ancien code
TokenData = Token

class UserWithToken(BaseModel):
    user: User
    token: Token

    class Config:
        json_schema_extra = {
            "example": {
                "user": {
                    "id": 1,
                    "phone": "+243810000001",
                    "email": "user@example.com",
                    "full_name": "Jean Mutombo",
                    "province": "Kinshasa",
                    "commune": "Lemba",
                    "quartier": "Salongo",
                    "avenue": "Mangobo",
                    "profile_picture": "https://storage.example.com/profiles/user123.jpg",
                    "role": "citoyen",
                    "is_active": True,
                    "is_verified": False,
                    "points": 0,
                    "subscription_active": False,
                    "created_at": "2024-01-07T10:00:00Z",
                    "updated_at": "2024-01-07T10:00:00Z"
                },
                "token": {
                    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                    "token_type": "bearer"
                }
            }
        }

class UserList(BaseModel):
    items: List[User]
    total: int
    page: int
    size: int

    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "id": 1,
                        "phone": "+243810000001",
                        "email": "user@example.com",
                        "full_name": "Jean Mutombo",
                        "province": "Kinshasa",
                        "commune": "Lemba",
                        "quartier": "Salongo",
                        "avenue": "Mangobo",
                        "profile_picture": "https://storage.example.com/profiles/user123.jpg",
                        "role": "citoyen",
                        "is_active": True,
                        "is_verified": False,
                        "points": 0,
                        "subscription_active": False,
                        "created_at": "2024-01-07T10:00:00Z",
                        "updated_at": "2024-01-07T10:00:00Z"
                    }
                ],
                "total": 1,
                "page": 1,
                "size": 10
            }
        }

class UserStats(BaseModel):
    total: int
    by_role: Dict[str, int]
    by_commune: Dict[str, int]
    by_status: Dict[str, int]

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "total": 100,
                "by_role": {
                    "citoyen": 70,
                    "ramasseur": 15,
                    "superviseur": 10,
                    "coordinateur": 3,
                    "administrateur": 2
                },
                "by_commune": {
                    "Lemba": 30,
                    "Kintambo": 25,
                    "Gombe": 20,
                    "Lingwala": 15,
                    "Masina": 10
                },
                "by_status": {
                    "active": 95,
                    "inactive": 5
                }
            }
        }

class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)

    class Config:
        json_schema_extra = {
            "example": {
                "current_password": "oldpassword123",
                "new_password": "newpassword456"
            }
        }

class PasswordResetRequest(BaseModel):
    email: EmailStr

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com"
            }
        }

class PasswordReset(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)

    class Config:
        json_schema_extra = {
            "example": {
                "token": "reset_token_123",
                "new_password": "newpassword456"
            }
        }

class EmailVerification(BaseModel):
    token: str

    class Config:
        json_schema_extra = {
            "example": {
                "token": "verification_token_123"
            }
        }

class AgentCreate(UserCreate):
    pass

class RoleAssignment(BaseModel):
    user_id: int
    role: RoleEnum

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "role": "superviseur"
            }
        }

class ZoneAssignment(BaseModel):
    user_id: int
    commune: str
    quartier: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "commune": "Lemba",
                "quartier": "Salongo"
            }
        }

class PointsUpdate(BaseModel):
    user_id: int
    points: int = Field(..., ge=0, description="Nombre de points à ajouter/soustraire")
    reason: str = Field(..., description="Raison de la modification des points")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "points": 10,
                "reason": "Signalement validé"
            }
        }

# ========== NOUVEAU: Schéma pour utilisateur simplifié (utilisé dans Report) ==========
class UserSimple(BaseModel):
    id: int
    full_name: Optional[str] = None
    phone: Optional[str] = None
    commune: Optional[str] = None
    role: Optional[str] = None
    points: Optional[int] = None
    profile_picture: Optional[str] = None

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "full_name": "Jean Mutombo",
                "phone": "+243810000001",
                "commune": "Lemba",
                "role": "citoyen",
                "points": 1250,
                "profile_picture": "https://storage.example.com/profiles/user123.jpg"
            }
        }
# ====================================================================================

# ========== NOUVEAU: Schéma pour pagination ==========
class PaginatedUserResponse(BaseModel):
    items: List[User]
    total: int
    page: int
    size: int
    pages: int

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "items": [],
                "total": 0,
                "page": 1,
                "size": 10,
                "pages": 0
            }
        }
# ====================================================

# ========== NOUVEAU: Schéma pour statistiques étendues ==========
class UserExtendedStats(BaseModel):
    total_reports: int
    completed_reports: int
    pending_reports: int
    points_earned: int
    total_weight_collected: float
    subscription_months: int
    reports_by_month: List[Dict[str, Any]] = []
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "total_reports": 15,
                "completed_reports": 12,
                "pending_reports": 3,
                "points_earned": 1250,
                "total_weight_collected": 125.5,
                "subscription_months": 3,
                "reports_by_month": []
            }
        }
# =====================================================

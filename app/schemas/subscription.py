# app/schemas/subscription.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum

class SubscriptionStatusEnum(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PENDING = "pending"

# ========== SCHÉMAS DE BASE ==========
class SubscriptionBase(BaseModel):
    """Schéma de base pour les abonnements"""
    user_id: int = Field(..., example=1)
    amount: int = Field(default=100, example=100, description="Montant en centimes ou unité locale")
    payment_method: str = Field(default="mobile_money", example="orange_money")
    is_active: bool = Field(default=True)
    
    class Config:
        from_attributes = True

class SubscriptionCreate(SubscriptionBase):
    """Schéma pour créer un abonnement"""
    end_date: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "amount": 2250,
                "payment_method": "orange_money",
                "is_active": True,
                "end_date": "2024-02-07T10:00:00Z"
            }
        }

class SubscriptionUpdate(BaseModel):
    """Schéma pour mettre à jour un abonnement"""
    amount: Optional[int] = None
    payment_method: Optional[str] = None
    is_active: Optional[bool] = None
    end_date: Optional[datetime] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "is_active": False
            }
        }

# ========== SCHÉMAS DE RÉPONSE ==========
class SubscriptionResponse(SubscriptionBase):
    """Schéma de réponse pour un abonnement"""
    id: int
    start_date: datetime
    end_date: Optional[datetime] = None
    created_at: datetime
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "user_id": 1,
                "amount": 2250,
                "payment_method": "orange_money",
                "is_active": True,
                "start_date": "2024-01-07T10:00:00Z",
                "end_date": "2024-02-07T10:00:00Z",
                "created_at": "2024-01-07T10:00:00Z"
            }
        }

class SubscriptionDetail(SubscriptionResponse):
    """Schéma détaillé avec informations utilisateur"""
    user_full_name: Optional[str] = None
    user_phone: Optional[str] = None
    user_commune: Optional[str] = None
    days_remaining: Optional[int] = None
    
    class Config:
        from_attributes = True

# ========== SCHÉMAS POUR PAIEMENT ==========
class PaymentInitiation(BaseModel):
    """Schéma pour initier un paiement"""
    user_id: int
    amount: int
    payment_method: str
    phone_number: Optional[str] = Field(None, example="+243810000001")
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": 1,
                "amount": 2250,
                "payment_method": "orange_money",
                "phone_number": "+243810000001"
            }
        }

class PaymentConfirmation(BaseModel):
    """Schéma pour confirmer un paiement"""
    transaction_id: str
    status: str
    payment_method: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "transaction_id": "TX123456789",
                "status": "success",
                "payment_method": "orange_money"
            }
        }

# ========== NOUVEAU: Statistiques d'abonnement ==========
class SubscriptionStats(BaseModel):
    """Statistiques des abonnements pour dashboard admin"""
    total_active: int
    total_expired: int
    total_cancelled: int
    total_pending: int
    total_revenue: int
    monthly_revenue: int
    active_by_method: dict
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_active": 150,
                "total_expired": 45,
                "total_cancelled": 12,
                "total_pending": 8,
                "total_revenue": 337500,
                "monthly_revenue": 112500,
                "active_by_method": {
                    "orange_money": 80,
                    "mpesa": 45,
                    "airtel_money": 25
                }
            }
        }

class UserSubscriptionStatus(BaseModel):
    """Statut d'abonnement pour un utilisateur"""
    is_active: bool
    current_subscription: Optional[SubscriptionResponse] = None
    has_auto_renewal: bool = Field(default=False)
    days_until_expiry: Optional[int] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "is_active": True,
                "current_subscription": {
                    "id": 1,
                    "user_id": 1,
                    "amount": 2250,
                    "payment_method": "orange_money",
                    "is_active": True,
                    "start_date": "2024-01-07T10:00:00Z",
                    "end_date": "2024-02-07T10:00:00Z",
                    "created_at": "2024-01-07T10:00:00Z"
                },
                "has_auto_renewal": True,
                "days_until_expiry": 25
            }
        }

# app/api/subscriptions.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from .. import models, schemas
from ..database import get_db
from ..api.deps import get_current_user

router = APIRouter()

@router.get("/me/active", response_model=schemas.UserSubscriptionStatus)
def get_my_active_subscription(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Récupère l'abonnement actif de l'utilisateur connecté.
    """
    subscription = db.query(models.Subscription)\
        .filter(
            models.Subscription.user_id == current_user.id,
            models.Subscription.is_active == True,
            models.Subscription.end_date > datetime.utcnow()
        )\
        .order_by(models.Subscription.created_at.desc())\
        .first()
    
    if not subscription:
        return {
            "is_active": False,
            "current_subscription": None,
            "has_auto_renewal": False,
            "days_until_expiry": None
        }
    
    days_remaining = (subscription.end_date - datetime.utcnow()).days if subscription.end_date else None
    
    return {
        "is_active": True,
        "current_subscription": subscription,
        "has_auto_renewal": True,
        "days_until_expiry": days_remaining
    }

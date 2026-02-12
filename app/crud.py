from sqlalchemy.orm import Session, joinedload
from typing import Optional, List
from . import models, schemas
from .core.security import get_password_hash, verify_password

# --- UTILISATEURS ---
def get_user_by_phone(db: Session, phone: str):
    return db.query(models.User).filter(models.User.phone == phone).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = get_password_hash(user.password)
    db_user = models.User(
        phone=user.phone,
        full_name=user.full_name,
        hashed_password=hashed_password,
        commune=user.commune,
        quartier=user.quartier,
        avenue=user.avenue,
        role=user.role,
        id_card_url=user.id_card_url
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def authenticate_user(db: Session, phone: str, password: str):
    user = get_user_by_phone(db, phone=phone)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user

# --- SIGNALEMENTS ---
def create_report(db: Session, report: schemas.ReportCreate, user_id: int, image_url: str):
    from .models.report import ReportStatus
    
    db_report = models.Report(
        user_id=user_id,
        latitude=report.latitude,
        longitude=report.longitude,
        address_description=report.description,
        image_url=image_url,
        status=ReportStatus.PENDING
    )
    db.add(db_report)
    db.commit()
    db.refresh(db_report)
    return db_report

def get_reports_by_commune(db: Session, commune: str):
    return db.query(models.Report).options(joinedload(models.Report.user)).filter(models.Report.user.has(commune=commune)).all()

def get_user_reports(db: Session, user_id: int):
    return db.query(models.Report).filter(models.Report.user_id == user_id).all()

# app/models/report.py
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Enum as SQLEnum, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum

from ..database import Base

class ReportStatus(str, Enum):
    """Définition des états d'un signalement - ÉTENDUE"""
    PENDING = "PENDING"
    ASSIGNED = "ASSIGNED"  # Nouveau : assigné mais pas encore traité
    IN_PROGRESS = "IN_PROGRESS"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"  # Nouveau : photo soumise
    COMPLETED = "COMPLETED"
    DISPUTED = "DISPUTED"  # Nouveau : citoyen a refusé la confirmation

class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)

    # Localisation (GPS obligatoire)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    address_description = Column(String, nullable=True)  # Ex: "Devant l'église"

    # Description du problème
    description = Column(Text, nullable=True)

    # ========== NOUVEAUX CHAMPS POUR SCORING ==========
    # Poids vérifié par balance (critère #3)
    weight_kg = Column(Float, nullable=True)
    weight_verified_at = Column(DateTime, nullable=True)
    weight_verified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Score de qualité de description (0-30) - critère #2
    description_quality_score = Column(Integer, nullable=True)
    # ==================================================

    # Preuve initiale (photo du citoyen)
    image_url = Column(String, nullable=False)  # Photo uploadée par citoyen

    # État (Utilise l'Enum définie ci-dessus)
    status = Column(SQLEnum(ReportStatus), default=ReportStatus.PENDING)

    # Pour la confirmation client (ancien champ - gardé pour compatibilité)
    client_confirmed = Column(Boolean, default=False)

    # --- NOUVEAUX CHAMPS POUR CONFIRMATION PHOTO ---
    # Photo de preuve du ramassage (soumise par le ramasseur)
    cleanup_photo_url = Column(String, nullable=True)

    # Horodatage de la photo de confirmation
    cleanup_photo_submitted_at = Column(DateTime, nullable=True)

    # Confirmation par le citoyen
    citizen_confirmed = Column(Boolean, default=False)
    citizen_confirmed_at = Column(DateTime, nullable=True)

    # Code de confirmation unique (UUID) pour sécurité
    confirmation_code = Column(String(8), unique=True, nullable=True)

    # En cas de refus de confirmation
    dispute_reason = Column(Text, nullable=True)  # Raison du désaccord

    # Délai d'attente de confirmation (en heures)
    confirmation_deadline = Column(DateTime, nullable=True)

    # Flag pour auto-confirmation
    auto_confirmed = Column(Boolean, default=False)

    # Dernière action
    last_action = Column(String(50), nullable=True)  # "photo_uploaded", "confirmed", "disputed", "weight_recorded"
    last_action_at = Column(DateTime, nullable=True)

    # Horodatage
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)

    # Relations (Lien vers les autres tables)
    # Clés étrangères
    user_id = Column(Integer, ForeignKey("users.id"))
    collector_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Nouvelles clés pour la géolocalisation
    commune_id = Column(Integer, ForeignKey("communes.id"), nullable=True)
    quartier_id = Column(Integer, ForeignKey("quartiers.id"), nullable=True)

    # CORRECTION : Relations avec syntaxe compatible
    user = relationship("User", back_populates="reports", foreign_keys=[user_id])
    collector = relationship("User", back_populates="assigned_reports", foreign_keys=[collector_id])
    weight_verifier = relationship("User", foreign_keys=[weight_verified_by])  # NOUVEAU

    # Relations avec Commune et Quartier
    commune = relationship("Commune", back_populates="reports")
    quartier = relationship("Quartier", back_populates="reports")

    def __repr__(self):
        return f"<Report ID {self.id} at {self.latitude}, {self.longitude}>"

    # Méthode pour vérifier si le délai de confirmation est expiré
    def is_confirmation_expired(self):
        if not self.confirmation_deadline:
            return False
        return datetime.utcnow() > self.confirmation_deadline

    # Méthode pour obtenir le statut de confirmation
    def get_confirmation_status(self):
        if self.citizen_confirmed:
            return "confirmed"
        elif self.dispute_reason:
            return "disputed"
        elif self.auto_confirmed:
            return "auto_confirmed"
        elif self.is_confirmation_expired():
            return "expired"
        elif self.status == ReportStatus.AWAITING_CONFIRMATION:
            return "awaiting"
        else:
            return "not_applicable"

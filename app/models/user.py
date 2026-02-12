# app/models/user.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from typing import Optional

from ..database import Base

class RoleEnum(str, enum.Enum):
    """
    Hiérarchie des rôles pour la gestion de la salubrité urbaine.
    """
    CITOYEN = "citoyen"
    RAMASSEUR = "ramasseur"
    SUPERVISEUR = "superviseur"
    COORDINATEUR = "coordinateur"
    ADMINISTRATEUR = "administrateur"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    # Informations d'identification
    phone = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)

    # Profil
    full_name = Column(String, nullable=False)
    role = Column(SQLEnum(RoleEnum), default=RoleEnum.CITOYEN)

    # Adresse
    province = Column(String, index=True, nullable=True)
    commune = Column(String, index=True, nullable=False)
    quartier = Column(String, index=True, nullable=True)
    avenue = Column(String, nullable=True)

    # Vérification
    id_card_url = Column(String, nullable=True)
    profile_picture = Column(String, nullable=True)  # NOUVEAU: Photo de profil
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    # Gamification & Abonnement
    points = Column(Integer, default=0)
    subscription_active = Column(Boolean, default=False)

    # Horodatage
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # CORRECTION : Utiliser des chaînes pour éviter les imports circulaires
    reports = relationship("Report", back_populates="user", foreign_keys="Report.user_id")
    assigned_reports = relationship("Report", back_populates="collector", foreign_keys="Report.collector_id")
    subscriptions = relationship("Subscription", back_populates="user")

    def __repr__(self):
        return f"<User {self.full_name} ({self.role}) in {self.commune}>"

    def is_agent(self):
        return self.role in [
            RoleEnum.RAMASSEUR,
            RoleEnum.SUPERVISEUR,
            RoleEnum.COORDINATEUR,
            RoleEnum.ADMINISTRATEUR
        ]

    def can_manage_user(self, target_user):
        """Vérifie si cet utilisateur peut gérer un autre utilisateur"""
        hierarchy = {
            RoleEnum.CITOYEN: 0,
            RoleEnum.RAMASSEUR: 1,
            RoleEnum.SUPERVISEUR: 2,
            RoleEnum.COORDINATEUR: 3,
            RoleEnum.ADMINISTRATEUR: 4
        }

        # Même utilisateur
        if self.id == target_user.id:
            return True

        # Vérifier la hiérarchie
        if hierarchy.get(self.role, 0) > hierarchy.get(target_user.role, 0):
            # Vérifier la zone géographique
            if self.role == RoleEnum.SUPERVISEUR:
                return self.commune == target_user.commune and self.quartier == target_user.quartier
            elif self.role == RoleEnum.COORDINATEUR:
                return self.commune == target_user.commune
            elif self.role == RoleEnum.ADMINISTRATEUR:
                return self.commune == target_user.commune
        return False

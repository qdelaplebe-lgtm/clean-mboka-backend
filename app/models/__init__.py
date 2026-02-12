# app/models/__init__.py
from .user import User, RoleEnum
from .report import Report, ReportStatus
from .subscription import Subscription
from .commune import Commune, Quartier  # Important : Quartier est dans commune.py

__all__ = [
    "User", 
    "Report", 
    "Subscription", 
    "RoleEnum", 
    "ReportStatus",
    "Commune", 
    "Quartier"  # N'oubliez pas d'ajouter Quartier ici
]

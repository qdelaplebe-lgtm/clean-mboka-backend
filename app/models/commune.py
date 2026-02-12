# app/models/commune.py
from sqlalchemy import Column, Integer, String, Float, ForeignKey, JSON
from sqlalchemy.orm import relationship
from ..database import Base

class Commune(Base):
    __tablename__ = "communes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    postal_code = Column(String, nullable=True)

    # Coordonnées géographiques (centre de la commune)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Pour stocker les contours de la commune (GeoJSON simplifié)
    boundaries = Column(JSON, nullable=True)

    # CORRECTION : Utiliser le même nom partout
    quartiers = relationship("Quartier", back_populates="commune")

    # Relation vers Report (doit correspondre à report.py)
    reports = relationship("Report", back_populates="commune")

class Quartier(Base):
    __tablename__ = "quartiers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)

    # Clé étrangère
    commune_id = Column(Integer, ForeignKey("communes.id"))

    # Coordonnées géographiques (centre du quartier)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Pour stocker les contours du quartier (GeoJSON simplifié)
    boundaries = Column(JSON, nullable=True)

    # CORRECTION : Relations cohérentes
    commune = relationship("Commune", back_populates="quartiers")
    
    # Relation vers Report (doit correspondre à report.py)
    reports = relationship("Report", back_populates="quartier")

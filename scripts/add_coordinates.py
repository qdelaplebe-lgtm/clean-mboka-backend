# scripts/add_coordinates.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import engine, SessionLocal
from app.models.commune import Commune, Quartier

# Coordonnées approximatives pour Kinshasa
commune_coordinates = {
    "GOMBE": (-4.3052, 15.3004),
    "LINGWALA": (-4.3292, 15.2984),
    "KINSHASA": (-4.3310, 15.3074),
    "BARUMBU": (-4.3405, 15.3200),
    "NGALIEMA": (-4.3545, 15.2234),
    "LIMETE": (-4.3688, 15.3456),
    "MATETE": (-4.3872, 15.3456),
    "KASA-VUBU": (-4.3339, 15.2891),
    "NGABA": (-4.3695, 15.2895),
    "KALAMU": (-4.3418, 15.2937),
    "NGIRI-NGIRI": (-4.3295, 15.2777),
    "LEMBA": (-4.3698, 15.3289),
    "KISENSO": (-4.4043, 15.3356),
    "MONT-NGAFULA": (-4.4532, 15.2639),
    "MASINA": (-4.3833, 15.3986),
    "NDJILI": (-4.4035, 15.3636),
    "KIMBANSEKE": (-4.4294, 15.3145),
    "BUMBU": (-4.3475, 15.3433),
    "MAKALA": (-4.3582, 15.3600),
    "SELEMBAO": (-4.3833, 15.3683),
    "KITAMBO": (-4.3243, 15.3532),
    "BANDALUNGWA": (-4.3358, 15.2756),
    "NSELE": (-4.2833, 15.5667),
    "MALUKU": (-4.1667, 15.9167)
}

def add_coordinates():
    db = SessionLocal()
    try:
        # Mettre à jour les communes
        for commune_name, (lat, lng) in commune_coordinates.items():
            commune = db.query(Commune).filter(
                Commune.name == commune_name
            ).first()
            if commune:
                commune.latitude = lat
                commune.longitude = lng
                print(f"Mise à jour {commune_name}: {lat}, {lng}")
        
        # Pour les quartiers, utiliser les coordonnées de la commune
        for commune_name, (lat, lng) in commune_coordinates.items():
            commune = db.query(Commune).filter(
                Commune.name == commune_name
            ).first()
            if commune:
                quartiers = db.query(Quartier).filter(
                    Quartier.commune_id == commune.id
                ).all()
                
                # Distribuer les quartiers autour du centre de la commune
                for i, quartier in enumerate(quartiers):
                    # Petit décalage pour chaque quartier
                    offset_lat = (i % 3) * 0.005
                    offset_lng = (i // 3) * 0.005
                    quartier.latitude = lat + offset_lat
                    quartier.longitude = lng + offset_lng
        
        db.commit()
        print("Coordonnées ajoutées avec succès !")
    except Exception as e:
        db.rollback()
        print(f"Erreur: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    add_coordinates()

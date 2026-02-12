# scripts/update_reports_geo.py
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import SessionLocal
from app.models.report import Report
from app.models.commune import Commune, Quartier

def update_reports_geolocation():
    db = SessionLocal()
    try:
        # Pour chaque signalement, trouver la commune et quartier les plus proches
        reports = db.query(Report).filter(
            Report.commune_id.is_(None)
        ).all()
        
        for report in reports:
            if report.latitude and report.longitude:
                # Trouver la commune la plus proche (méthode simple)
                closest_commune = db.query(Commune).order_by(
                    func.sqrt(
                        func.pow(Commune.latitude - report.latitude, 2) +
                        func.pow(Commune.longitude - report.longitude, 2)
                    )
                ).first()
                
                if closest_commune:
                    report.commune_id = closest_commune.id
                    
                    # Trouver le quartier le plus proche dans cette commune
                    closest_quartier = db.query(Quartier).filter(
                        Quartier.commune_id == closest_commune.id
                    ).order_by(
                        func.sqrt(
                            func.pow(Quartier.latitude - report.latitude, 2) +
                            func.pow(Quartier.longitude - report.longitude, 2)
                        )
                    ).first()
                    
                    if closest_quartier:
                        report.quartier_id = closest_quartier.id
        
        db.commit()
        print(f"{len(reports)} signalements mis à jour")
    except Exception as e:
        db.rollback()
        print(f"Erreur: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    update_reports_geolocation()

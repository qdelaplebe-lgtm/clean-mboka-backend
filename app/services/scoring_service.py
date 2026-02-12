# app/services/scoring_service.py
"""
Service de calcul et gestion des points citoyens.
Critères :
1. Abonnement mensuel actif → +10 points/mois
2. Qualité de description → 0-30 points
3. Poids des déchets → 2 points/kg
4. Bonus confirmation rapide → +20 points
"""
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, List
import re

from .. import models, schemas


class ScoringService:
    """Moteur de calcul des points citoyens - NE SUPPRIME RIEN, AJOUTE LA LOGIQUE"""

    # CONSTANTES DE PONDÉRATION
    POINTS_ABONNEMENT_MENSUEL = 10
    POINTS_PAR_KG = 2
    POINTS_MAX_DESCRIPTION = 30
    POINTS_CONFIRMATION_BONUS = 20

    # SEUILS POUR TIRAGE AU SORT
    SEUILS_TIRAGE = {
        1000: "Kit scolaire",
        2000: "Sac de riz 25kg",
        3500: "Kit nettoyage + congélateur",
        5000: "Moto",
        7500: "Véhicule de collecte"
    }

    @staticmethod
    def calculer_score_description(description: str) -> int:
        """
        Analyse la qualité de la description du signalement.
        Retourne un score entre 0 et 30.
        Préservation totale - AJOUT PURE.
        """
        if not description or not isinstance(description, str) or len(description.strip()) < 10:
            return 0

        score = 0
        desc_lower = description.lower()

        # 1. Longueur (max 10 points)
        mots = len(description.split())
        if mots >= 20:
            score += 10
        elif mots >= 10:
            score += 5
        elif mots >= 5:
            score += 2

        # 2. Mots-clés spécifiques aux déchets (max 12 points)
        mots_cles = {
            'plastique': 2, 'bouteille': 2, 'sachet': 2, 'bouteilles': 2, 'plastiques': 2,
            'organique': 2, 'nourriture': 2, 'restes': 2, 'alimentaire': 2,
            'encombrant': 2, 'meuble': 2, 'électroménager': 2, 'canapé': 2, 'matelas': 2,
            'médical': 3, 'dangereux': 3, 'verre': 2, 'vitre': 2, 'brisé': 1,
            'carton': 1, 'papier': 1, 'métal': 2, 'ferraille': 2,
            'sacs': 1, 'tas': 1, 'dépôt': 1, 'sauvage': 2
        }

        for mot, valeur in mots_cles.items():
            if mot in desc_lower:
                score += valeur

        # 3. Présence de quantités (max 4 points)
        if re.search(r'\d+\s*(kg|kilo|kilos|tonne|tonnes|sac|sacs|unité|unités|m|m²|m3)', desc_lower):
            score += 4

        # 4. Structure et ponctuation (max 4 points)
        if ',' in description and '.' in description:
            score += 2
        if description[0].isupper():  # Commence par majuscule
            score += 1
        if '?' in description or '!' in description:  # Expression d'urgence
            score += 1

        return min(score, 30)  # Plafonné à 30

    @staticmethod
    def calculer_points_signalement(
        db_report: models.Report,
        user: models.User
    ) -> Dict[str, any]:
        """
        Calcule les points gagnés pour un signalement spécifique.
        """
        points = {}
        total = 0

        # Critère 2 : Qualité description
        score_desc = db_report.description_quality_score or 0
        if score_desc > 0:
            points['description'] = score_desc
            total += score_desc

        # Critère 3 : Poids
        if db_report.weight_kg and db_report.weight_kg > 0:
            points_poids = int(db_report.weight_kg * ScoringService.POINTS_PAR_KG)
            points['poids'] = points_poids
            total += points_poids

        # Bonus confirmation rapide (moins de 24h entre photo et confirmation)
        if (db_report.citizen_confirmed and 
            db_report.cleanup_photo_submitted_at and 
            db_report.citizen_confirmed_at):
            delai = db_report.citizen_confirmed_at - db_report.cleanup_photo_submitted_at
            if delai.total_seconds() < 86400:  # 24h
                points['confirmation_rapide'] = ScoringService.POINTS_CONFIRMATION_BONUS
                total += ScoringService.POINTS_CONFIRMATION_BONUS

        return {
            'details': points,
            'total': total,
            'report_id': db_report.id
        }

    @staticmethod
    def attribuer_points_abonnement(user: models.User, db: Session) -> int:
        """
        Ajoute les points d'abonnement mensuel si l'utilisateur est abonné.
        À appeler par une tâche cron le 1er de chaque mois.
        """
        if not user.subscription_active:
            return 0

        # Vérifier si l'abonnement est toujours valide
        subscription_active = db.query(models.Subscription)\
            .filter(
                models.Subscription.user_id == user.id,
                models.Subscription.is_active == True,
                models.Subscription.end_date > datetime.utcnow()
            ).first()

        if subscription_active:
            user.points = (user.points or 0) + ScoringService.POINTS_ABONNEMENT_MENSUEL
            db.commit()
            return ScoringService.POINTS_ABONNEMENT_MENSUEL
        else:
            # Désactiver automatiquement si expiré
            user.subscription_active = False
            db.commit()
            return 0

    @staticmethod
    def get_seuils_atteints(points: int) -> list:
        """
        Retourne la liste des cadeaux pour lesquels l'utilisateur est éligible.
        """
        seuils_atteints = []
        for seuil, cadeau in sorted(ScoringService.SEUILS_TIRAGE.items()):
            if points >= seuil:
                seuils_atteints.append({
                    'seuil': seuil,
                    'cadeau': cadeau,
                    'eligible': True
                })
        return seuils_atteints

    @staticmethod
    def get_prochain_seuil(points: int) -> Optional[Dict]:
        """
        Retourne le prochain seuil à atteindre.
        """
        for seuil, cadeau in sorted(ScoringService.SEUILS_TIRAGE.items()):
            if points < seuil:
                return {
                    'seuil': seuil,
                    'cadeau': cadeau,
                    'points_manquants': seuil - points
                }
        return None

    @staticmethod
    def is_eligible_for_lottery(user: models.User) -> bool:
        """
        Vérifie si l'utilisateur a atteint le seuil minimum pour le tirage au sort.
        """
        seuil_minimum = min(ScoringService.SEUILS_TIRAGE.keys())
        return (user.points or 0) >= seuil_minimum

    @staticmethod
    def calculate_user_stats(db: Session, user_id: int) -> Dict:
        """
        Calcule les statistiques complètes d'un citoyen.
        """
        from sqlalchemy import func
        
        # Total des signalements
        total_reports = db.query(models.Report)\
            .filter(models.Report.user_id == user_id)\
            .count()
        
        # Poids total collecté
        total_weight = db.query(
                func.coalesce(func.sum(models.Report.weight_kg), 0)
            )\
            .filter(models.Report.user_id == user_id)\
            .scalar() or 0
        
        return {
            'total_reports': total_reports,
            'total_weight_kg': float(total_weight)
        }

"""Génération du rétroplanning de réponse à un marché public BTP.

Calcule le rétroplanning déterministe à rebours depuis la date limite de remise
des plis en jours ouvrés français (excluant samedis, dimanches et jours fériés légaux).
Refuse d'inventer une date si la date limite n'est pas identifiée dans le DCE.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import (
    charger_json,
    ecrire_fichier_securise,
    ecrire_json,
    est_jour_ouvre,
    parser_date_et_echeance,
    reculer_jours_ouvres,
    resoudre_chemin_securise,
)

logger = logging.getLogger("calendrier")


def parser_date_fr(date_str: str) -> Optional[datetime.datetime]:
    """Parse une date au format français standard ou ISO 8601 via le parseur unifié."""
    if not date_str:
        return None
    dt, _, _ = parser_date_et_echeance(date_str)
    return dt


def calculer_retroplanning(
    date_limite: Union[datetime.datetime, datetime.date, str, Dict[str, Any]],
    contradictions: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Génère les jalons clés à rebours en jours ouvrés légaux depuis la date limite."""
    dt: Optional[datetime.datetime] = None
    if isinstance(date_limite, dict):
        d_str = (
            date_limite.get("calendrier", {}).get("date_limite_retenue")
            or date_limite.get("date_limite")
            or date_limite.get("date_limite_remise")
        )
        if d_str:
            dt = parser_date_fr(str(d_str))
        if contradictions is None:
            contradictions = date_limite.get("contradictions_detectees", [])
    elif isinstance(date_limite, str):
        dt = parser_date_fr(date_limite)
    elif isinstance(date_limite, datetime.datetime):
        dt = date_limite
    elif isinstance(date_limite, datetime.date):
        dt = datetime.datetime(date_limite.year, date_limite.month, date_limite.day, 18, 0, 0)

    if not dt:
        return []

    jalons = []
    date_ref = dt.date()
    
    # Jalon 1 : Clôture officielle (J)
    jalons.append({
        "jalon": "Échéance officielle de clôture de la consultation",
        "echeance": dt.strftime("%d/%m/%Y à %H:%M"),
        "delta_jours_ouvres": 0,
        "responsable": "Plateforme profil d'acheteur",
        "description": "Fermeture automatique de la salle des dépôts. Tout pli en cours de téléversement est rejeté.",
        "statut": "CRITIQUE"
    })
    
    # Jalon 2 : Dépôt sécurisé (J-1 ouvré)
    d_depot = reculer_jours_ouvres(date_ref, 1)
    jalons.append({
        "jalon": "Dépôt final du pli sur la plateforme",
        "echeance": d_depot.strftime("%d/%m/%Y avant 16:00"),
        "delta_jours_ouvres": -1,
        "responsable": "Dirigeant / Chargé d'affaires habilité",
        "description": "Téléversement de l'archive complète (Candidature + Offre) et téléchargement du récépissé électronique d'horodatage.",
        "statut": "OBLIGATOIRE"
    })
    
    # Jalon 3 : Contrôle final et test à blanc (J-2 ouvrés)
    d_test = reculer_jours_ouvres(date_ref, 2)
    jalons.append({
        "jalon": "Test de connexion et contrôle final croisé",
        "echeance": d_test.strftime("%d/%m/%Y"),
        "delta_jours_ouvres": -2,
        "responsable": "Équipe réponse marché",
        "description": "Vérification des accès au profil d'acheteur, audit des pièces avec scripts/controle_final.py et vérification du certificat de signature si imposé.",
        "statut": "QUALITE"
    })
    
    # Jalon 4 : Finalisation du mémoire technique (J-3 ouvrés)
    d_memoire = reculer_jours_ouvres(date_ref, 3)
    jalons.append({
        "jalon": "Bouclage de la trame du mémoire technique",
        "echeance": d_memoire.strftime("%d/%m/%Y"),
        "delta_jours_ouvres": -3,
        "responsable": "Conducteur de travaux / Rédacteur",
        "description": "Suppression de toutes les balises [À FOURNIR], intégration des fiches techniques fabricants et exports PDF propres.",
        "statut": "PRODUCTION"
    })
    
    # Jalon 5 : Bouclage du chiffrage (J-5 ouvrés)
    d_chiffrage = reculer_jours_ouvres(date_ref, 5)
    jalons.append({
        "jalon": "Validation définitive du chiffrage et de la DPGF",
        "echeance": d_chiffrage.strftime("%d/%m/%Y"),
        "delta_jours_ouvres": -5,
        "responsable": "Métreur / Chiffreur",
        "description": "Contrôle arithmétique rigoureux sous scripts/controle_prix.py, vérification des sous-détails et arrêt du prix de vente.",
        "statut": "PRODUCTION"
    })
    
    # Jalon 6 : Date limite questions à l'acheteur (J-7 ouvrés)
    d_questions = reculer_jours_ouvres(date_ref, 7)
    jalons.append({
        "jalon": "Dernier délai pour poser des questions à l'acheteur",
        "echeance": d_questions.strftime("%d/%m/%Y"),
        "delta_jours_ouvres": -7,
        "responsable": "Chargé d'affaires",
        "description": "Dépôt des demandes d'éclaircissements techniques ou signalement des contradictions détectées entre pièces.",
        "statut": "PROCEDURE"
    })
    
    # Jalon 7 : Visite sur site (J-10 ouvrés)
    d_visite = reculer_jours_ouvres(date_ref, 10)
    jalons.append({
        "jalon": "Visite obligatoire ou recommandée sur les lieux",
        "echeance": d_visite.strftime("%d/%m/%Y"),
        "delta_jours_ouvres": -10,
        "responsable": "Conducteur de travaux",
        "description": "Reconnaissance des accès, contraintes de toiture et délivrance du certificat ou récépissé de visite signé par la MOA.",
        "statut": "PREREQUIS"
    })
    
    # Tri chronologique ascendant (du plus ancien au jour J)
    jalons.sort(key=lambda x: x["delta_jours_ouvres"])
    return jalons


def generer_markdown_calendrier(analyse: Dict[str, Any], jalons: List[Dict[str, Any]], calculable: bool) -> str:
    """Rédige la présentation du rétroplanning en Markdown (style sobre, zéro emoji)."""
    date_limite_texte = analyse.get("calendrier", {}).get("date_limite_retenue", "Non définie")
    
    md = []
    md.append(f"# Rétroplanning de Réponse — {analyse.get('objet', 'Marché BTP')}\n")
    md.append(f"> **Date limite de clôture impérative** : `{date_limite_texte}`\n")
    
    if not calculable:
        md.append("## Avertissement : Rétroplanning non calculable")
        md.append("Aucune date limite valide n'a pu être extraite des pièces du DCE.")
        md.append("Veuillez renseigner manuellement la date limite de remise des plis pour générer les jalons en jours ouvrés.\n")
        return "\n".join(md)
        
    md.append("## Tableau de marche à rebours (en jours ouvrés français)\n")
    md.append("| Échéance prévisionnelle | Jalon opérationnel | Responsable | Objectif et livrable attendu |")
    md.append("| :--- | :--- | :--- | :--- |")
    for j in jalons:
        md.append(f"| **{j['echeance']}** | {j['jalon']} | {j['responsable']} | {j['description']} |")
    md.append("")
    
    md.append("## Consignes de sécurité pour le dépôt dématérialisé")
    md.append("1. **Règle absolue du dépôt à J-1 ouvré** : Ne jamais attendre le jour de la clôture pour initier la transmission des fichiers volumineux (mémoires techniques et plans).")
    md.append("2. **Vérification du certificat de signature** : Si la signature électronique est requise dès le dépôt au RC, s'assurer de la validité de la clé USB/token RGS** / eIDAS 48 heures avant l'échéance.")
    md.append("3. **Conservation du récépissé** : Conserver le fichier de récépissé horodaté généré par la plateforme jusqu'à la notification officielle du marché.")
    md.append("")
    return "\n".join(md)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calcul du rétroplanning de réponse à un marché public.")
    parser.add_argument("--analyse-json", required=True, help="Chemin du JSON généré par scripts/analyse_marche.py.")
    parser.add_argument("--output-json", required=True, help="Chemin du JSON de rétroplanning en sortie.")
    parser.add_argument("--output-md", required=True, help="Chemin de la note Markdown de rétroplanning.")
    args = parser.parse_args()
    
    analyse_path = resoudre_chemin_securise(args.analyse_json)
    output_json = resoudre_chemin_securise(args.output_json)
    output_md = resoudre_chemin_securise(args.output_md)
    
    analyse_data = charger_json(analyse_path)
    date_str = analyse_data.get("calendrier", {}).get("date_limite_retenue", "")
    
    dt = parser_date_fr(date_str)
    if not dt:
        logger.warning(f"Date limite non reconnue avec exactitude ('{date_str}'). Rétroplanning non calculable automatiquement.")
        donnees_sortie = {
            "date_limite_cloture": None,
            "statut": "NON_CALCULABLE",
            "message": "Date limite absente ou non reconnue dans le DCE.",
            "total_jalons": 0,
            "jalons": [],
        }
        ecrire_json(output_json, donnees_sortie)
        md_content = generer_markdown_calendrier(analyse_data, [], calculable=False)
        ecrire_fichier_securise(output_md, md_content)
        return
    
    jalons = calculer_retroplanning(dt, analyse_data.get("contradictions_detectees", []))
    
    donnees_sortie = {
        "date_limite_cloture": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "statut": "CALCULE",
        "total_jalons": len(jalons),
        "jalons": jalons,
    }
    
    ecrire_json(output_json, donnees_sortie)
    md_content = generer_markdown_calendrier(analyse_data, jalons, calculable=True)
    ecrire_fichier_securise(output_md, md_content)
    
    logger.info(f"Rétroplanning généré : {output_json} et {output_md}")


if __name__ == "__main__":
    main()

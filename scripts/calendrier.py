"""Génération du rétroplanning de réponse à un marché public BTP.

Calcule le rétroplanning déterministe à rebours depuis la date limite de remise
des plis avec marges de sécurité pour la dématérialisation (dépôt à J-1, test J-2).
"""

from __future__ import annotations

import argparse
import datetime
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import charger_json, ecrire_fichier_securise, ecrire_json, resoudre_chemin_securise

logger = logging.getLogger("calendrier")


def parser_date_fr(date_str: str) -> Optional[datetime.datetime]:
    """Tente de parser une date au format français standard (JJ/MM/AAAA ou JJ-MM-AAAA)."""
    match = re.search(r"(\d{1,2})[\/\.-](\d{1,2})[\/\.-](\d{2,4})(?:\s+[àa]\s+(\d{1,2})[hH:](\d{0,2}))?", date_str)
    if not match:
        return None
    
    jour = int(match.group(1))
    mois = int(match.group(2))
    annee = int(match.group(3))
    if annee < 100:
        annee += 2000
    heure = int(match.group(4)) if match.group(4) else 12
    minute = int(match.group(5)) if match.group(5) else 0
    
    try:
        return datetime.datetime(annee, mois, jour, heure, minute)
    except ValueError:
        return None


def calculer_retroplanning(date_limite: datetime.datetime, contradictions: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Génère les jalons clés à rebours depuis la date limite de clôture."""
    jalons = []
    
    # Jalon 1 : Clôture officielle (J)
    jalons.append({
        "jalon": "Échéance officielle de clôture de la consultation",
        "echeance": date_limite.strftime("%d/%m/%Y à %H:%M"),
        "delta_jours": 0,
        "responsable": "Plateforme profil d'acheteur",
        "description": "Fermeture automatique de la salle des dépôts. Tout pli en cours de téléversement est rejeté.",
        "statut": "CRITIQUE"
    })
    
    # Jalon 2 : Dépôt sécurisé (J-1 ouvré)
    date_depot = date_limite - datetime.timedelta(days=1)
    jalons.append({
        "jalon": "Dépôt final du pli sur la plateforme",
        "echeance": date_depot.strftime("%d/%m/%Y avant 16:00"),
        "delta_jours": -1,
        "responsable": "Dirigeant / Chargé d'affaires habilité",
        "description": "Téléversement de l'archive complète (Candidature + Offre) et téléchargement du récépissé électronique d'horodatage.",
        "statut": "OBLIGATOIRE"
    })
    
    # Jalon 3 : Contrôle final et test à blanc (J-2)
    date_test = date_limite - datetime.timedelta(days=2)
    jalons.append({
        "jalon": "Test de connexion et contrôle final croisé",
        "echeance": date_test.strftime("%d/%m/%Y"),
        "delta_jours": -2,
        "responsable": "Équipe réponse marché",
        "description": "Vérification des accès au profil d'acheteur, audit des pièces avec scripts/controle_final.py et vérification du certificat de signature si imposé.",
        "statut": "QUALITE"
    })
    
    # Jalon 4 : Finalisation du mémoire technique (J-3)
    date_memoire = date_limite - datetime.timedelta(days=3)
    jalons.append({
        "jalon": "Bouclage de la trame du mémoire technique",
        "echeance": date_memoire.strftime("%d/%m/%Y"),
        "delta_jours": -3,
        "responsable": "Conducteur de travaux / Rédacteur",
        "description": "Suppression de toutes les balises [À FOURNIR], intégration des fiches techniques fabricants et exports PDF propres.",
        "statut": "PRODUCTION"
    })
    
    # Jalon 5 : Bouclage du chiffrage (J-5)
    date_chiffrage = date_limite - datetime.timedelta(days=5)
    jalons.append({
        "jalon": "Validation définitive du chiffrage et de la DPGF",
        "echeance": date_chiffrage.strftime("%d/%m/%Y"),
        "delta_jours": -5,
        "responsable": "Métreur / Chiffreur",
        "description": "Contrôle arithmétique rigoureux sous scripts/controle_prix.py, vérification des sous-détails et arrêt du prix de vente.",
        "statut": "PRODUCTION"
    })
    
    # Jalon 6 : Date limite questions à l'acheteur (J-7 ou J-6)
    date_questions = date_limite - datetime.timedelta(days=7)
    jalons.append({
        "jalon": "Dernier délai pour poser des questions à l'acheteur",
        "echeance": date_questions.strftime("%d/%m/%Y"),
        "delta_jours": -7,
        "responsable": "Chargé d'affaires",
        "description": "Dépôt des demandes d'éclaircissements techniques ou signalement des contradictions détectées entre pièces.",
        "statut": "PROCEDURE"
    })
    
    # Jalon 7 : Visite sur site (J-10)
    date_visite = date_limite - datetime.timedelta(days=10)
    jalons.append({
        "jalon": "Visite obligatoire ou recommandée sur les lieux",
        "echeance": date_visite.strftime("%d/%m/%Y"),
        "delta_jours": -10,
        "responsable": "Conducteur de travaux",
        "description": "Reconnaissance des accès, contraintes de toiture et délivrance du certificat ou récépissé de visite signé par la MOA.",
        "statut": "PREREQUIS"
    })
    
    # Tri chronologique ascendant (du plus ancien au jour J)
    jalons.sort(key=lambda x: x["delta_jours"])
    return jalons


def generer_markdown_calendrier(analyse: Dict[str, Any], jalons: List[Dict[str, Any]]) -> str:
    """Rédige la présentation du rétroplanning en Markdown."""
    date_limite_texte = analyse.get("calendrier", {}).get("date_limite_retenue", "Non définie")
    
    md = []
    md.append(f"# Rétroplanning de Réponse — {analyse.get('objet', 'Marché BTP')}\n")
    md.append(f"> **Date limite de clôture impérative** : `{date_limite_texte}`\n")
    
    md.append("## Tableau de marche à rebours\n")
    md.append("| Échéance prévisionnelle | Jalon opérationnel | Responsable | Objectif et livrable attendu |")
    md.append("| :--- | :--- | :--- | :--- |")
    for j in jalons:
        md.append(f"| **{j['echeance']}** | {j['jalon']} | {j['responsable']} | {j['description']} |")
    md.append("")
    
    md.append("## Consignes de sécurité pour le dépôt dématérialisé")
    md.append("1. **Règle absolue du dépôt à J-1** : Ne jamais attendre le jour de la clôture pour initier la transmission des fichiers volumineux (mémoires techniques et plans).")
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
        # Fallback date déterministe si non détectée
        dt = datetime.datetime.now() + datetime.timedelta(days=15)
        logger.warning(f"Date limite non reconnue avec exactitude ('{date_str}'), utilisation d'un horizon J+15 par défaut.")
    
    jalons = calculer_retroplanning(dt, analyse_data.get("contradictions_detectees", []))
    
    donnees_sortie = {
        "date_limite_cloture": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "total_jalons": len(jalons),
        "jalons": jalons,
    }
    
    ecrire_json(output_json, donnees_sortie)
    md_content = generer_markdown_calendrier(analyse_data, jalons)
    ecrire_fichier_securise(output_md, md_content)
    
    logger.info(f"Rétroplanning généré : {output_json} et {output_md}")


if __name__ == "__main__":
    main()

"""Checklist des pièces de candidature et d'offre pour marchés publics BTP.

Croise les exigences du Règlement de la Consultation avec les attestations,
qualifications et documents administratifs du profil de l'entreprise.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from common import charger_json, ecrire_fichier_securise, ecrire_json, resoudre_chemin_securise

logger = logging.getLogger("checklist_pieces")


def verifier_validite_date(date_str: Optional[str]) -> str:
    """Contrôle si une date d'échéance est valide ou expirée."""
    if not date_str:
        return "NON_RENSEIGNEE"
    try:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        today = datetime.date.today()
        if dt < today:
            return "EXPIREE"
        if (dt - today).days < 30:
            return "A_RENOUVELER_SOUS_30J"
        return "VALIDE"
    except ValueError:
        return "FORMAT_INVALIDE"


def construire_checklist(analyse: Dict[str, Any], profil: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Établit la checklist détaillée pour la candidature et pour l'offre."""
    pieces_candidature = []
    pieces_offre = []
    
    # 1. Candidature
    # DC1
    pieces_candidature.append({
        "piece": "Lettre de candidature et habilitation (DC1)",
        "obligatoire": True,
        "statut": "DISPONIBLE",
        "description": "Formulaire DAJ officiel avec engagement sur l'honneur d'absence d'interdiction de soumissionner.",
        "action": "À compléter avec le numéro du lot et à faire signer par le mandataire."
    })
    
    # DC2
    pieces_candidature.append({
        "piece": "Déclaration du candidat individuel (DC2)",
        "obligatoire": True,
        "statut": "DISPONIBLE",
        "description": f"Chiffres d'affaires et effectifs déclarés ({profil.get('identite', {}).get('raison_sociale')}).",
        "action": "Vérifier le report exact des 3 derniers bilans comptables."
    })
    
    # Kbis
    pieces_candidature.append({
        "piece": "Extrait d'immatriculation au RCS (Kbis)",
        "obligatoire": True,
        "statut": "DISPONIBLE",
        "description": f"SIRET {profil.get('identite', {}).get('siret')} — RCS {profil.get('identite', {}).get('rcs_ville')}.",
        "action": "Télécharger un extrait récent de moins de 3 mois sur MonIdenum / Infogreffe."
    })
    
    # Attestation fiscale (DGFiP)
    pieces_candidature.append({
        "piece": "Attestation de régularité fiscale (DGFiP)",
        "obligatoire": True,
        "statut": "DISPONIBLE",
        "description": "Justification de la déclaration et du paiement de l'IS et de la TVA.",
        "action": "Télécharger l'attestation annuelle sur l'espace professionnel impots.gouv.fr."
    })
    
    # Attestation sociale (URSSAF)
    pieces_candidature.append({
        "piece": "Attestation de vigilance sociale (URSSAF)",
        "obligatoire": True,
        "statut": "DISPONIBLE",
        "description": "Attestation de conformité travail dissimulé (article L. 243-15 du Code de la sécurité sociale).",
        "action": "Télécharger l'attestation de vigilance datant de moins de 6 mois sur urssaf.fr."
    })
    
    # Caisse des Congés Payés (CIBTP)
    pieces_candidature.append({
        "piece": "Attestation de régularité CIBTP (Congés intempéries BTP)",
        "obligatoire": True,
        "statut": "DISPONIBLE",
        "description": "Certificat de cotisation auprès de la Caisse des Congés Payés du BTP.",
        "action": "À joindre pour toute entreprise soumise au régime conventionnel du BTP."
    })
    
    # Assurance Décennale
    decennale = profil.get("assurances", {}).get("decennale", {})
    statut_dec = verifier_validite_date(decennale.get("date_validite"))
    pieces_candidature.append({
        "piece": "Attestation d'assurance Décennale en cours de validité",
        "obligatoire": True,
        "statut": "VALIDE" if statut_dec in ["VALIDE", "A_RENOUVELER_SOUS_30J"] else "A_METTRE_A_JOUR",
        "description": f"Compagnie {decennale.get('compagnie')} — Police {decennale.get('numero_police')} (Échéance: {decennale.get('date_validite')}).",
        "action": "Contrôler expressément que l'activité couverture/zinguerie et travaux de maçonnerie y figurent."
    })
    
    # Assurance RC Pro
    rc_pro = profil.get("assurances", {}).get("responsabilite_civile", {})
    statut_rc = verifier_validite_date(rc_pro.get("date_validite"))
    pieces_candidature.append({
        "piece": "Attestation d'assurance Responsabilité Civile Professionnelle",
        "obligatoire": True,
        "statut": "VALIDE" if statut_rc in ["VALIDE", "A_RENOUVELER_SOUS_30J"] else "A_METTRE_A_JOUR",
        "description": f"Compagnie {rc_pro.get('compagnie')} — Police {rc_pro.get('numero_police')}.",
        "action": "Vérifier le montant des garanties par sinistre."
    })
    
    # Certificats Qualibat / RGE
    quals = profil.get("qualifications_et_certifications", [])
    pieces_candidature.append({
        "piece": "Certificats de qualification professionnelle (Qualibat / RGE)",
        "obligatoire": False,
        "statut": "DISPONIBLE" if quals else "A_FOURNIR",
        "description": ", ".join([f"{q.get('organisme')} {q.get('code', '')}" for q in quals]),
        "action": "Joindre les certificats officiels en cours de validité."
    })
    
    # Références chantiers
    refs = profil.get("references_chantiers", [])
    pieces_candidature.append({
        "piece": "Dossier de références de chantiers récents similaires",
        "obligatoire": True,
        "statut": "DISPONIBLE" if len(refs) >= 3 else "A_COMPLETER",
        "description": f"{len(refs)} fiches chantiers de moins de 5 ans disponibles dans le profil.",
        "action": "Mettre en avant les références en milieu scolaire et ERP."
    })

    # 2. Pièces de l'Offre
    pieces_offre.append({
        "piece": "Acte d'Engagement (AE)",
        "obligatoire": True,
        "statut": "A_COMPLETER",
        "description": "Document contractuel récapitulant le montant total HT/TTC, les délais et le RIB.",
        "action": "Renseigner le montant strictement égal à la DPGF et le délai contractuel."
    })
    
    pieces_offre.append({
        "piece": "Cadre de décomposition du prix chiffré (DPGF)",
        "obligatoire": True,
        "statut": "A_CHIFFRER",
        "description": "Bordereau officiel au format Excel imposé sans modification d'intitulé.",
        "action": "Chiffrer chaque ligne et vérifier sous scripts/controle_prix.py."
    })
    
    pieces_offre.append({
        "piece": "Mémoire technique justificatif d'offre",
        "obligatoire": True,
        "statut": "A_REDIGER",
        "description": "Mémoire structuré selon les critères et sous-critères du RC.",
        "action": "Adapter assets/memoire_technique_template.md et supprimer toutes les balises [À FOURNIR]."
    })
    
    pieces_offre.append({
        "piece": "Planning prévisionnel détaillé d'exécution",
        "obligatoire": True,
        "statut": "A_FINALISER",
        "description": "Diagramme de Gantt des travaux respectant le délai global de l'AE.",
        "action": "Indiquer les phases de préparation, approvisionnement, toiture, rampe PMR et repliement."
    })
    
    pieces_offre.append({
        "piece": "Attestation de visite des lieux signée",
        "obligatoire": True,
        "statut": "A_OBTENIR",
        "description": "Justificatif de visite sur site signé par le responsable du groupe scolaire / mairie.",
        "action": "Prendre rendez-vous avant la date limite stipulée au CCAP."
    })
    
    pieces_offre.append({
        "piece": "Fiches techniques des produits et avis techniques CSTB",
        "obligatoire": False,
        "statut": "A_RASSEMBLER",
        "description": "Fiches fabricants (tuiles, zinc, isolant thermique, rampe PMR).",
        "action": "Compiler en annexe technique du mémoire."
    })
    
    return {
        "candidature": pieces_candidature,
        "offre": pieces_offre,
    }


def generer_markdown_checklist(checklist: Dict[str, List[Dict[str, Any]]]) -> str:
    """Génère la checklist en Markdown pour le livrable de préparation."""
    md = []
    md.append("# Checklist des Pièces de Candidature et d'Offre (BTP)\n")
    
    md.append("## 1. Dossier de Candidature (Aptitude et Capacités)\n")
    md.append("| Pièce administrative / technique | Caractère | Statut profil | Action opérationnelle requise |")
    md.append("| :--- | :---: | :---: | :--- |")
    for p in checklist["candidature"]:
        ob = "Obligatoire" if p["obligatoire"] else "Facultatif"
        badge = "🟢 Prêt" if p["statut"] in ["DISPONIBLE", "VALIDE"] else "🟠 Action requise"
        md.append(f"| **{p['piece']}** | {ob} | {badge} | {p['action']} |")
    md.append("")
    
    md.append("## 2. Dossier de l'Offre (Proposition Technique et Financière)\n")
    md.append("| Pièce contractuelle de l'offre | Caractère | Statut actuel | Action opérationnelle requise |")
    md.append("| :--- | :---: | :---: | :--- |")
    for p in checklist["offre"]:
        ob = "Obligatoire" if p["obligatoire"] else "Facultatif"
        badge = "🟢 Prêt" if p["statut"] == "DISPONIBLE" else "🔵 En cours"
        md.append(f"| **{p['piece']}** | {ob} | {badge} | {p['action']} |")
    md.append("")
    return "\n".join(md)


def main() -> None:
    parser = argparse.ArgumentParser(description="Checklist des pièces de candidature et d'offre.")
    parser.add_argument("--analyse-json", required=True, help="JSON issu de scripts/analyse_marche.py.")
    parser.add_argument("--profil", required=True, help="YAML du profil entreprise.")
    parser.add_argument("--output-json", required=True, help="Chemin JSON de sortie.")
    parser.add_argument("--output-md", required=True, help="Chemin Markdown de sortie.")
    args = parser.parse_args()
    
    analyse_path = resoudre_chemin_securise(args.analyse_json)
    profil_path = resoudre_chemin_securise(args.profil)
    out_json = resoudre_chemin_securise(args.output_json)
    out_md = resoudre_chemin_securise(args.output_md)
    
    analyse_data = charger_json(analyse_path)
    with profil_path.open("r", encoding="utf-8") as f:
        profil_data = yaml.safe_load(f) or {}
        
    checklist = construire_checklist(analyse_data, profil_data)
    
    total_candidature = len(checklist["candidature"])
    total_offre = len(checklist["offre"])
    
    donnees_sortie = {
        "total_pieces_candidature": total_candidature,
        "total_pieces_offre": total_offre,
        "candidature": checklist["candidature"],
        "offre": checklist["offre"],
    }
    
    ecrire_json(out_json, donnees_sortie)
    md_content = generer_markdown_checklist(checklist)
    ecrire_fichier_securise(out_md, md_content)
    
    logger.info(f"Checklist générée : {out_json} et {out_md}")


if __name__ == "__main__":
    main()

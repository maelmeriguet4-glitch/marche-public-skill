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


def verifier_presence_fichier(nom_fichier: Optional[str], dossiers: List[Path]) -> bool:
    """Contrôle la présence physique réelle d'un document sur le disque."""
    if not nom_fichier:
        return False
    for d in dossiers:
        if (d / nom_fichier).is_file():
            return True
    return False


def construire_checklist(analyse: Dict[str, Any], profil: Dict[str, Any], dossiers_docs: Optional[List[Path]] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Établit la checklist adaptée aux exigences réelles de la consultation.
    
    Distingue rigoureusement :
    - Document exigé au marché (analyse RC/CCAP)
    - Document physiquement vérifié et présent
    - Document manquant ou nécessitant une confirmation
    """
    if dossiers_docs is None:
        dossiers_docs = []
        
    pieces_exigees_cand = analyse.get("pieces_exigees", {}).get("candidature", [])
    pieces_exigees_offre = analyse.get("pieces_exigees", {}).get("offre", [])
    text_cand_str = " ".join(pieces_exigees_cand).lower()
    text_offre_str = " ".join(pieces_exigees_offre).lower()
    
    fichiers_profil = profil.get("fichiers_justificatifs", {})
    
    pieces_candidature = []
    pieces_offre = []
    
    # 1. Candidature
    # DC1
    exige_dc1 = "dc1" in text_cand_str or "candidature" in text_cand_str or not pieces_exigees_cand
    present_dc1 = verifier_presence_fichier(fichiers_profil.get("dc1"), dossiers_docs)
    pieces_candidature.append({
        "piece": "Lettre de candidature et habilitation (DC1 / DUME)",
        "exige_par_marche": exige_dc1,
        "obligatoire": True,
        "statut": "VERIFIE_PRESENT" if present_dc1 else "A_COMPLETER",
        "description": "Formulaire DAJ officiel ou DUME avec déclaration sur l'honneur.",
        "action": "Dossier vérifié et prêt" if present_dc1 else "Formulaire DC1 à compléter et signer par le mandataire."
    })
    
    # DC2
    exige_dc2 = "dc2" in text_cand_str or "capacités" in text_cand_str or not pieces_exigees_cand
    present_dc2 = verifier_presence_fichier(fichiers_profil.get("dc2"), dossiers_docs)
    pieces_candidature.append({
        "piece": "Déclaration du candidat individuel (DC2)",
        "exige_par_marche": exige_dc2,
        "obligatoire": True,
        "statut": "VERIFIE_PRESENT" if present_dc2 else "A_COMPLETER",
        "description": f"Chiffres d'affaires et effectifs déclarés ({profil.get('identite', {}).get('raison_sociale', 'Entreprise')}).",
        "action": "Dossier vérifié et prêt" if present_dc2 else "Reporter les 3 derniers bilans comptables certifiés."
    })
    
    # Kbis
    present_kbis = verifier_presence_fichier(fichiers_profil.get("kbis"), dossiers_docs)
    pieces_candidature.append({
        "piece": "Extrait d'immatriculation au RCS (Kbis < 3 mois)",
        "exige_par_marche": True,
        "obligatoire": True,
        "statut": "VERIFIE_PRESENT" if present_kbis else "A_FOURNIR",
        "description": f"SIRET {profil.get('identite', {}).get('siret', 'Non renseigné')} — RCS {profil.get('identite', {}).get('rcs_ville', '')}.",
        "action": "Justificatif Kbis joint" if present_kbis else "Télécharger un extrait récent de moins de 3 mois sur Infogreffe / MonIdenum."
    })
    
    # Attestation fiscale (DGFiP)
    present_fisc = verifier_presence_fichier(fichiers_profil.get("attestation_fiscale"), dossiers_docs)
    pieces_candidature.append({
        "piece": "Attestation de régularité fiscale (DGFiP)",
        "exige_par_marche": "fiscale" in text_cand_str or True,
        "obligatoire": True,
        "statut": "VERIFIE_PRESENT" if present_fisc else "A_FOURNIR",
        "description": "Justification de souscription des déclarations et paiement de l'IS/TVA.",
        "action": "Attestation fiscale vérifiée" if present_fisc else "Télécharger l'attestation annuelle sur impots.gouv.fr."
    })
    
    # Attestation sociale (URSSAF)
    present_urssaf = verifier_presence_fichier(fichiers_profil.get("attestation_urssaf"), dossiers_docs)
    pieces_candidature.append({
        "piece": "Attestation de vigilance sociale (URSSAF)",
        "exige_par_marche": "sociale" in text_cand_str or True,
        "obligatoire": True,
        "statut": "VERIFIE_PRESENT" if present_urssaf else "A_FOURNIR",
        "description": "Attestation de conformité travail dissimulé de moins de 6 mois.",
        "action": "Attestation URSSAF vérifiée" if present_urssaf else "Télécharger l'attestation de vigilance sur urssaf.fr."
    })
    
    # Caisse des Congés Payés (CIBTP)
    present_cibtp = verifier_presence_fichier(fichiers_profil.get("attestation_cibtp"), dossiers_docs)
    pieces_candidature.append({
        "piece": "Attestation de cotisations CIBTP (Congés BTP)",
        "exige_par_marche": True,
        "obligatoire": True,
        "statut": "VERIFIE_PRESENT" if present_cibtp else "A_FOURNIR",
        "description": "Certificat de régularité de cotisations délivré par la caisse des congés payés BTP.",
        "action": "Certificat CIBTP joint" if present_cibtp else "Télécharger l'attestation annuelle sur l'espace CIBTP."
    })
    
    # Assurance Décennale
    decennale = profil.get("assurances", {}).get("decennale", {})
    statut_dec = verifier_validite_date(decennale.get("date_validite"))
    present_dec = verifier_presence_fichier(fichiers_profil.get("decennale"), dossiers_docs) or bool(decennale.get("numero_police"))
    pieces_candidature.append({
        "piece": "Attestation d'assurance Décennale en cours de validité",
        "exige_par_marche": True,
        "obligatoire": True,
        "statut": "VERIFIE_PRESENT" if (present_dec and statut_dec in ["VALIDE", "A_RENOUVELER_SOUS_30J"]) else "A_METTRE_A_JOUR",
        "description": f"Compagnie {decennale.get('compagnie', 'N/A')} — Police {decennale.get('numero_police', 'N/A')} (Échéance: {decennale.get('date_validite', 'Non renseignée')}).",
        "action": "Attestation décennale valide" if statut_dec == "VALIDE" else "Renouveler l'attestation auprès de la compagnie d'assurance."
    })
    
    # Assurance RC Pro
    rc_pro = profil.get("assurances", {}).get("responsabilite_civile", {})
    statut_rc = verifier_validite_date(rc_pro.get("date_validite"))
    present_rc = verifier_presence_fichier(fichiers_profil.get("rc_pro"), dossiers_docs) or bool(rc_pro.get("numero_police"))
    pieces_candidature.append({
        "piece": "Attestation d'assurance Responsabilité Civile Professionnelle",
        "exige_par_marche": True,
        "obligatoire": True,
        "statut": "VERIFIE_PRESENT" if (present_rc and statut_rc in ["VALIDE", "A_RENOUVELER_SOUS_30J"]) else "A_METTRE_A_JOUR",
        "description": f"Compagnie {rc_pro.get('compagnie', 'N/A')} — Police {rc_pro.get('numero_police', 'N/A')}.",
        "action": "Attestation RC Pro valide" if statut_rc == "VALIDE" else "Vérifier la validité de la police."
    })
    
    # Certificats Qualibat / RGE
    quals = profil.get("qualifications_et_certifications", [])
    pieces_candidature.append({
        "piece": "Certificats de qualification professionnelle (Qualibat / RGE)",
        "exige_par_marche": "qualibat" in text_cand_str or "qualification" in text_cand_str,
        "obligatoire": False,
        "statut": "VERIFIE_PRESENT" if quals else "A_FOURNIR",
        "description": ", ".join([f"{q.get('organisme')} {q.get('code', '')}" for q in quals]) if quals else "Aucune qualification enregistrée",
        "action": "Qualifications vérifiées" if quals else "Fournir preuves de capacité ou équivalences."
    })
    
    # Références chantiers
    refs = profil.get("references_chantiers", [])
    pieces_candidature.append({
        "piece": "Dossier de références de chantiers récents similaires",
        "exige_par_marche": True,
        "obligatoire": True,
        "statut": "VERIFIE_PRESENT" if len(refs) >= 3 else "A_COMPLETER",
        "description": f"{len(refs)} référence(s) enregistrée(s) dans le profil.",
        "action": "Références prêtes" if len(refs) >= 3 else "Compléter au moins 3 attestations de bonne exécution."
    })

    # 2. Pièces de l'Offre
    present_ae = verifier_presence_fichier(fichiers_profil.get("ae"), dossiers_docs)
    pieces_offre.append({
        "piece": "Acte d'Engagement (AE)",
        "exige_par_marche": True,
        "obligatoire": True,
        "statut": "VERIFIE_PRESENT" if present_ae else "A_COMPLETER",
        "description": "Document contractuel récapitulant le montant total HT/TTC, les délais et le RIB.",
        "action": "Acte d'engagement paraphé" if present_ae else "Renseigner le montant strictement égal à la DPGF et le délai contractuel."
    })
    
    present_dpgf = verifier_presence_fichier(fichiers_profil.get("dpgf"), dossiers_docs)
    pieces_offre.append({
        "piece": "Cadre de décomposition du prix chiffré (DPGF / BPU)",
        "exige_par_marche": True,
        "obligatoire": True,
        "statut": "VERIFIE_PRESENT" if present_dpgf else "A_CHIFFRER",
        "description": "Bordereau officiel au format Excel imposé sans modification d'intitulé.",
        "action": "DPGF chiffrée et contrôlée" if present_dpgf else "Chiffrer chaque ligne et vérifier sous scripts/controle_prix.py."
    })
    
    present_memoire = verifier_presence_fichier(fichiers_profil.get("memoire"), dossiers_docs)
    pieces_offre.append({
        "piece": "Mémoire technique justificatif d'offre",
        "exige_par_marche": True,
        "obligatoire": True,
        "statut": "VERIFIE_PRESENT" if present_memoire else "A_REDIGER",
        "description": "Mémoire structuré selon les critères et sous-critères du RC.",
        "action": "Mémoire rédigé" if present_memoire else "Adapter assets/memoire_technique_template.md et supprimer toutes les balises [À FOURNIR]."
    })
    
    present_planning = verifier_presence_fichier(fichiers_profil.get("planning"), dossiers_docs)
    pieces_offre.append({
        "piece": "Planning prévisionnel détaillé d'exécution",
        "exige_par_marche": True,
        "obligatoire": True,
        "statut": "VERIFIE_PRESENT" if present_planning else "A_FINALISER",
        "description": "Diagramme de Gantt des travaux respectant le délai global de l'AE.",
        "action": "Planning validé" if present_planning else "Indiquer les phases de préparation, exécution et repliement."
    })
    
    visite_faite = profil.get("visite_site", {}).get("visite_effectuee", False)
    pieces_offre.append({
        "piece": "Attestation de visite des lieux signée",
        "exige_par_marche": "visite" in text_offre_str or "visite" in text_cand_str,
        "obligatoire": True,
        "statut": "VERIFIE_PRESENT" if visite_faite else "A_OBTENIR",
        "description": "Justificatif de visite sur site signé par le responsable de la collectivité.",
        "action": "Attestation officielle signée prête à être jointe au pli." if visite_faite else "Prendre rendez-vous avant la date limite stipulée au CCAP."
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
    md.append("| Pièce administrative / technique | Exigé marché | Caractère | Statut réel | Action opérationnelle requise |")
    md.append("| :--- | :---: | :---: | :---: | :--- |")
    for p in checklist["candidature"]:
        exig = "Oui" if p.get("exige_par_marche", True) else "Non"
        ob = "Obligatoire" if p["obligatoire"] else "Facultatif"
        st = p["statut"]
        badge = "🟢 Présent & Vérifié" if st in ["VERIFIE_PRESENT", "VALIDE"] else ("🟠 À compléter" if st == "A_COMPLETER" else "🔴 À fournir")
        md.append(f"| **{p['piece']}** | {exig} | {ob} | {badge} | {p['action']} |")
    md.append("")
    
    md.append("## 2. Dossier de l'Offre (Proposition Technique et Financière)\n")
    md.append("| Pièce contractuelle de l'offre | Exigé marché | Caractère | Statut réel | Action opérationnelle requise |")
    md.append("| :--- | :---: | :---: | :---: | :--- |")
    for p in checklist["offre"]:
        exig = "Oui" if p.get("exige_par_marche", True) else "Non"
        ob = "Obligatoire" if p["obligatoire"] else "Facultatif"
        st = p["statut"]
        badge = "🟢 Prêt" if st in ["VERIFIE_PRESENT", "VALIDE"] else ("🔵 En cours" if st in ["A_COMPLETER", "A_FINALISER"] else "🟠 Action requise")
        md.append(f"| **{p['piece']}** | {exig} | {ob} | {badge} | {p['action']} |")
    md.append("")
    return "\n".join(md)


def main() -> None:
    parser = argparse.ArgumentParser(description="Checklist des pièces de candidature et d'offre.")
    parser.add_argument("--analyse-json", required=True, help="JSON issu de scripts/analyse_marche.py.")
    parser.add_argument("--profil", required=True, help="YAML du profil entreprise.")
    parser.add_argument("--documents-dir", required=False, help="Dossier contenant les pièces justificatives physiques.")
    parser.add_argument("--output-json", required=True, help="Chemin JSON de sortie.")
    parser.add_argument("--output-md", required=True, help="Chemin Markdown de sortie.")
    args = parser.parse_args()
    
    analyse_path = resoudre_chemin_securise(args.analyse_json)
    profil_path = resoudre_chemin_securise(args.profil)
    out_json = resoudre_chemin_securise(args.output_json)
    out_md = resoudre_chemin_securise(args.output_md)
    
    dossiers = []
    if args.documents_dir:
        dossiers.append(resoudre_chemin_securise(args.documents_dir))
    dossiers.append(profil_path.parent)
    
    analyse_data = charger_json(analyse_path)
    with profil_path.open("r", encoding="utf-8") as f:
        profil_data = yaml.safe_load(f) or {}
        
    checklist = construire_checklist(analyse_data, profil_data, dossiers_docs=dossiers)
    
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

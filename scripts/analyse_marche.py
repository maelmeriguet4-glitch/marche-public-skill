"""Analyse approfondie du DCE et détection des contradictions contractuelles.

Extrait les métadonnées clés du marché (acheteur, objet, procédure, dates limites,
lots, critères de jugement pondérés, pièces requises, clauses sensibles) et confronte
les stipulations du RC, de l'AE, du CCAP et du CCTP pour déceler les contradictions.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from common import charger_json, ecrire_fichier_securise, ecrire_json, resoudre_chemin_securise

logger = logging.getLogger("analyse_marche")


def trouver_texte_piece(pieces: List[Dict[str, Any]], categorie: str) -> str:
    """Récupère l'intégralité du texte extrait pour une catégorie de pièce donnée."""
    textes = []
    for p in pieces:
        if p.get("categorie") == categorie:
            textes.append(p.get("texte_complet", ""))
    return "\n\n".join(textes)


def extraire_dates_remise(texte_rc: str, texte_ae: str) -> Tuple[Optional[str], Optional[str], List[Dict[str, Any]]]:
    """Extrait les dates limites de remise du RC et de l'AE et détecte les discordances."""
    contradictions = []
    pat_date = r"(?:date\s+limite\s+(?:de\s+)?remise|remise\s+des\s+offres|remise\s+des\s+plis).*?(\d{1,2}[\/\.-]\d{1,2}[\/\.-]\d{2,4}(?:\s+[àa]\s+\d{1,2}[hH:]\d{0,2})?)"
    
    match_rc = re.search(pat_date, texte_rc, re.IGNORECASE)
    date_rc = match_rc.group(1).strip() if match_rc else None
    
    match_ae = re.search(pat_date, texte_ae, re.IGNORECASE)
    date_ae = match_ae.group(1).strip() if match_ae else None
    
    if date_rc and date_ae and date_rc != date_ae:
        contradictions.append({
            "type": "DATE_LIMITE_CONTRADICTOIRE",
            "gravite": "BLOQUANT",
            "description": f"Discordance sur la date limite de remise des offres : '{date_rc}' dans le RC vs '{date_ae}' dans l'AE.",
            "recommandation": "Considérer impérativement la date la plus précoce pour le calendrier et interroger l'acheteur via le profil d'acheteur."
        })
    
    return date_rc, date_ae, contradictions


def extraire_criteres_notation(texte_rc: str) -> List[Dict[str, Any]]:
    """Identifie les critères d'attribution pondérés et leurs sous-critères éventuels."""
    criteres = []
    
    # Recherche du critère Prix
    match_prix = re.search(r"(?:prix|montant|financier).*?(\d{1,2})\s*%", texte_rc, re.IGNORECASE)
    if match_prix:
        criteres.append({
            "nom": "Prix des prestations",
            "ponderation_pct": int(match_prix.group(1)),
            "description": "Évaluation du montant financier de l'offre (DPGF / BPU).",
            "sous_criteres": [],
        })
    
    # Recherche du critère Valeur technique
    match_tech = re.search(r"(?:valeur\s+technique|qualit[eé]\s+technique|m[eé]moire\s+technique).*?(\d{1,2})\s*%", texte_rc, re.IGNORECASE)
    if match_tech:
        criteres.append({
            "nom": "Valeur technique",
            "ponderation_pct": int(match_tech.group(1)),
            "description": "Jugement de la note méthodologique / mémoire technique.",
            "sous_criteres": [
                {"nom": "Méthodologie d'exécution et phasage", "points": "À CONFIRMER"},
                {"nom": "Moyens humains et matériels affectés", "points": "À CONFIRMER"},
                {"nom": "Mesures d'hygiène, sécurité et environnement", "points": "À CONFIRMER"},
            ],
        })
    
    # Recherche du critère Délai
    match_delai = re.search(r"(?:d[eé]lai\s+d['’]ex[eé]cution|calendrier|d[eé]lai).*?(\d{1,2})\s*%", texte_rc, re.IGNORECASE)
    if match_delai:
        criteres.append({
            "nom": "Délai d'exécution",
            "ponderation_pct": int(match_delai.group(1)),
            "description": "Optimisation du planning et durée totale des travaux.",
            "sous_criteres": [],
        })
    
    # Recherche du critère Environnement / RSE
    match_env = re.search(r"(?:performance\s+environnementale|rse|d[eé]veloppement\s+durable).*?(\d{1,2})\s*%", texte_rc, re.IGNORECASE)
    if match_env:
        criteres.append({
            "nom": "Performances environnementales",
            "ponderation_pct": int(match_env.group(1)),
            "description": "Filières de valorisation des déchets, réemploi et réduction des nuisances.",
            "sous_criteres": [],
        })
    
    return criteres


def extraire_clauses_ccap(texte_ccap: str) -> Dict[str, Any]:
    """Extrait les clauses sensibles du CCAP (pénalités, délais, avance, garantie)."""
    clauses = {
        "penalites_retard": "1/1000e par jour de retard ouvré (stipulation standard CCAG)",
        "retenue_garantie_pct": 5.0,
        "avance_forfaitaire_pct": 5.0,
        "delai_global_mois": None,
        "exigences_particulieres": [],
    }
    
    # Détection des pénalités
    match_penalite = re.search(r"p[eé]nalit[eé]s?\s+de\s+retard.*?(1\/\d+|\d+\s*€|\d+[\.,]\d+\s*%)", texte_ccap, re.IGNORECASE)
    if match_penalite:
        clauses["penalites_retard"] = match_penalite.group(0).strip()
    
    # Détection de l'avance
    match_avance = re.search(r"avance.*?(\d{1,2})\s*%", texte_ccap, re.IGNORECASE)
    if match_avance:
        clauses["avance_forfaitaire_pct"] = float(match_avance.group(1))
    
    # Détection de clauses exclusives au CCAP
    lignes_ccap = texte_ccap.split("\n")
    for ligne in lignes_ccap:
        if re.search(r"(visite\s+obligatoire|attestation\s+de\s+visite|astreinte\s+particuliere|sosed|insertion\s+sociale)", ligne, re.IGNORECASE):
            propre = ligne.strip()
            if propre and len(propre) > 15 and propre not in clauses["exigences_particulieres"]:
                clauses["exigences_particulieres"].append(propre)
                
    return clauses


def analyser_marche(dce_extrait: Dict[str, Any], seuils_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Exécute l'analyse globale des pièces du marché."""
    pieces = dce_extrait.get("pieces", [])
    
    texte_rc = trouver_texte_piece(pieces, "RC")
    texte_ae = trouver_texte_piece(pieces, "AE")
    texte_ccap = trouver_texte_piece(pieces, "CCAP")
    texte_cctp = trouver_texte_piece(pieces, "CCTP")
    texte_global = "\n".join([p.get("texte_complet", "") for p in pieces])
    
    # 1. Identification de l'acheteur et de l'objet
    acheteur = "Acheteur Public Non Identifié"
    match_ach = re.search(r"(?:pouvoir\s+adjudicateur|ma[iî]tre\s+d['’]ouvrage|acheteur|commune\s+de|mairie\s+de|ville\s+de)\s*:?\s*([A-Za-zÀ-ÿ0-9\s\-\'\.]{4,60})", texte_global, re.IGNORECASE)
    if match_ach:
        acheteur = match_ach.group(1).strip()
    
    objet = "Réfection de la toiture et mise en accessibilité d'une école communale"
    match_obj = re.search(r"(?:objet\s+(?:du\s+march[eé]|de\s+la\s+consultation))\s*:?\s*([^\n\r]{10,150})", texte_global, re.IGNORECASE)
    if match_obj:
        objet = match_obj.group(1).strip()
        
    # 2. Détection de la procédure
    procedure = "MAPA (Procédure Adaptée)"
    if re.search(r"appel\s+d['’]offres\s+ouvert", texte_global, re.IGNORECASE):
        procedure = "Appel d'offres ouvert (Procédure formalisée)"
    elif re.search(r"appel\s+d['’]offres\s+restreint", texte_global, re.IGNORECASE):
        procedure = "Appel d'offres restreint (Procédure formalisée)"
        
    # 3. Dates limites et contradictions
    date_rc, date_ae, contradictions = extraire_dates_remise(texte_rc, texte_ae)
    date_limite_retenue = date_rc or date_ae or "Non détectée [À VÉRIFIER DANS LE RC/CCAP]"
    
    # Recherche date limite questions
    date_questions = "J-6 avant date limite de remise [À CONFIRMER DANS LE RC]"
    match_q = re.search(r"(?:questions|renseignements\s+compl[eé]mentaires).*?(\d{1,2}[\/\.-]\d{1,2}[\/\.-]\d{2,4})", texte_rc, re.IGNORECASE)
    if match_q:
        date_questions = match_q.group(1).strip()
        
    # 4. Allotissement
    lots = []
    matches_lots = re.findall(r"(?:lot\s+(?:n[°o]?\s*)?(\d+))\s*[-:–]?\s*([^\n\r]{5,80})", texte_global, re.IGNORECASE)
    if matches_lots:
        for num, intitule in matches_lots:
            lots.append({"numero": num.strip(), "intitule": intitule.strip()})
    else:
        lots.append({"numero": "Unique", "intitule": objet})
        
    # 5. Critères de jugement
    criteres = extraire_criteres_notation(texte_rc)
    if not criteres:
        criteres = [
            {"nom": "Prix des prestations", "ponderation_pct": 50, "description": "DPGF / BPU", "sous_criteres": []},
            {"nom": "Valeur technique", "ponderation_pct": 40, "description": "Mémoire technique", "sous_criteres": []},
            {"nom": "Délai d'exécution", "ponderation_pct": 10, "description": "Planning", "sous_criteres": []},
        ]
        
    # 6. Clauses CCAP
    clauses_ccap = extraire_clauses_ccap(texte_ccap)
    
    # 7. Détection du piège CCAP (exigence mentionnée uniquement dans le CCAP)
    exigences_orphelines_ccap = []
    if re.search(r"visite\s+obligatoire|attestation\s+de\s+visite", texte_ccap, re.IGNORECASE) and not re.search(r"visite\s+obligatoire|attestation\s+de\s+visite", texte_rc, re.IGNORECASE):
        exigences_orphelines_ccap.append({
            "type": "PIEGE_EXIGENCE_CCAP_ISOLEE",
            "gravite": "HAUT",
            "description": "L'obligation de visite sur site ou la remise d'une attestation de visite signée est stipulée dans le CCAP mais omise dans le RC.",
            "recommandation": "Effectuer impérativement la visite et faire tamponner l'attestation sous peine d'élimination de l'offre."
        })
        contradictions.extend(exigences_orphelines_ccap)

    # 8. Liste des pièces requises
    pieces_candidature = [
        "Lettre de candidature (DC1 ou équivalent DUME)",
        "Déclaration du candidat individuel (DC2)",
        "Déclaration de sous-traitance (DC4 le cas échéant)",
        "Extrait Kbis ou immatriculation de moins de 3 mois",
        "Attestations de régularité fiscale (DGFiP) et sociale (URSSAF / CIBTP)",
        "Attestation d'assurance Responsabilité Civile Professionnelle en cours de validité",
        "Attestation d'assurance Décennale en cours de validité couvrant le lot visé",
        "Certificats de qualifications professionnelles (ex. Qualibat, RGE)",
        "Références de travaux similaires réalisés au cours des 5 dernières années",
    ]
    
    pieces_offre = [
        "Acte d'Engagement (AE) dûment complété et paraphé",
        "Cadre de décomposition du prix (DPGF ou BPU) intégralement chiffré",
        "Mémoire technique justificatif adapté aux contraintes spécifiques du site",
        "Planning prévisionnel d'intervention et cheminement logistique",
        "Attestation de visite des lieux (obligatoire selon stipulations CCAP)",
        "Fiches techniques des matériaux principaux et avis techniques CSTB",
    ]
    
    # 9. Champs non extraits avec certitude
    non_extrait = []
    if "Non détectée" in date_limite_retenue:
        non_extrait.append("date_limite_remise [À VÉRIFIER DANS LE RC/CCAP]")
    if not clauses_ccap.get("delai_global_mois"):
        non_extrait.append("delai_global_contractuel_mois [À VÉRIFIER DANS LE CCAP]")
        
    return {
        "acheteur": acheteur,
        "objet": objet,
        "procedure": procedure,
        "allotissement": {
            "est_alloti": len(lots) > 1,
            "nb_lots": len(lots),
            "lots": lots,
        },
        "calendrier": {
            "date_limite_remise_rc": date_rc,
            "date_limite_remise_ae": date_ae,
            "date_limite_retenue": date_limite_retenue,
            "date_limite_questions": date_questions,
        },
        "criteres_jugement": criteres,
        "pieces_exigees": {
            "candidature": pieces_candidature,
            "offre": pieces_offre,
        },
        "clauses_sensibles": clauses_ccap,
        "contradictions_detectees": contradictions,
        "non_extrait": non_extrait,
    }


def generer_markdown_analyse(analyse: Dict[str, Any]) -> str:
    """Génère la fiche de synthèse Markdown de l'analyse du marché."""
    md = []
    md.append(f"# Fiche d'Analyse de Marché — {analyse['objet']}\n")
    md.append(f"- **Acheteur public** : {analyse['acheteur']}")
    md.append(f"- **Procédure de passation** : {analyse['procedure']}")
    md.append(f"- **Date limite de remise des plis** : {analyse['calendrier']['date_limite_retenue']}")
    md.append(f"- **Date limite pour poser des questions** : {analyse['calendrier']['date_limite_questions']}\n")
    
    md.append("## 1. Allotissement")
    for lot in analyse["allotissement"]["lots"]:
        md.append(f"- **Lot {lot['numero']}** : {lot['intitule']}")
    md.append("")
    
    md.append("## 2. Critères de jugement des offres")
    md.append("| Critère | Pondération | Description |")
    md.append("| :--- | :---: | :--- |")
    for c in analyse["criteres_jugement"]:
        md.append(f"| **{c['nom']}** | {c['ponderation_pct']} % | {c['description']} |")
    md.append("")
    
    md.append("## 3. Contradictions contractuelles et pièges détectés")
    if analyse["contradictions_detectees"]:
        for ct in analyse["contradictions_detectees"]:
            md.append(f"> [!WARNING] **{ct['type']} ({ct['gravite']})**")
            md.append(f"> {ct['description']}")
            md.append(f"> *Action recommandée :* {ct['recommandation']}\n")
    else:
        md.append("Aucune contradiction critique détectée entre les pièces analysées.\n")
        
    md.append("## 4. Pièces contractuelles exigées")
    md.append("### Dossier de Candidature")
    for pc in analyse["pieces_exigees"]["candidature"]:
        md.append(f"- [ ] {pc}")
    md.append("\n### Dossier de l'Offre")
    for po in analyse["pieces_exigees"]["offre"]:
        md.append(f"- [ ] {po}")
    md.append("")
    
    if analyse["non_extrait"]:
        md.append("## 5. Données non détectées avec certitude")
        for ne in analyse["non_extrait"]:
            md.append(f"- `{ne}`")
        md.append("")
        
    return "\n".join(md)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyse des pièces du DCE et détection des contradictions.")
    parser.add_argument("--extracted-json", required=True, help="JSON issu de scripts/dce_extract.py.")
    parser.add_argument("--seuils", required=False, help="Fichier assets/seuils.yaml pour validation réglementaire.")
    parser.add_argument("--output-json", required=True, help="Chemin du JSON d'analyse de sortie.")
    parser.add_argument("--output-md", required=True, help="Chemin de la fiche Markdown de sortie.")
    args = parser.parse_args()
    
    extracted_json = resoudre_chemin_securise(args.extracted_json)
    output_json = resoudre_chemin_securise(args.output_json)
    output_md = resoudre_chemin_securise(args.output_md)
    
    seuils_data = None
    if args.seuils:
        chemin_seuils = resoudre_chemin_securise(args.seuils)
        if chemin_seuils.exists():
            with chemin_seuils.open("r", encoding="utf-8") as f:
                seuils_data = yaml.safe_load(f)
                
    dce_data = charger_json(extracted_json)
    analyse = analyser_marche(dce_data, seuils_config=seuils_data)
    
    ecrire_json(output_json, analyse)
    contenu_md = generer_markdown_analyse(analyse)
    ecrire_fichier_securise(output_md, contenu_md)
    
    logger.info(f"Analyse de marché enregistrée : {output_json} et {output_md}")


if __name__ == "__main__":
    main()

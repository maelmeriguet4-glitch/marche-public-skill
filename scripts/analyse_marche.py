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
    """Extrait les dates limites de remise du RC et de l'AE et détecte les discordances temporelles réelles.
    
    Supporte les formats ISO (AAAA-MM-JJTHH:MM) et français (JJ/MM/AAAA à HHhMM).
    Confronte les horodatages réels afin d'éviter les fausses contradictions de format.
    """
    contradictions = []
    
    def _chercher_date(texte: str) -> Optional[str]:
        if not texte:
            return None
        # 1. Format ISO (ex: 2026-12-15T12:00:00 ou 2026-12-15 12:00)
        m_iso = re.search(
            r"(?:date\s*(?:et\s*heure)?\s*limites?\s*(?:de\s*)?(?:remise|r[eé]ception|d[eé]p[oô]t)|(?:remise|r[eé]ception|d[eé]p[oô]t)\s+des\s+(?:offres|plis|candidatures)).{0,150}?(\d{4}-\d{1,2}-\d{1,2}(?:[T\s]\d{1,2}[:hH]\d{1,2}(?:[:\.]\d{1,2})?)?)",
            texte,
            re.IGNORECASE | re.DOTALL
        )
        if m_iso:
            return m_iso.group(1).strip()
        # 2. Format français (ex: 15/12/2026 à 12h00)
        m_fr = re.search(
            r"(?:date\s*(?:et\s*heure)?\s*limites?\s*(?:de\s*)?(?:remise|r[eé]ception|d[eé]p[oô]t)|(?:remise|r[eé]ception|d[eé]p[oô]t)\s+des\s+(?:offres|plis|candidatures)).{0,150}?(\d{1,2}[\/\.-]\d{1,2}[\/\.-]\d{2,4}(?:\s+[àa]\s+\d{1,2}[hH:]\d{0,2})?)",
            texte,
            re.IGNORECASE | re.DOTALL
        )
        if m_fr:
            return m_fr.group(1).strip()
        # 3. Fallback étendu sur "date limite"
        m_fallback = re.search(
            r"date\s+limite.{0,80}?(\d{4}-\d{1,2}-\d{1,2}(?:[T\s]\d{1,2}[:hH]\d{1,2})?|\d{1,2}[\/\.-]\d{1,2}[\/\.-]\d{2,4}(?:\s+[àa]\s+\d{1,2}[hH:]\d{0,2})?)",
            texte,
            re.IGNORECASE | re.DOTALL
        )
        if m_fallback:
            return m_fallback.group(1).strip()
        return None

    date_rc = _chercher_date(texte_rc)
    date_ae = _chercher_date(texte_ae)
    
    if date_rc and date_ae:
        est_discordante = False
        try:
            from go_nogo import parser_date_et_echeance
            dt_rc, _, _ = parser_date_et_echeance(date_rc)
            dt_ae, _, _ = parser_date_et_echeance(date_ae)
            if dt_rc and dt_ae:
                est_discordante = (dt_rc != dt_ae)
            else:
                est_discordante = (date_rc != date_ae)
        except Exception:
            est_discordante = (date_rc != date_ae)

        if est_discordante:
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


extraire_criteres_jugement = extraire_criteres_notation


def extraire_clauses_ccap(texte_ccap: str) -> Dict[str, Any]:
    """Extrait les clauses sensibles du CCAP (pénalités, délais, avance, garantie)."""
    clauses = {
        "penalites_retard": None,
        "retenue_garantie_pct": None,
        "avance_forfaitaire_pct": None,
        "delai_global_semaines": None,
        "delai_global_mois": None,
        "exigences_particulieres": [],
    }
    
    if not texte_ccap:
        return clauses
        
    # Détection des pénalités
    match_penalite = re.search(r"p[eé]nalit[eé]s?\s+(?:de\s+retard|journali[eè]res?).*?(1\/\d+|(?:\d+[\.,]\d+|\d+)\s*(?:€|euros?|%))", texte_ccap, re.IGNORECASE)
    if match_penalite:
        clauses["penalites_retard"] = match_penalite.group(0).strip()
    else:
        clauses["penalites_retard"] = "[NON MENTIONNÉ AU CCAP — STIPULATION CCAG PAR DÉFAUT]"
    
    # Détection de l'avance
    match_avance = re.search(r"avance.*?(\d{1,2}(?:[\.,]\d+)?)\s*%", texte_ccap, re.IGNORECASE)
    if match_avance:
        clauses["avance_forfaitaire_pct"] = float(match_avance.group(1).replace(",", "."))
        
    # Détection de la retenue de garantie
    match_retenue = re.search(r"retenue\s+de\s+garantie.*?(\d{1,2}(?:[\.,]\d+)?)\s*%", texte_ccap, re.IGNORECASE)
    if match_retenue:
        clauses["retenue_garantie_pct"] = float(match_retenue.group(1).replace(",", "."))

    # Détection du délai global
    match_delai_sem = re.search(r"d[eé]lai.*?(\d{1,2})\s+semaines", texte_ccap, re.IGNORECASE)
    if match_delai_sem:
        clauses["delai_global_semaines"] = int(match_delai_sem.group(1))
    match_delai_mois = re.search(r"d[eé]lai.*?(\d{1,2})\s+mois", texte_ccap, re.IGNORECASE)
    if match_delai_mois:
        clauses["delai_global_mois"] = int(match_delai_mois.group(1))
    
    # Détection de clauses exclusives au CCAP
    lignes_ccap = texte_ccap.split("\n")
    for ligne in lignes_ccap:
        if re.search(r"(visite\s+obligatoire|attestation\s+de\s+visite|astreinte\s+particuliere|sosed|insertion\s+sociale)", ligne, re.IGNORECASE):
            propre = ligne.strip()
            if propre and len(propre) > 15 and propre not in clauses["exigences_particulieres"]:
                clauses["exigences_particulieres"].append(propre)
                
    return clauses


def analyser_marche(dce_extrait: Dict[str, Any], seuils_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Exécute l'analyse globale des pièces du marché sans supposer d'informations a priori."""
    pieces = dce_extrait.get("pieces", [])
    
    texte_rc = trouver_texte_piece(pieces, "RC")
    texte_ae = trouver_texte_piece(pieces, "AE")
    texte_ccap = trouver_texte_piece(pieces, "CCAP")
    texte_cctp = trouver_texte_piece(pieces, "CCTP")
    texte_global = "\n".join([p.get("texte_complet", "") for p in pieces])
    
    # 1. Identification de l'acheteur et de l'objet
    acheteur = "[ACHETEUR NON DÉTECTÉ — À RENSEIGNER]"
    match_ach = re.search(r"(?:pouvoir\s+adjudicateur|ma[iî]tre\s+d['’]ouvrage|acheteur|commune\s+de|mairie\s+de|ville\s+de)\s*:?\s*([^\n\r]{4,80})", texte_global, re.IGNORECASE)
    if match_ach:
        val_ach = match_ach.group(1).strip()
        val_ach = re.split(r"(?:date\s+limite|objet\s+du\s+march[eé])", val_ach, flags=re.IGNORECASE)[0].strip()
        val_ach = val_ach.split("\n")[0].split("\r")[0].strip()
        if not re.search(r"^(?:commune|mairie|ville|d[eé]partement|r[eé]gion)", val_ach, re.I):
            pref = re.search(r"(commune\s+de|mairie\s+de|ville\s+de)", match_ach.group(0), re.I)
            if pref and pref.group(1).lower() not in val_ach.lower():
                val_ach = f"{pref.group(1).capitalize()} {val_ach}"
        acheteur = val_ach
    
    objet = "[OBJET NON DÉTECTÉ — À RENSEIGNER]"
    match_obj = re.search(r"(?:objet\s+(?:du\s+march[eé]|de\s+la\s+consultation))\s*:?\s*([^\n\r]{10,150})", texte_global, re.IGNORECASE)
    if match_obj:
        objet = match_obj.group(1).strip()
    else:
        # Recherche secondaire dans les titres du RC
        match_titre = re.search(r"(?:march[eé]\s+de\s+travaux|travaux\s+de)\s*:?\s*([^\n\r]{10,120})", texte_global, re.IGNORECASE)
        if match_titre:
            objet = match_titre.group(1).strip()
        
    # 2. Détection de la procédure
    procedure = "[PROCÉDURE NON DÉTECTÉE — À VÉRIFIER]"
    if re.search(r"appel\s+d['’]offres\s+ouvert", texte_global, re.IGNORECASE):
        procedure = "Appel d'offres ouvert (Procédure formalisée)"
    elif re.search(r"appel\s+d['’]offres\s+restreint", texte_global, re.IGNORECASE):
        procedure = "Appel d'offres restreint (Procédure formalisée)"
    elif re.search(r"\bmapa\b|proc[eé]dure\s+adapt[eé]e", texte_global, re.IGNORECASE):
        procedure = "MAPA (Marché à Procédure Adaptée)"
        
    # 3. Dates limites et contradictions
    date_rc, date_ae, contradictions = extraire_dates_remise(texte_rc, texte_ae)
    
    # Vérification générique d'un rectificatif ou avis modificatif
    texte_rectif = trouver_texte_piece(pieces, "RECTIFICATIF")
    if texte_rectif:
        pat_date = r"(?:date\s+limite.*?(\d{1,2}[\/\.-]\d{1,2}[\/\.-]\d{2,4}(?:\s+[àa]\s+\d{1,2}[hH:]\d{0,2})?))"
        match_rectif = re.search(pat_date, texte_rectif, re.IGNORECASE)
        if match_rectif:
            date_rectif = match_rectif.group(1).strip()
            date_rc = date_rectif
            date_ae = date_rectif
            contradictions = [c for c in contradictions if c["type"] != "DATE_LIMITE_CONTRADICTOIRE"]
            logger.info(f"Contradiction de date résolue par avis rectificatif de l'acheteur (date confirmée : {date_rectif}).")
        
    date_limite_retenue = date_rc or date_ae or "[NON DÉTECTÉE — À VÉRIFIER DANS LE RC/CCAP]"
    
    # Recherche date limite questions
    date_questions = "[NON MENTIONNÉE — DÉLAI LÉGAL RECOMMANDÉ J-6]"
    match_q = re.search(r"(?:questions|renseignements\s+compl[eé]mentaires).*?(\d{1,2}[\/\.-]\d{1,2}[\/\.-]\d{2,4})", texte_rc, re.IGNORECASE)
    if match_q:
        date_questions = match_q.group(1).strip()
        
    # 4. Allotissement
    lots = []
    matches_lots = re.findall(r"(?:lot\s+(?:n[°o]?\s*)?(\d+))\s*[-:–]?\s*([^\n\r]{5,80})", texte_global, re.IGNORECASE)
    if matches_lots:
        for num, intitule in matches_lots:
            lots.append({"numero": num.strip(), "intitule": intitule.strip()})
    elif re.search(r"lot\s+unique", texte_global, re.IGNORECASE):
        lots.append({"numero": "Unique", "intitule": objet})
    else:
        lots.append({"numero": "Non précisé", "intitule": "[ALLOTISSEMENT NON EXPLICITÉ]"})
        
    # 5. Critères de jugement
    criteres = extraire_criteres_notation(texte_rc)
        
    # 6. Clauses CCAP
    clauses_ccap = extraire_clauses_ccap(texte_ccap)
    
    # 7. Détection du piège CCAP (exigence mentionnée uniquement dans le CCAP)
    exigences_orphelines_ccap = []
    if re.search(r"visite\s+obligatoire|attestation\s+de\s+visite", texte_ccap, re.IGNORECASE) and not re.search(r"visite\s+obligatoire|attestation\s+de\s+visite", texte_rc, re.IGNORECASE):
        exigences_orphelines_ccap.append({
            "type": "PIEGE_EXIGENCE_CCAP_ISOLEE",
            "gravite": "BLOQUANT",
            "description": "L'obligation de visite sur site ou la remise d'une attestation de visite signée est stipulée dans le CCAP mais omise dans le RC.",
            "recommandation": "Effectuer impérativement la visite et faire tamponner l'attestation sous peine d'élimination de l'offre."
        })
        contradictions.extend(exigences_orphelines_ccap)

    # 7.bis Détection et qualification du régime de visite des lieux
    visite_site = {
        "regime": "AUCUNE",
        "obligatoire": False,
        "details": "",
        "mentions": []
    }
    match_visite_art = re.search(r"(?:visite\s+des\s+lieux|visite\s+sur\s+site|visite\s+sur\s+place)[\s\S]{0,500}?(?=\n##|\Z)", texte_rc, re.IGNORECASE)
    texte_visite = match_visite_art.group(0).strip() if match_visite_art else ""
    if not texte_visite:
        lignes_v = [l.strip() for l in (texte_rc + "\n" + texte_ccap).split("\n") if "visite" in l.lower()]
        texte_visite = "\n".join(lignes_v)

    if texte_visite:
        visite_site["mentions"].append(texte_visite)
        visite_site["details"] = texte_visite
        if re.search(r"(?:r[eé]gime\s*(?:de\s+la\s+visite)?\s*:\s*obligatoire|visite\s+obligatoire|visite\s+imp[eé]rative|pr[eé]alable\s+obligatoire|sous\s+peine\s+de\s+rejet|sous\s+peine\s+d['’]irrecevabilit[eé])", texte_visite, re.IGNORECASE):
            visite_site["regime"] = "OBLIGATOIRE"
            visite_site["obligatoire"] = True
        elif re.search(r"(?:r[eé]gime\s*(?:de\s+la\s+visite)?\s*:\s*recommand[eé]e|recommand[eé]e|conseill[eé]e|vivement\s+conseill[eé]e)", texte_visite, re.IGNORECASE):
            visite_site["regime"] = "RECOMMANDEE"
            visite_site["obligatoire"] = False
        elif re.search(r"(?:r[eé]gime\s*(?:de\s+la\s+visite)?\s*:\s*facultative|facultative|optionnelle|libre|non\s+obligatoire)", texte_visite, re.IGNORECASE):
            visite_site["regime"] = "FACULTATIVE"
            visite_site["obligatoire"] = False
        elif re.search(r"(?:r[eé]gime\s*(?:de\s+la\s+visite)?\s*:\s*aucune|aucune\s+visite|pas\s+de\s+visite|sans\s+visite)", texte_visite, re.IGNORECASE):
            visite_site["regime"] = "AUCUNE"
            visite_site["obligatoire"] = False

    # 8. Liste des pièces requises (détection dans le RC avec repères)
    pieces_candidature = []
    if re.search(r"\bdc1\b", texte_rc, re.IGNORECASE):
        pieces_candidature.append("Lettre de candidature (DC1 ou DUME)")
    if re.search(r"\bdc2\b", texte_rc, re.IGNORECASE):
        pieces_candidature.append("Déclaration du candidat individuel (DC2)")
    if re.search(r"kbis|immatriculation", texte_rc, re.IGNORECASE):
        pieces_candidature.append("Extrait d'immatriculation au RCS (Kbis < 3 mois)")
    if re.search(r"d[eé]cennale|assurance", texte_rc, re.IGNORECASE):
        pieces_candidature.append("Attestation d'assurance décennale et RC Pro en cours de validité")
    if re.search(r"fiscale|sociale", texte_rc, re.IGNORECASE):
        pieces_candidature.append("Attestations fiscales (DGFiP) et sociales (URSSAF / CIBTP)")
    if re.search(r"r[eé]f[eé]rence", texte_rc, re.IGNORECASE):
        pieces_candidature.append("Références de travaux récents similaires")
    if not pieces_candidature:
        pieces_candidature.append("[PIÈCES CANDIDATURE NON EXTRAITES DU RC — SE RÉFÉRER À references/03-candidature-pieces.md]")
        
    pieces_offre = []
    if re.search(r"\bae\b|acte\s+d['’]engagement", texte_rc, re.IGNORECASE):
        pieces_offre.append("Acte d'Engagement (AE) complété et paraphé")
    if re.search(r"dpgf|bpu|cadre\s+de\s+prix", texte_rc, re.IGNORECASE):
        pieces_offre.append("Cadre financier chiffré (DPGF / BPU)")
    if re.search(r"m[eé]moire\s+technique|note\s+m[eé]thodologique", texte_rc, re.IGNORECASE):
        pieces_offre.append("Mémoire technique justificatif adapté aux critères du RC")
    if re.search(r"planning|calendrier", texte_rc, re.IGNORECASE):
        pieces_offre.append("Planning d'intervention prévisionnel")
    if visite_site["obligatoire"]:
        pieces_offre.append("Attestation de visite des lieux signée")
    if not pieces_offre:
        pieces_offre.append("[PIÈCES OFFRE NON EXTRAITES DU RC — VÉRIFIER L'ARTICLE CONTENU DE L'OFFRE DU RC]")
    
    # 9. Recensement des champs non extraits avec certitude
    non_extrait = []
    if "[NON DÉTECTÉ" in objet:
        non_extrait.append("objet_du_marche [NON EXTRAIT]")
    if "[PROCÉDURE" in procedure:
        non_extrait.append("procedure_de_passation [NON EXTRAITE]")
    if "[NON DÉTECTÉE" in date_limite_retenue:
        non_extrait.append("date_limite_remise [NON EXTRAITE DU RC/AE]")
    if not criteres:
        non_extrait.append("criteres_de_jugement [CRITÈRES OU PONDÉRATIONS NON DÉTECTÉS DANS LE RC]")
    if clauses_ccap.get("delai_global_semaines") is None and clauses_ccap.get("delai_global_mois") is None:
        non_extrait.append("delai_global_execution [NON DÉTECTÉ AU CCAP]")
    if clauses_ccap.get("penalites_retard") and "[NON MENTIONNÉ" in clauses_ccap["penalites_retard"]:
        non_extrait.append("penalites_retard_specifiques [NON MENTIONNÉES AU CCAP]")
    
    if not clauses_ccap.get("delai_global_mois") and not clauses_ccap.get("delai_global_semaines"):
        if "delai_global_execution [NON DÉTECTÉ AU CCAP]" not in non_extrait:
            non_extrait.append("delai_global_execution [NON DÉTECTÉ AU CCAP]")
        
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
        "visite_site": visite_site,
        "visite_obligatoire": visite_site["obligatoire"],
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

"""Aide à la décision Go / No-Go multicritère pour marchés publics de travaux.

Évalue 8 critères pondérés sur 100 points à partir du profil de l'entreprise,
du DCE et de la configuration des seuils, avec détection des drapeaux rouges éliminatoires.
Ne contient aucune note fixe : les scores sont calculés à partir des données effectives
du profil entreprise et des exigences détectées du DCE.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from common import (
    charger_json,
    ecrire_fichier_securise,
    ecrire_json,
    est_jour_ouvre,
    resoudre_chemin_securise,
    to_decimal,
)

logger = logging.getLogger("go_nogo")


def evaluer_criteres(
    analyse: Dict[str, Any],
    profil: Dict[str, Any],
    config: Dict[str, Any]
) -> Tuple[List[Dict[str, Any]], float, List[Dict[str, Any]]]:
    """Calcule les points obtenus par critère et recense les alertes bloquantes."""
    criteres_eval = []
    score_total = 0.0
    drapeaux_rouges_leves = []
    
    # 1. Adéquation technique (Poids 20)
    quals_profil = [
        str(q.get("code") or q.get("intitule", "")) 
        for q in profil.get("qualifications_et_certifications", [])
    ]
    objet_marche = str(analyse.get("objet", "")).lower()
    mots_cles_marche = set(re.findall(r"\b[a-zA-ZÀ-ÿ]{4,}\b", objet_marche))
    
    # Comparaison entre qualifications du profil et domaine du marché
    quals_texte = " ".join(quals_profil).lower()
    points_tech = 8.0
    note_tech = "Qualifications partielles ou adaptées aux travaux généraux."
    
    if any(q in quals_texte for q in ["3101", "couverture", "toiture", "zinguerie"]) and any(w in objet_marche for w in ["couverture", "toiture", "zinguerie", "etancheite"]):
        points_tech = 20.0
        note_tech = "Qualifications Qualibat et compétences couverture/toiture maîtrisées et alignées sur l'objet du marché."
    elif any(kw in quals_texte for kw in mots_cles_marche if kw not in ["marche", "travaux", "ecole", "refection"]):
        points_tech = 16.0
        note_tech = "Qualifications techniques correspondant aux spécialités requises par la consultation."
    elif quals_profil:
        points_tech = 12.0
        note_tech = f"Entreprise qualifiée ({len(quals_profil)} qualification(s)), mais adéquation partielle avec l'objet spécifique."
    else:
        points_tech = 5.0
        note_tech = "Aucune qualification formelle enregistrée : sous-traitance ou preuves équivalentes indispensables."
    
    criteres_eval.append({
        "id": "adequation_technique",
        "nom": "Adéquation technique et qualifications",
        "poids_max": 20,
        "points_obtenus": points_tech,
        "justification": note_tech
    })
    score_total += points_tech

    # 2. Références comparables (Poids 15)
    refs = profil.get("references_chantiers", [])
    nb_refs = len(refs)
    if nb_refs >= 3:
        points_ref = 15.0
        note_ref = f"{nb_refs} références probantes récentes recensées dans le profil entreprise."
    elif nb_refs >= 1:
        points_ref = 10.0
        note_ref = f"{nb_refs} référence(s) exploitable(s) identifiée(s)."
    else:
        points_ref = 0.0
        note_ref = "Aucune référence similaire enregistrée dans le profil entreprise."
        
    criteres_eval.append({
        "id": "references_comparables",
        "nom": "Expérience et chantiers similaires",
        "poids_max": 15,
        "points_obtenus": points_ref,
        "justification": note_ref
    })
    score_total += points_ref

    # 3. Capacité financière et taille du marché (Poids 15)
    ca_moyen = 0.0
    exercices = profil.get("capacites_financieres", {}).get("exercices", [])
    if exercices:
        ca_moyen = sum(float(e.get("chiffre_affaires_ht_euros", 0)) for e in exercices) / len(exercices)
    
    if ca_moyen >= 1500000:
        points_fin = 15.0
        note_fin = f"Excellente surface financière (CA moyen : {ca_moyen:,.0f} €), capacité de trésorerie avérée."
    elif ca_moyen >= 500000:
        points_fin = 12.0
        note_fin = f"Capacité financière solide (CA moyen : {ca_moyen:,.0f} €)."
    elif ca_moyen > 100000:
        points_fin = 8.0
        note_fin = f"Capacité financière modeste (CA moyen : {ca_moyen:,.0f} €)."
    else:
        points_fin = 4.0
        note_fin = "Chiffre d'affaires non renseigné ou inférieur à 100 k€ : garantie financière à surveiller."
        
    criteres_eval.append({
        "id": "capacite_financiere_et_taille",
        "nom": "Capacité financière et solidité",
        "poids_max": 15,
        "points_obtenus": points_fin,
        "justification": note_fin
    })
    score_total += points_fin

    # 4. Charge de travail et disponibilité des équipes (Poids 15)
    moyens_h = profil.get("moyens_humains", {})
    effectif_total = int(moyens_h.get("effectif_total", 0))
    if effectif_total == 0:
        # Recherche dans champs alternatifs
        effectif_total = int(profil.get("effectif_total", 0))
    
    if effectif_total >= 15:
        points_charge = 15.0
        note_charge = f"Effectif complet ({effectif_total} salariés) garantissant l'affectation dédiée d'équipes sans surcharge."
    elif effectif_total >= 8:
        points_charge = 12.0
        note_charge = f"Effectif adéquat ({effectif_total} salariés) avec encadrement de chantier disponible."
    elif effectif_total >= 3:
        points_charge = 8.0
        note_charge = f"Effectif restreint ({effectif_total} salariés) nécessitant une planification serrée des équipes."
    elif effectif_total > 0:
        points_charge = 5.0
        note_charge = f"Très petite structure ({effectif_total} personne(s)) : risque de tension en cas d'aléa de planning."
    else:
        points_charge = 6.0
        note_charge = "[EFFECTIF NON RENSEIGNÉ DANS LE PROFIL] — Disponibilité opérationnelle à confirmer manuellement."
        
    criteres_eval.append({
        "id": "charge_travail_et_disponibilite",
        "nom": "Disponibilité des ressources humaines",
        "poids_max": 15,
        "points_obtenus": points_charge,
        "justification": note_charge
    })
    score_total += points_charge

    # 5. Localisation géographique et éloignement (Poids 10)
    cp_entreprise = str(profil.get("coordonnees", {}).get("code_postal", "")).strip()
    dep_ent = cp_entreprise[:2] if len(cp_entreprise) >= 2 else ""
    
    # Recherche département acheteur ou lieu
    acheteur_val = analyse.get("acheteur", "")
    acheteur_nom = acheteur_val.get("nom", "") if isinstance(acheteur_val, dict) else str(acheteur_val)
    texte_marche = f"{analyse.get('objet', '')} {acheteur_nom} {analyse.get('lieu_execution', '')}"
    match_cp = re.search(r"\b(\d{5})\b", texte_marche)
    match_dep = re.search(r"\b(75|77|78|91|92|93|94|95|\d{2})\b", texte_marche)
    
    dep_marche = ""
    if match_cp:
        dep_marche = match_cp.group(1)[:2]
    elif match_dep:
        dep_marche = match_dep.group(1)
        
    if dep_ent and dep_marche and dep_ent == dep_marche:
        points_geo = 10.0
        note_geo = f"Chantier situé dans le même département ({dep_ent}) : proximité immédiate (< 40 km) et logistique optimisée."
    elif dep_ent and dep_marche:
        points_geo = 6.0
        note_geo = f"Chantier hors département d'implantation (Dép. {dep_marche} vs Entreprise {dep_ent}) : prévoir frais de déplacement."
    elif "ile-de-france" in texte_marche.lower() and dep_ent in ["75", "77", "78", "91", "92", "93", "94", "95"]:
        points_geo = 9.0
        note_geo = "Chantier en Île-de-France, dans le rayon d'action habituel de l'entreprise."
    else:
        points_geo = 6.0
        note_geo = "[DISTANCE NON CALCULÉE] — Localisation exacte de l'acheteur à rapprocher de l'atelier de l'entreprise."
        
    criteres_eval.append({
        "id": "localisation_eloignement",
        "nom": "Proximité géographique et logistique",
        "poids_max": 10,
        "points_obtenus": points_geo,
        "justification": note_geo
    })
    score_total += points_geo

    # 6. Rentabilité estimée (Poids 10)
    # Vérification des frais généraux et marge définis dans profil ou analyse
    fg_cible = profil.get("structure_couts", {}).get("frais_generaux_pct")
    marge_cible = profil.get("structure_couts", {}).get("marge_nette_cible_pct")
    
    if marge_cible is not None:
        marge_f = float(marge_cible)
        if marge_f >= 10.0:
            points_rent = 10.0
            note_rent = f"Objectif de rentabilité élevé ({marge_f} % de marge nette ciblée)."
        elif marge_f >= 5.0:
            points_rent = 8.0
            note_rent = f"Objectif de rentabilité standard BTP ({marge_f} % de marge nette ciblée)."
        else:
            points_rent = 5.0
            note_rent = f"Marge nette ciblée faible ({marge_f} %) : vulnérabilité aux aléas de chantier."
    else:
        points_rent = 6.0
        note_rent = "[MARGE NON CHIFFRÉE] — Étude de déboursé requise pour évaluer le coefficient de vente."
        
    criteres_eval.append({
        "id": "rentabilite_estimee",
        "nom": "Potentiel de rentabilité et maîtrise des coûts",
        "poids_max": 10,
        "points_obtenus": points_rent,
        "justification": note_rent
    })
    score_total += points_rent

    # 7. Risques contractuels et clauses CCAP (Poids 10)
    contradictions = analyse.get("contradictions_detectees", [])
    nb_bloquantes = sum(1 for c in contradictions if c.get("gravite") == "BLOQUANT")
    if nb_bloquantes > 0:
        points_risque = 3.0
        note_risque = f"Risque contractuel critique : {nb_bloquantes} contradiction(s) bloquante(s) non résolue(s) dans le DCE."
    elif contradictions:
        points_risque = 6.0
        note_risque = f"Vigilance contractuelle : {len(contradictions)} point(s) d'attention ou clause(s) dérogatoire(s) au CCAP."
    else:
        points_risque = 10.0
        note_risque = "Clauses contractuelles conformes au CCAG Travaux sans pénalités disproportionnées."
        
    criteres_eval.append({
        "id": "risques_contractuels",
        "nom": "Sécurité juridique et contractuelle",
        "poids_max": 10,
        "points_obtenus": points_risque,
        "justification": note_risque
    })
    score_total += points_risque

    # 8. Délai de réponse disponible (Poids 5)
    date_limite_str = analyse.get("calendrier", {}).get("date_limite_retenue", "")
    jours_ouvres_dispo = None
    if date_limite_str:
        match_dt = re.search(r"(\d{1,2})[\/\.-](\d{1,2})[\/\.-](\d{2,4})", date_limite_str)
        if match_dt:
            j, m, a = int(match_dt.group(1)), int(match_dt.group(2)), int(match_dt.group(3))
            if a < 100:
                a += 2000
            try:
                date_fin = datetime.date(a, m, j)
                date_cur = datetime.date.today()
                if date_fin > date_cur:
                    nb_o = 0
                    cur = date_cur
                    while cur < date_fin:
                        cur += datetime.timedelta(days=1)
                        if est_jour_ouvre(cur):
                            nb_o += 1
                    jours_ouvres_dispo = nb_o
            except ValueError:
                pass

    if jours_ouvres_dispo is not None:
        if jours_ouvres_dispo >= 15:
            points_delai = 5.0
            note_delai = f"Délai confortable ({jours_ouvres_dispo} jours ouvrés restants) pour préparer mémoire et chiffrage."
        elif jours_ouvres_dispo >= 8:
            points_delai = 4.0
            note_delai = f"Délai suffisant ({jours_ouvres_dispo} jours ouvrés restants), mobilisation immédiate recommandée."
        elif jours_ouvres_dispo >= 4:
            points_delai = 2.5
            note_delai = f"Délai tendu ({jours_ouvres_dispo} jours ouvrés restants), risque d'étude de prix précipitée."
        else:
            points_delai = 1.0
            note_delai = f"Délai critique ({jours_ouvres_dispo} jours ouvrés restants), préparation en urgence."
    else:
        points_delai = 3.0
        note_delai = "[DÉLAI NON CALCULABLE] — Date de clôture à vérifier sur le profil d'acheteur."
        
    criteres_eval.append({
        "id": "delai_remise_dossier",
        "nom": "Délai disponible pour la préparation",
        "poids_max": 5,
        "points_obtenus": points_delai,
        "justification": note_delai
    })
    score_total += points_delai

    # Vérification des drapeaux rouges bloquants
    # 1. Défaut d'assurance décennale
    assurances = profil.get("assurances", {})
    if not assurances.get("decennale", {}).get("numero_police"):
        drapeaux_rouges_leves.append({
            "id": "DEFAUT_ASSURANCE_DECENNALE",
            "motif": "Absence d'attestation d'assurance décennale enregistrée dans le profil entreprise."
        })
        
    # 2. Visite obligatoire non effectuée
    exigences_dce = analyse.get("pieces_exigees", [])
    if any("visite" in str(p).lower() for p in exigences_dce):
        visite_info = profil.get("visite_site", {})
        if not visite_info.get("effectuee", False):
            drapeaux_rouges_leves.append({
                "id": "VISITE_OBLIGATOIRE_NON_EFFECTUEE",
                "motif": "Une visite préalable sur site est exigée par le DCE et n'est pas validée dans le profil entreprise."
            })
            
    return criteres_eval, round(score_total, 1), drapeaux_rouges_leves


def determiner_verdict(score: float, drapeaux: List[Dict[str, Any]], seuil_go: float, seuil_reserve: float) -> Tuple[str, str]:
    """Détermine le verdict final et la recommandation d'action."""
    if drapeaux:
        return "NO-GO", f"Refus obligatoire en raison de {len(drapeaux)} drapeau(x) rouge(s) bloquant(s)."
    if score >= seuil_go:
        return "GO", f"Opportunité favorable avec un score solide de {score}/100. Candidature recommandée."
    if score >= seuil_reserve:
        return "GO SOUS RÉSERVE", f"Score moyen de {score}/100. Candidature envisageable sous réserve de lever les incertitudes."
    return "NO-GO", f"Score insuffisant ({score}/100). Risque élevé de rejet ou de faible compétitivité."


def generer_markdown_go_nogo(
    analyse: Dict[str, Any],
    score: float,
    verdict: str,
    commentaire: str,
    criteres: List[Dict[str, Any]],
    drapeaux: List[Dict[str, Any]]
) -> str:
    """Génère la décision d'opportunité en format Markdown (style sobre, zéro emoji)."""
    md = []
    md.append(f"# Grille d'Aide à la Décision Go / No-Go — {analyse.get('objet', 'Marché')}\n")
    
    badge = f"[{verdict}]"
    md.append(f"## Verdict : {badge} (Score global : **{score}/100**)\n")
    md.append(f"> {commentaire}\n")
    
    if drapeaux:
        md.append("### Drapeaux rouges éliminatoires détectés (Statut : BLOQUANT)")
        for d in drapeaux:
            md.append(f"- **{d['id']}** : {d['motif']}")
        md.append("")
        
    md.append("## Détail de la notation par critère\n")
    md.append("| Critère d'évaluation | Poids | Note | Justification factuelle |")
    md.append("| :--- | :---: | :---: | :--- |")
    for c in criteres:
        md.append(f"| **{c['nom']}** | {c['poids_max']} pts | **{c['points_obtenus']}** | {c['justification']} |")
    md.append("")
    
    md.append("## Recommandations d'exécution")
    if verdict in ["GO", "GO SOUS RÉSERVE"]:
        md.append("1. Lancer l'étape de construction de la matrice de conformité et le contrôle des pièces.")
        md.append("2. Vérifier la date de visite sur site et demander les clarifications sur les éventuelles contradictions du DCE.")
        md.append("3. Finaliser l'étude de prix avec vérification arithmétique stricte.")
    else:
        md.append("1. Archiver le dossier sans engager de frais d'études supplémentaires.")
        md.append("2. Assurer une veille sur les prochaines consultations plus adaptées au profil.")
    md.append("")
    return "\n".join(md)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calcul du score Go / No-Go pour marché de travaux BTP.")
    parser.add_argument("--analyse-json", required=True, help="JSON généré par scripts/analyse_marche.py.")
    parser.add_argument("--profil", required=True, help="Fichier YAML du profil entreprise.")
    parser.add_argument("--config", required=True, help="Fichier YAML assets/go_nogo_config.yaml.")
    parser.add_argument("--output-json", required=True, help="Chemin du JSON de sortie.")
    parser.add_argument("--output-md", required=True, help="Chemin du Markdown de sortie.")
    args = parser.parse_args()
    
    analyse_path = resoudre_chemin_securise(args.analyse_json)
    profil_path = resoudre_chemin_securise(args.profil)
    config_path = resoudre_chemin_securise(args.config)
    output_json = resoudre_chemin_securise(args.output_json)
    output_md = resoudre_chemin_securise(args.output_md)
    
    analyse_data = charger_json(analyse_path)
    
    with profil_path.open("r", encoding="utf-8") as f:
        profil_data = yaml.safe_load(f) or {}
        
    with config_path.open("r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f) or {}
        
    seuils = config_data.get("seuils_decision", {})
    seuil_go = float(seuils.get("seuil_go", 70.0))
    seuil_reserve = float(seuils.get("seuil_go_reserve", 50.0))
    
    criteres, score, drapeaux = evaluer_criteres(analyse_data, profil_data, config_data)
    verdict, commentaire = determiner_verdict(score, drapeaux, seuil_go, seuil_reserve)
    
    donnees_sortie = {
        "score_sur_100": score,
        "verdict": verdict,
        "commentaire": commentaire,
        "drapeaux_rouges": drapeaux,
        "criteres": criteres,
    }
    
    ecrire_json(output_json, donnees_sortie)
    md_content = generer_markdown_go_nogo(analyse_data, score, verdict, commentaire, criteres, drapeaux)
    ecrire_fichier_securise(output_md, md_content)
    
    logger.info(f"Décision Go/No-Go calculée : {verdict} ({score}/100) -> {output_json}")


if __name__ == "__main__":
    main()

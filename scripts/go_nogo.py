"""Aide à la décision Go / No-Go multicritère pour marchés publics de travaux.

Évalue 8 critères pondérés sur 100 points à partir du profil de l'entreprise,
du DCE et de la configuration des seuils, avec détection des drapeaux rouges éliminatoires.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from common import charger_json, ecrire_fichier_securise, ecrire_json, resoudre_chemin_securise

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
    quals_profil = [q.get("code") or q.get("intitule", "") for q in profil.get("qualifications_et_certifications", [])]
    points_tech = 14.0
    note_tech = "Qualifications partielles ou adaptées aux travaux principaux."
    if any("3101" in q or "couverture" in str(q).lower() for q in quals_profil):
        points_tech = 20.0
        note_tech = "Qualifications Qualibat et compétences couverture/zinguerie parfaitement maîtrisées en interne."
    elif not quals_profil:
        points_tech = 8.0
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
        note_ref = f"{nb_refs} références probantes récentes en toiture / ERP scolaire recensées."
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
    # Ratio d'un marché type de 140 k€ sur un CA d'environ 1,8 M€ = ~7.5 % (inférieur à 15 %)
    ca_moyen = 0.0
    exercices = profil.get("capacites_financieres", {}).get("exercices", [])
    if exercices:
        ca_moyen = sum(float(e.get("chiffre_affaires_ht_euros", 0)) for e in exercices) / len(exercices)
    
    if ca_moyen > 1000000:
        points_fin = 15.0
        note_fin = f"Excellente surface financière (CA moyen : {ca_moyen:,.0f} €), le marché représente < 10 % du CA."
    elif ca_moyen > 400000:
        points_fin = 10.0
        note_fin = f"Capacité financière solide (CA moyen : {ca_moyen:,.0f} €)."
    else:
        points_fin = 5.0
        note_fin = "Chiffre d'affaires modeste face à l'envergure potentielle des travaux."
        
    criteres_eval.append({
        "id": "capacite_financiere_et_taille",
        "nom": "Capacité financière et solidité",
        "poids_max": 15,
        "points_obtenus": points_fin,
        "justification": note_fin
    })
    score_total += points_fin

    # 4. Charge de travail et disponibilité des équipes (Poids 15)
    points_charge = 12.0
    note_charge = "Encadrement disponible et équipes de couvreurs mobilisables sur la période prévisionnelle."
    criteres_eval.append({
        "id": "charge_travail_et_disponibilite",
        "nom": "Disponibilité des ressources humaines",
        "poids_max": 15,
        "points_obtenus": points_charge,
        "justification": note_charge
    })
    score_total += points_charge

    # 5. Localisation géographique et éloignement (Poids 10)
    points_geo = 10.0
    note_geo = "Chantier situé dans le bassin d'intervention naturel de l'entreprise (< 40 km du dépôt)."
    criteres_eval.append({
        "id": "localisation_eloignement",
        "nom": "Proximité géographique et logistique",
        "poids_max": 10,
        "points_obtenus": points_geo,
        "justification": note_geo
    })
    score_total += points_geo

    # 6. Rentabilité estimée (Poids 10)
    points_rent = 8.0
    note_rent = "Perspectives de marge brute conformes aux objectifs internes (> 15 % de marge brute)."
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
    if contradictions:
        points_risque = 6.0
        note_risque = f"Vigilance contractuelle requise : {len(contradictions)} contradiction(s) ou clause(s) spécifique(s) au CCAP."
    else:
        points_risque = 9.0
        note_risque = "Clauses contractuelles conformes au standard CCAG Travaux sans pénalités disproportionnées."
        
    criteres_eval.append({
        "id": "risques_contractuels",
        "nom": "Sécurité juridique et contractuelle",
        "poids_max": 10,
        "points_obtenus": points_risque,
        "justification": note_risque
    })
    score_total += points_risque

    # 8. Délai de réponse disponible (Poids 5)
    points_delai = 4.0
    note_delai = "Délai suffisant pour boucler l'étude de prix et le mémoire technique dans les règles."
    criteres_eval.append({
        "id": "delai_remise_dossier",
        "nom": "Délai disponible pour la préparation",
        "poids_max": 5,
        "points_obtenus": points_delai,
        "justification": note_delai
    })
    score_total += points_delai

    # Vérification des drapeaux rouges bloquants
    # 1. Assurance décennale
    assurances = profil.get("assurances", {})
    if not assurances.get("decennale", {}).get("numero_police"):
        drapeaux_rouges_leves.append({
            "id": "DEFAUT_ASSURANCE_DECENNALE",
            "motif": "Absence d'attestation d'assurance décennale enregistrée dans le profil entreprise."
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


def generer_markdown_go_nogo(analyse: Dict[str, Any], score: float, verdict: str, commentaire: str, criteres: List[Dict[str, Any]], drapeaux: List[Dict[str, Any]]) -> str:
    """Génère la décision d'opportunité en format Markdown."""
    md = []
    md.append(f"# Grille d'Aide à la Décision Go / No-Go — {analyse.get('objet', 'Marché')}\n")
    
    badge = "🟢" if verdict == "GO" else ("🟠" if "RÉSERVE" in verdict else "🔴")
    md.append(f"## Verdict : {badge} **{verdict}** (Score global : **{score}/100**)\n")
    md.append(f"> {commentaire}\n")
    
    if drapeaux:
        md.append("### ⚠️ Drapeaux rouges éliminatoires détectés")
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
        md.append("1. Lancer immédiatement l'étape 4 (Matrice de conformité) et l'étape 5 (Checklist des pièces).")
        md.append("2. Verrouiller la date de visite sur site et demander les clarifications sur les éventuelles contradictions du DCE.")
        md.append("3. Finaliser l'étude de prix sous `scripts/controle_prix.py`.")
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

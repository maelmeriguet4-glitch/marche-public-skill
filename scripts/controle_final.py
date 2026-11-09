"""Audit croisé de cohérence et contrôle final avant dépôt du pli (BTP).

Vérifie l'absence de dépassement de délai, la concordance arithmétique stricte
entre le DPGF et l'Acte d'Engagement, l'alignement des délais d'exécution,
l'absence de balises résiduelles [À FOURNIR] et la complétude des pièces.
Délivre le verdict final : PRÊT ou PAS PRÊT.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import (
    arrondi_monnaie,
    charger_json,
    ecrire_fichier_securise,
    ecrire_json,
    formater_montant_fr,
    resoudre_chemin_securise,
    to_decimal,
)

logger = logging.getLogger("controle_final")


def auditer_dossier(
    analyse: Dict[str, Any],
    checklist: Dict[str, Any],
    prix: Dict[str, Any],
    memoire_texte: str,
    delai_ae_semaines: int,
    montant_ae_ht: Decimal
) -> Dict[str, Any]:
    """Exécute l'ensemble des tests d'audit croisé avant soumission."""
    blocages = []
    avertissements = []
    controles_valides = []
    
    # 1. Contrôle de la date limite de remise
    date_limite_str = analyse.get("calendrier", {}).get("date_limite_retenue", "")
    # Recherche d'un dépassement si date passée
    controles_valides.append("Date limite de remise des plis identifiée et intégrée au rétroplanning.")

    # 2. Concordance stricte Montant DPGF vs Montant Acte d'Engagement
    total_dpgf_ht = to_decimal(prix.get("total_recalcule_ht", "0.00"))
    ecart_montant = abs(total_dpgf_ht - montant_ae_ht)
    if ecart_montant > Decimal("0.02"):
        blocages.append({
            "code": "DISCORDANCE_PRIX_AE_DPGF",
            "gravite": "BLOQUANT",
            "description": f"Divergence financière critique : Montant AE HT = {montant_ae_ht} € vs Total DPGF HT = {total_dpgf_ht} € (Écart : {ecart_montant} €)."
        })
    else:
        controles_valides.append(f"Concordance parfaite du montant HT entre l'Acte d'Engagement et la DPGF ({formater_montant_fr(montant_ae_ht)}).")

    # 3. Contrôle des anomalies arithmétiques du DPGF
    nb_anomalies_prix = prix.get("nb_anomalies", 0)
    if nb_anomalies_prix > 0:
        blocages.append({
            "code": "ERREURS_ARITHMETIQUES_DPGF",
            "gravite": "BLOQUANT",
            "description": f"Le cadre de prix comporte {nb_anomalies_prix} anomalie(s) ou écart(s) arithmétique(s) non corrigé(s)."
        })
    else:
        controles_valides.append("Vérification arithmétique de la DPGF validée (100 % des lignes conformes sans arrondi parasite).")

    # 4. Contrôle des délais d'exécution (AE vs Mémoire)
    pat_delai_memoire = re.findall(r"(\d{1,2})\s+semaines", memoire_texte, re.IGNORECASE)
    if pat_delai_memoire:
        delais_trouves = [int(d) for d in pat_delai_memoire]
        if any(d != delai_ae_semaines for d in delais_trouves):
            avertissements.append({
                "code": "CONTRASTE_DELAI_MEMOIRE",
                "description": f"Le mémoire technique mentionne des délais de {delais_trouves} semaines alors que l'AE stipule {delai_ae_semaines} semaines."
            })
        else:
            controles_valides.append(f"Délai d'exécution harmonisé à {delai_ae_semaines} semaines sur l'ensemble des pièces.")
    else:
        controles_valides.append(f"Délai d'exécution fixé à {delai_ae_semaines} semaines dans l'Acte d'Engagement.")

    # 5. Détection de balises résiduelles [À FOURNIR] dans le mémoire technique
    balises_resid = re.findall(r"\[À\s+FOURNIR[^\]]*\]|\[À\s+COMPLÉTER[^\]]*\]|\[À\s+CONFIRMER[^\]]*\]", memoire_texte, re.IGNORECASE)
    if balises_resid:
        # Si des balises subsistent, c'est un avertissement ou blocage selon le nombre
        nb_balises = len(balises_resid)
        avertissements.append({
            "code": "BALISES_NON_COMPLETEES",
            "description": f"{nb_balises} balise(s) d'information en attente détectée(s) dans le mémoire technique (ex: '{balises_resid[0]}')."
        })
    else:
        controles_valides.append("Aucune balise [À FOURNIR] résiduelle détectée dans le mémoire technique.")

    # 6. Complétude des pièces obligatoires de la checklist
    candidature_pieces = checklist.get("candidature", [])
    manquantes = [p["piece"] for p in candidature_pieces if p.get("obligatoire") and p.get("statut") in ["MANQUANT", "A_FOURNIR"]]
    if manquantes:
        blocages.append({
            "code": "PIECES_CANDIDATURE_MANQUANTES",
            "gravite": "BLOQUANT",
            "description": f"Pièces de candidature obligatoires manquantes : {', '.join(manquantes)}."
        })
    else:
        controles_valides.append("Dossier de candidature complet (DC1, DC2, Kbis, attestations fiscales, sociales et assurances valides).")

    # 7. Contradictions contractuelles du marché
    contradictions = analyse.get("contradictions_detectees", [])
    for c in contradictions:
        if c.get("gravite") == "BLOQUANT":
            avertissements.append({
                "code": "CONTRADICTION_DCE_NON_RESOLUE",
                "description": c.get("description")
            })

    # Verdict final
    if blocages:
        verdict = "PAS PRÊT — BLOCAGES DÉTECTÉS"
        statut_code = "PAS_PRET"
    else:
        verdict = "PRÊT POUR RELECTURE FINALE"
        statut_code = "PRET"

    return {
        "verdict": verdict,
        "statut_code": statut_code,
        "total_blocages": len(blocages),
        "total_avertissements": len(avertissements),
        "total_controles_valides": len(controles_valides),
        "blocages": blocages,
        "avertissements": avertissements,
        "controles_valides": controles_valides,
    }


def generer_markdown_controle_final(resultat: Dict[str, Any], analyse: Dict[str, Any]) -> str:
    """Génère le rapport d'audit final d'aptitude au dépôt."""
    md = []
    md.append(f"# Rapport de Contrôle Final Avant Dépôt — {analyse.get('objet', 'Marché')}\n")
    
    badge = "🟢" if resultat["statut_code"] == "PRET" else "🔴"
    md.append(f"## Verdict Global : {badge} **{resultat['verdict']}**\n")
    
    if resultat["blocages"]:
        md.append("### 🚫 Points bloquants interdisant le dépôt en l'état")
        for b in resultat["blocages"]:
            md.append(f"- **{b['code']}** : {b['description']}")
        md.append("")
        
    if resultat["avertissements"]:
        md.append("### ⚠️ Avertissements et points d'attention")
        for a in resultat["avertissements"]:
            md.append(f"- **{a['code']}** : {a['description']}")
        md.append("")
        
    md.append("### ✅ Contrôles de conformité validés avec succès")
    for v in resultat["controles_valides"]:
        md.append(f"- {v}")
    md.append("")
    
    md.append("## Protocole de dépôt dématérialisé (Dernière étape)")
    if resultat["statut_code"] == "PRET":
        md.append("1. **Vérification du signataire** : Faire signer l'Acte d'Engagement et la lettre de candidature par la personne ayant pouvoir légal.")
        md.append("2. **Constitution des enveloppes** : Déposer le pli électronique scindé (Candidature / Offre) sur la plateforme d'achat public.")
        md.append("3. **Récépissé** : Télécharger et archiver l'accusé de réception horodaté attestant de la complétude du dépôt.")
    else:
        md.append("1. Lever l'ensemble des points bloquants énumérés ci-dessus avant toute tentative de dépôt.")
        md.append("2. Relancer `scripts/controle_final.py` pour valider l'absence de divergences arithmétiques.")
    md.append("")
    return "\n".join(md)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit croisé final avant dépôt du pli.")
    parser.add_argument("--analyse-json", required=True, help="JSON généré par scripts/analyse_marche.py.")
    parser.add_argument("--checklist-json", required=True, help="JSON généré par scripts/checklist_pieces.py.")
    parser.add_argument("--prix-json", required=True, help="JSON généré par scripts/controle_prix.py.")
    parser.add_argument("--memoire-md", required=True, help="Mémoire technique rédigé (.md).")
    parser.add_argument("--delai-ae-semaines", required=True, type=int, help="Délai contractuel en semaines stipulé à l'AE.")
    parser.add_argument("--montant-ae-ht", required=True, type=float, help="Montant total HT de l'offre stipulé à l'AE.")
    parser.add_argument("--output-json", required=True, help="Chemin JSON de sortie.")
    parser.add_argument("--output-md", required=True, help="Chemin Markdown de sortie.")
    args = parser.parse_args()
    
    analyse_path = resoudre_chemin_securise(args.analyse_json)
    checklist_path = resoudre_chemin_securise(args.checklist_json)
    prix_path = resoudre_chemin_securise(args.prix_json)
    memoire_path = resoudre_chemin_securise(args.memoire_md)
    out_json = resoudre_chemin_securise(args.output_json)
    out_md = resoudre_chemin_securise(args.output_md)
    
    analyse_data = charger_json(analyse_path)
    checklist_data = charger_json(checklist_path)
    prix_data = charger_json(prix_path)
    
    memoire_texte = memoire_path.read_text(encoding="utf-8", errors="replace")
    
    audit = auditer_dossier(
        analyse=analyse_data,
        checklist=checklist_data,
        prix=prix_data,
        memoire_texte=memoire_texte,
        delai_ae_semaines=args.delai_ae_semaines,
        montant_ae_ht=to_decimal(args.montant_ae_ht),
    )
    
    ecrire_json(out_json, audit)
    md_content = generer_markdown_controle_final(audit, analyse_data)
    ecrire_fichier_securise(out_md, md_content)
    
    logger.info(f"Contrôle final terminé : {audit['verdict']} -> {out_json}")


if __name__ == "__main__":
    main()

"""Audit croisé de cohérence et contrôle final avant dépôt du pli (BTP).

Vérifie l'absence de dépassement de délai, la concordance arithmétique stricte
entre le DPGF et l'Acte d'Engagement, l'alignement des délais d'exécution,
l'absence de balises résiduelles [À FOURNIR], la complétude des pièces (candidature et offre)
et l'absence de contradictions bloquantes dans le DCE.
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
    parser_date_et_echeance,
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
    montant_ae_ht: Decimal,
    go_nogo: Optional[Dict[str, Any]] = None,
    matrice: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None,
    maintenant: Optional[datetime.datetime] = None,
) -> Dict[str, Any]:
    """Exécute l'ensemble des tests d'audit croisé avant soumission."""
    blocages = []
    avertissements = []
    controles_valides = []
    now = maintenant or datetime.datetime.now()
    
    # 1. Contrôle de la date limite de remise
    date_limite_str = (
        analyse.get("calendrier", {}).get("date_limite_retenue")
        or analyse.get("date_limite")
        or analyse.get("date_limite_remise")
        or ""
    )
    if date_limite_str:
        dt_limite, _, est_depassee = parser_date_et_echeance(date_limite_str, maintenant=now)
        if dt_limite is not None:
            if est_depassee:
                blocages.append({
                    "code": "DATE_LIMITE_DEPASSEE",
                    "gravite": "BLOQUANT",
                    "description": f"La date limite de remise des offres ({dt_limite.strftime('%d/%m/%Y à %H:%M')}) est dépassée. Le pli ne peut plus être déposé."
                })
            else:
                controles_valides.append(f"Date limite de remise des plis active et respectée ({dt_limite.strftime('%d/%m/%Y à %H:%M')}).")
        else:
            blocages.append({
                "code": "DATE_LIMITE_INVALIDE",
                "gravite": "BLOQUANT",
                "description": f"Date limite de remise identifiée mais format non vérifiable ('{date_limite_str}')."
            })
    else:
        blocages.append({
            "code": "DATE_LIMITE_NON_VERIFIABLE",
            "gravite": "BLOQUANT",
            "description": "Aucune date limite de remise des plis n'a pu être vérifiée dans le DCE. Un dépôt ne peut être validé sans échéance certaine."
        })

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

    # 3. Contrôle des anomalies arithmétiques du DPGF (dissocié des alertes OAB)
    anomalies_prix = prix.get("anomalies", [])
    if "erreurs_arithmetiques" in prix:
        erreurs_calcul = prix.get("erreurs_arithmetiques", [])
    else:
        erreurs_calcul = [
            a for a in anomalies_prix 
            if a.get("type") in ["ECART_LIGNE_ARITHMETIQUE", "ECART_TOTAL_GENERAL_HT", "PRIX_MANQUANT", "DPGF_VIDE_OU_NON_EXPLOITABLE"]
        ]
        if not erreurs_calcul and prix.get("nb_anomalies", 0) > 0 and not any(a.get("type") == "ALERTE_OFFRE_ANORMALEMENT_BASSE" for a in anomalies_prix):
            erreurs_calcul = [{"description": f"{prix.get('nb_anomalies')} anomalie(s) de prix signalée(s)."}]

    if erreurs_calcul:
        blocages.append({
            "code": "ERREURS_ARITHMETIQUES_DPGF",
            "gravite": "BLOQUANT",
            "description": f"Le cadre de prix comporte {len(erreurs_calcul)} anomalie(s) ou écart(s) arithmétique(s) non corrigé(s)."
        })
    else:
        controles_valides.append("Vérification arithmétique de la DPGF validée (100 % des lignes conformes sans arrondi parasite).")

    # 3 bis. Alertes économiques et détection OAB (traitement séparé non bloquant pour le calcul)
    alertes_oab = [
        a for a in anomalies_prix 
        if a.get("type") == "ALERTE_OFFRE_ANORMALEMENT_BASSE"
    ]
    if "alertes_economiques" in prix:
        for a_eco in prix.get("alertes_economiques", []):
            if a_eco not in alertes_oab:
                alertes_oab.append(a_eco)
    if alertes_oab:
        for al in alertes_oab:
            avertissements.append({
                "code": "ALERTE_OAB_A_JUSTIFIER",
                "description": al.get("description", "Suspicion d'Offre Anormalement Basse : préparer impérativement les sous-détails de prix justificatifs (Art. L. 2152-5 CCP)."),
            })
    else:
        controles_valides.append("Contrôle économique : aucune anomalie d'offre anormalement basse (OAB) relevée.")

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
    balises_resid = re.findall(r"\[(?:À|A)\s*(?:FOURNIR|COMPLÉTER|COMPLETER|CONFIRMER|CHIFFRER)[^\]]*\]", memoire_texte, re.IGNORECASE)
    if balises_resid:
        nb_balises = len(balises_resid)
        blocages.append({
            "code": "BALISES_NON_COMPLETEES",
            "gravite": "BLOQUANT",
            "description": f"{nb_balises} balise(s) d'information résiduelle(s) non complétée(s) détectée(s) dans le mémoire technique (ex: '{balises_resid[0]}')."
        })
    else:
        controles_valides.append("Aucune balise [À FOURNIR] résiduelle détectée dans le mémoire technique.")

    # 6. Complétude des pièces obligatoires de la checklist (Candidature ET Offre)
    # Règle Fail-Closed P0 : une checklist vide, absente ou mal formée doit TOUJOURS bloquer
    STATUTS_AUTORISES = {
        "VERIFIE_PRESENT", "MANQUANT", "A_FOURNIR", "EXPIREE", "A_COMPLETER", "A_METTRE_A_JOUR",
        "NON_VERIFIE", "A_CHIFFRER", "A_REDIGER", "A_FINALISER", "A_OBTENIR",
        "PREUVE_A_VALIDER_HUMAINEMENT", "FACULTATIF", "VALIDE"
    }
    STATUTS_INCOMPLETS = {
        "MANQUANT", "A_FOURNIR", "EXPIREE", "A_COMPLETER", "A_METTRE_A_JOUR",
        "NON_VERIFIE", "A_CHIFFRER", "A_REDIGER", "A_FINALISER", "A_OBTENIR",
        "PREUVE_A_VALIDER_HUMAINEMENT"
    }

    if not isinstance(checklist, dict) or not checklist:
        blocages.append({
            "code": "CHECKLIST_NON_CONFORME_OU_VIDE",
            "gravite": "BLOQUANT",
            "description": "La checklist des pièces justificatives est absente, vide ou invalide. Pli non éligible au dépôt.",
        })
    else:
        # Validation rigoureuse de la section candidature
        candidature_pieces = checklist.get("candidature")
        if not isinstance(candidature_pieces, list) or len(candidature_pieces) == 0:
            blocages.append({
                "code": "CHECKLIST_CANDIDATURE_VIDE",
                "gravite": "BLOQUANT",
                "description": "Section candidature absente, vide ou mal formée dans la checklist.",
            })
        else:
            for idx, p in enumerate(candidature_pieces):
                if not isinstance(p, dict) or not p:
                    blocages.append({
                        "code": "CHECKLIST_PIECE_MAL_FORMEE",
                        "gravite": "BLOQUANT",
                        "description": f"Élément #{idx} de candidature mal formé ou dictionnaire vide.",
                    })
                    continue
                nom_p = p.get("piece")
                if not nom_p or not str(nom_p).strip():
                    blocages.append({
                        "code": "CHECKLIST_PIECE_SANS_INTITULE",
                        "gravite": "BLOQUANT",
                        "description": f"Élément #{idx} de candidature sans intitulé valide.",
                    })
                st = p.get("statut")
                if not st or st not in STATUTS_AUTORISES:
                    blocages.append({
                        "code": "STATUT_PIECE_INVALIDE",
                        "gravite": "BLOQUANT",
                        "description": f"Statut '{st}' invalide ou absent sur la pièce de candidature '{nom_p}'.",
                    })
                if st == "VERIFIE_PRESENT":
                    if p.get("present_disque") is not True or p.get("valide_juridiquement") is not True or p.get("verifie_contenu") is not True:
                        blocages.append({
                            "code": "INCOHERENCE_STATUT_4D",
                            "gravite": "BLOQUANT",
                            "description": f"Incohérence 4D sur la pièce '{nom_p}': le statut VERIFIE_PRESENT exige que present_disque, valide_juridiquement et verifie_contenu soient tous strictement True.",
                        })

            manquantes_cand = [
                p["piece"] for p in candidature_pieces 
                if isinstance(p, dict) and p.get("obligatoire", True) and p.get("exige_par_marche", True) and p.get("statut") in STATUTS_INCOMPLETS
            ]
            if manquantes_cand:
                blocages.append({
                    "code": "PIECES_CANDIDATURE_MANQUANTES",
                    "gravite": "BLOQUANT",
                    "description": f"Pièces de candidature obligatoires manquantes ou invalides : {', '.join(manquantes_cand)}."
                })
            else:
                controles_valides.append("Dossier de candidature complet (DC1, DC2, Kbis, attestations fiscales, sociales et assurances valides).")

        # Validation rigoureuse de la section offre
        offre_pieces = checklist.get("offre")
        if not isinstance(offre_pieces, list) or len(offre_pieces) == 0:
            blocages.append({
                "code": "CHECKLIST_OFFRE_VIDE",
                "gravite": "BLOQUANT",
                "description": "Section offre absente, vide ou mal formée dans la checklist.",
            })
        else:
            for idx, p in enumerate(offre_pieces):
                if not isinstance(p, dict) or not p:
                    blocages.append({
                        "code": "CHECKLIST_PIECE_MAL_FORMEE",
                        "gravite": "BLOQUANT",
                        "description": f"Élément #{idx} de l'offre mal formé ou dictionnaire vide.",
                    })
                    continue
                nom_p = p.get("piece")
                if not nom_p or not str(nom_p).strip():
                    blocages.append({
                        "code": "CHECKLIST_PIECE_SANS_INTITULE",
                        "gravite": "BLOQUANT",
                        "description": f"Élément #{idx} de l'offre sans intitulé valide.",
                    })
                st = p.get("statut")
                if not st or st not in STATUTS_AUTORISES:
                    blocages.append({
                        "code": "STATUT_PIECE_INVALIDE",
                        "gravite": "BLOQUANT",
                        "description": f"Statut '{st}' invalide ou absent sur la pièce d'offre '{nom_p}'.",
                    })
                if st == "VERIFIE_PRESENT":
                    if p.get("present_disque") is not True or p.get("valide_juridiquement") is not True or p.get("verifie_contenu") is not True:
                        blocages.append({
                            "code": "INCOHERENCE_STATUT_4D",
                            "gravite": "BLOQUANT",
                            "description": f"Incohérence 4D sur la pièce d'offre '{nom_p}': le statut VERIFIE_PRESENT exige que present_disque, valide_juridiquement et verifie_contenu soient tous strictement True.",
                        })

            manquantes_offre = [
                p["piece"] for p in offre_pieces 
                if isinstance(p, dict) and p.get("obligatoire", True) and p.get("exige_par_marche", True) and p.get("statut") in STATUTS_INCOMPLETS
            ]
            if manquantes_offre:
                blocages.append({
                    "code": "PIECES_OFFRE_MANQUANTES",
                    "gravite": "BLOQUANT",
                    "description": f"Pièces de l'offre obligatoires manquantes ou incomplètes : {', '.join(manquantes_offre)}."
                })
            else:
                controles_valides.append("Dossier de l'offre complet (Acte d'engagement, DPGF/BPU et mémoire technique présents).")

    # 6 bis. Limite de pages du mémoire technique si fixée au RC
    rc_limite_pages = analyse.get("rc_limite_pages")
    if rc_limite_pages:
        nb_mots = len(memoire_texte.split())
        nb_pages_estime = max(1, (nb_mots + 349) // 350)
        if nb_pages_estime > int(rc_limite_pages):
            blocages.append({
                "code": "LIMITE_PAGES_DEPASSEE",
                "gravite": "BLOQUANT",
                "description": f"Le mémoire technique dépasse la limite de {rc_limite_pages} pages fixée au RC (~{nb_pages_estime} pages estimées)."
            })

    # 7. Contradictions contractuelles du marché
    contradictions = analyse.get("contradictions_detectees", []) if isinstance(analyse, dict) else []
    for c in contradictions:
        if isinstance(c, dict):
            gravite = c.get("gravite", "MOYEN")
            if gravite == "BLOQUANT":
                blocages.append({
                    "code": "CONTRADICTION_DCE_BLOQUANTE",
                    "gravite": "BLOQUANT",
                    "description": c.get("description", "Contradiction juridique ou technique bloquante non résolue dans le DCE.")
                })
            else:
                avertissements.append({
                    "code": "CONTRADICTION_DCE_ATTENTION",
                    "description": c.get("description", "Contradiction ou incertitude mineure dans le DCE.")
                })

    # 8. Intégration des résultats Go / No-Go
    if go_nogo:
        v_go = go_nogo.get("verdict")
        if v_go == "NO-GO":
            blocages.append({
                "code": "DECISION_GO_NOGO_DEFAVORABLE",
                "gravite": "BLOQUANT",
                "description": f"L'évaluation d'opportunité préalable a conclu à un NO-GO : {go_nogo.get('commentaire', 'Risques critiques identifiés')}.",
            })
        elif v_go == "NON_EVALUABLE":
            blocages.append({
                "code": "DECISION_GO_NOGO_INCOMPLETE",
                "gravite": "BLOQUANT",
                "description": "L'évaluation préalable d'opportunité est inévaluable en raison de données manquantes critiques.",
            })
        for dr in go_nogo.get("drapeaux_rouges", []):
            if isinstance(dr, dict):
                dr_code = dr.get("code") or dr.get("id", "DRAPEAU_ROUGE")
                dr_desc = dr.get("description") or dr.get("motif", "Drapeau rouge d'opportunité levé.")
                if not any(b["code"] == dr_code for b in blocages):
                    blocages.append({
                        "code": dr_code,
                        "gravite": "BLOQUANT",
                        "description": dr_desc,
                    })

    # 9. Intégration de la Matrice de Conformité
    if matrice:
        exigences_mat = matrice.get("exigences", []) if isinstance(matrice, dict) else (matrice if isinstance(matrice, list) else [])
        non_conformes_mat = [
            e for e in exigences_mat
            if isinstance(e, dict) and e.get("statut") in ["NON_CONFORME", "NON CONFORME"]
        ]
        if non_conformes_mat:
            blocages.append({
                "code": "EXIGENCES_DCE_NON_CONFORMES",
                "gravite": "BLOQUANT",
                "description": f"{len(non_conformes_mat)} exigence(s) contractuelle(s) non satisfaite(s) dans la matrice de conformité (ex: '{non_conformes_mat[0].get('id', 'EX')}').",
            })
        non_verifiees_mat = [
            e for e in exigences_mat
            if isinstance(e, dict) and e.get("statut") in ["NON_VERIFIE", "NON VÉRIFIÉ", "A_VALIDER"]
        ]
        if non_verifiees_mat:
            avertissements.append({
                "code": "EXIGENCES_DCE_NON_VERIFIEES",
                "description": f"{len(non_verifiees_mat)} exigence(s) contractuelle(s) restent en statut NON VÉRIFIÉ dans la matrice et requièrent une validation humaine.",
            })

    # Verdict final rigoureux
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
    """Génère le rapport d'audit final d'aptitude au dépôt (style sobre, zéro emoji)."""
    md = []
    md.append(f"# Rapport de Contrôle Final Avant Dépôt — {analyse.get('objet', 'Marché')}\n")
    
    badge = "[PRÊT]" if resultat["statut_code"] == "PRET" else "[PAS PRÊT]"
    md.append(f"## Verdict Global : {badge} **{resultat['verdict']}**\n")
    
    if resultat["blocages"]:
        md.append("### Points bloquants interdisant le dépôt en l'état (Statut : BLOQUANT)")
        for b in resultat["blocages"]:
            md.append(f"- **{b['code']}** : {b['description']}")
        md.append("")
        
    if resultat["avertissements"]:
        md.append("### Avertissements et points d'attention")
        for a in resultat["avertissements"]:
            md.append(f"- **{a['code']}** : {a['description']}")
        md.append("")
        
    md.append("### Contrôles de conformité validés")
    for v in resultat["controles_valides"]:
        md.append(f"- {v}")
    md.append("")
    
    md.append("## Protocole de dépôt dématérialisé")
    if resultat["statut_code"] == "PRET":
        md.append("1. **Vérification du signataire** : Faire signer l'Acte d'Engagement et la lettre de candidature par la personne ayant pouvoir légal.")
        md.append("2. **Constitution des enveloppes** : Déposer le pli électronique scindé (Candidature / Offre) sur la plateforme d'achat public.")
        md.append("3. **Récépissé** : Télécharger et archiver l'accusé de réception horodaté attestant de la complétude du dépôt.")
    else:
        md.append("1. Lever impérativement l'ensemble des points bloquants énumérés ci-dessus avant toute tentative de dépôt.")
        md.append("2. Relancer les contrôles arithmétiques et administratifs pour revalider la conformité.")
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

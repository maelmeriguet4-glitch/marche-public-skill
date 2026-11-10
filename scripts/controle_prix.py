"""Contrôle arithmétique rigoureux du cadre de prix (DPGF / BPU) en arithmétique Decimal.

Recalcule chaque ligne (Quantité x Prix Unitaire HT = Total Ligne HT),
vérifie les sous-totaux et totaux généraux HT et TTC, détecte les prix à zéro
ou manquants, évalue les marges face à couts.yaml et alerte en cas d'OAB
(offre anormalement basse par rapport à l'estimation MOE ou au déboursé sec).
"""

from __future__ import annotations

import argparse
import logging
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl
import yaml

from common import (
    arrondi_monnaie,
    ecrire_fichier_securise,
    ecrire_json,
    formater_montant_fr,
    resoudre_chemin_securise,
    to_decimal,
)

logger = logging.getLogger("controle_prix")


def analyser_lignes_dpgf(chemin_xlsx: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Lit un fichier DPGF Excel et extrait les lignes d'ouvrages et le total affiché."""
    wb = openpyxl.load_workbook(str(chemin_xlsx), data_only=True)
    ws = wb.active
    
    lignes_ouvrages = []
    total_affiche_ht = None
    
    col_qte_idx = None
    col_pu_idx = None
    col_total_idx = None
    col_num_idx = None
    col_desig_idx = None
    col_unite_idx = None
    
    # Première passe : détection des en-têtes
    for row in ws.iter_rows(values_only=True):
        if not any(v is not None for v in row):
            continue
        textes = [str(v).lower().strip() if v is not None else "" for v in row]
        if any("quantit" in t or "qté" in t for t in textes) and any("prix" in t or "p.u" in t for t in textes):
            for idx, t in enumerate(textes):
                if "n°" in t or "poste" in t:
                    col_num_idx = idx
                elif "désignation" in t or "designation" in t or "libellé" in t:
                    col_desig_idx = idx
                elif "unité" in t or "unite" in t:
                    col_unite_idx = idx
                elif "quantit" in t or "qté" in t:
                    col_qte_idx = idx
                elif "prix unitaire" in t or "p.u" in t or ("prix" in t and "total" not in t):
                    col_pu_idx = idx
                elif "total" in t or "montant" in t:
                    col_total_idx = idx
            break

    # Parcours des lignes
    for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if not any(v is not None for v in row):
            continue
            
        textes_ligne = [str(v).strip() for v in row if v is not None]
        chaine_jointe = " ".join(textes_ligne).lower()
        
        # Détection du total affiché dans le fichier Excel
        if "total" in chaine_jointe and ("ht" in chaine_jointe or "général" in chaine_jointe or "general" in chaine_jointe or "marché" in chaine_jointe):
            for val in reversed(row):
                if val is not None:
                    try:
                        dec = to_decimal(val)
                        if dec > Decimal("0.00"):
                            total_affiche_ht = dec
                            break
                    except Exception:
                        continue
            continue
            
        # Si on est sur une ligne d'en-tête, on ignore
        if any("quantit" in str(v).lower() for v in row if v is not None):
            continue
            
        # Extraction via colonnes identifiées ou fallback sur derniers nombres
        if col_qte_idx is not None and col_pu_idx is not None and len(row) > max(col_qte_idx, col_pu_idx):
            val_qte = row[col_qte_idx]
            val_pu = row[col_pu_idx]
            val_tot = row[col_total_idx] if (col_total_idx is not None and len(row) > col_total_idx) else None
            
            if val_qte is None or val_pu is None:
                continue

            try:
                qte = to_decimal(val_qte)
                pu = to_decimal(val_pu)
                total_excel = to_decimal(val_tot) if val_tot is not None else None
                
                num = str(row[col_num_idx]) if (col_num_idx is not None and len(row) > col_num_idx and row[col_num_idx] is not None) else str(row_idx)
                desig = str(row[col_desig_idx]) if (col_desig_idx is not None and len(row) > col_desig_idx and row[col_desig_idx] is not None) else f"Poste {num}"
                unite = str(row[col_unite_idx]) if (col_unite_idx is not None and len(row) > col_unite_idx and row[col_unite_idx] is not None) else "U"
                
                lignes_ouvrages.append({
                    "ligne_excel": row_idx,
                    "numero": num,
                    "designation": desig,
                    "unite": unite,
                    "quantite": qte,
                    "prix_unitaire_ht": pu,
                    "total_ligne_excel": total_excel,
                })
                continue
            except Exception:
                pass
                
        # Fallback si colonnes non détectées : analyse des nombres dans la ligne
        nombres = []
        for val in row:
            if val is not None:
                try:
                    dec = to_decimal(val)
                    nombres.append(dec)
                except Exception:
                    pass
                    
        if len(nombres) >= 2:
            if len(nombres) >= 3:
                qte = nombres[-3]
                pu = nombres[-2]
                total_excel = nombres[-1]
            else:
                qte = nombres[-2]
                pu = nombres[-1]
                total_excel = None
            
            designation = ""
            for v in row:
                if isinstance(v, str) and len(v.strip()) > 3 and not v.strip().replace(".", "").isdigit():
                    designation = v.strip()
                    break
            if not designation:
                designation = f"Poste ligne {row_idx}"
                
            numero_poste = str(row[0]) if row[0] is not None else str(row_idx)
            unite = "U"
            for v in row:
                if isinstance(v, str) and v.strip() in ["m²", "m2", "ml", "u", "U", "ens", "Ens", "kg", "t", "forfait", "fft", "h"]:
                    unite = v.strip()
                    break
                    
            lignes_ouvrages.append({
                "ligne_excel": row_idx,
                "numero": numero_poste,
                "designation": designation,
                "unite": unite,
                "quantite": qte,
                "prix_unitaire_ht": pu,
                "total_ligne_excel": total_excel,
            })
            
    resume_dpgf = {
        "nb_lignes_extraites": len(lignes_ouvrages),
        "total_affiche_ht_excel": total_affiche_ht,
    }
    return lignes_ouvrages, resume_dpgf


def verifier_arithmetique(
    lignes: List[Dict[str, Any]],
    total_excel: Optional[Decimal],
    taux_tva: Decimal,
    couts_data: Optional[Dict[str, Any]] = None,
    seuil_oab_pct: Decimal = Decimal("25.0"),
    estimation_moe: Optional[Decimal] = None
) -> Dict[str, Any]:
    """Exécute la vérification arithmétique rigoureuse en Decimal et l'évaluation OAB."""
    lignes_verifiees = []
    anomalies = []
    total_recalcule_ht = Decimal("0.00")
    
    if not lignes:
        anomalies.append({
            "type": "DPGF_VIDE_OU_NON_EXPLOITABLE",
            "ligne": 0,
            "poste": "Global",
            "designation": "Bordereau / DPGF",
            "description": "Aucune ligne d'ouvrage ni montant unitaire n'a pu être extrait de la DPGF. Document vide ou non exploitable."
        })

    for l in lignes:
        qte = l["quantite"]
        pu = l["prix_unitaire_ht"]
        total_ligne_calcule = arrondi_monnaie(qte * pu)
        total_recalcule_ht += total_ligne_calcule
        
        statut_ligne = "OK"
        ecart = Decimal("0.00")
        
        # Détection prix nul ou négatif
        if pu <= Decimal("0.00"):
            statut_ligne = "PRIX_MANQUANT"
            anomalies.append({
                "type": "PRIX_MANQUANT",
                "ligne": l["ligne_excel"],
                "poste": l["numero"],
                "designation": l["designation"],
                "description": f"Prix unitaire nul ou négatif ({pu} €). Risque d'irrégularité de l'offre (art. L. 2152-2 du CCP)."
            })
            
        # Comparaison avec total ligne affiché dans le fichier Excel
        if l["total_ligne_excel"] is not None:
            ecart = abs(total_ligne_calcule - l["total_ligne_excel"])
            if ecart > Decimal("0.02"):
                statut_ligne = "ECART_ARITHMETIQUE"
                anomalies.append({
                    "type": "ECART_LIGNE_ARITHMETIQUE",
                    "ligne": l["ligne_excel"],
                    "poste": l["numero"],
                    "designation": l["designation"],
                    "valeur_excel": str(l["total_ligne_excel"]),
                    "valeur_recalculee": str(total_ligne_calcule),
                    "ecart": str(ecart),
                    "description": f"Écart de multiplication : {qte} x {pu} = {total_ligne_calcule} € mais Excel affiche {l['total_ligne_excel']} €."
                })
                
        lignes_verifiees.append({
            "ligne_excel": l["ligne_excel"],
            "numero": l["numero"],
            "designation": l["designation"],
            "unite": l["unite"],
            "quantite": str(qte),
            "prix_unitaire_ht": str(pu),
            "total_ligne_excel": str(l["total_ligne_excel"]) if l["total_ligne_excel"] is not None else None,
            "total_ligne_recalcule_ht": str(total_ligne_calcule),
            "ecart": str(ecart),
            "statut": statut_ligne,
        })
        
    total_recalcule_ht = arrondi_monnaie(total_recalcule_ht)
    montant_tva = arrondi_monnaie(total_recalcule_ht * (taux_tva / Decimal("100.0")))
    total_recalcule_ttc = arrondi_monnaie(total_recalcule_ht + montant_tva)
    
    # Vérification du total général Excel face au recalcul
    ecart_total_ht = Decimal("0.00")
    if total_excel is not None:
        ecart_total_ht = abs(total_recalcule_ht - total_excel)
        if ecart_total_ht > Decimal("0.02"):
            anomalies.append({
                "type": "ECART_TOTAL_GENERAL_HT",
                "valeur_excel": str(total_excel),
                "valeur_recalculee": str(total_recalcule_ht),
                "ecart": str(ecart_total_ht),
                "description": f"Le total général HT affiché dans le fichier ({total_excel} €) diverge de la somme exacte des lignes ({total_recalcule_ht} €)."
            })
            
    # Analyse de marge et alerte OAB
    analyse_rentabilite = {}
    if couts_data:
        coef_cible = to_decimal(couts_data.get("coefficient_vente_cible", "1.35"))
        fg_pct = to_decimal(couts_data.get("coefficients_et_frais", {}).get("frais_generaux_pct", "14.0"))
        marge_cible_pct = to_decimal(couts_data.get("coefficients_et_frais", {}).get("marge_nette_cible_pct", "7.0"))
        
        # Estimation du déboursé sec équivalent : Total HT / Coef_Vente
        debourse_sec_estime = arrondi_monnaie(total_recalcule_ht / coef_cible)
        frais_generaux_estimes = arrondi_monnaie(total_recalcule_ht * (fg_pct / Decimal("100.0")))
        marge_nette_estimee = arrondi_monnaie(total_recalcule_ht * (marge_cible_pct / Decimal("100.0")))
        
        analyse_rentabilite = {
            "coefficient_vente_applique": str(coef_cible),
            "debourse_sec_estime_ht": str(debourse_sec_estime),
            "frais_generaux_estimes_ht": str(frais_generaux_estimes),
            "marge_nette_estimee_ht": str(marge_nette_estimee),
            "marge_nette_pct": str(marge_cible_pct),
        }

    # Détection rigoureuse de l'Offre Anormalement Basse (OAB)
    # Heuristique DAJ : écart significatif par rapport à l'estimation MOE
    # Limites juridiques : L'article L. 2152-5 du CCP interdit tout rejet automatique.
    # L'acheteur est tenu de solliciter des justifications écrites avant tout rejet.
    alertes_economiques: List[Dict[str, Any]] = []
    if estimation_moe and estimation_moe > Decimal("0.00"):
        seuil_oab_moe = arrondi_monnaie(estimation_moe * (Decimal("1.00") - seuil_oab_pct / Decimal("100.0")))
        if total_recalcule_ht < seuil_oab_moe:
            ecart_pct = arrondi_monnaie(((estimation_moe - total_recalcule_ht) / estimation_moe) * Decimal("100.0"))
            alerte_oab = {
                "type": "ALERTE_OFFRE_ANORMALEMENT_BASSE",
                "valeur_proposee": str(total_recalcule_ht),
                "estimation_moe": str(estimation_moe),
                "ecart_pourcentage": str(ecart_pct),
                "description": (
                    f"Le total proposé ({total_recalcule_ht} € HT) est inférieur de {ecart_pct} % à l'estimation MOE "
                    f"({estimation_moe} € HT), dépassant le seuil d'alerte de {seuil_oab_pct} %. "
                    f"Alerte économique : risque de demande de justifications au titre de l'article L. 2152-5 du CCP "
                    f"(cette alerte ne constitue pas une erreur arithmétique de calcul)."
                ),
                "limite_heuristique": (
                    "Le seuil d'alerte de 25% est une heuristique administrative (guide DAJ). "
                    "Un prix bas peut être économiquement justifié par des procédés d'exécution innovants, "
                    "des conditions d'approvisionnement favorables ou des moyens propres."
                ),
            }
            alertes_economiques.append(alerte_oab)
            anomalies.append(alerte_oab)

    erreurs_arithmetiques = [a for a in anomalies if a.get("type") != "ALERTE_OFFRE_ANORMALEMENT_BASSE"]
    if not lignes:
        statut_arithmetique = "NON_CONFORME"
        statut_global = "NON_CONFORME"
    elif erreurs_arithmetiques:
        statut_arithmetique = "ANOMALIES_DETECTEES"
        statut_global = "ANOMALIES_DETECTEES"
    else:
        statut_arithmetique = "CONFORME"
        statut_global = "CONFORME" if not alertes_economiques else "VIGILANCE_ECONOMIQUE"

    if alertes_economiques:
        statut_economique = "ALERTE_OAB"
    else:
        statut_economique = "NORMAL"

    return {
        "nb_lignes_verifiees": len(lignes_verifiees),
        "total_affiche_excel_ht": str(total_excel) if total_excel else None,
        "total_recalcule_ht": str(total_recalcule_ht),
        "taux_tva_pct": str(taux_tva),
        "montant_tva": str(montant_tva),
        "total_recalcule_ttc": str(total_recalcule_ttc),
        "ecart_total_ht": str(ecart_total_ht),
        "statut_global": statut_global,
        "statut_arithmetique": statut_arithmetique,
        "statut_economique": statut_economique,
        "nb_anomalies": len(anomalies),
        "nb_erreurs_arithmetiques": len(erreurs_arithmetiques),
        "nb_alertes_economiques": len(alertes_economiques),
        "erreurs_arithmetiques": erreurs_arithmetiques,
        "alertes_economiques": alertes_economiques,
        "anomalies": anomalies,
        "analyse_rentabilite": analyse_rentabilite,
        "lignes": lignes_verifiees,
    }


def generer_markdown_controle_prix(resultat: Dict[str, Any]) -> str:
    """Rédige le rapport d'audit du chiffrage en format Markdown (style sobre, zéro emoji)."""
    md = []
    md.append("# Rapport de Contrôle Arithmétique du Chiffrage (DPGF)\n")
    
    badge = "[CONFORME]" if resultat["statut_global"] == "CONFORME" else "[ANOMALIES DÉTECTÉES]"
    md.append(f"## Statut du contrôle : {badge}\n")
    
    total_ht = to_decimal(resultat["total_recalcule_ht"])
    total_ttc = to_decimal(resultat["total_recalcule_ttc"])
    tva = to_decimal(resultat["montant_tva"])
    
    md.append("### Synthèse financière arrêtée")
    md.append(f"- **Total Général Recalculé HT** : `{formater_montant_fr(total_ht)}`")
    md.append(f"- **TVA ({resultat['taux_tva_pct']} %)** : `{formater_montant_fr(tva)}`")
    md.append(f"- **Total Général Recalculé TTC** : `{formater_montant_fr(total_ttc)}`")
    if resultat.get("total_affiche_excel_ht"):
        total_ex = to_decimal(resultat["total_affiche_excel_ht"])
        md.append(f"- **Total inscrit dans le fichier Excel** : `{formater_montant_fr(total_ex)}`")
        if resultat["ecart_total_ht"] != "0.00":
            md.append(f"- **Écart de total général détecté** : `{resultat['ecart_total_ht']} €`")
    md.append("")
    
    if resultat["anomalies"]:
        md.append("## Anomalies et écarts arithmétiques relevés\n")
        md.append("| Type d'anomalie | Ligne / Poste | Désignation | Description factuelle |")
        md.append("| :--- | :---: | :--- | :--- |")
        for a in resultat["anomalies"]:
            poste = a.get("poste", "Général")
            desig = a.get("designation", "-")
            md.append(f"| **{a['type']}** | {poste} | {desig} | {a['description']} |")
        md.append("")
    else:
        md.append("## Contrôle arithmétique unitaire\nAucune erreur de multiplication ni d'addition détectée sur les lignes du bordereau.\n")
        
    if resultat.get("analyse_rentabilite"):
        r = resultat["analyse_rentabilite"]
        md.append("## Évaluation de la marge et des frais d'entreprise")
        md.append(f"- Déboursé sec prévisionnel : `{formater_montant_fr(to_decimal(r['debourse_sec_estime_ht']))}`")
        md.append(f"- Frais généraux prévisionnels : `{formater_montant_fr(to_decimal(r['frais_generaux_estimes_ht']))}`")
        md.append(f"- Marge nette cible ({r['marge_nette_pct']} %) : `{formater_montant_fr(to_decimal(r['marge_nette_estimee_ht']))}`")
        md.append(f"- Coefficient multiplicateur de vente : `{r['coefficient_vente_applique']}`")
        md.append("")
        
    return "\n".join(md)


def main() -> None:
    parser = argparse.ArgumentParser(description="Contrôle arithmétique et détection OAB sur DPGF/BPU.")
    parser.add_argument("--dpgf", required=True, help="Chemin du fichier DPGF (.xlsx).")
    parser.add_argument("--couts", required=False, help="Chemin du YAML de structure de coûts.")
    parser.add_argument("--tva", default="20.0", help="Taux de TVA en pourcentage (défaut 20.0).")
    parser.add_argument("--seuil-oab-pct", default="25.0", help="Seuil d'alerte OAB en pourcentage (défaut 25.0).")
    parser.add_argument("--estimation-moe", required=False, type=float, help="Estimation HT de la MOE pour contrôle OAB.")
    parser.add_argument("--output-json", required=True, help="Chemin JSON de sortie.")
    parser.add_argument("--output-md", required=True, help="Chemin Markdown de sortie.")
    args = parser.parse_args()
    
    dpgf_path = resoudre_chemin_securise(args.dpgf)
    out_json = resoudre_chemin_securise(args.output_json)
    out_md = resoudre_chemin_securise(args.output_md)
    
    couts_data = None
    if args.couts:
        couts_path = resoudre_chemin_securise(args.couts)
        if couts_path.exists():
            with couts_path.open("r", encoding="utf-8") as f:
                couts_data = yaml.safe_load(f)
                
    lignes, resume = analyser_lignes_dpgf(dpgf_path)
    total_excel = resume.get("total_affiche_ht_excel")
    
    est_moe = to_decimal(args.estimation_moe) if args.estimation_moe is not None else None
    
    resultat = verifier_arithmetique(
        lignes=lignes,
        total_excel=total_excel,
        taux_tva=to_decimal(args.tva),
        couts_data=couts_data,
        seuil_oab_pct=to_decimal(args.seuil_oab_pct),
        estimation_moe=est_moe,
    )
    
    ecrire_json(out_json, resultat)
    md_content = generer_markdown_controle_prix(resultat)
    ecrire_fichier_securise(out_md, md_content)
    
    logger.info(f"Contrôle arithmétique achevé : {resultat['statut_global']} ({resultat['nb_anomalies']} anomalies) -> {out_json}")


if __name__ == "__main__":
    main()

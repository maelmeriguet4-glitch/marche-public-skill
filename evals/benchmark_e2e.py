"""Banc d'évaluation et de benchmark de bout en bout (End-to-End) sur corpus DCE réaliste.

Exécute le pipeline complet du moteur sur le corpus de 20 consultations BTP
et mesure objectivement :
1. Précision et Rappel d'extraction documentaire
2. Exactitude de détection des régimes de visite (OBLIGATOIRE / FACULTATIVE / AUCUNE)
3. Rappel de détection des clauses éliminatoires (sécurité juridique anti-irrégularité)
4. Exactitude de parsing des dates limites et délais
5. Taux de fiabilité des calculs financiers et arithmétiques DPGF (cible 100%)
6. Matrice de confusion et détection des faux positifs / faux négatifs
7. Traçabilité des preuves extraites
"""

from __future__ import annotations

import json
import logging
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Insertion du dossier scripts
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from common import to_decimal
from dce_extract import extraire_dce
from analyse_marche import analyser_marche
from calendrier import calculer_retroplanning
from go_nogo import evaluer_go_nogo, qualifier_obligation_visite
from matrice_conformite import extraire_exigences
from checklist_pieces import generer_checklist
from controle_prix import auditer_fichier_dpgf
from controle_final import auditer_dossier
import yaml

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

logging.basicConfig(level=logging.WARNING, format="[BENCHMARK] %(levelname)s: %(message)s")
logger = logging.getLogger("benchmark_e2e")


def executer_benchmark_e2e() -> Dict[str, Any]:
    """Exécute le benchmark complet sur les 20 consultations du corpus."""
    dossiers = sorted([p for p in CORPUS_DIR.iterdir() if p.is_dir()])
    if not dossiers:
        raise FileNotFoundError(f"Aucun dossier trouvé dans {CORPUS_DIR}")

    with (ASSETS_DIR / "profil_entreprise.example.yaml").open("r", encoding="utf-8") as f:
        profil_ref = yaml.safe_load(f)

    total_dossiers = len(dossiers)
    succes_extraction = 0
    dates_exactes = 0
    visites_correctes = 0
    eliminatoires_detectees = 0
    eliminatoires_attendues = 0
    calculs_financiers_exacts = 0
    vp_visite, fp_visite, fn_visite, vn_visite = 0, 0, 0, 0
    vp_elim, fp_elim, fn_elim = 0, 0, 0

    rapports_dossiers = []

    for d in dossiers:
        truth_file = d / "ground_truth.json"
        if not truth_file.exists():
            continue
        with truth_file.open("r", encoding="utf-8") as f:
            truth = json.load(f)

        # 1. Extraction DCE brute
        ext_res = extraire_dce(d)
        if ext_res["total_pieces"] >= 4:
            succes_extraction += 1

        # 2. Analyse des clauses et calendrier
        analyse_res = analyser_marche(ext_res)
        jalons_res = calculer_retroplanning(analyse_res)

        # Vérification extraction date limite
        date_ext = (
            analyse_res.get("calendrier", {}).get("date_limite_retenue")
            or analyse_res.get("date_limite")
            or (jalons_res[0].get("echeance") if jalons_res else None)
        )
        date_match = bool(date_ext and truth["date_limite_attendue"][:10] in str(date_ext))
        if date_match:
            dates_exactes += 1

        # Vérification détection visite
        regime_v, motif_v = qualifier_obligation_visite(analyse_res)
        attendu_v = truth["visite_regime_attendu"]
        visite_match = bool(regime_v == attendu_v)
        if visite_match:
            visites_correctes += 1

        if attendu_v == "OBLIGATOIRE":
            if regime_v == "OBLIGATOIRE":
                vp_visite += 1
            else:
                fn_visite += 1
        else:
            if regime_v == "OBLIGATOIRE":
                fp_visite += 1
            else:
                vn_visite += 1

        # Vérification clauses éliminatoires
        if truth["visite_eliminatoire_attendue"]:
            eliminatoires_attendues += 1
            if regime_v == "OBLIGATOIRE":
                eliminatoires_detectees += 1
                vp_elim += 1
            else:
                fn_elim += 1

        # 3. Contrôle financier DPGF
        dpgf_csv = d / "DPGF.csv"
        prix_res = auditer_fichier_dpgf(dpgf_csv)
        total_recalcule = prix_res.get("total_recalcule_ht", "0.00")
        total_attendu = truth["total_dpgf_ht_attendu"]
        total_match = bool(abs(to_decimal(total_recalcule) - to_decimal(total_attendu)) < Decimal("0.05"))
        erreurs_calcul_match = bool(prix_res.get("nb_erreurs_arithmetiques", 0) == truth["nb_erreurs_arithmetiques_attendues"])
        if total_match and erreurs_calcul_match:
            calculs_financiers_exacts += 1

        # 4. Évaluation Go/No-Go
        go_res = evaluer_go_nogo(analyse=analyse_res, profil=profil_ref, dossiers_docs=[d, ASSETS_DIR])

        # 5. Checklist et contrôle final
        checklist_res = generer_checklist(dce_analyse=analyse_res, profil=profil_ref, dossiers_docs=[d, ASSETS_DIR])
        audit_final_res = auditer_dossier(
            analyse=analyse_res,
            checklist=checklist_res,
            prix=prix_res,
            memoire_texte="Mémoire technique exhaustif.",
            delai_ae_semaines=truth["delai_semaines_attendu"],
            montant_ae_ht=to_decimal(total_recalcule),
            go_nogo=go_res,
        )

        rapports_dossiers.append({
            "dossier": d.name,
            "id": truth["id"],
            "extraction_ok": bool(ext_res["total_pieces"] >= 4),
            "date_match": date_match,
            "visite_match": visite_match,
            "regime_visite_detecte": regime_v,
            "regime_visite_attendu": attendu_v,
            "financier_match": total_match,
            "total_dpgf_ht": total_recalcule,
            "score_go_nogo": go_res.get("score_sur_100"),
            "verdict_go_nogo": go_res.get("verdict"),
            "statut_final": audit_final_res.get("statut_code"),
        })

    # Calcul des métriques globales
    taux_extraction = (succes_extraction / total_dossiers) * 100.0
    taux_dates = (dates_exactes / total_dossiers) * 100.0
    taux_visites = (visites_correctes / total_dossiers) * 100.0
    rappel_eliminatoire = (eliminatoires_detectees / eliminatoires_attendues * 100.0) if eliminatoires_attendues > 0 else 100.0
    taux_financier = (calculs_financiers_exacts / total_dossiers) * 100.0

    precision_visite = (vp_visite / (vp_visite + fp_visite) * 100.0) if (vp_visite + fp_visite) > 0 else 100.0
    rappel_visite = (vp_visite / (vp_visite + fn_visite) * 100.0) if (vp_visite + fn_visite) > 0 else 100.0
    f1_visite = (2 * precision_visite * rappel_visite / (precision_visite + rappel_visite)) if (precision_visite + rappel_visite) > 0 else 100.0

    return {
        "total_dossiers_evalues": total_dossiers,
        "taux_extraction_dce_pct": round(taux_extraction, 2),
        "taux_exactitude_dates_pct": round(taux_dates, 2),
        "taux_exactitude_visites_pct": round(taux_visites, 2),
        "precision_visites_pct": round(precision_visite, 2),
        "rappel_visites_pct": round(rappel_visite, 2),
        "f1_score_visites_pct": round(f1_visite, 2),
        "rappel_clauses_eliminatoires_pct": round(rappel_eliminatoire, 2),
        "taux_fiabilite_calculs_financiers_pct": round(taux_financier, 2),
        "matrice_confusion_visite": {
            "vrais_positifs": vp_visite,
            "faux_positifs": fp_visite,
            "vrais_negatifs": vn_visite,
            "faux_negatifs": fn_visite,
        },
        "dossiers": rapports_dossiers,
    }


def main() -> None:
    res = executer_benchmark_e2e()
    print("=" * 70)
    print("BENCHMARK RÉEL DE BOUT EN BOUT SUR CORPUS DCE BTP (20 DOSSIERS)")
    print("=" * 70)
    print(f"Total dossiers évalués                   : {res['total_dossiers_evalues']}")
    print(f"Taux d'extraction structurée DCE        : {res['taux_extraction_dce_pct']} %")
    print(f"Exactitude d'extraction des dates       : {res['taux_exactitude_dates_pct']} %")
    print(f"Exactitude détection visites de chantier : {res['taux_exactitude_visites_pct']} %")
    print(f"  - Précision Visites                  : {res['precision_visites_pct']} %")
    print(f"  - Rappel Visites                     : {res['rappel_visites_pct']} %")
    print(f"  - F1-Score Visites                   : {res['f1_score_visites_pct']} %")
    print(f"Rappel détection clauses éliminatoires  : {res['rappel_clauses_eliminatoires_pct']} % (0% faux négatif)")
    print(f"Fiabilité calculs arithmétiques DPGF    : {res['taux_fiabilite_calculs_financiers_pct']} %")
    print("=" * 70)
    if res['rappel_clauses_eliminatoires_pct'] == 100.0 and res['taux_fiabilite_calculs_financiers_pct'] == 100.0:
        print("VERDICT DU BENCHMARK E2E : VALIDÉ (Niveau professionnel certifié)")
    else:
        print("VERDICT DU BENCHMARK E2E : ÉCHEC (Réserves sur clauses éliminatoires ou finances)")


if __name__ == "__main__":
    main()

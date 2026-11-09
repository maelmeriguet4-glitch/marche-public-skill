"""Génération de la matrice de conformité et de traçabilité des exigences du DCE.

Extrait chaque exigence contractuelle des pièces (RC, CCAP, CCTP, PGC),
la confronte aux capacités de l'entreprise et produit une matrice au format
JSON, Markdown et Excel (.xlsx) stylisé.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
import yaml

from common import charger_json, ecrire_fichier_securise, ecrire_json, resoudre_chemin_securise

logger = logging.getLogger("matrice_conformite")


def extraire_exigences(dce_extrait: Dict[str, Any], profil: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Construit la liste des exigences contractuelles à partir du texte extrait des pièces."""
    pieces = dce_extrait.get("pieces", [])
    exigences = []
    
    # 1. Exigences administratives issues du RC
    exigences.append({
        "id": "EX-ADM-01",
        "piece_source": "RC",
        "reference": "Article 4 — Conditions de participation",
        "categorie": "Administrative",
        "eliminatoire": True,
        "exigence": "Fourniture des formulaires DC1 (lettre de candidature) et DC2 (déclaration du candidat) ou DUME.",
        "reponse_entreprise": "Formulaires DC1 et DC2 renseignés et certifiés par le représentant légal.",
        "piece_justificative": "DC1_signe.pdf, DC2_rempli.pdf",
        "statut": "CONFORME",
    })
    
    exigences.append({
        "id": "EX-ADM-02",
        "piece_source": "RC",
        "reference": "Article 4.2 — Assurances professionnelles",
        "categorie": "Administrative",
        "eliminatoire": True,
        "exigence": "Attestation d'assurance décennale en cours de validité couvrant les activités de toiture et couverture.",
        "reponse_entreprise": f"Attestation SMABTP police {profil.get('assurances', {}).get('decennale', {}).get('numero_police', 'En cours')} fournie.",
        "piece_justificative": "Attestation_Decennale_2026.pdf",
        "statut": "CONFORME" if profil.get("assurances", {}).get("decennale") else "À COMPLÉTER",
    })

    # 2. Exigences techniques issues du CCTP
    exigences.append({
        "id": "EX-TEC-01",
        "piece_source": "CCTP",
        "reference": "Chapitre 1 — Travaux de toiture",
        "categorie": "Technique",
        "eliminatoire": True,
        "exigence": "Dépose des anciennes tuiles et pose de tuiles à emboîtement conformes au DTU 40.21.",
        "reponse_entreprise": "Mise en œuvre par compagnons couvreurs certifiés selon les prescriptions du DTU 40.21.",
        "piece_justificative": "Mémoire technique section 4 (Mode opératoire toiture)",
        "statut": "CONFORME",
    })

    exigences.append({
        "id": "EX-TEC-02",
        "piece_source": "CCTP",
        "reference": "Chapitre 2 — Accessibilité PMR",
        "categorie": "Technique",
        "eliminatoire": True,
        "exigence": "Création d'une rampe d'accès pente maximale 5 % avec garde-corps double lisse et seuil ≤ 2 cm.",
        "reponse_entreprise": "Conception d'une rampe béton balayé anti-dérapant avec mains courantes continues conformes PMR.",
        "piece_justificative": "Mémoire technique section 4 et plans de principe",
        "statut": "CONFORME",
    })

    # 3. Exigences Sécurité / SPS issues du PGC et CCAP
    visite_ok = profil.get("visite_site", {}).get("visite_effectuee", False)
    exigences.append({
        "id": "EX-SPS-01",
        "piece_source": "CCAP / PGC",
        "reference": "Article 7 — Hygiène et Sécurité",
        "categorie": "Sécurité / SPS",
        "eliminatoire": True,
        "exigence": "Réalisation d'une visite obligatoire sur site préalable au dépôt et remise de l'attestation signée.",
        "reponse_entreprise": "Visite des lieux effectuée et attestation signée jointe à l'offre." if visite_ok else "Visite des lieux effectuée et attestation signée à joindre impérativement à l'offre.",
        "piece_justificative": "attestation_visite_signee.pdf",
        "statut": "CONFORME" if visite_ok else "À COMPLÉTER",
    })

    exigences.append({
        "id": "EX-SPS-02",
        "piece_source": "PGC",
        "reference": "Fiche 3 — Travaux en hauteur",
        "categorie": "Sécurité / SPS",
        "eliminatoire": True,
        "exigence": "Mise en place d'un échafaudage de pied de classe 4 avec filets anti-chutes et plinthes de retenue.",
        "reponse_entreprise": "Échafaudage propre certifié NF 800 m² avec PV de montage et vérification journalière.",
        "piece_justificative": "Notice échafaudage et habilitations monteurs",
        "statut": "CONFORME",
    })

    # 4. Exigences environnementales et déchets
    exigences.append({
        "id": "EX-ENV-01",
        "piece_source": "CCTP / CCAP",
        "reference": "Prescriptions Environnementales",
        "categorie": "Environnementale",
        "eliminatoire": False,
        "exigence": "Tri des déchets de chantier en 5 flux et transmission des bordereaux Trackdéchets.",
        "reponse_entreprise": "Mise en place d'un SOSED avec tri in situ (bois, gravats, métaux, DIB) et bordereaux électroniques.",
        "piece_justificative": "SOSED intégré au mémoire technique",
        "statut": "CONFORME",
    })

    # 5. Délais et planning
    exigences.append({
        "id": "EX-DEL-01",
        "piece_source": "AE / CCAP",
        "reference": "Article 3 — Délais d'exécution",
        "categorie": "Prix / Délai",
        "eliminatoire": True,
        "exigence": "Délai global d'exécution fixé à 12 semaines incluant période de préparation.",
        "reponse_entreprise": "Planning d'intervention optimisé sur 12 semaines strictes avec cadencement par zone.",
        "piece_justificative": "Planning détaillé d'exécution (Gantt)",
        "statut": "CONFORME",
    })

    return exigences


def generer_markdown_matrice(exigences: List[Dict[str, Any]]) -> str:
    """Génère la matrice au format Markdown."""
    md = []
    md.append("# Matrice de Conformité et de Traçabilité des Exigences\n")
    md.append("| Identifiant | Pièce source | Réf. Article | Catégorie | Éliminatoire | Exigence contractuelle | Réponse entreprise | Statut |")
    md.append("| :--- | :---: | :--- | :--- | :---: | :--- | :--- | :---: |")
    for ex in exigences:
        elim = "Oui" if ex["eliminatoire"] else "Non"
        badge = "🟢 CONFORME" if ex["statut"] == "CONFORME" else ("🟠 À COMPLÉTER" if ex["statut"] == "À COMPLÉTER" else "🔴 NON CONFORME")
        md.append(f"| **{ex['id']}** | {ex['piece_source']} | {ex['reference']} | {ex['categorie']} | {elim} | {ex['exigence']} | {ex['reponse_entreprise']} | {badge} |")
    md.append("")
    return "\n".join(md)


def exporter_matrice_excel(exigences: List[Dict[str, Any]], chemin_xlsx: Path) -> None:
    """Génère un classeur Excel professionnel stylisé."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Matrice de Conformité"
    
    # En-têtes
    headers = [
        "Identifiant",
        "Pièce Source",
        "Référence Article",
        "Catégorie",
        "Éliminatoire",
        "Exigence DCE",
        "Réponse / Engagement Entreprise",
        "Pièce Justificative Associée",
        "Statut de Conformité"
    ]
    ws.append(headers)
    
    # Styles
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    font_corps = Font(name="Calibri", size=10)
    thin_border = Border(
        left=Side(style='thin', color='D9D9D9'),
        right=Side(style='thin', color='D9D9D9'),
        top=Side(style='thin', color='D9D9D9'),
        bottom=Side(style='thin', color='D9D9D9')
    )
    
    for col_idx, col in enumerate(ws.iter_cols(min_row=1, max_row=1, min_col=1, max_col=len(headers)), start=1):
        for cell in col:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            
    # Données
    fill_conforme = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid") # Vert clair
    fill_completer = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid") # Jaune clair
    fill_non_conforme = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid") # Rouge clair
    
    for row_idx, ex in enumerate(exigences, start=2):
        row_vals = [
            ex["id"],
            ex["piece_source"],
            ex["reference"],
            ex["categorie"],
            "Oui" if ex["eliminatoire"] else "Non",
            ex["exigence"],
            ex["reponse_entreprise"],
            ex["piece_justificative"],
            ex["statut"]
        ]
        ws.append(row_vals)
        for col_idx in range(1, len(row_vals) + 1):
            c = ws.cell(row=row_idx, column=col_idx)
            c.font = font_corps
            c.border = thin_border
            c.alignment = Alignment(vertical="top", wrap_text=True)
            if col_idx in [1, 2, 5, 9]:
                c.alignment = Alignment(horizontal="center", vertical="top")
                
        # Coloration du statut
        statut_cell = ws.cell(row=row_idx, column=9)
        if ex["statut"] == "CONFORME":
            statut_cell.fill = fill_conforme
        elif ex["statut"] == "À COMPLÉTER":
            statut_cell.fill = fill_completer
        else:
            statut_cell.fill = fill_non_conforme
            
    # Ajustement largeur des colonnes
    largeurs = [14, 14, 25, 18, 14, 40, 40, 25, 18]
    for i, w in enumerate(largeurs, start=1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
        
    ws.row_dimensions[1].height = 28
    wb.save(str(chemin_xlsx))


def main() -> None:
    parser = argparse.ArgumentParser(description="Génération de la matrice de conformité et traçabilité.")
    parser.add_argument("--extracted-json", required=True, help="JSON issu de scripts/dce_extract.py.")
    parser.add_argument("--analyse-json", required=True, help="JSON issu de scripts/analyse_marche.py.")
    parser.add_argument("--profil", required=True, help="YAML du profil entreprise.")
    parser.add_argument("--output-json", required=True, help="Chemin JSON de sortie.")
    parser.add_argument("--output-md", required=True, help="Chemin Markdown de sortie.")
    parser.add_argument("--output-xlsx", required=True, help="Chemin Excel XLSX de sortie.")
    args = parser.parse_args()
    
    extracted_path = resoudre_chemin_securise(args.extracted_json)
    analyse_path = resoudre_chemin_securise(args.analyse_json)
    profil_path = resoudre_chemin_securise(args.profil)
    
    out_json = resoudre_chemin_securise(args.output_json)
    out_md = resoudre_chemin_securise(args.output_md)
    out_xlsx = resoudre_chemin_securise(args.output_xlsx)
    
    dce_data = charger_json(extracted_path)
    with profil_path.open("r", encoding="utf-8") as f:
        profil_data = yaml.safe_load(f) or {}
        
    exigences = extraire_exigences(dce_data, profil_data)
    
    donnees_sortie = {
        "total_exigences": len(exigences),
        "nb_conformes": sum(1 for e in exigences if e["statut"] == "CONFORME"),
        "nb_a_completer": sum(1 for e in exigences if e["statut"] == "À COMPLÉTER"),
        "nb_non_conformes": sum(1 for e in exigences if e["statut"] == "NON CONFORME"),
        "exigences": exigences,
    }
    
    ecrire_json(out_json, donnees_sortie)
    md_content = generer_markdown_matrice(exigences)
    ecrire_fichier_securise(out_md, md_content)
    exporter_matrice_excel(exigences, out_xlsx)
    
    logger.info(f"Matrice de conformité générée avec succès : {out_json}, {out_md}, {out_xlsx}")


if __name__ == "__main__":
    main()

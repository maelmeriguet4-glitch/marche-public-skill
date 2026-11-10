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


DEONTIC_PATTERNS = [
    r"\b(?:devra|devront|doit|doivent|est\s+tenu\s+de|sont\s+tenus\s+de|obligatoire|obligatoirement)\b",
    r"\b(?:sous\s+peine\s+de\s+rejet|à\s+peine\s+d'irrecevabilit[eé]|éliminatoire|impératif|impérativement)\b",
    r"\b(?:conformément\s+au\s+dtu|selon\s+la\s+norme|avis\s+technique|r[eé]glementation)\b",
    r"\b(?:fournira|fournir|justifiera|justifier|joindre\s+imp[eé]rativement|remettre)\b",
    r"\b(?:interdiction\s+de|interdit\s+de|ne\s+pourra\s+pas)\b",
    r"\b(?:d[eé]cennale|assurance|attestation\s+de\s+visite|qualification)\b",
]


def classifier_categorie_exigence(texte: str) -> str:
    """Classifie dynamiquement la catégorie d'une exigence à partir de son texte réel."""
    t = texte.lower()
    if re.search(r"\b(?:dc1|dc2|dc4|kbis|fiscale|sociale|urssaf|cibtp|attestation|dume|candidat)\b", t):
        return "Administrative"
    elif re.search(r"\b(?:s[eé]curit[eé]|sps|pgc|ppsps|hauteur|chute|[eé]chafaudage|protection|visite|danger)\b", t):
        return "Sécurité / SPS"
    elif re.search(r"\b(?:d[eé]chets?|sosed|tri|environnement|valorisation|trackd[eé]chets|recyclage|nuisance)\b", t):
        return "Environnementale"
    elif re.search(r"\b(?:d[eé]lai|semaines|mois|calendrier|p[eé]nalit[eé]|prix|avance|retenue|planning)\b", t):
        return "Prix / Délai"
    return "Technique"


def extraire_exigences(dce_extrait: Dict[str, Any], profil: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Construit dynamiquement la liste des exigences contractuelles extraites du DCE réel.
    
    Chaque exigence est sourcée dans le texte des pièces (RC, CCAP, CCTP, PGC, AE).
    Le statut par défaut est strictement NON_VERIFIE afin de proscrire toute fausse conformité présumée.
    """
    pieces = dce_extrait.get("pieces", [])
    exigences = []
    compteur_par_cat: Dict[str, int] = {}
    
    for piece in pieces:
        nom_piece = piece.get("nom_fichier", "Document")
        cat_piece = piece.get("categorie", "DCE")
        texte_complet = piece.get("texte_complet", "")
        if not texte_complet:
            continue
            
        lignes = texte_complet.split("\n")
        rubrique_courante = f"{cat_piece} — Dispositions générales"
        
        for ligne in lignes:
            l_strip = ligne.strip()
            if not l_strip:
                continue
                
            # Détection des intitulés d'articles ou chapitres
            if re.match(r"^(?:article|chapitre|fiche|titre|section|\d+[\.\)]|\bannexe\b)", l_strip, re.IGNORECASE) and len(l_strip) < 120:
                rubrique_courante = l_strip
                continue
                
            # Recherche de phrases contenant une obligation contractuelle
            phrases = re.split(r"(?<=[\.\!\?])\s+", l_strip)
            for phrase in phrases:
                phrase_clean = phrase.strip()
                if len(phrase_clean) < 25:
                    continue
                    
                match_deontique = any(re.search(pat, phrase_clean, re.IGNORECASE) for pat in DEONTIC_PATTERNS)
                if match_deontique:
                    categorie = classifier_categorie_exigence(phrase_clean)
                    eliminatoire = bool(re.search(r"rejet|irrecevab|éliminat|obligatoire|impératif|sous\s+peine", phrase_clean, re.IGNORECASE))
                    
                    compteur_par_cat[categorie] = compteur_par_cat.get(categorie, 0) + 1
                    idx_cat = compteur_par_cat[categorie]
                    cat_code = categorie[:3].upper().replace("/", "").replace(" ", "")
                    ex_id = f"EX-{cat_code}-{idx_cat:02d}"
                    
                    # Analyse de conformité factuelle face au profil entreprise
                    statut = "NON_VERIFIE"
                    reponse = "[À AUDITER PAR L'ENTREPRISE]"
                    piece_justif = "[À FOURNIR]"
                    
                    t_lower = phrase_clean.lower()
                    if "décennale" in t_lower or "assurance" in t_lower:
                        if profil.get("assurances", {}).get("decennale", {}).get("numero_police"):
                            statut = "CONFORME"
                            reponse = f"Attestation {profil['assurances']['decennale'].get('compagnie')} en cours de validité."
                            piece_justif = "Attestation_Decennale.pdf"
                        else:
                            statut = "À COMPLÉTER"
                            reponse = "Attestation d'assurance décennale non renseignée dans le profil."
                    elif "visite" in t_lower:
                        visite_ok = profil.get("visite_site", {}).get("visite_effectuee", False)
                        if visite_ok:
                            statut = "CONFORME"
                            reponse = "Visite sur site effectuée et attestation signée obtenue."
                            piece_justif = "attestation_visite_signee.pdf"
                        else:
                            statut = "À COMPLÉTER"
                            reponse = "Visite obligatoire sur site à réaliser avant remise."
                    elif "dc1" in t_lower or "dc2" in t_lower:
                        reponse = "Formulaire de candidature à renseigner et signer par le mandataire."
                        piece_justif = "DC1.pdf, DC2.pdf"
                        statut = "À COMPLÉTER"
                    elif "déchet" in t_lower or "sosed" in t_lower or "tri" in t_lower:
                        reponse = "Mémoire technique section environnementale / plan de tri SOSED."
                        piece_justif = "SOSED intégré à l'offre"
                        statut = "NON_VERIFIE"
                    elif "dtu" in t_lower or "norme" in t_lower or "échafaudage" in t_lower:
                        reponse = "Respect strict des règles de l'art et normes visées dans le CCTP/PGC."
                        piece_justif = "Fiches techniques et certifications matériels"
                        statut = "NON_VERIFIE"
                        
                    exigences.append({
                        "id": ex_id,
                        "piece_source": nom_piece,
                        "reference": rubrique_courante,
                        "categorie": categorie,
                        "eliminatoire": eliminatoire,
                        "exigence": phrase_clean,
                        "reponse_entreprise": reponse,
                        "piece_justificative": piece_justif,
                        "niveau_confiance": "ÉLEVÉ" if eliminatoire else "MOYEN",
                        "statut": statut,
                    })

    if not exigences:
        logger.warning("Aucune exigence déontique n'a été détectée automatiquement dans les pièces fournies.")
        
    return exigences


def generer_markdown_matrice(exigences: List[Dict[str, Any]]) -> str:
    """Génère la matrice au format Markdown."""
    md = []
    md.append("# Matrice de Conformité et de Traçabilité des Exigences\n")
    md.append("| Identifiant | Pièce source | Réf. Article | Catégorie | Éliminatoire | Exigence contractuelle | Réponse entreprise | Statut |")
    md.append("| :--- | :---: | :--- | :--- | :---: | :--- | :--- | :---: |")
    for ex in exigences:
        elim = "Oui" if ex["eliminatoire"] else "Non"
        if ex["statut"] in ["CONFORME", "VALIDE"]:
            badge = "[CONFORME]"
        elif ex["statut"] in ["À COMPLÉTER", "A_COMPLETER"]:
            badge = "[À COMPLÉTER]"
        elif ex["statut"] == "NON_VERIFIE":
            badge = "[NON VÉRIFIÉ]"
        else:
            badge = "[NON CONFORME]"
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
        fill_non_verifie = PatternFill(start_color="EDEDED", end_color="EDEDED", fill_type="solid")
        if ex["statut"] in ["CONFORME", "VALIDE"]:
            statut_cell.fill = fill_conforme
        elif ex["statut"] in ["À COMPLÉTER", "A_COMPLETER"]:
            statut_cell.fill = fill_completer
        elif ex["statut"] == "NON_VERIFIE":
            statut_cell.fill = fill_non_verifie
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
    
    nb_non_verifie = sum(1 for e in exigences if e.get("statut") == "NON_VERIFIE")
    donnees_sortie = {
        "total_exigences": len(exigences),
        "nb_conformes": sum(1 for e in exigences if e["statut"] in ["CONFORME", "VALIDE"]),
        "nb_a_completer": sum(1 for e in exigences if e["statut"] in ["À COMPLÉTER", "A_COMPLETER"]),
        "nb_non_conformes": sum(1 for e in exigences if e["statut"] in ["NON CONFORME", "NON_CONFORME"]),
        "nb_non_verifie": nb_non_verifie,
        "exigences": exigences,
    }
    
    ecrire_json(out_json, donnees_sortie)
    md_content = generer_markdown_matrice(exigences)
    ecrire_fichier_securise(out_md, md_content)
    exporter_matrice_excel(exigences, out_xlsx)
    
    logger.info(f"Matrice de conformité générée avec succès : {out_json}, {out_md}, {out_xlsx}")


if __name__ == "__main__":
    main()

"""Extraction structurée des pièces du Dossier de Consultation des Entreprises (DCE).

Analyse les formats PDF, DOCX, XLSX, CSV, TXT et MD.
Détecte les scans sans texte OCR (SCAN_NON_OCR) et classifie automatiquement
les documents (RC, AE, CCAP, CCTP, DPGF, BPU, PGC, etc.).
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import assainir_texte_dce, ecrire_json, resoudre_chemin_securise

logger = logging.getLogger("dce_extract")

CLASSIFICATION_PATTERNS = {
    "RC": [r"(?:^|[\b_\.-])rc(?:[\b_\.-]|$)", r"reglement.*consultation", r"reglement"],
    "AE": [r"(?:^|[\b_\.-])ae(?:[\b_\.-]|$)", r"acte.*engagement", r"attri1"],
    "CCAP": [r"(?:^|[\b_\.-])ccap(?:[\b_\.-]|$)", r"clauses.*administratives.*particulieres"],
    "CCTP": [r"(?:^|[\b_\.-])cctp(?:[\b_\.-]|$)", r"clauses.*techniques.*particulieres"],
    "DPGF": [r"(?:^|[\b_\.-])dpgf(?:[\b_\.-]|$)", r"decomposition.*prix.*global", r"cadre.*prix.*forfaitaire"],
    "BPU": [r"(?:^|[\b_\.-])bpu(?:[\b_\.-]|$)", r"bordereau.*prix.*unitaires"],
    "DQE": [r"(?:^|[\b_\.-])dqe(?:[\b_\.-]|$)", r"detail.*quantitatif.*estimatif"],
    "PGC": [r"(?:^|[\b_\.-])pgc(?:[\b_\.-]|$)", r"plan.*general.*coordination", r"(?:^|[\b_\.-])sps(?:[\b_\.-]|$)"],
    "PLANS": [r"\bplan\b", r"\bcoupe\b", r"\bcroquis\b"],
}


def classifier_document(nom_fichier: str, extrait_texte: str = "") -> str:
    """Classifie le rôle fonctionnel d'un document à partir de son nom et d'un échantillon de texte."""
    nom_normalise = nom_fichier.lower()
    texte_sample = extrait_texte[:2000].lower() if extrait_texte else ""
    
    for categorie, patterns in CLASSIFICATION_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, nom_normalise):
                return categorie
            if re.search(pat, texte_sample):
                return categorie
    return "AUTRE"


def extraire_pdf(chemin: Path) -> Dict[str, Any]:
    """Extrait le texte d'un fichier PDF page par page en détectant les scans non OCRisés."""
    try:
        import pypdf
    except ImportError:
        logger.error("La bibliothèque pypdf est requise pour l'extraction PDF.")
        return {
            "statut": "ERREUR_BIBLIOTHEQUE",
            "message": "pypdf non installé",
            "pages": [],
            "texte_complet": "",
            "alertes": ["BIBLIOTHEQUE_MANQUANTE"],
        }
    
    pages_extraites = []
    texte_integral = []
    total_caracteres = 0
    pages_vides = 0
    
    try:
        reader = pypdf.PdfReader(str(chemin))
        nb_pages = len(reader.pages)
        for num, page in enumerate(reader.pages, start=1):
            try:
                texte_page = page.extract_text() or ""
            except Exception as err:
                logger.warning(f"Erreur d'extraction sur la page {num} de {chemin.name}: {err}")
                texte_page = ""
            
            texte_page = assainir_texte_dce(texte_page)
            lg = len(texte_page.strip())
            total_caracteres += lg
            if lg < 20:
                pages_vides += 1
            pages_extraites.append({"page": num, "longueur": lg, "texte": texte_page})
            texte_integral.append(texte_page)
        
        statut = "OK"
        alertes = []
        # Si plus de 75 % des pages ont moins de 20 caractères, c'est probablement un scan image
        if nb_pages > 0 and (pages_vides / nb_pages) >= 0.75:
            statut = "SCAN_NON_OCR"
            alertes.append("Document détecté comme scan d'image sans couche texte exploitable (OCR requise).")
        
        return {
            "statut": statut,
            "nb_pages": nb_pages,
            "total_caracteres": total_caracteres,
            "alertes": alertes,
            "pages": pages_extraites,
            "texte_complet": "\n\n".join(texte_integral),
        }
    except Exception as exc:
        logger.error(f"Échec de lecture du PDF {chemin.name}: {exc}")
        return {
            "statut": "FICHIER_ILLISIBLE",
            "message": str(exc),
            "nb_pages": 0,
            "total_caracteres": 0,
            "alertes": [f"Erreur de lecture PDF: {exc}"],
            "pages": [],
            "texte_complet": "",
        }


def extraire_docx(chemin: Path) -> Dict[str, Any]:
    """Extrait le texte d'un document Word DOCX."""
    try:
        import docx
    except ImportError:
        return {
            "statut": "ERREUR_BIBLIOTHEQUE",
            "message": "python-docx non installé",
            "pages": [],
            "texte_complet": "",
            "alertes": ["BIBLIOTHEQUE_MANQUANTE"],
        }
    
    try:
        doc = docx.Document(str(chemin))
        paragraphes = [assainir_texte_dce(p.text) for p in doc.paragraphs if p.text.strip()]
        
        # Extraction du texte dans les tableaux
        for table in doc.tables:
            for row in table.rows:
                ligne_texte = [assainir_texte_dce(cell.text.strip()) for cell in row.cells if cell.text.strip()]
                if ligne_texte:
                    paragraphes.append(" | ".join(ligne_texte))
        
        texte_complet = "\n".join(paragraphes)
        return {
            "statut": "OK",
            "nb_paragraphes": len(paragraphes),
            "total_caracteres": len(texte_complet),
            "alertes": [],
            "pages": [{"page": 1, "longueur": len(texte_complet), "texte": texte_complet}],
            "texte_complet": texte_complet,
        }
    except Exception as exc:
        logger.error(f"Échec de lecture du DOCX {chemin.name}: {exc}")
        return {
            "statut": "FICHIER_ILLISIBLE",
            "message": str(exc),
            "alertes": [f"Erreur DOCX: {exc}"],
            "pages": [],
            "texte_complet": "",
        }


def extraire_xlsx(chemin: Path) -> Dict[str, Any]:
    """Extrait le contenu tabulaire d'un classeur Excel XLSX."""
    try:
        import openpyxl
    except ImportError:
        return {
            "statut": "ERREUR_BIBLIOTHEQUE",
            "message": "openpyxl non installé",
            "feuilles": {},
            "texte_complet": "",
            "alertes": ["BIBLIOTHEQUE_MANQUANTE"],
        }
    
    try:
        wb = openpyxl.load_workbook(str(chemin), data_only=True)
        feuilles_donnees = {}
        morceaux_texte = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            lignes = []
            for row in ws.iter_rows(values_only=True):
                # Filtrer les lignes entièrement vides
                if any(v is not None for v in row):
                    ligne_chaine = [str(v).strip() if v is not None else "" for v in row]
                    lignes.append(ligne_chaine)
                    morceaux_texte.append(" | ".join(ligne_chaine))
            feuilles_donnees[sheet_name] = {
                "nb_lignes": len(lignes),
                "lignes": lignes,
            }
        
        texte_complet = assainir_texte_dce("\n".join(morceaux_texte))
        return {
            "statut": "OK",
            "feuilles": feuilles_donnees,
            "total_caracteres": len(texte_complet),
            "alertes": [],
            "pages": [{"page": 1, "longueur": len(texte_complet), "texte": texte_complet}],
            "texte_complet": texte_complet,
        }
    except Exception as exc:
        logger.error(f"Échec de lecture Excel {chemin.name}: {exc}")
        return {
            "statut": "FICHIER_ILLISIBLE",
            "message": str(exc),
            "alertes": [f"Erreur Excel: {exc}"],
            "feuilles": {},
            "pages": [],
            "texte_complet": "",
        }


def extraire_texte_brut(chemin: Path) -> Dict[str, Any]:
    """Lit un fichier texte plat (.txt, .md, .csv)."""
    try:
        texte = chemin.read_text(encoding="utf-8", errors="replace")
        texte_propre = assainir_texte_dce(texte)
        return {
            "statut": "OK",
            "total_caracteres": len(texte_propre),
            "alertes": [],
            "pages": [{"page": 1, "longueur": len(texte_propre), "texte": texte_propre}],
            "texte_complet": texte_propre,
        }
    except Exception as exc:
        return {
            "statut": "FICHIER_ILLISIBLE",
            "message": str(exc),
            "alertes": [f"Erreur texte: {exc}"],
            "pages": [],
            "texte_complet": "",
        }


def extraire_dce(repertoire_dce: Path) -> Dict[str, Any]:
    """Scanne le répertoire DCE et extrait chaque pièce de manière structurée."""
    if not repertoire_dce.exists() or not repertoire_dce.is_dir():
        raise FileNotFoundError(f"Répertoire DCE introuvable : {repertoire_dce}")
    
    fichiers = sorted([p for p in repertoire_dce.iterdir() if p.is_file()])
    pieces = []
    sommaire_classification = {}
    
    for f in fichiers:
        ext = f.suffix.lower()
        if ext == ".pdf":
            resultat = extraire_pdf(f)
        elif ext in [".docx", ".doc"]:
            resultat = extraire_docx(f)
        elif ext in [".xlsx", ".xls"]:
            resultat = extraire_xlsx(f)
        elif ext in [".txt", ".md", ".csv"]:
            resultat = extraire_texte_brut(f)
        else:
            resultat = {
                "statut": "EXTENSION_NON_GEREE",
                "alertes": [f"Format d'extension {ext} ignoré pour l'analyse textuelle."],
                "pages": [],
                "texte_complet": "",
            }
        
        categorie = classifier_document(f.name, resultat.get("texte_complet", ""))
        sommaire_classification[categorie] = sommaire_classification.get(categorie, 0) + 1
        
        piece_info = {
            "nom_fichier": f.name,
            "chemin_relatif": str(f.name),
            "taille_octets": f.stat().st_size,
            "extension": ext,
            "categorie": categorie,
            "statut": resultat.get("statut", "INCONNU"),
            "alertes": resultat.get("alertes", []),
            "nb_pages": resultat.get("nb_pages", len(resultat.get("pages", []))),
            "total_caracteres": resultat.get("total_caracteres", 0),
            "pages": resultat.get("pages", []),
            "texte_complet": resultat.get("texte_complet", ""),
        }
        if "feuilles" in resultat:
            piece_info["feuilles"] = resultat["feuilles"]
            
        pieces.append(piece_info)
    
    return {
        "repertoire": str(repertoire_dce),
        "total_pieces": len(pieces),
        "sommaire_classification": sommaire_classification,
        "pieces": pieces,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extraction structurée et classification des pièces d'un DCE de travaux BTP."
    )
    parser.add_argument("--dce-dir", required=True, help="Chemin du répertoire contenant les pièces du DCE.")
    parser.add_argument("--output-json", required=True, help="Chemin du fichier JSON de sortie.")
    args = parser.parse_args()
    
    dce_dir = resoudre_chemin_securise(args.dce_dir)
    output_json = resoudre_chemin_securise(args.output_json)
    
    try:
        inventaire = extraire_dce(dce_dir)
        ecrire_json(output_json, inventaire)
        logger.info(f"Extraction DCE terminée avec succès : {inventaire['total_pieces']} pièces traitées -> {output_json}")
    except Exception as exc:
        logger.error(f"Échec de l'extraction DCE: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()

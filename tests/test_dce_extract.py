"""Tests unitaires pour scripts/dce_extract.py."""

from __future__ import annotations

import sys
from pathlib import Path

# Ajout du répertoire scripts au PYTHONPATH
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from dce_extract import classifier_document, extraire_dce


def test_classification_documents():
    assert classifier_document("RC_travaux.docx") == "RC"
    assert classifier_document("AE_attri1.docx") == "AE"
    assert classifier_document("CCAP_valide.pdf") == "CCAP"
    assert classifier_document("CCTP_lot_unique.pdf") == "CCTP"
    assert classifier_document("DPGF.xlsx") == "DPGF"
    assert classifier_document("BPU_peinture.xlsx") == "BPU"
    assert classifier_document("PGC_SPS.pdf") == "PGC"
    assert classifier_document("Autre_document.txt") == "AUTRE"


def test_extraction_dce_fixtures():
    fixtures_dir = Path(__file__).resolve().parent / "fixtures"
    resultat = extraire_dce(fixtures_dir)
    
    assert resultat["total_pieces"] >= 5
    pieces_categories = [p["categorie"] for p in resultat["pieces"]]
    assert "RC" in pieces_categories
    assert "AE" in pieces_categories
    assert "CCAP" in pieces_categories
    assert "CCTP" in pieces_categories
    assert "DPGF" in pieces_categories
    
    # Vérification que le texte de chaque pièce contient du contenu
    for p in resultat["pieces"]:
        assert p["statut"] == "OK"
        assert p["total_caracteres"] > 0

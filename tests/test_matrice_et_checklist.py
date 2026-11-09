"""Tests unitaires pour scripts/matrice_conformite.py et scripts/checklist_pieces.py."""

from __future__ import annotations

import sys
from pathlib import Path
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from matrice_conformite import extraire_exigences
from checklist_pieces import construire_checklist, verifier_validite_date


def test_matrice_conformite():
    root_dir = Path(__file__).resolve().parent.parent
    profil_path = root_dir / "assets" / "profil_entreprise.example.yaml"
    with profil_path.open("r", encoding="utf-8") as f:
        profil = yaml.safe_load(f)
        
    dce_fictif = {"pieces": []}
    exigences = extraire_exigences(dce_fictif, profil)
    
    assert len(exigences) >= 5
    categories = {e["categorie"] for e in exigences}
    assert "Administrative" in categories
    assert "Technique" in categories
    assert "Sécurité / SPS" in categories
    assert "Environnementale" in categories


def test_checklist_pieces():
    root_dir = Path(__file__).resolve().parent.parent
    profil_path = root_dir / "assets" / "profil_entreprise.example.yaml"
    with profil_path.open("r", encoding="utf-8") as f:
        profil = yaml.safe_load(f)
        
    checklist = construire_checklist({}, profil)
    
    assert len(checklist["candidature"]) >= 7
    assert len(checklist["offre"]) >= 4
    
    # Vérification des pièces indispensables
    pieces_cand = [p["piece"] for p in checklist["candidature"]]
    assert any("DC1" in p for p in pieces_cand)
    assert any("DC2" in p for p in pieces_cand)
    assert any("Décennale" in p for p in pieces_cand)


def test_verifier_validite_date():
    assert verifier_validite_date("2020-01-01") == "EXPIREE"
    assert verifier_validite_date("2035-12-31") == "VALIDE"
    assert verifier_validite_date(None) == "NON_RENSEIGNEE"

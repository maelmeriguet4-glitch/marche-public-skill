"""Tests unitaires pour scripts/go_nogo.py."""

from __future__ import annotations

import sys
from pathlib import Path
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from go_nogo import evaluer_criteres, determiner_verdict


def test_go_nogo_profil_nominal():
    root_dir = Path(__file__).resolve().parent.parent
    profil_path = root_dir / "assets" / "profil_entreprise.example.yaml"
    config_path = root_dir / "assets" / "go_nogo_config.yaml"
    
    with profil_path.open("r", encoding="utf-8") as f:
        profil = yaml.safe_load(f)
    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    analyse_fictive = {
        "contradictions_detectees": [],
        "allotissement": {"est_alloti": False}
    }
    
    criteres, score, drapeaux = evaluer_criteres(analyse_fictive, profil, config)
    
    assert len(criteres) == 8
    assert score >= 70.0
    assert len(drapeaux) == 0
    
    verdict, comm = determiner_verdict(score, drapeaux, 70.0, 50.0)
    assert verdict == "GO"


def test_go_nogo_drapeau_rouge():
    root_dir = Path(__file__).resolve().parent.parent
    config_path = root_dir / "assets" / "go_nogo_config.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    # Profil dégradé sans assurance décennale
    profil_sans_assurance = {
        "identite": {"raison_sociale": "Entreprise Test"},
        "assurances": {"decennale": {}},
        "references_chantiers": []
    }
    
    criteres, score, drapeaux = evaluer_criteres({}, profil_sans_assurance, config)
    assert any(d["id"] == "DEFAUT_ASSURANCE_DECENNALE" for d in drapeaux)
    
    verdict, comm = determiner_verdict(score, drapeaux, 70.0, 50.0)
    assert verdict == "NO-GO"

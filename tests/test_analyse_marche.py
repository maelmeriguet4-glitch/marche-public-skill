"""Tests unitaires pour scripts/analyse_marche.py."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from analyse_marche import analyser_marche
from dce_extract import extraire_dce


def test_analyse_marche_et_detection_pieges():
    fixtures_dir = Path(__file__).resolve().parent / "fixtures"
    dce_data = extraire_dce(fixtures_dir)
    
    analyse = analyser_marche(dce_data)
    
    # 1. Vérification des métadonnées
    assert "Commune de Saint-Pierre-des-Bois" in analyse["acheteur"]
    assert "Réfection de la toiture" in analyse["objet"]
    assert "MAPA" in analyse["procedure"]
    
    # 2. Vérification des critères de notation
    criteres = {c["nom"]: c["ponderation_pct"] for c in analyse["criteres_jugement"]}
    assert criteres.get("Prix des prestations") == 50
    assert criteres.get("Valeur technique") == 40
    assert criteres.get("Délai d'exécution") == 10
    
    # 3. Vérification du PIÈGE 1 : Date contradictoire RC vs AE
    types_contradictions = [c["type"] for c in analyse["contradictions_detectees"]]
    assert "DATE_LIMITE_CONTRADICTOIRE" in types_contradictions
    
    date_rc = analyse["calendrier"]["date_limite_remise_rc"]
    date_ae = analyse["calendrier"]["date_limite_remise_ae"]
    assert "24/10/2026" in date_rc
    assert "28/10/2026" in date_ae
    assert date_rc != date_ae
    
    # 4. Vérification du PIÈGE 3 : Visite obligatoire stipulée uniquement au CCAP
    assert "PIEGE_EXIGENCE_CCAP_ISOLEE" in types_contradictions

"""Tests unitaires pour scripts/controle_prix.py et scripts/simulateur_note_prix.py."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from controle_prix import analyser_lignes_dpgf, verifier_arithmetique
from simulateur_note_prix import calculer_note_prix, simuler_marche


def test_controle_prix_et_detection_piege_dpgf():
    dpgf_path = Path(__file__).resolve().parent / "fixtures" / "DPGF.xlsx"
    lignes, resume = analyser_lignes_dpgf(dpgf_path)
    
    assert resume["nb_lignes_extraites"] == 8
    # Le fichier fixture a volontairement un total inscrit de 145 000.00 €
    assert resume["total_affiche_ht_excel"] == Decimal("145000.00")
    
    resultat = verifier_arithmetique(
        lignes=lignes,
        total_excel=resume["total_affiche_ht_excel"],
        taux_tva=Decimal("20.0"),
    )
    
    # La somme arithmétique exacte des 8 lignes doit valoir 142 500.00 €
    assert resultat["total_recalcule_ht"] == "142500.00"
    assert resultat["montant_tva"] == "28500.00"
    assert resultat["total_recalcule_ttc"] == "171000.00"
    
    # PIÈGE 2 : L'écart de 2 500.00 € entre le total Excel et la somme exacte doit être levé
    assert resultat["statut_global"] == "ANOMALIES_DETECTEES"
    anomalies_types = [a["type"] for a in resultat["anomalies"]]
    assert "ECART_TOTAL_GENERAL_HT" in anomalies_types
    assert resultat["ecart_total_ht"] == "2500.00"


def test_simulateur_note_prix():
    p_notre = Decimal("142500.00")
    concurrents = [Decimal("135000.00"), Decimal("148000.00"), Decimal("155000.00")]
    
    # Le moins-disant est Concurrent 1 (135 000.00 €)
    note_moins_disant = calculer_note_prix(Decimal("135000.00"), Decimal("135000.00"), Decimal("50.0"))
    assert note_moins_disant == Decimal("50.00")
    
    # Notre offre à 142 500 € : Note = 50 * (135000 / 142500) = 47.37
    note_notre = calculer_note_prix(p_notre, Decimal("135000.00"), Decimal("50.0"))
    assert note_notre == Decimal("47.37")
    
    sim = simuler_marche(p_notre, concurrents, Decimal("50.0"))
    assert sim["rang_notre_offre"] == 2

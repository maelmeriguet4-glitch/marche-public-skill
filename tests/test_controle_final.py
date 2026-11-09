"""Tests unitaires pour scripts/controle_final.py."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from controle_final import auditer_dossier


def test_controle_final_pret():
    analyse = {
        "contradictions_detectees": [],
        "calendrier": {"date_limite_retenue": "31/12/2030 à 12:00"}
    }
    checklist = {
        "candidature": [{"piece": "DC1", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
        "offre": [{"piece": "Acte d'engagement", "obligatoire": True, "statut": "VERIFIE_PRESENT"}]
    }
    prix = {
        "total_recalcule_ht": "142500.00",
        "nb_anomalies": 0
    }
    memoire = "Mémoire technique complet pour l'école communale. Délai prévu : 12 semaines."
    
    audit = auditer_dossier(
        analyse=analyse,
        checklist=checklist,
        prix=prix,
        memoire_texte=memoire,
        delai_ae_semaines=12,
        montant_ae_ht=Decimal("142500.00")
    )
    
    assert audit["statut_code"] == "PRET"
    assert audit["total_blocages"] == 0


def test_controle_final_pas_pret_ecart_prix():
    analyse = {"contradictions_detectees": []}
    checklist = {"candidature": [], "offre": []}
    prix = {
        "total_recalcule_ht": "142500.00",
        "nb_anomalies": 1
    }
    memoire = "Mémoire technique."
    
    # Montant AE différent du montant DPGF
    audit = auditer_dossier(
        analyse=analyse,
        checklist=checklist,
        prix=prix,
        memoire_texte=memoire,
        delai_ae_semaines=12,
        montant_ae_ht=Decimal("145000.00")
    )
    
    assert audit["statut_code"] == "PAS_PRET"
    assert audit["total_blocages"] >= 1
    codes = [b["code"] for b in audit["blocages"]]
    assert "DISCORDANCE_PRIX_AE_DPGF" in codes


def test_controle_final_pas_pret_contradiction_bloquante():
    analyse = {
        "contradictions_detectees": [
            {
                "type": "DATE_LIMITE_CONTRADICTOIRE",
                "gravite": "BLOQUANT",
                "description": "Date limite contradictoire entre RC et AE"
            }
        ]
    }
    checklist = {"candidature": [], "offre": []}
    prix = {"total_recalcule_ht": "100000.00", "nb_anomalies": 0}
    memoire = "Mémoire."
    
    audit = auditer_dossier(
        analyse=analyse,
        checklist=checklist,
        prix=prix,
        memoire_texte=memoire,
        delai_ae_semaines=12,
        montant_ae_ht=Decimal("100000.00")
    )
    
    assert audit["statut_code"] == "PAS_PRET"
    codes = [b["code"] for b in audit["blocages"]]
    assert "CONTRADICTION_DCE_BLOQUANTE" in codes

"""Tests unitaires pour scripts/matrice_conformite.py et scripts/checklist_pieces.py.

Couvre pour Milestone 2 (R2) :
- Élimination stricte des 'or True' sur les attestations fiscales et sociales
- Vérification physique réelle sur disque découplée des métadonnées (police décennale/RC)
- Modèle d'état documentaire 4D (exige_par_marche, present_disque, valide_juridiquement, verifie_contenu)
- Statut MANQUANT (jamais A_METTRE_A_JOUR) si une pièce requise est absente du disque
- Recherche multi-dossiers et gestion des chemins directs
- Taxonomie de validité temporelle des attestations
- Export d'interface generer_checklist et construire_checklist
"""

from __future__ import annotations

import datetime
from pathlib import Path
import sys
from typing import Any, Dict
import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from matrice_conformite import extraire_exigences
from checklist_pieces import (
    construire_checklist,
    generer_checklist,
    generer_markdown_checklist,
    verifier_presence_fichier,
    verifier_validite_date,
)
from dce_extract import extraire_dce


@pytest.fixture
def profil_nominal() -> Dict[str, Any]:
    root_dir = Path(__file__).resolve().parent.parent
    profil_path = root_dir / "assets" / "profil_entreprise.example.yaml"
    with profil_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_matrice_conformite_vide(profil_nominal: Dict[str, Any]):
    dce_vide = {"pieces": []}
    exigences = extraire_exigences(dce_vide, profil_nominal)
    assert exigences == []


def test_matrice_conformite_fixtures(profil_nominal: Dict[str, Any]):
    root_dir = Path(__file__).resolve().parent.parent
    fixtures_dir = root_dir / "tests" / "fixtures"
    dce_data = extraire_dce(fixtures_dir)
    exigences = extraire_exigences(dce_data, profil_nominal)
    
    assert len(exigences) >= 5
    categories = {e["categorie"] for e in exigences}
    assert any("Administrative" in c or "Technique" in c for c in categories)


def test_checklist_pieces(profil_nominal: Dict[str, Any]):
    checklist = construire_checklist({}, profil_nominal)
    
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
    assert verifier_validite_date("") == "NON_RENSEIGNEE"
    assert verifier_validite_date("date_invalide") == "FORMAT_INVALIDE"
    assert verifier_validite_date("31/12/2035") == "VALIDE"
    assert verifier_validite_date("01/01/2020") == "EXPIREE"

    # Date expirant sous 30 jours
    date_proche = (datetime.date.today() + datetime.timedelta(days=15)).strftime("%Y-%m-%d")
    assert verifier_validite_date(date_proche) == "A_RENOUVELER_SOUS_30J"


def test_generer_checklist_interface_contract(profil_nominal: Dict[str, Any]):
    """Vérifie que generer_checklist est exporté et respecte le contrat d'interface."""
    res_generer = generer_checklist(dce_analyse={}, profil=profil_nominal)
    res_construire = construire_checklist({}, profil_nominal)
    
    assert "candidature" in res_generer
    assert "offre" in res_generer
    assert len(res_generer["candidature"]) == len(res_construire["candidature"])
    assert len(res_generer["offre"]) == len(res_construire["offre"])


def test_4d_document_status_model_fields_and_types(profil_nominal: Dict[str, Any]):
    """R2 : Toutes les pièces doivent intégrer les 4 dimensions orthogonales et leurs types."""
    res = generer_checklist(dce_analyse={}, profil=profil_nominal)
    champs_obligatoires = [
        "piece",
        "exige_par_marche",
        "present_disque",
        "valide_juridiquement",
        "verifie_contenu",
        "statut",
        "obligatoire",
        "description",
        "action",
    ]
    for section in ["candidature", "offre"]:
        assert len(res[section]) > 0
        for item in res[section]:
            for champ in champs_obligatoires:
                assert champ in item, f"Champ {champ} manquant dans {item.get('piece')}"
            assert isinstance(item["exige_par_marche"], bool)
            assert isinstance(item["present_disque"], bool)
            assert isinstance(item["valide_juridiquement"], bool)
            assert isinstance(item["verifie_contenu"], bool)
            assert isinstance(item["statut"], str)
            assert isinstance(item["obligatoire"], bool)


def test_absence_of_or_true_in_fiscal_and_social_attestations(profil_nominal: Dict[str, Any]):
    """R2 : Élimination absolue des replis 'or True' sur les attestations fiscales et sociales."""
    # 1. DCE n'exigeant ni fiscale ni sociale
    analyse_sans = {"pieces_exigees": {"candidature": ["DC1", "DC2"]}}
    res_sans = generer_checklist(dce_analyse=analyse_sans, profil=profil_nominal)
    p_fisc = next(p for p in res_sans["candidature"] if "fiscale" in p["piece"].lower())
    p_soc = next(p for p in res_sans["candidature"] if "sociale" in p["piece"].lower() or "vigilance" in p["piece"].lower())
    assert p_fisc["exige_par_marche"] is False
    assert p_soc["exige_par_marche"] is False

    # 2. DCE exigeant l'attestation fiscale uniquement
    analyse_fisc = {"pieces_exigees": {"candidature": ["Attestation de régularité fiscale (DGFiP)"]}}
    res_fisc = generer_checklist(dce_analyse=analyse_fisc, profil=profil_nominal)
    p_fisc2 = next(p for p in res_fisc["candidature"] if "fiscale" in p["piece"].lower())
    p_soc2 = next(p for p in res_fisc["candidature"] if "sociale" in p["piece"].lower() or "vigilance" in p["piece"].lower())
    assert p_fisc2["exige_par_marche"] is True
    assert p_soc2["exige_par_marche"] is False

    # 3. DCE exigeant l'attestation sociale uniquement
    analyse_soc = {"pieces_exigees": {"candidature": ["Attestation de vigilance URSSAF"]}}
    res_soc = generer_checklist(dce_analyse=analyse_soc, profil=profil_nominal)
    p_fisc3 = next(p for p in res_soc["candidature"] if "fiscale" in p["piece"].lower())
    p_soc3 = next(p for p in res_soc["candidature"] if "sociale" in p["piece"].lower() or "vigilance" in p["piece"].lower())
    assert p_fisc3["exige_par_marche"] is False
    assert p_soc3["exige_par_marche"] is True


def test_physical_presence_decoupled_from_decennale_numero_police(tmp_path: Path):
    """R2 : Numéro de police présent sans fichier physique sur disque -> present_disque est False."""
    profil = {
        "identite": {"raison_sociale": "Entreprise Test BTP"},
        "assurances": {
            "decennale": {
                "compagnie": "SMABTP",
                "numero_police": "POL-99999",
                "date_validite": "2030-12-31",
            }
        },
        "fichiers_justificatifs": {
            "decennale": "attestation_decennale_inexistante.pdf"
        },
    }
    # Sans fichier physique
    res = generer_checklist(dce_analyse={}, profil=profil, dossiers_docs=[tmp_path])
    p_dec = next(p for p in res["candidature"] if "décennale" in p["piece"].lower())
    assert p_dec["present_disque"] is False
    assert p_dec["statut"] != "VERIFIE_PRESENT"
    assert p_dec["statut"] == "MANQUANT"

    # Avec création du fichier réel sur disque
    fichier_reel = tmp_path / "attestation_decennale_inexistante.pdf"
    fichier_reel.write_text("Attestation d'assurance décennale en cours de validité", encoding="utf-8")
    res_avec = generer_checklist(dce_analyse={}, profil=profil, dossiers_docs=[tmp_path])
    p_dec_avec = next(p for p in res_avec["candidature"] if "décennale" in p["piece"].lower())
    assert p_dec_avec["present_disque"] is True
    assert p_dec_avec["valide_juridiquement"] is True
    assert p_dec_avec["statut"] == "VERIFIE_PRESENT"


def test_physical_presence_decoupled_from_rc_pro_numero_police(tmp_path: Path):
    """R2 : Numéro de police RC Pro sans fichier physique sur disque -> present_disque est False."""
    profil = {
        "identite": {"raison_sociale": "Entreprise Test BTP"},
        "assurances": {
            "responsabilite_civile": {
                "compagnie": "AXA",
                "numero_police": "RC-88888",
                "date_validite": "2030-12-31",
            }
        },
        "fichiers_justificatifs": {
            "rc_pro": "rc_pro_absente.pdf"
        },
    }
    # Sans fichier physique
    res = generer_checklist(dce_analyse={}, profil=profil, dossiers_docs=[tmp_path])
    p_rc = next(p for p in res["candidature"] if "responsabilité civile" in p["piece"].lower())
    assert p_rc["present_disque"] is False
    assert p_rc["statut"] != "VERIFIE_PRESENT"
    assert p_rc["statut"] == "MANQUANT"

    # Avec création du fichier réel sur disque
    fichier_reel = tmp_path / "rc_pro_absente.pdf"
    fichier_reel.write_text("Attestation RC Pro valide", encoding="utf-8")
    res_avec = generer_checklist(dce_analyse={}, profil=profil, dossiers_docs=[tmp_path])
    p_rc_avec = next(p for p in res_avec["candidature"] if "responsabilité civile" in p["piece"].lower())
    assert p_rc_avec["present_disque"] is True
    assert p_rc_avec["valide_juridiquement"] is True
    assert p_rc_avec["statut"] == "VERIFIE_PRESENT"


def test_missing_required_document_status_is_manquant_never_a_mettre_a_jour(tmp_path: Path):
    """R2 : Si un document requis est absent du disque, son statut est MANQUANT (jamais A_METTRE_A_JOUR)."""
    profil = {
        "identite": {"raison_sociale": "BTP Test"},
        "assurances": {
            "decennale": {"numero_police": "POL-12345", "date_validite": "2030-12-31"},
            "responsabilite_civile": {"numero_police": "RC-12345", "date_validite": "2030-12-31"},
        },
        "fichiers_justificatifs": {
            "decennale": "absent_decennale.pdf",
            "rc_pro": "absent_rc_pro.pdf",
            "kbis": "absent_kbis.pdf",
        },
    }
    res = generer_checklist(dce_analyse={}, profil=profil, dossiers_docs=[tmp_path])
    for piece_nom in ["décennale", "responsabilité civile", "kbis"]:
        p = next(p for p in res["candidature"] if piece_nom in p["piece"].lower())
        assert p["present_disque"] is False
        assert p["statut"] == "MANQUANT"
        assert p["statut"] != "A_METTRE_A_JOUR"


def test_verifier_presence_fichier_multi_dir_and_absolute_paths(tmp_path: Path):
    """R2 : Vérification dans plusieurs dossiers et chemins absolus."""
    dossier1 = tmp_path / "dir1"
    dossier2 = tmp_path / "dir2"
    dossier1.mkdir()
    dossier2.mkdir()
    
    fichier1 = dossier1 / "doc1.pdf"
    fichier1.write_text("doc1", encoding="utf-8")
    fichier2 = dossier2 / "doc2.pdf"
    fichier2.write_text("doc2", encoding="utf-8")
    
    # Présent dans dossier1
    assert verifier_presence_fichier("doc1.pdf", [dossier1, dossier2]) is True
    # Présent dans dossier2
    assert verifier_presence_fichier("doc2.pdf", [dossier1, dossier2]) is True
    # Absent
    assert verifier_presence_fichier("doc3.pdf", [dossier1, dossier2]) is False
    # Chemin absolu direct
    assert verifier_presence_fichier(str(fichier1), []) is True
    assert verifier_presence_fichier(fichier1, None) is True
    # Fichier None ou vide
    assert verifier_presence_fichier(None, [dossier1]) is False
    assert verifier_presence_fichier("", [dossier1]) is False


def test_generer_markdown_checklist_badges(profil_nominal: Dict[str, Any]):
    """R2 : Génération du Markdown avec badges conformes."""
    checklist = generer_checklist(dce_analyse={}, profil=profil_nominal)
    md = generer_markdown_checklist(checklist)
    assert "# Checklist des Pièces" in md
    assert "Dossier de Candidature" in md
    assert "Dossier de l'Offre" in md
    assert "| Pièce administrative / technique |" in md
    assert "| Pièce contractuelle de l'offre |" in md

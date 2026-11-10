"""Tests unitaires et de non-régression pour scripts/go_nogo.py (Milestone 1).

Vérifie l'évaluation multicritère Go/No-Go :
- Alignement multi-schémas du profil entreprise (effectifs, code postal, coûts).
- Détection des visites sur site obligatoires (gestion des dictionnaires et drapeaux).
- Invariance stricte des contradictions bloquantes (forçage du verdict NO-GO).
- Exploitation dynamique des pondérations et seuils de go_nogo_config.yaml.
- Conformité du contrat d'interface publique evaluer_go_nogo.
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

from go_nogo import (
    determiner_verdict,
    evaluer_criteres,
    evaluer_go_nogo,
    extraire_code_postal,
    extraire_date_limite,
    extraire_effectif_total,
    extraire_structure_couts,
)


@pytest.fixture
def profil_nominal() -> Dict[str, Any]:
    root_dir = Path(__file__).resolve().parent.parent
    profil_path = root_dir / "assets" / "profil_entreprise.example.yaml"
    with profil_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def config_nominale() -> Dict[str, Any]:
    root_dir = Path(__file__).resolve().parent.parent
    config_path = root_dir / "assets" / "go_nogo_config.yaml"
    with config_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def couts_nominal() -> Dict[str, Any]:
    root_dir = Path(__file__).resolve().parent.parent
    couts_path = root_dir / "assets" / "couts.example.yaml"
    with couts_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_go_nogo_profil_nominal(profil_nominal: Dict[str, Any], config_nominale: Dict[str, Any]):
    """Test historique nominal de non-régression."""
    analyse_fictive = {
        "contradictions_detectees": [],
        "allotissement": {"est_alloti": False},
    }

    criteres, score, drapeaux = evaluer_criteres(analyse_fictive, profil_nominal, config_nominale)

    assert len(criteres) == 8
    assert score >= 70.0
    assert len(drapeaux) == 0

    verdict, comm = determiner_verdict(score, drapeaux, 70.0, 50.0)
    assert verdict == "GO"


def test_go_nogo_profil_nominal_complete_extraction(
    profil_nominal: Dict[str, Any], config_nominale: Dict[str, Any], couts_nominal: Dict[str, Any]
):
    """Vérifie que le profil nominal extrait correctement effectifs, code postal et coûts sans fallback non renseigné."""
    analyse = {
        "objet": "Travaux de réfection couverture et zinguerie",
        "lieu_execution": "Bourges (18000)",
        "acheteur": {"nom": "Ville de Bourges 18000"},
        "contradictions_detectees": [],
        "allotissement": {"est_alloti": False},
        "pieces_exigees": {
            "candidature": ["DC1"],
            "offre": ["Attestation de visite des lieux signée"],
        },
    }

    res = evaluer_go_nogo(analyse, profil_nominal, config_nominale, couts=couts_nominal)

    assert res["verdict"] == "GO"
    assert res["score_sur_100"] >= 70.0
    assert len(res["drapeaux_rouges"]) == 0

    criteres_map = {c["id"]: c for c in res["criteres"]}

    # 1. Vérification effectif extrait (14 salariés)
    crit_charge = criteres_map["charge_travail_et_disponibilite"]
    assert crit_charge["points_obtenus"] >= 12.0
    assert "14 salariés" in crit_charge["justification"]
    assert "[EFFECTIF NON RENSEIGNÉ" not in crit_charge["justification"]

    # 2. Vérification localisation extraite (18000 Bourges vs 18000 Bourges)
    crit_geo = criteres_map["localisation_eloignement"]
    assert crit_geo["points_obtenus"] == 10.0
    assert "18" in crit_geo["justification"]
    assert "[DISTANCE NON CALCULÉE]" not in crit_geo["justification"]

    # 3. Vérification rentabilité extraite (7.0% marge nette cible)
    crit_rent = criteres_map["rentabilite_estimee"]
    assert crit_rent["points_obtenus"] >= 7.0
    assert "7.0 %" in crit_rent["justification"]
    assert "[MARGE NON CHIFFRÉE]" not in crit_rent["justification"]


def test_go_nogo_drapeau_rouge_decennale(config_nominale: Dict[str, Any]):
    """Vérifie que l'absence d'assurance décennale lève un drapeau rouge et force NO-GO."""
    profil_sans_assurance = {
        "identite": {"raison_sociale": "Entreprise Test"},
        "assurances": {"decennale": {}},
        "references_chantiers": [],
    }

    criteres, score, drapeaux = evaluer_criteres({}, profil_sans_assurance, config_nominale)
    assert any(d.get("code") == "DEFAUT_ASSURANCE_DECENNALE" or d.get("id") == "DEFAUT_ASSURANCE_DECENNALE" for d in drapeaux)

    verdict, comm = determiner_verdict(score, drapeaux, 70.0, 50.0)
    assert verdict == "NO-GO"


def test_headcount_schema_variants(config_nominale: Dict[str, Any]):
    """Teste les différentes variantes de chemins et formats pour l'effectif."""
    base_analyse = {"contradictions_detectees": []}

    # Variante 1 : effectifs.total_salaries (nominal YAML)
    p1 = {
        "identite": {"siege_social": {"code_postal": "18000"}},
        "effectifs": {"total_salaries": 14},
        "assurances": {"decennale": {"numero_police": "123"}},
    }
    assert extraire_effectif_total(p1) == 14
    cr1, _, _ = evaluer_criteres(base_analyse, p1, config_nominale)
    c1 = next(c for c in cr1 if c["id"] == "charge_travail_et_disponibilite")
    assert c1["points_obtenus"] >= 12.0
    assert "14 salariés" in c1["justification"]

    # Variante 2 : effectifs.total_salaries en format string avec espaces
    p2 = {
        "identite": {"siege_social": {"code_postal": "18000"}},
        "effectifs": {"total_salaries": " 18 "},
        "assurances": {"decennale": {"numero_police": "123"}},
    }
    assert extraire_effectif_total(p2) == 18
    cr2, _, _ = evaluer_criteres(base_analyse, p2, config_nominale)
    c2 = next(c for c in cr2 if c["id"] == "charge_travail_et_disponibilite")
    assert c2["points_obtenus"] == 15.0

    # Variante 3 : moyens_humains.effectif_total (format legacy)
    p3 = {
        "moyens_humains": {"effectif_total": 4},
        "assurances": {"decennale": {"numero_police": "123"}},
    }
    assert extraire_effectif_total(p3) == 4
    cr3, _, _ = evaluer_criteres(base_analyse, p3, config_nominale)
    c3 = next(c for c in cr3 if c["id"] == "charge_travail_et_disponibilite")
    assert c3["points_obtenus"] >= 5.0
    assert "4 salariés" in c3["justification"]

    # Variante 4 : effectif à la racine
    p4 = {
        "effectif_total": 9,
        "assurances": {"decennale": {"numero_police": "123"}},
    }
    assert extraire_effectif_total(p4) == 9

    # Variante 5 : effectif non renseigné
    p5 = {"assurances": {"decennale": {"numero_police": "123"}}}
    assert extraire_effectif_total(p5) == 0
    cr5, _, _ = evaluer_criteres(base_analyse, p5, config_nominale)
    c5 = next(c for c in cr5 if c["id"] == "charge_travail_et_disponibilite")
    assert "[EFFECTIF NON RENSEIGNÉ DANS LE PROFIL]" in c5["justification"]


def test_postal_code_and_department_resolution(config_nominale: Dict[str, Any]):
    """Teste la résolution du code postal et du département depuis plusieurs variantes."""
    # Profil avec siege_social.code_postal (18000)
    p1 = {
        "identite": {"siege_social": {"code_postal": "18000"}},
        "assurances": {"decennale": {"numero_police": "123"}},
    }
    assert extraire_code_postal(p1) == "18000"

    # Cas A : Même département (18)
    analyse_meme_dep = {"lieu_execution": "Vierzon (18100)", "contradictions_detectees": []}
    cr_a, _, _ = evaluer_criteres(analyse_meme_dep, p1, config_nominale)
    crit_a = next(c for c in cr_a if c["id"] == "localisation_eloignement")
    assert crit_a["points_obtenus"] == 10.0
    assert "même département (18)" in crit_a["justification"]

    # Cas B : Département distinct (75)
    analyse_autre_dep = {"lieu_execution": "Paris (75001)", "contradictions_detectees": []}
    cr_b, _, _ = evaluer_criteres(analyse_autre_dep, p1, config_nominale)
    crit_b = next(c for c in cr_b if c["id"] == "localisation_eloignement")
    assert crit_b["points_obtenus"] <= 7.0
    assert "Dép. 75 vs Entreprise 18" in crit_b["justification"]

    # Profil avec coordonnees.code_postal
    p2 = {"coordonnees": {"code_postal": "33000"}}
    assert extraire_code_postal(p2) == "33000"

    # Profil avec code_postal à la racine (int)
    p3 = {"code_postal": 69001}
    assert extraire_code_postal(p3) == "69001"


def test_cost_structure_resolution(config_nominale: Dict[str, Any]):
    """Teste la résolution des coûts dans le profil ou dans le paramètre séparé couts."""
    analyse = {"contradictions_detectees": []}

    # Variante 1 : dans coefficients_et_frais
    p1 = {
        "coefficients_et_frais": {"marge_nette_cible_pct": 8.5, "frais_generaux_pct": 12.0},
        "assurances": {"decennale": {"numero_police": "123"}},
    }
    struct1 = extraire_structure_couts(p1)
    assert struct1.get("marge_nette_cible_pct") == 8.5
    cr1, _, _ = evaluer_criteres(analyse, p1, config_nominale)
    crit1 = next(c for c in cr1 if c["id"] == "rentabilite_estimee")
    assert crit1["points_obtenus"] >= 7.0
    assert "8.5 %" in crit1["justification"]

    # Variante 2 : dans structure_couts
    p2 = {
        "structure_couts": {"marge_nette_cible_pct": 11.0},
        "assurances": {"decennale": {"numero_police": "123"}},
    }
    cr2, _, _ = evaluer_criteres(analyse, p2, config_nominale)
    crit2 = next(c for c in cr2 if c["id"] == "rentabilite_estimee")
    assert crit2["points_obtenus"] == 10.0
    assert "11.0 %" in crit2["justification"]

    # Variante 3 : via paramètre couts externe
    p3 = {"assurances": {"decennale": {"numero_police": "123"}}}
    couts_ext = {"coefficients_et_frais": {"marge_nette_cible_pct": 12.0}}
    cr3, _, _ = evaluer_criteres(analyse, p3, config_nominale, couts=couts_ext)
    crit3 = next(c for c in cr3 if c["id"] == "rentabilite_estimee")
    assert crit3["points_obtenus"] == 10.0
    assert "12.0 %" in crit3["justification"]


def test_site_visit_mandatory_dict_unfulfilled(config_nominale: Dict[str, Any]):
    """Vérifie qu'une visite exigée dans un dict pieces_exigees non réalisée lève VISITE_OBLIGATOIRE_MANQUEE."""
    analyse = {
        "pieces_exigees": {
            "candidature": ["DC1", "DC2"],
            "offre": ["Acte d'engagement", "DPGF", "Visite sur site obligatoire"],
        },
        "contradictions_detectees": [],
    }
    profil = {
        "identite": {"siege_social": {"code_postal": "18000"}},
        "assurances": {"decennale": {"numero_police": "123"}},
        "visite_site": {"visite_effectuee": False},
    }

    _, score, drapeaux = evaluer_criteres(analyse, profil, config_nominale)

    ids_drapeaux = [d.get("code") or d.get("id") for d in drapeaux]
    assert "VISITE_OBLIGATOIRE_MANQUEE" in ids_drapeaux

    verdict, _ = determiner_verdict(score, drapeaux)
    assert verdict == "NO-GO"


def test_site_visit_mandatory_visited_nominal(profil_nominal: Dict[str, Any], config_nominale: Dict[str, Any]):
    """Vérifie qu'un profil avec visite_effectuee: true ne lève PAS de drapeau rouge."""
    analyse = {
        "pieces_exigees": {
            "candidature": ["DC1"],
            "offre": ["Attestation de visite des lieux signée"],
        },
        "contradictions_detectees": [],
    }
    _, _, drapeaux = evaluer_criteres(analyse, profil_nominal, config_nominale)
    ids_drapeaux = [d.get("code") or d.get("id") for d in drapeaux]
    assert "VISITE_OBLIGATOIRE_MANQUEE" not in ids_drapeaux


def test_site_visit_detection_in_clauses_sensibles(config_nominale: Dict[str, Any]):
    """Vérifie la détection de l'obligation de visite dans les clauses sensibles."""
    analyse = {
        "clauses_sensibles": {
            "exigences_particulieres": ["Visite des lieux préalable obligatoire sous peine d'irrecevabilité"]
        },
        "contradictions_detectees": [],
    }
    profil = {
        "assurances": {"decennale": {"numero_police": "123"}},
        "visite_site": {"visite_effectuee": False},
    }
    _, _, drapeaux = evaluer_criteres(analyse, profil, config_nominale)
    assert any("VISITE" in (d.get("code") or d.get("id", "")) for d in drapeaux)


def test_blocking_contradiction_forces_nogo_even_with_high_score(
    profil_nominal: Dict[str, Any], config_nominale: Dict[str, Any]
):
    """Invariance R1: toute contradiction BLOQUANT doit donner 0 pts au critère 7, lever un drapeau et forcer NO-GO."""
    analyse = {
        "objet": "Travaux de couverture toiture zinc",
        "lieu_execution": "Bourges (18000)",
        "contradictions_detectees": [
            {
                "type": "PIEGE_EXIGENCE_CCAP_ISOLEE",
                "gravite": "BLOQUANT",
                "description": "Obligation de visite sur site stipulée dans le CCAP mais omise dans le RC.",
            }
        ],
    }

    res = evaluer_go_nogo(analyse, profil_nominal, config_nominale)

    # Le critère 7 risques_contractuels doit être ramené à 0.0
    crit7 = next(c for c in res["criteres"] if c["id"] == "risques_contractuels")
    assert crit7["points_obtenus"] == 0.0

    # Drapeau rouge bloquant obligatoire
    codes_drapeaux = [d.get("code") or d.get("id") for d in res["drapeaux_rouges"]]
    assert "CONTRADICTION_CONTRACTUELLE_BLOQUANTE" in codes_drapeaux

    # Le verdict doit STRICTEMENT être NO-GO
    assert res["verdict"] == "NO-GO"
    assert "Refus obligatoire" in res["commentaire"]


def test_config_overrides_weights_and_thresholds(profil_nominal: Dict[str, Any]):
    """Vérifie que la configuration surcharge bien les poids des critères et les seuils de décision."""
    custom_config = {
        "seuils_decision": {
            "seuil_go": 85.0,
            "seuil_go_reserve": 65.0,
        },
        "criteres": {
            "adequation_technique": {
                "poids": 30,
                "bareme": {"qualifications_completes": 30.0},
            },
            "delai_remise_dossier": {
                "poids": 15,
                "bareme": {"plus_de_10_jours_ouvres": 15.0},
            },
        },
    }

    analyse = {
        "objet": "Travaux de couverture",
        "lieu_execution": "Bourges (18000)",
        "contradictions_detectees": [],
    }

    res = evaluer_go_nogo(analyse, profil_nominal, custom_config)

    criteres_map = {c["id"]: c for c in res["criteres"]}
    assert criteres_map["adequation_technique"]["poids_max"] == 30
    assert criteres_map["delai_remise_dossier"]["poids_max"] == 15

    # Si le score obtenu est entre 65 et 85, le seuil rehaussé impose GO SOUS RÉSERVE
    if 65.0 <= res["score_sur_100"] < 85.0:
        assert res["verdict"] == "GO SOUS RÉSERVE"


def test_evaluer_go_nogo_public_interface(profil_nominal: Dict[str, Any]):
    """Valide la conformité stricte du dictionnaire renvoyé par l'interface contractuelle."""
    analyse = {"contradictions_detectees": []}
    res = evaluer_go_nogo(analyse, profil_nominal)

    assert isinstance(res, dict)
    assert "score_sur_100" in res and isinstance(res["score_sur_100"], float)
    assert "verdict" in res and res["verdict"] in ["GO", "NO-GO", "GO SOUS RÉSERVE"]
    assert "commentaire" in res and isinstance(res["commentaire"], str)
    assert "drapeaux_rouges" in res and isinstance(res["drapeaux_rouges"], list)
    assert "criteres" in res and isinstance(res["criteres"], list)
    assert len(res["criteres"]) == 8


def test_bidding_exclusion_red_flag(config_nominale: Dict[str, Any]):
    """Vérifie qu'un profil avec interdiction de soumissionner lève INTERDICTION_SOUMISSIONNER."""
    profil_exclu = {
        "identite": {"raison_sociale": "Entreprise Exclue"},
        "assurances": {"decennale": {"numero_police": "123"}},
        "interdiction_soumissionner": True,
    }
    analyse = {"contradictions_detectees": []}

    res = evaluer_go_nogo(analyse, profil_exclu, config_nominale)
    assert res["verdict"] == "NO-GO"
    codes = [d.get("code") or d.get("id") for d in res["drapeaux_rouges"]]
    assert "INTERDICTION_SOUMISSIONNER" in codes


def test_expired_deadline_red_flag(profil_nominal: Dict[str, Any], config_nominale: Dict[str, Any]):
    """Vérifie qu'une date limite expirée lève DATE_LIMITE_DEPASSEE et force NO-GO."""
    analyse = {
        "calendrier": {"date_limite_retenue": "01/01/2020 à 12h00"},
        "contradictions_detectees": [],
    }

    res = evaluer_go_nogo(analyse, profil_nominal, config_nominale)
    assert res["verdict"] == "NO-GO"
    codes = [d.get("code") or d.get("id") for d in res["drapeaux_rouges"]]
    assert "DATE_LIMITE_DEPASSEE" in codes
    crit8 = next(c for c in res["criteres"] if c["id"] == "delai_remise_dossier")
    assert crit8["points_obtenus"] == 0.0


def test_iso_date_parsing_future_tender_no_false_date_depassee(
    profil_nominal: Dict[str, Any], config_nominale: Dict[str, Any]
):
    """Vérifie qu'une date future au format ISO 8601 (2026-11-20) n'est pas confondue avec 2020."""
    analyse_future = {
        "objet": "Travaux de couverture",
        "lieu_execution": "Bourges (18000)",
        "calendrier": {"date_limite_retenue": "2026-11-20"},
        "contradictions_detectees": [],
    }

    res = evaluer_go_nogo(analyse_future, profil_nominal, config_nominale)
    codes = [d.get("code") or d.get("id") for d in res["drapeaux_rouges"]]
    assert "DATE_LIMITE_DEPASSEE" not in codes
    crit8 = next(c for c in res["criteres"] if c["id"] == "delai_remise_dossier")
    assert crit8["points_obtenus"] > 0.0


def test_couts_precedence_over_profil_structure_couts(config_nominale: Dict[str, Any]):
    """Vérifie que le paramètre couts prend la priorité absolue sur structure_couts du profil."""
    profil = {
        "assurances": {"decennale": {"numero_police": "123"}},
        "structure_couts": {"marge_nette_cible_pct": 5.0},
    }
    couts_override = {
        "structure_couts": {"marge_nette_cible_pct": 12.0},
    }
    res_couts = extraire_structure_couts(profil, couts=couts_override)
    assert res_couts["marge_nette_cible_pct"] == 12.0

    analyse = {"contradictions_detectees": []}
    res = evaluer_go_nogo(analyse, profil, config_nominale, couts=couts_override)
    crit_rent = next(c for c in res["criteres"] if c["id"] == "rentabilite_estimee")
    assert crit_rent["points_obtenus"] == 10.0
    assert "12.0 %" in crit_rent["justification"]


def test_extraire_date_limite_direct_call():
    """Valide extraire_date_limite sur différents formats et types d'entrée."""
    d_iso, s_iso = extraire_date_limite({"calendrier": {"date_limite_retenue": "2026-11-20"}})
    assert d_iso == datetime.date(2026, 11, 20)
    assert s_iso == "2026-11-20"

    d_fr, s_fr = extraire_date_limite("15/06/2026")
    assert d_fr == datetime.date(2026, 6, 15)

    d_empty, s_empty = extraire_date_limite(None)
    assert d_empty is None
    assert s_empty == ""


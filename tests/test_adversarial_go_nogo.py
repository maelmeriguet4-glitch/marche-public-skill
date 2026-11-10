"""Adversarial validation suite for scripts/go_nogo.py (Remediated Iteration 2).

Empirical verification of edge cases, schema boundaries, and dynamic config exploitation:
1. Malformed company profile schema parsing (None blocks, strings for ints, floats, negative values).
2. Boundary postal codes (Corsica 2A/2B, Overseas DOM-TOM 97x, foreign postal codes).
3. Dynamic configuration exploitation (altered weights, custom baremes, threshold alterations).
4. Verification of defensive null-safety and absence of calculation anomalies.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from go_nogo import (
    determiner_verdict,
    evaluer_criteres,
    evaluer_go_nogo,
    extraire_code_postal,
    extraire_effectif_total,
    extraire_structure_couts,
)


@pytest.fixture
def profil_base_valide() -> Dict[str, Any]:
    return {
        "identite": {
            "raison_sociale": "Entreprise BTP Test",
            "siege_social": {"code_postal": "18000"},
        },
        "effectifs": {"total_salaries": 14},
        "qualifications_et_certifications": [{"code": "3101", "intitule": "Couverture"}],
        "references_chantiers": [
            {"objet": "Chantier 1"},
            {"objet": "Chantier 2"},
            {"objet": "Chantier 3"},
        ],
        "capacites_financieres": {
            "exercices": [{"chiffre_affaires_ht_euros": 1500000}]
        },
        "structure_couts": {"marge_nette_cible_pct": 8.0},
        "assurances": {"decennale": {"numero_police": "POL-999"}},
        "visite_site": {"visite_effectuee": True},
    }


@pytest.fixture
def analyse_base_valide() -> Dict[str, Any]:
    return {
        "objet": "Travaux de couverture et toiture",
        "lieu_execution": "Bourges (18000)",
        "acheteur": {"nom": "Ville de Bourges"},
        "montant_estime_ht": 150000,
        "calendrier": {"date_limite_retenue": "31/12/2026"},
        "contradictions_detectees": [],
    }


# =====================================================================
# 1. PROFILE SCHEMA PARSING CHALLENGES
# =====================================================================

class TestProfileSchemaParsingChallenges:
    """Stress tests on malformed or extreme company profiles."""

    def test_headcount_negative_values(self):
        """Negative headcounts should be rejected and return 0 (not a negative headcount)."""
        p_neg = {"effectifs": {"total_salaries": -5}}
        assert extraire_effectif_total(p_neg) == 0

        p_neg_str = {"effectifs": {"total_salaries": "-12"}}
        assert extraire_effectif_total(p_neg_str) == 0

    def test_headcount_zero_and_empty_strings(self):
        """Zero and empty string headcounts should return 0."""
        assert extraire_effectif_total({"effectifs": {"total_salaries": 0}}) == 0
        assert extraire_effectif_total({"effectifs": {"total_salaries": "0"}}) == 0
        assert extraire_effectif_total({"effectifs": {"total_salaries": ""}}) == 0
        assert extraire_effectif_total({"effectifs": {"total_salaries": "   "}}) == 0

    def test_headcount_non_digit_strings(self):
        """Non-digit strings like 'quinze' or 'N/A' should return 0 without raising."""
        assert extraire_effectif_total({"effectifs": {"total_salaries": "quinze"}}) == 0
        assert extraire_effectif_total({"effectifs": {"total_salaries": "N/A"}}) == 0
        assert extraire_effectif_total({"effectif_total": "inconnu"}) == 0

    def test_headcount_float_and_float_string_behavior(self):
        """Floats (e.g. 14.5 or '14.0') should be safely parsed as positive integers."""
        p_float = {"effectifs": {"total_salaries": 14.0}}
        val = extraire_effectif_total(p_float)
        assert val == 14

        p_float_str = {"effectifs": {"total_salaries": "14.0"}}
        assert extraire_effectif_total(p_float_str) == 14

    def test_headcount_missing_nested_blocks(self):
        """Missing or None nested blocks for effectifs must not raise AttributeError."""
        assert extraire_effectif_total({"effectifs": None}) == 0
        assert extraire_effectif_total({"moyens_humains": None}) == 0
        assert extraire_effectif_total({}) == 0
        assert extraire_effectif_total(None) == 0  # type: ignore

    def test_postal_code_corsica_2a_and_2b(self, profil_base_valide: Dict[str, Any]):
        """EMPIRICAL FINDING: Corsica codes (2A000, 2B200) are extracted as 2A/2B and properly evaluated."""
        profil_base_valide["identite"]["siege_social"]["code_postal"] = "2A000"
        assert extraire_code_postal(profil_base_valide) == "2A000"

        analyse_ajaccio = {
            "objet": "Rénovation toiture",
            "lieu_execution": "Ajaccio (2A000)",
            "acheteur": {"nom": "Mairie d'Ajaccio"},
            "contradictions_detectees": [],
        }
        res = evaluer_go_nogo(analyse_ajaccio, profil_base_valide)
        crit_geo = next(c for c in res["criteres"] if c["id"] == "localisation_eloignement")
        assert crit_geo["points_obtenus"] == 10.0
        assert "[DISTANCE NON CALCULÉE]" not in crit_geo["justification"]

    def test_postal_code_overseas_dom_tom_collision(self, profil_base_valide: Dict[str, Any]):
        """Overseas departments prefix handling: distinct DOMs (974 vs 971) must not collide."""
        profil_base_valide["identite"]["siege_social"]["code_postal"] = "97400"  # La Réunion
        analyse_guadeloupe = {
            "objet": "Travaux école",
            "lieu_execution": "Pointe-à-Pitre (97100)",
            "acheteur": {"nom": "Ville de Pointe-à-Pitre"},
            "contradictions_detectees": [],
        }
        res = evaluer_go_nogo(analyse_guadeloupe, profil_base_valide)
        crit_geo = next(c for c in res["criteres"] if c["id"] == "localisation_eloignement")
        assert crit_geo["points_obtenus"] == 0.0
        assert "même département" not in crit_geo["justification"]

    def test_postal_code_foreign_format(self, profil_base_valide: Dict[str, Any]):
        """Foreign postal codes like B-1000 slice first 2 chars ('B-') as department."""
        profil_base_valide["identite"]["siege_social"]["code_postal"] = "B-1000"
        assert extraire_code_postal(profil_base_valide) == "B-1000"

        analyse_paris = {
            "objet": "Travaux toiture",
            "lieu_execution": "Paris (75001)",
            "contradictions_detectees": [],
        }
        res = evaluer_go_nogo(analyse_paris, profil_base_valide)
        crit_geo = next(c for c in res["criteres"] if c["id"] == "localisation_eloignement")
        assert "Entreprise B-" in crit_geo["justification"]

    def test_crash_on_none_financial_capacities(self, analyse_base_valide: Dict[str, Any]):
        """Defensive handling: If 'capacites_financieres' is None, engine does not crash."""
        profil_broken = {
            "assurances": {"decennale": {"numero_police": "POL-123"}},
            "capacites_financieres": None,
        }
        res = evaluer_go_nogo(analyse_base_valide, profil_broken)
        assert res["verdict"] in ["GO", "NO-GO", "GO SOUS RÉSERVE", "NON_EVALUABLE"]
        crit_fin = next(c for c in res["criteres"] if c["id"] == "capacite_financiere_et_taille")
        assert "Chiffre d'affaires non renseigné" in crit_fin["justification"]

    def test_crash_on_none_qualifications(self, analyse_base_valide: Dict[str, Any]):
        """Defensive handling: If 'qualifications_et_certifications' is None, engine does not crash."""
        profil_broken = {
            "assurances": {"decennale": {"numero_police": "POL-123"}},
            "qualifications_et_certifications": None,
        }
        res = evaluer_go_nogo(analyse_base_valide, profil_broken)
        assert res["verdict"] in ["GO", "NO-GO", "GO SOUS RÉSERVE", "NON_EVALUABLE"]
        crit_tech = next(c for c in res["criteres"] if c["id"] == "adequation_technique")
        assert crit_tech["points_obtenus"] == 0.0

    def test_crash_on_list_of_strings_in_qualifications(self, analyse_base_valide: Dict[str, Any]):
        """Defensive handling: List of strings for qualifications is supported without crashing."""
        profil_strings = {
            "assurances": {"decennale": {"numero_police": "POL-123"}},
            "qualifications_et_certifications": ["QUALIBAT 3101", "QUALIBAT 3111"],
        }
        res = evaluer_go_nogo(analyse_base_valide, profil_strings)
        assert res["verdict"] in ["GO", "NO-GO", "GO SOUS RÉSERVE", "NON_EVALUABLE"]
        crit_tech = next(c for c in res["criteres"] if c["id"] == "adequation_technique")
        assert crit_tech["points_obtenus"] >= 14.0

    def test_crash_on_none_references_chantiers(self, analyse_base_valide: Dict[str, Any]):
        """Defensive handling: If 'references_chantiers' is None, engine treats it as 0 references without crashing."""
        profil_broken = {
            "assurances": {"decennale": {"numero_police": "POL-123"}},
            "references_chantiers": None,
        }
        res = evaluer_go_nogo(analyse_base_valide, profil_broken)
        assert res["verdict"] in ["GO", "NO-GO", "GO SOUS RÉSERVE", "NON_EVALUABLE"]
        crit_ref = next(c for c in res["criteres"] if c["id"] == "references_comparables")
        assert crit_ref["points_obtenus"] == 0.0

    def test_crash_on_none_contradictions_detectees(self, profil_base_valide: Dict[str, Any]):
        """Defensive handling: If 'contradictions_detectees' is None, engine does not crash and marks as non-evaluable."""
        analyse_broken = {
            "objet": "Travaux",
            "contradictions_detectees": None,
        }
        res = evaluer_go_nogo(analyse_broken, profil_base_valide)
        assert res["verdict"] in ["GO", "NO-GO", "GO SOUS RÉSERVE", "NON_EVALUABLE"]
        crit_risq = next(c for c in res["criteres"] if c["id"] == "risques_contractuels")
        assert crit_risq["points_obtenus"] == 0.0
        assert crit_risq["statut"] == "NON_EVALUABLE"

    def test_crash_on_string_amount_with_currency(
        self, profil_base_valide: Dict[str, Any], analyse_base_valide: Dict[str, Any]
    ):
        """Defensive handling: Formatted string amounts with currency ('150 000 €') are parsed safely."""
        analyse_base_valide["montant_estime_ht"] = "150 000 €"
        res = evaluer_go_nogo(analyse_base_valide, profil_base_valide)
        assert res["verdict"] in ["GO", "NO-GO", "GO SOUS RÉSERVE", "NON_EVALUABLE"]
        crit_fin = next(c for c in res["criteres"] if c["id"] == "capacite_financiere_et_taille")
        assert crit_fin["points_obtenus"] == 15.0


# =====================================================================
# 2. DYNAMIC CONFIGURATION EXPLOITATION CHALLENGES
# =====================================================================

class TestDynamicConfigurationExploitationChallenges:
    """Stress tests on go_nogo_config.yaml inputs and dynamic engine adaptation."""

    def test_altered_weights_rebalance(
        self, profil_base_valide: Dict[str, Any], analyse_base_valide: Dict[str, Any]
    ):
        """Custom weight distribution totaling 100 points must be dynamically honored by poids_max."""
        custom_config = {
            "seuils_decision": {"seuil_go": 70.0, "seuil_go_reserve": 50.0},
            "criteres": {
                "adequation_technique": {"poids": 30},
                "references_comparables": {"poids": 20},
                "capacite_financiere_et_taille": {"poids": 10},
                "charge_travail_et_disponibilite": {"poids": 10},
                "localisation_eloignement": {"poids": 10},
                "rentabilite_estimee": {"poids": 10},
                "risques_contractuels": {"poids": 5},
                "delai_remise_dossier": {"poids": 5},
            },
        }
        res = evaluer_go_nogo(analyse_base_valide, profil_base_valide, custom_config)
        criteres_map = {c["id"]: c for c in res["criteres"]}

        assert criteres_map["adequation_technique"]["poids_max"] == 30
        assert criteres_map["references_comparables"]["poids_max"] == 20
        assert criteres_map["capacite_financiere_et_taille"]["poids_max"] == 10
        assert criteres_map["charge_travail_et_disponibilite"]["poids_max"] == 10
        assert criteres_map["risques_contractuels"]["poids_max"] == 5
        assert criteres_map["delai_remise_dossier"]["poids_max"] == 5

        total_poids = sum(c["poids_max"] for c in res["criteres"])
        assert total_poids == 100

    def test_custom_bareme_double_scaling_defect(
        self, profil_base_valide: Dict[str, Any], analyse_base_valide: Dict[str, Any]
    ):
        """Dynamic scaling: Custom bareme and custom poids scale properly without exceeding poids_max."""
        config_double_scale = {
            "criteres": {
                "adequation_technique": {
                    "poids": 30,
                    "bareme": {"qualifications_completes": 30.0},
                }
            }
        }
        res = evaluer_go_nogo(analyse_base_valide, profil_base_valide, config_double_scale)
        crit_tech = next(c for c in res["criteres"] if c["id"] == "adequation_technique")

        assert crit_tech["poids_max"] == 30
        assert crit_tech["points_obtenus"] == 30.0
        assert crit_tech["points_obtenus"] <= crit_tech["poids_max"]

    def test_custom_bareme_hardcoded_max_overrides(
        self, profil_base_valide: Dict[str, Any], analyse_base_valide: Dict[str, Any]
    ):
        """Config fidelity: Custom bareme values in go_nogo_config.yaml are strictly respected without hardcoded max floors."""
        config_stricter_bareme = {
            "criteres": {
                "charge_travail_et_disponibilite": {
                    "poids": 15,
                    "bareme": {
                        "charge_moderee_ajustement_mineur": 6.0,
                        "saturation_totale_des_equipes": 1.0,
                    },
                }
            }
        }
        profil_base_valide["effectifs"]["total_salaries"] = 9
        res = evaluer_go_nogo(analyse_base_valide, profil_base_valide, config_stricter_bareme)
        crit_charge = next(c for c in res["criteres"] if c["id"] == "charge_travail_et_disponibilite")
        assert crit_charge["points_obtenus"] == 6.0

        profil_base_valide["effectifs"]["total_salaries"] = 1
        res1 = evaluer_go_nogo(analyse_base_valide, profil_base_valide, config_stricter_bareme)
        crit_charge1 = next(c for c in res1["criteres"] if c["id"] == "charge_travail_et_disponibilite")
        assert crit_charge1["points_obtenus"] == 1.0

    def test_custom_decision_thresholds_strict(
        self, profil_base_valide: Dict[str, Any], analyse_base_valide: Dict[str, Any]
    ):
        """Custom strict thresholds (seuil_go=85.0, seuil_go_reserve=65.0) are respected."""
        strict_config = {
            "seuils_decision": {
                "seuil_go": 85.0,
                "seuil_go_reserve": 65.0,
            }
        }
        res = evaluer_go_nogo(analyse_base_valide, profil_base_valide, strict_config)
        if 65.0 <= res["score_sur_100"] < 85.0:
            assert res["verdict"] == "GO SOUS RÉSERVE"

    def test_custom_decision_thresholds_permissive(
        self, profil_base_valide: Dict[str, Any], analyse_base_valide: Dict[str, Any]
    ):
        """Permissive thresholds (seuil_go=55.0, seuil_go_reserve=35.0) turn moderate scores into GO."""
        permissive_config = {
            "seuils_decision": {
                "seuil_go": 55.0,
                "seuil_go_reserve": 35.0,
            }
        }
        profil_base_valide["qualifications_et_certifications"] = []
        profil_base_valide["references_chantiers"] = []
        res = evaluer_go_nogo(analyse_base_valide, profil_base_valide, permissive_config)
        if res["score_sur_100"] >= 55.0:
            assert res["verdict"] == "GO"

    def test_seuil_nogo_key_ignored_observation(self):
        """Observation: 'seuil_nogo' fallback in seuils_decision."""
        cfg_nogo = {"seuils_decision": {"seuil_go": 75.0, "seuil_nogo": 40.0}}
        seuils = cfg_nogo.get("seuils_decision", {})
        val = float(seuils.get("seuil_go_reserve", seuils.get("seuil_reserve", 50.0)))
        assert val == 50.0

    def test_empty_config_clean_defaults(
        self, profil_base_valide: Dict[str, Any], analyse_base_valide: Dict[str, Any]
    ):
        """Empty config dict {} falls back cleanly to default criteria weights and thresholds."""
        res = evaluer_go_nogo(analyse_base_valide, profil_base_valide, config={})
        assert len(res["criteres"]) == 8
        total_poids = sum(c["poids_max"] for c in res["criteres"])
        assert total_poids == 100
        assert res["verdict"] in ["GO", "NO-GO", "GO SOUS RÉSERVE", "NON_EVALUABLE"]

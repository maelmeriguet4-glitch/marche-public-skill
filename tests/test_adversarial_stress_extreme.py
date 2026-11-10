"""Empirical Stress Test Harness: Extreme Custom Configs and Invariance Verification.

Adversarial testing targeting:
1. points_obtenus <= poids_max invariance across all criteria under extreme scaling.
2. Custom bareme fidelity: verification that no hardcoded floors or clamps override custom baremes.
3. Extreme custom weights (zero weights, massive weights, asymmetric weights).
4. Odd, fractional, and boundary decision thresholds.
5. Invariance of blocking red flags under extreme configurations.
6. Property-based fuzzing with randomized combinations of inputs and configs.
7. Empirical demonstration of unhandled decimal.InvalidOperation on formatted percentage strings in margin.
"""

from __future__ import annotations

import decimal
import random
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from go_nogo import evaluer_criteres, evaluer_go_nogo


@pytest.fixture
def nominal_profil() -> Dict[str, Any]:
    return {
        "identite": {
            "raison_sociale": "Entreprise BTP Stress",
            "siege_social": {"code_postal": "18000"},
        },
        "effectifs": {"total_salaries": 15},
        "qualifications_et_certifications": [{"code": "3101", "intitule": "Couverture"}],
        "references_chantiers": [{"objet": f"Chantier {i}"} for i in range(5)],
        "capacites_financieres": {
            "exercices": [{"chiffre_affaires_ht_euros": 2000000}]
        },
        "structure_couts": {"marge_nette_cible_pct": 12.0},
        "assurances": {
            "decennale": {
                "numero_police": "POL-123456",
                "attestation_fichier": "attestation_assurance_decennale.pdf",
            }
        },
        "visite_site": {
            "visite_effectuee": True,
            "attestation_fichier": "attestation_visite_signee.pdf",
        },
    }


@pytest.fixture
def nominal_analyse() -> Dict[str, Any]:
    return {
        "objet": "Travaux de couverture et toiture",
        "lieu_execution": "Bourges (18000)",
        "acheteur": {"nom": "Ville de Bourges"},
        "montant_estime_ht": 100000,
        "calendrier": {"date_limite_retenue": "31/12/2026"},
        "contradictions_detectees": [],
    }


# =============================================================================
# 1. BAREME CLAMP ELIMINATION & STRICT FIDELITY TESTS
# =============================================================================

class TestBaremeFidelityAndClamps:
    """Verifies that no hardcoded clamps (e.g. max(14, ...)) override custom baremes."""

    @pytest.mark.parametrize("tiny_val", [0.001, 0.05, 0.5, 1.0, 2.3])
    def test_adequation_technique_tiny_bareme_not_clamped(
        self, nominal_analyse: Dict[str, Any], nominal_profil: Dict[str, Any], tiny_val: float
    ):
        """Even with qualifications_completes, tiny custom bareme must be respected exactly."""
        config = {
            "criteres": {
                "adequation_technique": {
                    "poids": 20,
                    "bareme": {"qualifications_completes": tiny_val},
                }
            }
        }
        res = evaluer_go_nogo(nominal_analyse, nominal_profil, config)
        crit = next(c for c in res["criteres"] if c["id"] == "adequation_technique")
        assert crit["points_obtenus"] == round(tiny_val, 1)
        assert crit["points_obtenus"] <= crit["poids_max"]

    @pytest.mark.parametrize("tiny_val", [0.001, 0.1, 0.8, 1.5])
    def test_charge_travail_tiny_bareme_not_clamped(
        self, nominal_analyse: Dict[str, Any], nominal_profil: Dict[str, Any], tiny_val: float
    ):
        """Even with headcount >= 12, tiny custom bareme must not be raised by hardcoded floors."""
        config = {
            "criteres": {
                "charge_travail_et_disponibilite": {
                    "poids": 15,
                    "bareme": {"ressources_disponibles_immediatement": tiny_val},
                }
            }
        }
        res = evaluer_go_nogo(nominal_analyse, nominal_profil, config)
        crit = next(c for c in res["criteres"] if c["id"] == "charge_travail_et_disponibilite")
        assert crit["points_obtenus"] == round(tiny_val, 1)
        assert crit["points_obtenus"] <= crit["poids_max"]

    @pytest.mark.parametrize("tiny_val", [0.01, 0.2, 1.0])
    def test_references_tiny_bareme_not_clamped(
        self, nominal_analyse: Dict[str, Any], nominal_profil: Dict[str, Any], tiny_val: float
    ):
        """References criterion with >= 3 references strictly yields custom tiny bareme."""
        config = {
            "criteres": {
                "references_comparables": {
                    "poids": 15,
                    "bareme": {"trois_references_similaires_ou_plus": tiny_val},
                }
            }
        }
        res = evaluer_go_nogo(nominal_analyse, nominal_profil, config)
        crit = next(c for c in res["criteres"] if c["id"] == "references_comparables")
        assert crit["points_obtenus"] == round(tiny_val, 1)
        assert crit["points_obtenus"] <= crit["poids_max"]

    @pytest.mark.parametrize("tiny_val", [0.05, 0.5, 1.2])
    def test_capacite_financiere_tiny_bareme_not_clamped(
        self, nominal_analyse: Dict[str, Any], nominal_profil: Dict[str, Any], tiny_val: float
    ):
        """Financial capacity strictly yields custom tiny bareme without hardcoded minimums."""
        config = {
            "criteres": {
                "capacite_financiere_et_taille": {
                    "poids": 15,
                    "bareme": {"marche_inf_15pct_du_ca": tiny_val},
                }
            }
        }
        res = evaluer_go_nogo(nominal_analyse, nominal_profil, config)
        crit = next(c for c in res["criteres"] if c["id"] == "capacite_financiere_et_taille")
        assert crit["points_obtenus"] == round(tiny_val, 1)
        assert crit["points_obtenus"] <= crit["poids_max"]


# =============================================================================
# 2. INVARIANCE: points_obtenus NEVER EXCEEDS poids_max
# =============================================================================

class TestPointsObtenusNeverExceedsPoidsMax:
    """Verifies that under massive baremes or altered weights, points_obtenus <= poids_max."""

    @pytest.mark.parametrize(
        "poids,bareme_val",
        [
            (10, 50.0),      # bareme much larger than poids
            (5, 100.0),      # bareme 20x larger than poids
            (1, 999.0),      # extreme bareme over tiny weight
            (25, 250.0),
            (0, 50.0),       # zero weight with non-zero bareme
        ],
    )
    def test_massive_bareme_capped_at_poids_max(
        self, nominal_analyse: Dict[str, Any], nominal_profil: Dict[str, Any], poids: int, bareme_val: float
    ):
        """When bareme value exceeds default_poids, points_obtenus must clamp to poids_max."""
        config = {
            "criteres": {
                "adequation_technique": {
                    "poids": poids,
                    "bareme": {"qualifications_completes": bareme_val},
                },
                "references_comparables": {
                    "poids": poids,
                    "bareme": {"trois_references_similaires_ou_plus": bareme_val},
                },
                "capacite_financiere_et_taille": {
                    "poids": poids,
                    "bareme": {"marche_inf_15pct_du_ca": bareme_val},
                },
                "charge_travail_et_disponibilite": {
                    "poids": poids,
                    "bareme": {"ressources_disponibles_immediatement": bareme_val},
                },
                "localisation_eloignement": {
                    "poids": poids,
                    "bareme": {"distance_inf_30km": bareme_val},
                },
                "rentabilite_estimee": {
                    "poids": poids,
                    "bareme": {"marge_au_dessus_de_l_objectif": bareme_val},
                },
                "risques_contractuels": {
                    "poids": poids,
                    "bareme": {"clauses_standards_ccag_sans_piege": bareme_val},
                },
                "delai_remise_dossier": {
                    "poids": poids,
                    "bareme": {"plus_de_10_jours_ouvres": bareme_val},
                },
            }
        }
        res = evaluer_go_nogo(nominal_analyse, nominal_profil, config)
        for crit in res["criteres"]:
            assert crit["points_obtenus"] <= crit["poids_max"], (
                f"Violation on {crit['id']}: points_obtenus ({crit['points_obtenus']}) "
                f"> poids_max ({crit['poids_max']})"
            )
            if poids == 0:
                assert crit["points_obtenus"] == 0.0

    def test_all_eight_criteria_under_asymmetric_extreme_weights(
        self, nominal_analyse: Dict[str, Any], nominal_profil: Dict[str, Any]
    ):
        """Asymmetric extreme weights across criteria: weights ranging from 0 to 500."""
        config = {
            "criteres": {
                "adequation_technique": {"poids": 500, "bareme": {"qualifications_completes": 40.0}},
                "references_comparables": {"poids": 0, "bareme": {"trois_references_similaires_ou_plus": 25.0}},
                "capacite_financiere_et_taille": {"poids": 1, "bareme": {"marche_inf_15pct_du_ca": 100.0}},
                "charge_travail_et_disponibilite": {"poids": 50, "bareme": {"ressources_disponibles_immediatement": 30.0}},
                "localisation_eloignement": {"poids": 100, "bareme": {"distance_inf_30km": 10.0}},
                "rentabilite_estimee": {"poids": 200, "bareme": {"marge_au_dessus_de_l_objectif": 50.0}},
                "risques_contractuels": {"poids": 0, "bareme": {"clauses_standards_ccag_sans_piege": 10.0}},
                "delai_remise_dossier": {"poids": 3, "bareme": {"plus_de_10_jours_ouvres": 15.0}},
            }
        }
        res = evaluer_go_nogo(nominal_analyse, nominal_profil, config)
        for crit in res["criteres"]:
            assert crit["points_obtenus"] <= crit["poids_max"], (
                f"Violation on {crit['id']}: points {crit['points_obtenus']} > poids {crit['poids_max']}"
            )


# =============================================================================
# 3. EXTREME AND ODD THRESHOLDS
# =============================================================================

class TestOddThresholdsAndEdgeVerdicts:
    """Stress tests on unusual, boundary, or inverted thresholds."""

    def test_ultra_high_thresholds(
        self, nominal_analyse: Dict[str, Any], nominal_profil: Dict[str, Any]
    ):
        """If seuil_go = 99.5 and seuil_reserve = 95.0, high-scoring profile gets GO SOUS RÉSERVE."""
        config = {
            "seuils_decision": {
                "seuil_go": 99.5,
                "seuil_go_reserve": 95.0,
            }
        }
        res = evaluer_go_nogo(nominal_analyse, nominal_profil, config)
        assert res["score_sur_100"] <= 100.0
        if 95.0 <= res["score_sur_100"] < 99.5:
            assert res["verdict"] == "GO SOUS RÉSERVE"

    def test_ultra_low_thresholds(
        self, nominal_analyse: Dict[str, Any], nominal_profil: Dict[str, Any]
    ):
        """If seuil_go = 1.0, even weak profiles (no quals, no refs) get GO provided no red flags."""
        weak_profil = {
            "assurances": {
                "decennale": {
                    "numero_police": "POL-123",
                    "attestation_fichier": "attestation_assurance_decennale.pdf",
                }
            },
        }
        config = {
            "seuils_decision": {
                "seuil_go": 1.0,
                "seuil_go_reserve": 0.5,
            }
        }
        res = evaluer_go_nogo(nominal_analyse, weak_profil, config)
        assert res["score_sur_100"] >= 1.0
        assert res["verdict"] == "GO"

    def test_identical_thresholds(
        self, nominal_analyse: Dict[str, Any], nominal_profil: Dict[str, Any]
    ):
        """When seuil_go == seuil_go_reserve (e.g. 70.0), verdict is binary GO or NO-GO."""
        config = {
            "seuils_decision": {
                "seuil_go": 70.0,
                "seuil_go_reserve": 70.0,
            }
        }
        res = evaluer_go_nogo(nominal_analyse, nominal_profil, config)
        assert res["verdict"] in ["GO", "NO-GO"]

    def test_blocking_red_flag_overrides_any_threshold(
        self, nominal_analyse: Dict[str, Any], nominal_profil: Dict[str, Any]
    ):
        """Even with seuil_go = 0.0 and score = 100, a blocking contradiction strictly forces NO-GO."""
        nominal_analyse["contradictions_detectees"] = [
            {"description": "Contradiction bloquante planning", "gravite": "BLOQUANT"}
        ]
        config = {
            "seuils_decision": {
                "seuil_go": 0.0,
                "seuil_go_reserve": 0.0,
            }
        }
        res = evaluer_go_nogo(nominal_analyse, nominal_profil, config)
        assert res["verdict"] == "NO-GO"
        assert any(
            d.get("code") == "CONTRADICTION_CONTRACTUELLE_BLOQUANTE" for d in res["drapeaux_rouges"]
        )


# =============================================================================
# 4. PROPERTY-BASED RANDOMIZED STRESS FUZZING
# =============================================================================

class TestPropertyBasedRandomizedFuzzing:
    """Randomized fuzzing across 200 diverse configurations and company profiles."""

    def test_fuzzing_invariance_suite(self):
        rng = random.Random(42)

        for iteration in range(200):
            # 1. Generate random profile
            has_decennale = rng.choice([True, True, False])
            has_visit = rng.choice([True, False])
            headcount = rng.choice([-10, 0, 1, 5, 12, 50, "15", "invalid", None])
            cp = rng.choice(["18000", "75001", "2A000", "97400", "B-1000", "99", "", None])
            marge = rng.choice([-5.0, 0.0, 3.5, 8.0, 15.0, None, "10.0"])
            ca = rng.choice([0, 50000, 200000, 1500000, 5000000, None])

            profil: Dict[str, Any] = {
                "identite": {"siege_social": {"code_postal": cp}},
                "effectifs": {"total_salaries": headcount},
                "assurances": {"decennale": {"numero_police": "POL-FUZZ" if has_decennale else None}},
                "visite_site": {"visite_effectuee": has_visit},
                "structure_couts": {"marge_nette_cible_pct": marge},
            }
            if ca is not None:
                profil["capacites_financieres"] = {"exercices": [{"chiffre_affaires_ht_euros": ca}]}

            # 2. Generate random analyse
            has_blocking_contra = rng.choice([False, False, True])
            visite_required = rng.choice([False, True])
            date_choice = rng.choice(["2026-12-31", "31/12/2026", "2020-01-01", None])

            contras = []
            if has_blocking_contra:
                grav = rng.choice(["BLOQUANT", " bloquant ", "Bloquant\n", "BLOQUANT "])
                contras.append({"description": "Anomalie fuzzer", "gravite": grav})

            analyse: Dict[str, Any] = {
                "objet": rng.choice(["Couverture toiture", "Peinture", ""]),
                "lieu_execution": "Bourges (18000)",
                "montant_estime_ht": rng.choice([50000, 200000, "150 000 €", None]),
                "calendrier": {"date_limite_retenue": date_choice},
                "contradictions_detectees": contras,
            }
            if visite_required:
                analyse["pieces_exigees"] = {"technique": "Attestation de visite obligatoire"}

            # 3. Generate random custom config
            config: Dict[str, Any] = {
                "seuils_decision": {
                    "seuil_go": rng.uniform(40.0, 95.0),
                    "seuil_go_reserve": rng.uniform(20.0, 60.0),
                },
                "criteres": {
                    "adequation_technique": {
                        "poids": rng.randint(0, 50),
                        "bareme": {"qualifications_completes": rng.uniform(0.1, 100.0)},
                    },
                    "references_comparables": {
                        "poids": rng.randint(0, 50),
                        "bareme": {"trois_references_similaires_ou_plus": rng.uniform(0.1, 100.0)},
                    },
                    "capacite_financiere_et_taille": {
                        "poids": rng.randint(0, 50),
                    },
                    "charge_travail_et_disponibilite": {
                        "poids": rng.randint(0, 50),
                        "bareme": {"ressources_disponibles_immediatement": rng.uniform(0.1, 50.0)},
                    },
                    "localisation_eloignement": {
                        "poids": rng.randint(0, 50),
                    },
                    "rentabilite_estimee": {
                        "poids": rng.randint(0, 50),
                    },
                    "risques_contractuels": {
                        "poids": rng.randint(0, 50),
                    },
                    "delai_remise_dossier": {
                        "poids": rng.randint(0, 50),
                    },
                },
            }

            # 4. Execute engine
            res = evaluer_go_nogo(analyse, profil, config)

            # Invariance 1: No crash, valid dict keys
            assert "score_sur_100" in res
            assert "verdict" in res
            assert "criteres" in res
            assert "drapeaux_rouges" in res

            # Invariance 2: points_obtenus <= poids_max for EVERY criterion
            for crit in res["criteres"]:
                poids_max = crit["poids_max"]
                points = crit["points_obtenus"]
                assert points <= poids_max, (
                    f"Fuzzer run #{iteration}: {crit['id']} points ({points}) > poids_max ({poids_max})"
                )
                assert points >= 0.0, (
                    f"Fuzzer run #{iteration}: {crit['id']} negative points ({points})"
                )

            # Invariance 3: Blocking contradiction MUST force NO-GO
            if has_blocking_contra:
                assert res["verdict"] == "NO-GO", (
                    f"Fuzzer run #{iteration}: blocking contradiction failed to force NO-GO! Got {res['verdict']}"
                )
                assert any(
                    d.get("code") == "CONTRADICTION_CONTRACTUELLE_BLOQUANTE" for d in res["drapeaux_rouges"]
                )

            # Invariance 4: Missing decennale MUST force NO-GO
            if not has_decennale:
                assert res["verdict"] == "NO-GO", (
                    f"Fuzzer run #{iteration}: missing decennale failed to force NO-GO! Got {res['verdict']}"
                )

            # Invariance 5: Unperformed required visit MUST force NO-GO
            if visite_required and not has_visit:
                assert res["verdict"] == "NO-GO", (
                    f"Fuzzer run #{iteration}: missed visit failed to force NO-GO! Got {res['verdict']}"
                )

            # Invariance 6: Expired date (2020-01-01) MUST force NO-GO
            if date_choice == "2020-01-01":
                assert res["verdict"] == "NO-GO", (
                    f"Fuzzer run #{iteration}: expired date failed to force NO-GO! Got {res['verdict']}"
                )


# =============================================================================
# 5. EMPIRICALLY CONFIRMED DEFECT DEMONSTRATIONS
# =============================================================================

class TestEmpiricalDefectDemonstration:
    """Demonstrates uncovered edge-case bugs for remediation."""

    @pytest.mark.parametrize("marge_str", ["10 %", "10%", "8,5 %", "N/A", "inconnu"])
    def test_unhandled_invalid_operation_on_string_margin(
        self, nominal_analyse: Dict[str, Any], nominal_profil: Dict[str, Any], marge_str: str
    ):
        """DEFECT: In go_nogo.py line 551, float(to_decimal(str(marge_cible))) raises
        decimal.InvalidOperation which is NOT caught by `except (ValueError, TypeError):`.
        This causes an unhandled crash whenever a margin is given as '10 %' or 'inconnu'.
        """
        nominal_profil["structure_couts"]["marge_nette_cible_pct"] = marge_str
        with pytest.raises(decimal.InvalidOperation):
            evaluer_go_nogo(nominal_analyse, nominal_profil)

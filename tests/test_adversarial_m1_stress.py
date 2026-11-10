"""Adversarial stress test suite for scripts/go_nogo.py (Milestone 1 Edge Cases).

Empirical verification of:
1. Empty and corrupt inputs ({} + {}, None inputs, malformed structures).
2. Weight corruption and sum integrity (negative weights, sum != 100, threshold corruption).
3. Same-day deadline expiration at exact hour and missing/unparseable dates.
4. Negative visit phrasing and visit proof verification.
5. Visit physical file check bypass on disk.
6. Insurance verification (expired dates, mismatched trades, non-dict decennale schemas).
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path
from typing import Any, Dict
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from go_nogo import (
    evaluer_go_nogo,
    qualifier_obligation_visite,
    verifier_visite_effectuee_profil,
    verifier_assurances_go_nogo,
    valider_et_resoudre_poids,
    parser_date_et_echeance,
)


# ============================================================================
# 1. EMPTY AND CORRUPT INPUTS STRESS
# ============================================================================

class TestEmptyAndCorruptInputs:
    """Stress testing empty dictionaries and None values across all inputs."""

    def test_empty_dicts_yield_zero_pts_and_non_evaluable(self):
        """Dispatch Requirement: {} + {} must yield 0.0 pts and NON_EVALUABLE."""
        res = evaluer_go_nogo({}, {})
        assert res["score_total"] == 0.0
        assert res["score_sur_100"] == 0.0
        for crit in res["criteres"]:
            assert crit["points_obtenus"] == 0.0
            assert crit["statut"] == "NON_EVALUABLE"
        # The dispatch explicitly specifies verdict NON_EVALUABLE for {} + {}
        assert res["verdict"] == "NON_EVALUABLE", (
            f"Expected verdict NON_EVALUABLE for empty inputs, got {res['verdict']!r} "
            f"with drapeaux: {[d['code'] for d in res.get('drapeaux_rouges', [])]}"
        )

    def test_none_inputs_handled_defensively(self):
        """evaluer_go_nogo(None, None) should not crash."""
        res = evaluer_go_nogo(None, None)
        assert res["score_total"] == 0.0
        assert isinstance(res["criteres"], list)
        assert len(res["criteres"]) == 8

    def test_all_none_keys_in_analyse_and_profil(self):
        """When all keys in analyse and profil are explicitly None, score must be 0.0."""
        bad_analyse = {
            "objet": None,
            "lieu_execution": None,
            "acheteur": None,
            "montant_estime_ht": None,
            "calendrier": None,
            "clauses_sensibles": None,
            "pieces_exigees": None,
            "lots": None,
            "criteres_selection": None,
            "visite_obligatoire": None,
            "visite_site": None,
            "contradictions_detectees": None,
        }
        bad_profil = {
            "identite": None,
            "effectifs": None,
            "qualifications_et_certifications": None,
            "references_chantiers": None,
            "capacites_financieres": None,
            "structure_couts": None,
            "assurances": None,
            "visite_site": None,
        }
        res = evaluer_go_nogo(bad_analyse, bad_profil)
        # All criteria must be NON_EVALUABLE and score must be strictly 0.0
        c_risq = next(c for c in res["criteres"] if c["id"] == "risques_contractuels")
        assert c_risq["points_obtenus"] == 0.0, (
            f"risques_contractuels awarded {c_risq['points_obtenus']} unearned points on None inputs"
        )
        assert c_risq["statut"] == "NON_EVALUABLE"
        assert res["score_total"] == 0.0

    def test_unrelated_field_in_analyse_does_not_earn_free_contract_points(self):
        """If analyse contains an unrelated key (e.g. {'objet': 'Peinture'}),

        risques_contractuels must NOT fabricate contradictions_detectees=[] and award 10 pts.
        """
        analyse = {"objet": "Travaux de peinture"}
        res = evaluer_go_nogo(analyse, {})
        c_risq = next(c for c in res["criteres"] if c["id"] == "risques_contractuels")
        assert c_risq["statut"] == "NON_EVALUABLE", (
            f"Expected NON_EVALUABLE for unanalyzed contract clauses, got {c_risq['statut']} "
            f"with {c_risq['points_obtenus']} pts"
        )
        assert c_risq["points_obtenus"] == 0.0


# ============================================================================
# 2. CORRUPT WEIGHTS AND CONFIG STRESS
# ============================================================================

class TestCorruptWeightsAndConfig:
    """Stress testing malformed configurations, negative weights, and threshold corruptions."""

    def test_none_seuils_decision_does_not_crash(self):
        """config={'seuils_decision': None} must not crash with AttributeError."""
        res = evaluer_go_nogo({}, {}, config={"seuils_decision": None})
        assert "verdict" in res

    def test_none_seuil_go_does_not_crash(self):
        """config={'seuils_decision': {'seuil_go': None}} must not crash with TypeError."""
        res = evaluer_go_nogo({}, {}, config={"seuils_decision": {"seuil_go": None}})
        assert "verdict" in res

    def test_invalid_string_seuil_go_does_not_crash(self):
        """config={'seuils_decision': {'seuil_go': 'invalide'}} must not crash with ValueError."""
        res = evaluer_go_nogo({}, {}, config={"seuils_decision": {"seuil_go": "invalide"}})
        assert "verdict" in res

    def test_weights_sum_integrity_when_all_8_custom_weights_do_not_sum_to_100(self):
        """PROJECT.md line 78: 'Somme des poids vérifiée == 100.0'.

        Custom weights summing to 80 (e.g. 8 x 10) must be rebalanced or normalized to 100.0.
        """
        cfg_80 = {
            "criteres": {
                k: {"poids": 10.0}
                for k in [
                    "adequation_technique",
                    "references_comparables",
                    "capacite_financiere_et_taille",
                    "charge_travail_et_disponibilite",
                    "localisation_eloignement",
                    "rentabilite_estimee",
                    "risques_contractuels",
                    "delai_remise_dossier",
                ]
            }
        }
        res = evaluer_go_nogo({"objet": "Travaux"}, {}, config=cfg_80)
        assert res["somme_poids_verifiee"] == 100, (
            f"Expected somme_poids_verifiee == 100, got {res['somme_poids_verifiee']}"
        )

    def test_negative_weights_rejected_or_clamped(self):
        """A negative weight like -20 must not be allowed to produce negative weights or sum != 100."""
        cfg_neg = {"criteres": {"adequation_technique": {"poids": -20}}}
        poids = valider_et_resoudre_poids(cfg_neg)
        assert poids["adequation_technique"] >= 0.0, (
            f"Negative weight was accepted: {poids['adequation_technique']}"
        )
        assert abs(sum(poids.values()) - 100.0) < 1e-4


# ============================================================================
# 3. DATES AND DEADLINES STRESS
# ============================================================================

class TestDatesAndDeadlines:
    """Stress testing exact-hour deadline expiration and unparseable dates."""

    def test_same_day_deadline_expired_at_exact_hour(self):
        """Closing at 12:00, checking at 12:01 must trigger DATE_LIMITE_DEPASSEE."""
        now = datetime.datetime(2026, 11, 10, 12, 1, 0)
        analyse = {
            "objet": "Travaux de toiture",
            "calendrier": {"date_limite_retenue": "2026-11-10T12:00:00"},
            "lieu_execution": "Bourges (18000)",
            "montant_estime_ht": 100000,
        }
        profil = {
            "identite": {"siege_social": {"code_postal": "18000"}},
            "effectifs": {"total_salaries": 10},
            "qualifications_et_certifications": [{"code": "3101"}],
            "references_chantiers": [{"objet": "Chantier toiture"}],
            "capacites_financieres": {"exercices": [{"chiffre_affaires_ht_euros": 1000000}]},
            "structure_couts": {"marge_nette_cible_pct": 10},
            "assurances": {"decennale": {"numero_police": "POL-123"}},
        }
        res = evaluer_go_nogo(analyse, profil, maintenant=now)
        codes = [d["code"] for d in res.get("drapeaux_rouges", [])]
        assert "DATE_LIMITE_DEPASSEE" in codes
        assert res["verdict"] == "NO-GO"

    def test_same_day_deadline_before_exact_hour_is_not_expired(self):
        """Closing at 12:00, checking at 11:59 is NOT expired."""
        now = datetime.datetime(2026, 11, 10, 11, 59, 0)
        analyse = {
            "objet": "Travaux de toiture",
            "calendrier": {"date_limite_retenue": "2026-11-10T12:00:00"},
            "lieu_execution": "Bourges (18000)",
            "montant_estime_ht": 100000,
        }
        profil = {
            "identite": {"siege_social": {"code_postal": "18000"}},
            "effectifs": {"total_salaries": 10},
            "qualifications_et_certifications": [{"code": "3101"}],
            "references_chantiers": [{"objet": "Chantier toiture"}],
            "capacites_financieres": {"exercices": [{"chiffre_affaires_ht_euros": 1000000}]},
            "structure_couts": {"marge_nette_cible_pct": 10},
            "assurances": {"decennale": {"numero_police": "POL-123"}},
        }
        res = evaluer_go_nogo(analyse, profil, maintenant=now)
        codes = [d["code"] for d in res.get("drapeaux_rouges", [])]
        assert "DATE_LIMITE_DEPASSEE" not in codes

    def test_unparseable_date_prevents_unreserved_go(self):
        """An unparseable date must receive 0.0 pts, NON_EVALUABLE, and NOT allow positive GO."""
        analyse = {
            "objet": "Travaux de toiture",
            "calendrier": {"date_limite_retenue": "DATE_CORROMPUE_INVALIDE"},
            "lieu_execution": "Bourges (18000)",
            "montant_estime_ht": 100000,
        }
        profil = {
            "identite": {"siege_social": {"code_postal": "18000"}},
            "effectifs": {"total_salaries": 10},
            "qualifications_et_certifications": [{"code": "3101"}],
            "references_chantiers": [{"objet": "Chantier toiture"}],
            "capacites_financieres": {"exercices": [{"chiffre_affaires_ht_euros": 1000000}]},
            "structure_couts": {"marge_nette_cible_pct": 10},
            "assurances": {"decennale": {"numero_police": "POL-123"}},
        }
        res = evaluer_go_nogo(analyse, profil)
        assert res["verdict"] != "GO"
        assert res["verdict"] == "GO SOUS RÉSERVE"
        c_delai = next(c for c in res["criteres"] if c["id"] == "delai_remise_dossier")
        assert c_delai["points_obtenus"] == 0.0
        assert c_delai["statut"] == "NON_EVALUABLE"


# ============================================================================
# 4. VISITS AND INSURANCES STRESS
# ============================================================================

class TestVisitsAndInsurances:
    """Stress testing site visit phrasings, disk file verification, and decennale coverage."""

    @pytest.mark.parametrize(
        "phrase",
        [
            "La visite du site n'est pas obligatoire",
            "visite facultative",
            "La visite des lieux est non obligatoire pour ce lot",
            "aucune visite requise",
            "visite libre et a l'initiative du candidat",
            "visite recommandee mais non obligatoire",
        ],
    )
    def test_negative_visit_phrasing_does_not_raise_obligatoire(self, phrase: str):
        """Negative or optional visit phrasing must NOT be classified as OBLIGATOIRE."""
        regime, motif = qualifier_obligation_visite({"pieces_exigees": [phrase]})
        assert regime in ["FACULTATIVE", "RECOMMANDEE", "AUCUNE"]
        assert regime != "OBLIGATOIRE"

    def test_visit_declared_with_nonexistent_file_must_raise_red_flag_even_if_visite_effectuee_is_true(self):
        """CRITICAL VULNERABILITY CHECK:

        When a market mandates a site visit, and the company profile specifies:
        {'visite_site': {'visite_effectuee': True, 'attestation_fichier': 'certificat_fantome.pdf'}}
        where 'certificat_fantome.pdf' DOES NOT EXIST on disk,
        the engine MUST raise a red flag and MUST NOT grant a positive GO.
        """
        analyse = {
            "objet": "Travaux toiture",
            "visite_obligatoire": True,
            "calendrier": {"date_limite_retenue": "2026-12-15T12:00:00"},
            "lieu_execution": "Bourges (18000)",
            "montant_estime_ht": 100000,
        }
        profil = {
            "identite": {"siege_social": {"code_postal": "18000"}},
            "effectifs": {"total_salaries": 10},
            "qualifications_et_certifications": [{"code": "3101"}],
            "references_chantiers": [{"objet": "Chantier toiture"}],
            "capacites_financieres": {"exercices": [{"chiffre_affaires_ht_euros": 1000000}]},
            "structure_couts": {"marge_nette_cible_pct": 10},
            "assurances": {"decennale": {"numero_police": "POL-123"}},
            "visite_site": {
                "visite_effectuee": True,
                "attestation_fichier": "certificat_fantome_inexistant_sur_disque.pdf",
            },
        }
        res = evaluer_go_nogo(analyse, profil)
        codes = [d["code"] for d in res.get("drapeaux_rouges", [])]
        assert "VISITE_OBLIGATOIRE_MANQUEE" in codes, (
            f"VULNERABILITY: Fake visit file on disk was ignored because visite_effectuee=True! "
            f"Verdict: {res['verdict']}, Flags: {codes}"
        )
        assert res["verdict"] == "NO-GO"

    def test_insurance_with_expired_date_triggers_red_flag(self):
        """Insurance with expired date must raise ASSURANCE_DECENNALE_EXPIREE and NO-GO."""
        now = datetime.datetime(2026, 11, 10, 10, 0, 0)
        analyse = {
            "objet": "Travaux de couverture",
            "calendrier": {"date_limite_retenue": "2026-12-15T12:00:00"},
            "lieu_execution": "Bourges (18000)",
            "montant_estime_ht": 100000,
        }
        profil = {
            "identite": {"siege_social": {"code_postal": "18000"}},
            "effectifs": {"total_salaries": 10},
            "qualifications_et_certifications": [{"code": "3101"}],
            "references_chantiers": [{"objet": "Chantier toiture"}],
            "capacites_financieres": {"exercices": [{"chiffre_affaires_ht_euros": 1000000}]},
            "structure_couts": {"marge_nette_cible_pct": 10},
            "assurances": {
                "decennale": {
                    "numero_police": "POL-EXPIRED",
                    "date_validite": "2025-06-30",
                    "activites_couvertes": ["Couverture", "Zinguerie"],
                }
            },
        }
        res = evaluer_go_nogo(analyse, profil, maintenant=now)
        codes = [d["code"] for d in res.get("drapeaux_rouges", [])]
        assert "ASSURANCE_DECENNALE_EXPIREE" in codes
        assert res["verdict"] == "NO-GO"

    def test_insurance_with_mismatched_trade_activities_triggers_red_flag(self):
        """Insurance covering Plomberie for a VRD market must raise ASSURANCE_ACTIVITES_NON_COUVERTES."""
        analyse = {
            "objet": "Travaux de Voirie et Réseaux Divers (VRD) et terrassement",
            "calendrier": {"date_limite_retenue": "2026-12-15T12:00:00"},
            "lieu_execution": "Bourges (18000)",
            "montant_estime_ht": 100000,
        }
        profil = {
            "identite": {"siege_social": {"code_postal": "18000"}},
            "effectifs": {"total_salaries": 10},
            "qualifications_et_certifications": [{"code": "VRD"}],
            "references_chantiers": [{"objet": "Chantier VRD"}],
            "capacites_financieres": {"exercices": [{"chiffre_affaires_ht_euros": 1000000}]},
            "structure_couts": {"marge_nette_cible_pct": 10},
            "assurances": {
                "decennale": {
                    "numero_police": "POL-PLOMBERIE",
                    "date_validite": "2027-12-31",
                    "activites_couvertes": ["Plomberie", "Sanitaire", "Chauffage"],
                }
            },
        }
        res = evaluer_go_nogo(analyse, profil)
        codes = [d["code"] for d in res.get("drapeaux_rouges", [])]
        assert "ASSURANCE_ACTIVITES_NON_COUVERTES" in codes
        assert res["verdict"] == "NO-GO"

    def test_decennale_as_string_does_not_crash_engine(self):
        """CRASH CHECK: profil['assurances']['decennale'] as string must not crash with AttributeError."""
        profil = {"assurances": {"decennale": "AXA-123456"}}
        res = evaluer_go_nogo({}, profil)
        assert "verdict" in res

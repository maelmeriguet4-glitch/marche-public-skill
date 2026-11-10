"""Adversarial stress-test script for go_nogo.py (Milestone 1 - Iteration 2).

Probes blocking contradiction invariance and site visit detection across
extreme adversarial vectors: unicode spaces, tabs, punctuation, morphology,
nested data structures, and malformed inputs.
"""

from __future__ import annotations

import datetime
from pathlib import Path
import sys
from typing import Any, Dict, List
import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
ASSETS_DIR = ROOT_DIR / "assets"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import go_nogo


@pytest.fixture
def config_go_nogo() -> Dict[str, Any]:
    with (ASSETS_DIR / "go_nogo_config.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def profil_parfait() -> Dict[str, Any]:
    return {
        "identite": {
            "raison_sociale": "Entreprise Championne BTP",
            "siege_social": {"code_postal": "18000", "ville": "Bourges"},
        },
        "effectifs": {"total_salaries": 25},
        "capacites_financieres": {
            "exercices": [{"chiffre_affaires_ht_euros": 3000000.0}]
        },
        "references_chantiers": [
            {"intitule": "Chantier A"},
            {"intitule": "Chantier B"},
            {"intitule": "Chantier C"},
            {"intitule": "Chantier D"},
        ],
        "qualifications_et_certifications": [
            {"code": "3101", "intitule": "Couverture toiture etanchéité"}
        ],
        "assurances": {"decennale": {"numero_police": "POL-99999"}},
        "structure_couts": {"marge_nette_cible_pct": 12.0},
        "visite_site": {"visite_effectuee": True},
    }


@pytest.fixture
def analyse_parfaite() -> Dict[str, Any]:
    date_future = (datetime.date.today() + datetime.timedelta(days=30)).strftime("%d/%m/%Y")
    return {
        "objet": "Travaux de couverture toiture étanchéité",
        "acheteur": "Commune de Bourges 18000",
        "lieu_execution": "18000 Bourges",
        "montant_estime_ht": 100000.0,
        "calendrier": {"date_limite_retenue": date_future},
        "contradictions_detectees": [],
    }


# ==============================================================================
# 1. ADVANCED ADVERSARIAL BLOCKING CONTRADICTION TESTS
# ==============================================================================

class TestAdversarialContradictionsIter2:
    """Stress tests on blocking contradiction invariance."""

    @pytest.mark.parametrize("gravite_input", [
        "\tBLOQUANT",
        "BLOQUANT\t",
        "\t\tBLOQUANT\t\t",
        "\r\nBLOQUANT\r\n",
        "\u00A0BLOQUANT",          # Non-breaking space NBSP
        "BLOQUANT\u00A0",
        "\u00A0BLOQUANT\u00A0",
        "\u2002BLOQUANT\u2002",      # En space
        "\u2003BLOQUANT\u2003",      # Em space
        "\u2009BLOQUANT",            # Thin space
        "\u202FBLOQUANT\u202F",      # Narrow no-break space
        "\u3000BLOQUANT\u3000",      # Ideographic space
        "  \t \u00A0 BLOQUANT \u00A0 \t  ",  # Mixed whitespace
        "bLoQuAnT",                  # Alternating case
        "bloquant",
        "BLOQUANT",
        "Bloquant",
    ])
    def test_blocking_whitespace_and_casing_variations(
        self, gravite_input: str, config_go_nogo: Dict[str, Any], profil_parfait: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        """Must return NO-GO and raise CONTRADICTION_CONTRACTUELLE_BLOQUANTE."""
        analyse = dict(analyse_parfaite)
        analyse["contradictions_detectees"] = [
            {"type": "CLAUSE_DEROGATOIRE", "gravite": gravite_input, "description": "Contradiction test"}
        ]
        res = go_nogo.evaluer_go_nogo(analyse, profil_parfait, config_go_nogo)
        assert res["verdict"] == "NO-GO", (
            f"Adversarial gravite '{repr(gravite_input)}' failed to trigger NO-GO. Verdict: {res['verdict']}"
        )
        assert any(
            d.get("code") == "CONTRADICTION_CONTRACTUELLE_BLOQUANTE"
            for d in res["drapeaux_rouges"]
        )

    def test_non_dict_contradictions_in_list(
        self, config_go_nogo: Dict[str, Any], profil_parfait: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        """Malformed elements in contradictions_detectees (None, int, str) should not crash."""
        analyse = dict(analyse_parfaite)
        analyse["contradictions_detectees"] = [
            None,
            "juste une chaine",
            42,
            {"type": "TEST", "gravite": "BLOQUANT", "description": "Vraie bloquante"},
            {"non_gravite": "valeur"}
        ]
        res = go_nogo.evaluer_go_nogo(analyse, profil_parfait, config_go_nogo)
        assert res["verdict"] == "NO-GO"
        assert any(
            d.get("code") == "CONTRADICTION_CONTRACTUELLE_BLOQUANTE"
            for d in res["drapeaux_rouges"]
        )

    def test_contradictions_non_list_type(
        self, config_go_nogo: Dict[str, Any], profil_parfait: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        """contradictions_detectees as dict or string should not crash and default gracefully."""
        analyse = dict(analyse_parfaite)
        analyse["contradictions_detectees"] = {"type": "SINGLE_DICT", "gravite": "BLOQUANT"}
        res = go_nogo.evaluer_go_nogo(analyse, profil_parfait, config_go_nogo)
        # Does not crash
        assert "verdict" in res


# ==============================================================================
# 2. ADVANCED ADVERSARIAL SITE VISIT TESTS
# ==============================================================================

class TestAdversarialSiteVisitIter2:
    """Stress tests on site visit requirement detection."""

    @pytest.fixture
    def profil_sans_visite(self, profil_parfait: Dict[str, Any]) -> Dict[str, Any]:
        p = dict(profil_parfait)
        p["visite_site"] = {"visite_effectuee": False}
        p["visite_effectuee"] = False
        return p

    @pytest.mark.parametrize("nested_pieces", [
        # Multi-level nested lists and dicts
        {"lot1": {"candidature": {"pieces": ["Attestation de visite obligatoire"]}}},
        {"lots": [{"pieces_obligatoires": ["Certificat de visite des lieux"]}]},
        {"a": {"b": {"c": {"d": ["visite sur place impérative"]}}}},
        # String directly in pieces_exigees
        "Visite obligatoire sur site préalable au dépôt",
        # List with nested mixed types
        ["DC1", ["DC2", {"annexe": ["Attestation de visite indispensable"]}]],
    ])
    def test_site_visit_deeply_nested_structures(
        self, nested_pieces: Any, config_go_nogo: Dict[str, Any], profil_sans_visite: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        analyse = dict(analyse_parfaite)
        analyse["pieces_exigees"] = nested_pieces
        res = go_nogo.evaluer_go_nogo(analyse, profil_sans_visite, config_go_nogo)
        assert res["verdict"] == "NO-GO", (
            f"Failed to detect site visit in nested structure: {nested_pieces}. Verdict: {res['verdict']}"
        )
        assert any("VISITE" in (d.get("code") or "") for d in res["drapeaux_rouges"])

    @pytest.mark.parametrize("clause_phrase", [
        "La visite du site est obligatoire sous peine de rejet de l'offre.",
        "Une visite préalable des lieux est exigée pour apprécier les contraintes.",
        "Visite obligatoire requise avant tout chiffrage.",
        "Visite des lieux impérative avec émargement d'une attestation.",
        "Visite indispensable de la toiture.",
    ])
    def test_site_visit_in_clauses_sensibles_strings(
        self, clause_phrase: str, config_go_nogo: Dict[str, Any], profil_sans_visite: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        analyse = dict(analyse_parfaite)
        analyse["clauses_sensibles"] = {
            "article_12": clause_phrase
        }
        res = go_nogo.evaluer_go_nogo(analyse, profil_sans_visite, config_go_nogo)
        assert res["verdict"] == "NO-GO", (
            f"Failed to detect site visit in clause phrase: '{clause_phrase}'"
        )
        assert any("VISITE" in (d.get("code") or "") for d in res["drapeaux_rouges"])

    @pytest.mark.parametrize("contras_desc", [
        "Le RC mentionne une visite obligatoire alors que le CCAP n'en parle pas.",
        "Visite sur site exigée non planifiée.",
    ])
    def test_site_visit_detected_from_contradictions(
        self, contras_desc: str, config_go_nogo: Dict[str, Any], profil_sans_visite: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        analyse = dict(analyse_parfaite)
        analyse["contradictions_detectees"] = [
            {"type": "DISCORDANCE_VISITE", "gravite": "MOYEN", "description": contras_desc}
        ]
        res = go_nogo.evaluer_go_nogo(analyse, profil_sans_visite, config_go_nogo)
        assert res["verdict"] == "NO-GO"
        assert any("VISITE" in (d.get("code") or "") for d in res["drapeaux_rouges"])

    def test_profil_site_visit_variations_satisfied(
        self, config_go_nogo: Dict[str, Any], profil_parfait: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        """Different valid ways the profile declares visit was performed."""
        analyse = dict(analyse_parfaite)
        analyse["pieces_exigees"] = ["Attestation de visite obligatoire"]

        # Case 1: visite_site.effectuee == True
        p1 = dict(profil_parfait)
        p1["visite_site"] = {"effectuee": True, "attestation_fichier": "attestation_visite_signee.pdf"}
        res1 = go_nogo.evaluer_go_nogo(analyse, p1, config_go_nogo)
        assert not any("VISITE" in (d.get("code") or "") for d in res1["drapeaux_rouges"])

        # Case 2: visite_site.date_visite provided
        p2 = dict(profil_parfait)
        p2["visite_site"] = {"date_visite": "15/10/2026", "attestation_fichier": "attestation_visite_signee.pdf"}
        res2 = go_nogo.evaluer_go_nogo(analyse, p2, config_go_nogo)
        assert not any("VISITE" in (d.get("code") or "") for d in res2["drapeaux_rouges"])

        # Case 3: top-level visite_site_effectuee == True
        p3 = dict(profil_parfait)
        p3["visite_site"] = {"attestation_fichier": "attestation_visite_signee.pdf"}
        p3["visite_site_effectuee"] = True
        res3 = go_nogo.evaluer_go_nogo(analyse, p3, config_go_nogo)
        assert not any("VISITE" in (d.get("code") or "") for d in res3["drapeaux_rouges"])


# ==============================================================================
# 3. COMBINED PRESSURE AND SCORING INVARIANCE
# ==============================================================================

class TestCombinedInvariance:
    """Check that regardless of score (even 100/100), red flags strictly force NO-GO."""

    def test_score_100_with_blocking_contradiction_is_nogo(
        self, config_go_nogo: Dict[str, Any], profil_parfait: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        analyse = dict(analyse_parfaite)
        analyse["contradictions_detectees"] = [
            {"type": "CLAUSE_ABUSIVE", "gravite": "  BLOQUANT\t", "description": "Pénalité abusive"}
        ]
        res = go_nogo.evaluer_go_nogo(analyse, profil_parfait, config_go_nogo)
        assert res["verdict"] == "NO-GO"
        assert res["score_sur_100"] >= 70.0
        assert any(d.get("bloquant") is True for d in res["drapeaux_rouges"])

    def test_score_100_with_missing_site_visit_is_nogo(
        self, config_go_nogo: Dict[str, Any], profil_parfait: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        p = dict(profil_parfait)
        p["visite_site"] = {"visite_effectuee": False}
        p["visite_effectuee"] = False

        analyse = dict(analyse_parfaite)
        analyse["pieces_exigees"] = ["Attestation de visite obligatoire"]

        res = go_nogo.evaluer_go_nogo(analyse, p, config_go_nogo)
        assert res["verdict"] == "NO-GO"
        assert any(d.get("code") == "VISITE_OBLIGATOIRE_MANQUEE" for d in res["drapeaux_rouges"])

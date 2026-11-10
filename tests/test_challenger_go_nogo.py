"""Tests d'adversité empiriques (Challenger) pour scripts/go_nogo.py.

Banc de test adversarial développé par challenger_m1_1 pour vérifier :
1. La robustesse de l'invariance absolue des contradictions bloquantes (NO-GO garanti)
2. L'exhaustivité de la détection d'obligation de visite du site (formats, cas d'angles, phrasés subtils)
3. La résilience aux types malformés et aux valeurs nulles (NoneType)
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
    """Profil maximisant tous les critères (90+ points potentiels hors critère 7)."""
    return {
        "identite": {
            "raison_sociale": "Entreprise Championne BTP",
            "siege_social": {"code_postal": "18000", "ville": "Bourges"},
        },
        "effectifs": {"total_salaries": 25},  # >= 15 salariés -> 15 pts
        "capacites_financieres": {
            "exercices": [{"chiffre_affaires_ht_euros": 3000000.0}]  # CA solide -> 15 pts
        },
        "references_chantiers": [
            {"intitule": "Chantier A"},
            {"intitule": "Chantier B"},
            {"intitule": "Chantier C"},
            {"intitule": "Chantier D"},
        ],  # >= 3 refs -> 15 pts
        "qualifications_et_certifications": [
            {"code": "3101", "intitule": "Couverture toiture etanchéité"}
        ],  # aligné -> 20 pts
        "assurances": {
            "decennale": {
                "numero_police": "POL-99999",
                "attestation_fichier": "attestation_assurance_decennale.pdf",
            }
        },
        "structure_couts": {"marge_nette_cible_pct": 12.0},  # >= 10% -> 10 pts
        "visite_site": {
            "visite_effectuee": True,
            "attestation_fichier": "attestation_visite_signee.pdf",
        },
    }


@pytest.fixture
def analyse_parfaite() -> Dict[str, Any]:
    """Analyse DCE alignée avec le profil parfait et délai long (> 10 jours ouvrés -> 5 pts)."""
    date_future = (datetime.date.today() + datetime.timedelta(days=30)).strftime("%d/%m/%Y")
    return {
        "objet": "Travaux de couverture toiture étanchéité",
        "acheteur": "Commune de Bourges 18000",
        "lieu_execution": "18000 Bourges",
        "montant_estime_ht": 100000.0,  # 100k / 3M = 3.3% (< 15%) -> 15 pts
        "calendrier": {"date_limite_retenue": date_future},
        "contradictions_detectees": [],
    }


# ==============================================================================
# CHALLENGE 1 : GARANTIE DE CONTRADICTION BLOQUANTE
# ==============================================================================

class TestChallengeBlockingContradiction:
    """Vérifie qu'AUCUNE circonstance ne permet d'obtenir GO avec une contradiction bloquante."""

    def test_parfait_score_with_single_blocking_contradiction_exact_string(
        self, config_go_nogo: Dict[str, Any], profil_parfait: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        """Cas nominal : avec gravite='BLOQUANT', le verdict est strictement NO-GO."""
        analyse = dict(analyse_parfaite)
        analyse["contradictions_detectees"] = [
            {
                "type": "DATE_LIMITE_CONTRADICTOIRE",
                "gravite": "BLOQUANT",
                "description": "Discordance critique RC vs AE",
            }
        ]
        res = go_nogo.evaluer_go_nogo(analyse, profil_parfait, config_go_nogo)
        assert res["score_sur_100"] >= 70.0, f"Le score brut devrait dépasser 70 (score={res['score_sur_100']})"
        assert res["verdict"] == "NO-GO", "Le verdict DOIT être strictement NO-GO"
        assert any(
            d.get("code") == "CONTRADICTION_CONTRACTUELLE_BLOQUANTE"
            for d in res["drapeaux_rouges"]
        )

    @pytest.mark.parametrize("gravite_val", [
        "bloquant",
        "Bloquant",
        "BLOQUANT",
    ])
    def test_blocking_contradiction_casing(
        self, gravite_val: str, config_go_nogo: Dict[str, Any], profil_parfait: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        """La détection du mot-clé BLOQUANT est insensible à la casse sans espaces."""
        analyse = dict(analyse_parfaite)
        analyse["contradictions_detectees"] = [
            {"type": "CLAUSE_ABUSIVE", "gravite": gravite_val, "description": "Pénalité illégale"}
        ]
        res = go_nogo.evaluer_go_nogo(analyse, profil_parfait, config_go_nogo)
        assert res["verdict"] == "NO-GO"
        assert any("CONTRADICTION" in (d.get("code") or "") for d in res["drapeaux_rouges"])

    @pytest.mark.parametrize("gravite_whitespace", [
        " BLOQUANT",
        "BLOQUANT ",
        "  bloquant  ",
        "BLOQUANT\n",
    ])
    def test_blocking_contradiction_whitespace_vulnerability(
        self, gravite_whitespace: str, config_go_nogo: Dict[str, Any], profil_parfait: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        """Adversarial : Espaces ou retours chariot dans la valeur de gravité.
        FAIL si le moteur laisse passer un score >= 70 avec verdict GO !"""
        analyse = dict(analyse_parfaite)
        analyse["contradictions_detectees"] = [
            {"type": "CLAUSE_ABUSIVE", "gravite": gravite_whitespace, "description": "Pénalité avec espaces"}
        ]
        res = go_nogo.evaluer_go_nogo(analyse, profil_parfait, config_go_nogo)
        assert res["verdict"] == "NO-GO", (
            f"FAIL : La contradiction bloquante '{repr(gravite_whitespace)}' n'a pas déclenché NO-GO. "
            f"Verdict obtenu: {res['verdict']} (Score: {res['score_sur_100']})"
        )

    def test_multiple_contradictions_only_one_blocking(
        self, config_go_nogo: Dict[str, Any], profil_parfait: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        """Plusieurs contradictions mineures et UNE bloquante."""
        analyse = dict(analyse_parfaite)
        analyse["contradictions_detectees"] = [
            {"type": "INFO_MINEURE", "gravite": "MINEUR", "description": "Détail mineur"},
            {"type": "INFO_MOYENNE", "gravite": "MOYEN", "description": "Point d'attention"},
            {"type": "INFO_BLOQUANTE", "gravite": "BLOQUANT", "description": "Point bloquant"},
        ]
        res = go_nogo.evaluer_go_nogo(analyse, profil_parfait, config_go_nogo)
        assert res["verdict"] == "NO-GO"

    def test_non_blocking_contradictions_allow_go(
        self, config_go_nogo: Dict[str, Any], profil_parfait: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        """Sans contradiction bloquante, le profil parfait doit obtenir GO."""
        analyse = dict(analyse_parfaite)
        analyse["contradictions_detectees"] = [
            {"type": "INFO_MINEURE", "gravite": "MINEUR", "description": "Détail mineur"},
        ]
        res = go_nogo.evaluer_go_nogo(analyse, profil_parfait, config_go_nogo)
        assert res["verdict"] == "GO"


# ==============================================================================
# CHALLENGE 2 : DÉTECTION DE L'OBLIGATION DE VISITE
# ==============================================================================

class TestChallengeSiteVisitDetection:
    """Stress-test de la détection de l'obligation de visite du site."""

    @pytest.fixture
    def profil_sans_visite(self, profil_parfait: Dict[str, Any]) -> Dict[str, Any]:
        p = dict(profil_parfait)
        p["visite_site"] = {"visite_effectuee": False}
        p["visite_effectuee"] = False
        return p

    def test_pieces_exigees_nested_subdicts_vulnerability(
        self, config_go_nogo: Dict[str, Any], profil_sans_visite: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        """DCE avec pièces exigées imbriquées dans des sous-dictionnaires profonds (> 1 niveau)."""
        analyse = dict(analyse_parfaite)
        analyse["pieces_exigees"] = {
            "dossier_technique": {
                "sous_lot_1": ["Attestation de visite obligatoire signée"],
            }
        }
        res = go_nogo.evaluer_go_nogo(analyse, profil_sans_visite, config_go_nogo)
        assert res["verdict"] == "NO-GO", (
            f"FAIL : La visite imbriquée n'a pas été détectée. Verdict obtenu : {res['verdict']}"
        )
        assert any("VISITE" in (d.get("code") or "") for d in res["drapeaux_rouges"])

    @pytest.mark.parametrize("phrase_visite", [
        "Attestation de visite obligatoire des lieux",
        "VISITE OBLIGATOIRE SUR SITE",
        "Visite préalable obligatoire",
        "visite des lieux impérative",
        "visite sur place impérative",
        "Certificat de visite indispensable",
        "Visite obligatoire préalable à toute remise d'offre",
    ])
    def test_phrasings_in_pieces_exigees_list(
        self, phrase_visite: str, config_go_nogo: Dict[str, Any], profil_sans_visite: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        """Variations de phrasé dans pieces_exigees (liste)."""
        analyse = dict(analyse_parfaite)
        analyse["pieces_exigees"] = ["DC1", phrase_visite, "DC2"]
        res = go_nogo.evaluer_go_nogo(analyse, profil_sans_visite, config_go_nogo)
        assert res["verdict"] == "NO-GO", f"Visite non détectée avec le phrasé : '{phrase_visite}'"
        assert any("VISITE" in (d.get("code") or "") for d in res["drapeaux_rouges"])

    @pytest.mark.parametrize("phrase_visite", [
        "visite sur place impérative",
        "visite préalable obligatoire",
        "visite obligatoire sous peine de rejet",
    ])
    def test_phrasings_in_clauses_sensibles_dict_vulnerability(
        self, phrase_visite: str, config_go_nogo: Dict[str, Any], profil_sans_visite: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        """Variations de phrasé dans clauses_sensibles (dictionnaire arbitraire)."""
        analyse = dict(analyse_parfaite)
        analyse["clauses_sensibles"] = {
            "modalites_particulieres": phrase_visite
        }
        res = go_nogo.evaluer_go_nogo(analyse, profil_sans_visite, config_go_nogo)
        assert res["verdict"] == "NO-GO", (
            f"FAIL : Visite dans clauses_sensibles non détectée pour '{phrase_visite}'. "
            f"Verdict obtenu : {res['verdict']}"
        )
        assert any("VISITE" in (d.get("code") or "") for d in res["drapeaux_rouges"])

    def test_profil_visite_attestation_fichier_present(
        self, config_go_nogo: Dict[str, Any], profil_parfait: Dict[str, Any], analyse_parfaite: Dict[str, Any]
    ):
        """Profil avec attestation_fichier mais visite_effectuee absent -> considéré effectué."""
        p = dict(profil_parfait)
        p["visite_site"] = {"attestation_fichier": "attestation_visite_signee.pdf"}
        analyse = dict(analyse_parfaite)
        analyse["pieces_exigees"] = ["Attestation de visite obligatoire"]
        res = go_nogo.evaluer_go_nogo(analyse, p, config_go_nogo)
        assert not any("VISITE" in (d.get("code") or "") for d in res["drapeaux_rouges"])


# ==============================================================================
# CHALLENGE 3 : DONNÉES ENTRANTES ATYPIQUES & ROBUSTESSE AUX NULLS
# ==============================================================================

class TestChallengeRobustnessAndNullSafety:
    """Vérifie la robustesse aux entrées atypiques, types inattendus et valeurs None."""

    def test_empty_profil_and_empty_analyse(self, config_go_nogo: Dict[str, Any]):
        """Profil vide et analyse vide : ne doit pas crasher, doit retourner NO-GO ou NON_EVALUABLE."""
        res = go_nogo.evaluer_go_nogo({}, {}, config_go_nogo)
        assert res["verdict"] in ["NO-GO", "NON_EVALUABLE"]
        assert res["score_sur_100"] >= 0.0

    def test_null_contradictions_detectees_crash(self, config_go_nogo: Dict[str, Any]):
        """analyse['contradictions_detectees'] = None -> doit être géré sans crash TypeError."""
        analyse = {"contradictions_detectees": None}
        res = go_nogo.evaluer_go_nogo(analyse, {}, config_go_nogo)
        assert res["verdict"] in ["NO-GO", "NON_EVALUABLE"]

    def test_null_qualifications_crash(self, config_go_nogo: Dict[str, Any]):
        """profil['qualifications_et_certifications'] = None -> doit être géré sans crash TypeError."""
        profil = {"qualifications_et_certifications": None}
        res = go_nogo.evaluer_go_nogo({"contradictions_detectees": []}, profil, config_go_nogo)
        assert res["verdict"] in ["NO-GO", "NON_EVALUABLE"]

    def test_null_references_crash(self, config_go_nogo: Dict[str, Any]):
        """profil['references_chantiers'] = None -> doit être géré sans crash TypeError."""
        profil = {"references_chantiers": None}
        res = go_nogo.evaluer_go_nogo({"contradictions_detectees": []}, profil, config_go_nogo)
        assert res["verdict"] in ["NO-GO", "NON_EVALUABLE"]

    def test_effectifs_string_digits(self, config_go_nogo: Dict[str, Any], profil_parfait: Dict[str, Any]):
        """Effectifs sous forme de chaîne '25'."""
        p = dict(profil_parfait)
        p["effectifs"] = {"total_salaries": "25"}
        res = go_nogo.evaluer_go_nogo({"contradictions_detectees": []}, p, config_go_nogo)
        crit_charge = next(c for c in res["criteres"] if c["id"] == "charge_travail_et_disponibilite")
        assert crit_charge["points_obtenus"] == 15.0

    def test_code_postal_integer(self, config_go_nogo: Dict[str, Any], profil_parfait: Dict[str, Any]):
        """Code postal sous forme d'entier 18000."""
        p = dict(profil_parfait)
        p["identite"]["siege_social"]["code_postal"] = 18000
        res = go_nogo.evaluer_go_nogo({"acheteur": "Bourges 18000", "contradictions_detectees": []}, p, config_go_nogo)
        crit_geo = next(c for c in res["criteres"] if c["id"] == "localisation_eloignement")
        assert crit_geo["points_obtenus"] == 10.0

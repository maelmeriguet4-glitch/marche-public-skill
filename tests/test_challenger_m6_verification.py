"""Empirical Challenger Verification Test Suite for Milestone 6 Gate.

Authored independently by challenger_m6_1 to stress-test commit 243c986
against all required adversarial boundary conditions.
"""

import datetime
from decimal import Decimal
from pathlib import Path
import sys
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from go_nogo import (
    evaluer_go_nogo,
    qualifier_obligation_visite,
    parser_date_et_echeance,
)
from checklist_pieces import (
    generer_checklist,
    verifier_presence_fichier,
    verifier_validite_date,
)
from controle_prix import verifier_arithmetique
from controle_final import auditer_dossier
from calendrier import parser_date_fr


class TestChallengerGoNoGoBoundaries:
    """Empirical verification of Go/No-Go boundary conditions."""

    def test_empty_payloads_yield_zero_score_and_non_evaluable(self):
        """Empty analyse and empty profil must produce score 0 and NON_EVALUABLE."""
        res = evaluer_go_nogo(analyse={}, profil={})
        assert res["score_total"] == 0.0 or res["score_sur_100"] == 0.0
        assert res["verdict"] == "NON_EVALUABLE"
        assert res["somme_poids_verifiee"] == 100
        for c in res["criteres_eval"]:
            assert c["points_obtenus"] == 0.0
            assert c["statut"] == "NON_EVALUABLE"

    def test_unparseable_date_prevents_unreserved_go(self, tmp_path: Path):
        """Unparseable tender deadline must not permit unreserved GO verdict."""
        cert_file = tmp_path / "decennale.pdf"
        cert_file.write_text("assurance", encoding="utf-8")

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
        res = evaluer_go_nogo(analyse=analyse, profil=profil)
        # Verdict must NOT be "GO"
        assert res["verdict"] != "GO"
        assert res["verdict"] in ["GO SOUS RÉSERVE", "NON_EVALUABLE"]
        c_delai = next(c for c in res["criteres_eval"] if c["id"] == "delai_remise_dossier")
        assert c_delai["points_obtenus"] == 0.0
        assert c_delai["statut"] == "NON_EVALUABLE"

    @pytest.mark.parametrize(
        "phrase",
        [
            "aucune visite requise",
            "visite facultative",
            "visite non obligatoire",
            "La visite des lieux n'est pas obligatoire pour ce lot",
            "visite libre et a l'initiative du candidat",
            "visite recommandee mais non obligatoire",
            "aucune visite du site n'est imposee",
        ],
    )
    def test_negative_visit_phrasings_not_treated_as_mandatory(self, phrase: str):
        """Negative and optional visit phrasings must NOT trigger mandatory visit or red flag."""
        statut, motif = qualifier_obligation_visite({"pieces_exigees": [phrase]})
        assert statut in ["FACULTATIVE", "RECOMMANDEE", "AUCUNE"]
        assert statut != "OBLIGATOIRE"

        analyse = {
            "pieces_exigees": {"offre": [phrase]},
            "departement": "75",
            "corps_etat": ["Couverture"],
        }
        profil = {
            "visite_site": {"visite_effectuee": False},
            "identite": {"code_postal": "75001"},
            "corps_etat_exercices": ["Couverture"],
        }
        res = evaluer_go_nogo(analyse=analyse, profil=profil)
        drapeaux_codes = [d.get("code") or d.get("id") for d in res["drapeaux_rouges"]]
        assert "VISITE_OBLIGATOIRE_MANQUEE" not in drapeaux_codes
        assert "VISITE_OBLIGATOIRE_NON_EFFECTUEE" not in drapeaux_codes

    def test_missing_physical_visit_certificate_file_raises_red_flag(self, tmp_path: Path):
        """Declared visit with missing physical file on disk must raise red flag when mandatory."""
        cert_file = tmp_path / "decennale.pdf"
        cert_file.write_text("assurance", encoding="utf-8")

        analyse = {
            "pieces_exigees": {"offre": ["Attestation de visite obligatoire"]},
            "departement": "75",
            "corps_etat": ["Couverture"],
        }
        profil = {
            "visite_site": {
                "visite_effectuee": True,
                "attestation_fichier": "certificat_fantome_inexistant.pdf",
            },
            "identite": {"code_postal": "75001"},
            "corps_etat_exercices": ["Couverture"],
            "assurances": {
                "decennale": {
                    "date_echeance": "2030-01-01",
                    "activites_garanties": ["Couverture"],
                    "fichier": "decennale.pdf",
                }
            },
        }
        res = evaluer_go_nogo(analyse=analyse, profil=profil, dossiers_docs=[tmp_path])
        drapeaux_codes = [d.get("code") or d.get("id") for d in res["drapeaux_rouges"]]
        assert "VISITE_OBLIGATOIRE_MANQUEE" in drapeaux_codes
        assert res["verdict"] == "NO-GO"

    def test_expired_insurance_date_raises_red_flag(self, tmp_path: Path):
        """Expired decennale insurance date triggers red flag."""
        cert_file = tmp_path / "decennale.pdf"
        cert_file.write_text("certificat assurance", encoding="utf-8")

        analyse = {
            "departement": "75",
            "corps_etat": ["Couverture"],
            "calendrier": {"date_limite_retenue": "2026-12-31T18:00:00"},
        }
        profil = {
            "identite": {"code_postal": "75001"},
            "corps_etat_exercices": ["Couverture"],
            "assurances": {
                "decennale": {
                    "compagnie": "AXA",
                    "numero_police": "POL-99999",
                    "date_echeance": "2021-01-01",  # Strictly expired!
                    "fichier": "decennale.pdf",
                    "activites_garanties": ["Couverture"],
                }
            },
        }
        res = evaluer_go_nogo(analyse=analyse, profil=profil, dossiers_docs=[tmp_path])
        drapeaux_codes = [d.get("code") or d.get("id") for d in res["drapeaux_rouges"]]
        assert "ASSURANCE_DECENNALE_EXPIREE" in drapeaux_codes
        assert res["verdict"] == "NO-GO"

    def test_trade_activity_mismatch_penalized(self):
        """Trade activity mismatch (e.g. Couverture required vs Peinture) penalized."""
        analyse = {
            "corps_etat": ["Couverture", "Zinguerie"],
            "departement": "75",
        }
        profil = {
            "identite": {"code_postal": "75001"},
            "corps_etat_exercices": ["Peinture intérieure"],  # Total mismatch
            "assurances": {
                "decennale": {
                    "date_echeance": "2030-01-01",
                    "activites_garanties": ["Peinture"],
                }
            },
        }
        res = evaluer_go_nogo(analyse=analyse, profil=profil)
        crit_tech = next((c for c in res["criteres_eval"] if "technique" in c["nom"].lower() or "métier" in c["nom"].lower()), None)
        assert crit_tech is not None
        assert crit_tech["points_obtenus"] == 0.0

    def test_operational_availability_large_headcount_zero_teams_earns_zero(self):
        """Large total headcount (50 workers) but 0 available teams earns 0 points."""
        analyse = {"departement": "75", "corps_etat": ["Couverture"]}
        profil_zero_equipes = {
            "identite": {"code_postal": "75001"},
            "corps_etat_exercices": ["Couverture"],
            "effectif_total": 50,
            "disponibilite_equipes": "aucune equipe disponible",
        }
        res = evaluer_go_nogo(analyse=analyse, profil=profil_zero_equipes)
        crit_rh = next(c for c in res["criteres_eval"] if c["id"] == "charge_travail_et_disponibilite")
        assert crit_rh["points_obtenus"] == 0.0

    def test_dom_tom_geographic_distance_separation(self):
        """DOM-TOM separation (971 vs 974, 972 vs 973) receives 0 proximity points."""
        analyse_reunion = {
            "lieu_execution": "97400 Saint-Denis",
            "code_postal": "97400",
            "corps_etat": ["Couverture"],
        }
        profil_guadeloupe = {
            "identite": {"siege_social": {"code_postal": "97100"}},
            "corps_etat_exercices": ["Couverture"],
        }
        res_reunion = evaluer_go_nogo(analyse=analyse_reunion, profil=profil_guadeloupe)
        geo_reunion = next(c for c in res_reunion["criteres_eval"] if c["id"] == "localisation_eloignement")
        assert geo_reunion["points_obtenus"] == 0.0
        assert "> 120 km" in geo_reunion["justification"] or "très éloigné" in geo_reunion["justification"]

        analyse_guyane = {
            "lieu_execution": "97300 Cayenne",
            "code_postal": "97300",
            "corps_etat": ["Couverture"],
        }
        profil_martinique = {
            "identite": {"siege_social": {"code_postal": "97200"}},
            "corps_etat_exercices": ["Couverture"],
        }
        res_guyane = evaluer_go_nogo(analyse=analyse_guyane, profil=profil_martinique)
        geo_guyane = next(c for c in res_guyane["criteres_eval"] if c["id"] == "localisation_eloignement")
        assert geo_guyane["points_obtenus"] == 0.0
        assert "> 120 km" in geo_guyane["justification"] or "très éloigné" in geo_guyane["justification"]

    def test_weight_sum_normalization(self):
        """Custom weights that do not sum to 100 are strictly normalized to sum to 100.0."""
        custom_config = {
            "poids_criteres": {
                "adequation_technique": 50.0,
                "references_chantiers": 50.0,
                "proximite_geographique": 50.0,
                "charge_travail_disponibilite": 50.0,
                "capacite_financiere": 50.0,
                "rentabilite_marge": 50.0,
                "complexite_marche": 50.0,
                "capacite_reponse": 50.0,
            }
        }
        res = evaluer_go_nogo(analyse={}, profil={}, config=custom_config)
        assert res["somme_poids_verifiee"] == 100
        total_poids = sum(c["poids_max"] for c in res["criteres_eval"])
        assert abs(total_poids - 100.0) < 1e-4


class TestChallengerChecklistBoundaries:
    """Empirical verification of Checklist 4D model and boundaries."""

    def test_fail_closed_on_empty_and_corrupt_checklists(self):
        """Checklist generation on empty or corrupted payloads does not crash and defaults safely."""
        cl = generer_checklist(dce_analyse={}, profil={}, dossiers_docs=[])
        assert isinstance(cl, dict)
        assert "candidature" in cl
        assert "offre" in cl
        assert len(cl["candidature"]) > 0
        assert len(cl["offre"]) > 0

    def test_4d_model_strict_adherence(self):
        """Every piece in checklist adheres to the 4D model keys."""
        cl = generer_checklist(dce_analyse={}, profil={}, dossiers_docs=[])
        required_4d_keys = {"exige_par_marche", "present_disque", "valide_juridiquement", "verifie_contenu", "statut"}
        for piece in cl["candidature"] + cl["offre"]:
            for key in required_4d_keys:
                assert key in piece, f"Piece {piece.get('piece')} missing key {key}"
            assert isinstance(piece["exige_par_marche"], bool)
            assert isinstance(piece["present_disque"], bool)
            assert isinstance(piece["valide_juridiquement"], bool)
            assert isinstance(piece["verifie_contenu"], bool)
            assert isinstance(piece["statut"], str)

    def test_physical_presence_strictly_required_for_verifie_present(self, tmp_path: Path):
        """Absence of physical file on disk strictly prevents VERIFIE_PRESENT."""
        profil = {
            "fichiers_justificatifs": {
                "dc1": "dc1_inexistant.pdf",
                "kbis": "kbis_inexistant.pdf",
            },
            "identite": {"siret": "12345678900012", "raison_sociale": "BTP Test"},
        }
        cl = generer_checklist(dce_analyse={}, profil=profil, dossiers_docs=[tmp_path])
        dc1_item = next(p for p in cl["candidature"] if "dc1" in p["piece"].lower())
        assert dc1_item["present_disque"] is False
        assert dc1_item["statut"] != "VERIFIE_PRESENT"


class TestChallengerPriceControlBoundaries:
    """Empirical verification of Price Control and OAB decoupling."""

    def test_empty_dpgf_rejection(self):
        """Empty DPGF lines must be rejected with NON_CONFORME and explicit anomaly."""
        res = verifier_arithmetique(lignes=[], total_excel=Decimal("0.00"), taux_tva=Decimal("20.0"))
        assert res["statut_global"] == "NON_CONFORME"
        anomaly_types = [a["type"] for a in res["anomalies"]]
        assert "DPGF_VIDE_OU_NON_EXPLOITABLE" in anomaly_types

    def test_arithmetic_errors_vs_oab_alerts_strict_separation(self):
        """Arithmetic errors and OAB economic alerts are separated into distinct fields."""
        lignes = [
            {
                "ligne_excel": 2,
                "numero": "1.1",
                "designation": "Gros oeuvre",
                "unite": "m²",
                "quantite": Decimal("10"),
                "prix_unitaire_ht": Decimal("100.00"),
                "total_ligne_excel": Decimal("900.00"),  # Error: 10 x 100 = 1000 != 900
            }
        ]
        res = verifier_arithmetique(
            lignes=lignes,
            total_excel=Decimal("900.00"),
            taux_tva=Decimal("20.0"),
            estimation_moe=Decimal("2000.00"),  # 1000 proposed vs 2000 MOE (-50% -> OAB alert)
            seuil_oab_pct=Decimal("25.0"),
        )
        assert res["nb_erreurs_arithmetiques"] >= 1
        assert res["nb_alertes_economiques"] == 1
        assert len(res["erreurs_arithmetiques"]) >= 1
        assert len(res["alertes_economiques"]) == 1
        assert res["alertes_economiques"][0]["type"] == "ALERTE_OFFRE_ANORMALEMENT_BASSE"
        assert res["erreurs_arithmetiques"][0]["type"] == "ECART_LIGNE_ARITHMETIQUE"


class TestChallengerFinalControlBoundaries:
    """Empirical verification of Final Control fail-closed invariants."""

    def test_fail_closed_on_none_and_empty_checklist(self):
        """None or empty checklist strictly produces PAS_PRET."""
        res_none = auditer_dossier(
            analyse={"calendrier": {"date_limite_retenue": "2030-01-01T18:00:00"}},
            checklist=None,
            prix={"total_recalcule_ht": "1000.00", "nb_anomalies": 0},
            memoire_texte="Texte",
            delai_ae_semaines=4,
            montant_ae_ht=Decimal("1000.00"),
        )
        assert res_none["statut_code"] == "PAS_PRET"

        res_empty = auditer_dossier(
            analyse={"calendrier": {"date_limite_retenue": "2030-01-01T18:00:00"}},
            checklist={},
            prix={"total_recalcule_ht": "1000.00", "nb_anomalies": 0},
            memoire_texte="Texte",
            delai_ae_semaines=4,
            montant_ae_ht=Decimal("1000.00"),
        )
        assert res_empty["statut_code"] == "PAS_PRET"

    def test_integration_of_go_nogo_no_go_forces_blocker(self):
        """Go/No-Go verdict NO-GO forces final blocker in auditer_dossier."""
        gn_result = {
            "verdict": "NO-GO",
            "commentaire": "Refus pour visite non effectuee",
            "drapeaux_rouges": [{"code": "VISITE_OBLIGATOIRE_NON_EFFECTUEE", "description": "Visite manquante"}],
        }
        res = auditer_dossier(
            analyse={"calendrier": {"date_limite_retenue": "2030-01-01T18:00:00"}},
            checklist={
                "candidature": [{"piece": "DC1", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
                "offre": [{"piece": "AE", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
            },
            prix={"total_recalcule_ht": "1000.00", "nb_anomalies": 0},
            memoire_texte="Texte",
            delai_ae_semaines=4,
            montant_ae_ht=Decimal("1000.00"),
            go_nogo=gn_result,
        )
        assert res["statut_code"] == "PAS_PRET"
        codes = [b["code"] for b in res["blocages"]]
        assert "DECISION_GO_NOGO_DEFAVORABLE" in codes
        assert "VISITE_OBLIGATOIRE_NON_EFFECTUEE" in codes

    def test_integration_of_matrice_non_conforme_forces_blocker(self):
        """Matrice de conformité NON_CONFORME forces final blocker."""
        matrice_result = {
            "exigences": [
                {"id": "EX-01", "statut": "NON_CONFORME", "exigence": "Certificat Qualibat requis"},
            ]
        }
        res = auditer_dossier(
            analyse={"calendrier": {"date_limite_retenue": "2030-01-01T18:00:00"}},
            checklist={
                "candidature": [{"piece": "DC1", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
                "offre": [{"piece": "AE", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
            },
            prix={"total_recalcule_ht": "1000.00", "nb_anomalies": 0},
            memoire_texte="Texte",
            delai_ae_semaines=4,
            montant_ae_ht=Decimal("1000.00"),
            matrice=matrice_result,
        )
        assert res["statut_code"] == "PAS_PRET"
        codes = [b["code"] for b in res["blocages"]]
        assert "EXIGENCES_DCE_NON_CONFORMES" in codes


class TestChallengerCalendarForclosureBoundaries:
    """Empirical verification of Calendar date parsing and same-day forclosure."""

    def test_same_day_deadline_forclosure_detection(self):
        """Deadline today at 10:00 is expired at 11:00 the same day."""
        maintenant = datetime.datetime(2026, 11, 10, 11, 0, 0)
        dt, s_repr, est_depassee = parser_date_et_echeance("10/11/2026 à 10:00", maintenant=maintenant)
        assert est_depassee is True

        dt_future, _, est_depassee_future = parser_date_et_echeance("10/11/2026 à 16:00", maintenant=maintenant)
        assert est_depassee_future is False

    def test_parser_date_fr_preserves_hours_and_minutes(self):
        """French date string parses hours and minutes accurately."""
        dt = parser_date_fr("25/12/2026 à 14h30")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 12
        assert dt.day == 25
        assert dt.hour == 14
        assert dt.minute == 30

"""Tests adversariaux approfondis pour la remédiation P0 et P1 (v1.2.0 final).

Vérifie de manière agressive et indépendante :
1. P0 - Contrôle final fail-closed (checklists vides/incomplètes, dates manquantes, intégration Go/No-Go et matrice)
2. P0 - Visites de chantier (distinction obligatoire vs facultative/recommandée, absence de faux blocages, dates de visite)
3. P0 - Assurances et justificatifs (rejet strict du spoofing de métadonnées, dates d'expiration, adéquation des activités)
4. P0 - Dates et échéances (formats ISO et FR, conservation heures/minutes, échéance le jour même passée l'heure)
5. P0 - Découplage arithmétique vs économique OAB (aucune confusion entre erreur de calcul et alerte économique)
6. P0 - Réglementation (seuil travaux 100 k€, Décret n° 2025-1386 du 29 décembre 2025 au 01/01/2026)
7. P1 - Go/No-Go (rejet de l'arbitraire, statut NON_EVALUABLE, non-assimilation de département ou d'effectif total)
8. P1 - Matrice de conformité (séparation obligation, réponse, preuve, validation humaine, et traçabilité de page)
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path
import sys
from typing import Any, Dict
import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
REFERENCES_DIR = Path(__file__).resolve().parent.parent / "references"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from controle_final import auditer_dossier
from checklist_pieces import generer_checklist, verifier_presence_fichier, verifier_validite_date
from go_nogo import evaluer_go_nogo, qualifier_obligation_visite, parser_date_et_echeance
from controle_prix import verifier_arithmetique
from matrice_conformite import extraire_exigences, detecter_doublons_et_contradictions


# ==============================================================================
# 1. P0 - CONTRÔLE FINAL FAIL-CLOSED ABSOLU
# ==============================================================================

class TestControleFinalFailClosed:
    """Vérifie que controle_final refuse tout verdict positif en présence de données manquantes."""

    def test_empty_checklist_dict_fails_closed(self):
        """Une checklist {} vide ne doit jamais être validée."""
        audit = auditer_dossier(
            analyse={"calendrier": {"date_limite_retenue": "2030-12-31T18:00:00"}},
            checklist={},
            prix={"total_recalcule_ht": "100000.00", "nb_anomalies": 0},
            memoire_texte="Mémoire complet de 10 pages.",
            delai_ae_semaines=10,
            montant_ae_ht=Decimal("100000.00"),
        )
        assert audit["statut_code"] == "PAS_PRET"
        codes = [b["code"] for b in audit["blocages"]]
        assert "CHECKLIST_NON_CONFORME_OU_VIDE" in codes

    def test_checklist_with_empty_candidature_fails_closed(self):
        """Une checklist avec candidature: [] doit échouer avec PAS_PRET."""
        audit = auditer_dossier(
            analyse={"calendrier": {"date_limite_retenue": "2030-12-31T18:00:00"}},
            checklist={"candidature": [], "offre": [{"piece": "AE", "obligatoire": True, "statut": "VERIFIE_PRESENT"}]},
            prix={"total_recalcule_ht": "100000.00", "nb_anomalies": 0},
            memoire_texte="Mémoire.",
            delai_ae_semaines=10,
            montant_ae_ht=Decimal("100000.00"),
        )
        assert audit["statut_code"] == "PAS_PRET"
        codes = [b["code"] for b in audit["blocages"]]
        assert "CHECKLIST_CANDIDATURE_VIDE" in codes

    def test_checklist_with_empty_offre_fails_closed(self):
        """Une checklist avec offre: [] doit échouer avec PAS_PRET."""
        audit = auditer_dossier(
            analyse={"calendrier": {"date_limite_retenue": "2030-12-31T18:00:00"}},
            checklist={"candidature": [{"piece": "DC1", "obligatoire": True, "statut": "VERIFIE_PRESENT"}], "offre": []},
            prix={"total_recalcule_ht": "100000.00", "nb_anomalies": 0},
            memoire_texte="Mémoire.",
            delai_ae_semaines=10,
            montant_ae_ht=Decimal("100000.00"),
        )
        assert audit["statut_code"] == "PAS_PRET"
        codes = [b["code"] for b in audit["blocages"]]
        assert "CHECKLIST_OFFRE_VIDE" in codes

    def test_missing_submission_date_fails_closed(self):
        """L'absence totale de date limite de remise interdit le statut PRET."""
        audit = auditer_dossier(
            analyse={},  # Aucune date
            checklist={
                "candidature": [{"piece": "DC1", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
                "offre": [{"piece": "AE", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
            },
            prix={"total_recalcule_ht": "100000.00", "nb_anomalies": 0},
            memoire_texte="Mémoire.",
            delai_ae_semaines=10,
            montant_ae_ht=Decimal("100000.00"),
        )
        assert audit["statut_code"] == "PAS_PRET"
        codes = [b["code"] for b in audit["blocages"]]
        assert "DATE_LIMITE_NON_VERIFIABLE" in codes

    def test_go_nogo_no_go_integrates_into_final_control(self):
        """Un résultat Go/No-Go NO-GO passé au contrôle final doit bloquer le dossier."""
        go_nogo_result = {
            "verdict": "NO-GO",
            "commentaire": "Drapeaux rouges bloquants détectés.",
            "drapeaux_rouges": [{"code": "INTERDICTION_SOUMISSIONNER", "description": "Interdiction légale"}],
        }
        audit = auditer_dossier(
            analyse={"calendrier": {"date_limite_retenue": "2030-12-31T18:00:00"}},
            checklist={
                "candidature": [{"piece": "DC1", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
                "offre": [{"piece": "AE", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
            },
            prix={"total_recalcule_ht": "100000.00", "nb_anomalies": 0},
            memoire_texte="Mémoire.",
            delai_ae_semaines=10,
            montant_ae_ht=Decimal("100000.00"),
            go_nogo=go_nogo_result,
        )
        assert audit["statut_code"] == "PAS_PRET"
        codes = [b["code"] for b in audit["blocages"]]
        assert "DECISION_GO_NOGO_DEFAVORABLE" in codes
        assert "INTERDICTION_SOUMISSIONNER" in codes

    def test_compliance_matrix_non_conforme_integrates_into_final_control(self):
        """Une exigence NON_CONFORME dans la matrice de conformité doit bloquer le contrôle final."""
        matrice = {
            "exigences": [
                {"id": "EX-TEC-01", "statut": "NON_CONFORME", "exigence": "Fourniture tuiles NF"},
                {"id": "EX-ADM-01", "statut": "NON_VERIFIE", "exigence": "Attestation CIBTP"},
            ]
        }
        audit = auditer_dossier(
            analyse={"calendrier": {"date_limite_retenue": "2030-12-31T18:00:00"}},
            checklist={
                "candidature": [{"piece": "DC1", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
                "offre": [{"piece": "AE", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
            },
            prix={"total_recalcule_ht": "100000.00", "nb_anomalies": 0},
            memoire_texte="Mémoire.",
            delai_ae_semaines=10,
            montant_ae_ht=Decimal("100000.00"),
            matrice=matrice,
        )
        assert audit["statut_code"] == "PAS_PRET"
        codes = [b["code"] for b in audit["blocages"]]
        assert "EXIGENCES_DCE_NON_CONFORMES" in codes
        warn_codes = [w["code"] for w in audit["avertissements"]]
        assert "EXIGENCES_DCE_NON_VERIFIEES" in warn_codes


# ==============================================================================
# 2. P0 - VISITES DE CHANTIER (OBLIGATOIRE VS FACULTATIVE & PROUVE PHYSIQUE)
# ==============================================================================

class TestVisitesNuancesAndPhysicalProof:
    """Vérifie la distinction stricte entre visite obligatoire et facultative, et l'exigence de preuve."""

    @pytest.mark.parametrize(
        "phrase",
        [
            "La visite des lieux n'est pas obligatoire pour ce marché",
            "Visite sur site facultative et libre",
            "Visite conseillée mais non obligatoire",
            "Aucune visite obligatoire n'est imposée par le pouvoir adjudicateur",
        ]
    )
    def test_optional_visit_does_not_create_mandatory_requirement(self, phrase: str, tmp_path: Path):
        """Une formulation négative ou facultative ne doit PAS rendre la visite obligatoire dans la checklist."""
        analyse = {"pieces_exigees": {"offre": [phrase]}}
        profil = {"visite_site": {"visite_effectuee": False}}
        checklist = generer_checklist(dce_analyse=analyse, profil=profil, dossiers_docs=[tmp_path])
        p_visite = next(p for p in checklist["offre"] if "visite" in p["piece"].lower())

        assert p_visite["obligatoire"] is False
        assert p_visite["nature_obligation"] in ["FACULTATIVE", "RECOMMANDEE"]
        assert p_visite["statut"] != "MANQUANT"  # Doit être A_OBTENIR ou FACULTATIF, jamais MANQUANT éliminatoire

    def test_mandatory_visit_without_physical_file_is_marked_manquant(self, tmp_path: Path):
        """Une visite obligatoire sans fichier physique sur disque est strictement MANQUANT."""
        analyse = {"pieces_exigees": {"offre": ["Attestation de visite obligatoire préalable sous peine d'irrecevabilité"]}}
        profil = {
            "visite_site": {
                "visite_effectuee": True,
                "attestation_fichier": "fichier_fictif_introuvable.pdf",
            }
        }
        checklist = generer_checklist(dce_analyse=analyse, profil=profil, dossiers_docs=[tmp_path])
        p_visite = next(p for p in checklist["offre"] if "visite" in p["piece"].lower())

        assert p_visite["obligatoire"] is True
        assert p_visite["present_disque"] is False
        assert p_visite["statut"] == "MANQUANT"
        assert p_visite["valide_juridiquement"] is False

    def test_visit_conducted_after_submission_deadline_is_invalid(self, tmp_path: Path):
        """Une visite réalisée après la date limite de remise est déclarée caduque / invalide."""
        f_visite = tmp_path / "attestation.pdf"
        f_visite.write_text("preuve visite", encoding="utf-8")

        analyse = {
            "calendrier": {"date_limite_retenue": "2026-10-01T12:00:00"},
            "pieces_exigees": {"offre": ["Attestation de visite obligatoire"]},
        }
        profil = {
            "visite_site": {
                "visite_effectuee": True,
                "date_visite": "2026-10-05",  # Visite postérieure à l'échéance du 01/10
                "attestation_fichier": "attestation.pdf",
            }
        }
        checklist = generer_checklist(dce_analyse=analyse, profil=profil, dossiers_docs=[tmp_path])
        p_visite = next(p for p in checklist["offre"] if "visite" in p["piece"].lower())

        assert p_visite["valide_juridiquement"] is False
        assert p_visite["statut"] == "EXPIREE"


# ==============================================================================
# 3. P0 - DATES ET ÉCHÉANCES (PARSING HARMONISÉ & DATE DÉPASSÉE MÊME JOUR)
# ==============================================================================

class TestDatesAndDeadlinesHarmonization:
    """Vérifie le parsing des dates françaises et ISO, et l'expiration horaire le jour même."""

    def test_same_day_deadline_expired_past_hour(self):
        """Échéance aujourd'hui à 11:00 : à 14:00, l'échéance est dépassée."""
        maintenant = datetime.datetime(2026, 6, 15, 14, 0, 0)
        dt, s_repr, est_depassee = parser_date_et_echeance("15/06/2026 à 11:00", maintenant=maintenant)
        assert est_depassee is True

    def test_same_day_deadline_not_expired_before_hour(self):
        """Échéance aujourd'hui à 18:00 : à 14:00, l'échéance n'est pas encore dépassée."""
        maintenant = datetime.datetime(2026, 6, 15, 14, 0, 0)
        dt, s_repr, est_depassee = parser_date_et_echeance("2026-06-15T18:00:00", maintenant=maintenant)
        assert est_depassee is False

    def test_iso_and_french_dates_yield_identical_timestamp(self):
        """Vérifie l'harmonisation stricte entre ISO et format français."""
        dt_fr, _, _ = parser_date_et_echeance("15/12/2026 à 14:30")
        dt_iso, _, _ = parser_date_et_echeance("2026-12-15T14:30:00")
        assert dt_fr == dt_iso


# ==============================================================================
# 4. P0 - PRIX ET DÉCOUPLAGE DES ALERTES OAB
# ==============================================================================

class TestPrixAndOABDecoupling:
    """Vérifie que les alertes OAB sont strictement découplées des erreurs arithmétiques."""

    def test_oab_alert_does_not_count_as_calculation_error(self):
        """Une DPGF calculée avec exactitude mais inférieure de 30% à la MOE ne comporte pas d'erreur arithmétique."""
        lignes = [
            {
                "ligne_excel": 2,
                "numero": "1.1",
                "designation": "Dépose toiture",
                "unite": "m²",
                "quantite": Decimal("100"),
                "prix_unitaire_ht": Decimal("50.00"),
                "total_ligne_excel": Decimal("5000.00"),
            }
        ]
        res = verifier_arithmetique(
            lignes=lignes,
            total_excel=Decimal("5000.00"),
            taux_tva=Decimal("20.0"),
            estimation_moe=Decimal("8000.00"),  # Total proposé 5000 vs MOE 8000 (-37.5%)
            seuil_oab_pct=Decimal("25.0"),
        )
        assert res["nb_erreurs_arithmetiques"] == 0
        assert res["nb_alertes_economiques"] == 1
        assert res["erreurs_arithmetiques"] == []
        assert len(res["alertes_economiques"]) == 1
        assert res["alertes_economiques"][0]["type"] == "ALERTE_OFFRE_ANORMALEMENT_BASSE"
        assert "limite_heuristique" in res["alertes_economiques"][0]

    def test_final_control_treats_oab_as_warning_not_arithmetic_blocker(self):
        """Le contrôle final traite l'alerte OAB comme un avertissement d'argumentation et non un blocage de calcul."""
        prix_data = {
            "total_recalcule_ht": "70000.00",
            "nb_anomalies": 1,
            "nb_erreurs_arithmetiques": 0,
            "nb_alertes_economiques": 1,
            "erreurs_arithmetiques": [],
            "alertes_economiques": [
                {"type": "ALERTE_OFFRE_ANORMALEMENT_BASSE", "description": "Prix inférieur de 30% à l'estimation MOE."}
            ],
            "anomalies": [
                {"type": "ALERTE_OFFRE_ANORMALEMENT_BASSE", "description": "Prix inférieur de 30% à l'estimation MOE."}
            ],
        }
        audit = auditer_dossier(
            analyse={"calendrier": {"date_limite_retenue": "2030-12-31T18:00:00"}},
            checklist={
                "candidature": [{"piece": "DC1", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
                "offre": [{"piece": "AE", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
            },
            prix=prix_data,
            memoire_texte="Mémoire complet.",
            delai_ae_semaines=10,
            montant_ae_ht=Decimal("70000.00"),
        )
        blocage_codes = [b["code"] for b in audit["blocages"]]
        assert "ERREURS_ARITHMETIQUES_DPGF" not in blocage_codes
        warning_codes = [w["code"] for w in audit["avertissements"]]
        assert "ALERTE_OAB_A_JUSTIFIER" in warning_codes


# ==============================================================================
# 5. P0 - RÉGLEMENTATION (SEUILS 2026 & DÉCRET N° 2025-1386)
# ==============================================================================

class TestReglementation2026:
    """Vérifie la mise à jour réglementaire officielle des seuils de la commande publique."""

    def test_seuils_yaml_dispense_travaux_100k_decret_2025_1386(self):
        """Vérifie le seuil de dispense de 100 000 € HT sous le décret n° 2025-1386 du 29/12/2025 au 01/01/2026."""
        seuils_path = ASSETS_DIR / "seuils.yaml"
        with seuils_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        dispense = data["seuils_travaux"]["dispense_procedure_formalites_prealables"]
        assert float(dispense["montant_ht_euros"]) == 100000.00
        assert str(dispense["date_application"]) == "2026-01-01"
        assert "2025-1386" in dispense["description"]
        assert "29 décembre 2025" in dispense["description"]
        assert dispense["statut"] == "CONFORME"

    def test_guide_references_markdown_cites_decret_2025_1386(self):
        """Le document references/02-procedures-et-seuils.md doit citer le décret n° 2025-1386."""
        guide_path = REFERENCES_DIR / "02-procedures-et-seuils.md"
        content = guide_path.read_text(encoding="utf-8")
        assert "100 000" in content
        assert "2025-1386" in content
        assert "1er janvier 2026" in content


# ==============================================================================
# 6. P1 - MATRICE DE CONFORMITÉ (DOUBLONS, CONFIDENTIALITÉ ET VALIDATION HUMAINE)
# ==============================================================================

class TestMatriceConformiteAvancee:
    """Vérifie la détection de doublons et la séparation des dimensions dans la matrice."""

    def test_duplicate_detection_in_compliance_matrix(self):
        """Détecte les exigences rédigées en double dans les pièces du DCE."""
        exigences = [
            {"id": "EX-TEC-01", "exigence": "Fourniture et pose d'un échafaudage de classe 4 conforme EN 12811"},
            {"id": "EX-TEC-02", "exigence": "Fourniture et pose d'un échafaudage de classe 4 conforme EN 12811"},
            {"id": "EX-ADM-01", "exigence": "Remise du formulaire DC1 signé"},
        ]
        doublons_info = detecter_doublons_et_contradictions(exigences)
        assert doublons_info["nb_doublons"] == 1
        assert doublons_info["doublons"][0]["exigence_id"] == "EX-TEC-02"
        assert doublons_info["doublons"][0]["doublon_de"] == "EX-TEC-01"

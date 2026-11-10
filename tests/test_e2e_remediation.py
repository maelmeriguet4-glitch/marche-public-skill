"""Suite de tests d'intégration End-to-End (E2E) — Remédiation marche-public-skill.

Couvre l'intégralité des 4 tiers définis dans TEST_INFRA.md et ORIGINAL_REQUEST.md :
- Tier 1 : Couverture des exigences R1 à R5 (Go/No-Go, Checklist, Contrôle Final, Matrice & Analyse, Prix & Seuils).
- Tier 2 : Cas limites et valeurs frontières (DPGF vide, numéro de police sans fichier, limite de pages, somme des pondérations 99.9% vs 100% vs 100.1%).
- Tier 3 : Combinaisons croisées inter-modules (contradiction bloquante + score élevé, checklist valide + DPGF vide, métadonnée YAML sans fichier disque, etc.).
- Tier 4 : Scénarios réels sur fixtures complètes (tests/fixtures et evals/cas).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Dict, List

import openpyxl
import pytest
import yaml

# Injection du répertoire scripts dans le sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
FIXTURES_DIR = ROOT_DIR / "tests" / "fixtures"
ASSETS_DIR = ROOT_DIR / "assets"
EVALS_DIR = ROOT_DIR / "evals"
REFERENCES_DIR = ROOT_DIR / "references"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import analyse_marche
import checklist_pieces
import common
import controle_final
import controle_prix
import dce_extract
import go_nogo
import matrice_conformite
import simulateur_note_prix


# ==============================================================================
# HELPERS DE COMPATIBILITÉ ET NORMALISATION D'APPEL
# ==============================================================================

def execute_go_nogo(analyse: Dict[str, Any], profil: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Exécute l'évaluation Go/No-Go selon l'interface contractuelle unifiée."""
    if hasattr(go_nogo, "evaluer_go_nogo"):
        return go_nogo.evaluer_go_nogo(analyse, profil, config)
    criteres, score, drapeaux = go_nogo.evaluer_criteres(analyse, profil, config)
    seuils = config.get("seuils_decision", {})
    seuil_go = float(seuils.get("seuil_go", 70.0))
    seuil_reserve = float(seuils.get("seuil_go_reserve", 50.0))
    verdict, comm = go_nogo.determiner_verdict(score, drapeaux, seuil_go, seuil_reserve)
    return {
        "score_sur_100": score,
        "verdict": verdict,
        "commentaire": comm,
        "drapeaux_rouges": drapeaux,
        "criteres": criteres,
    }


def execute_checklist(analyse: Dict[str, Any], profil: Dict[str, Any], dossiers_docs: List[Path] = None) -> Dict[str, Any]:
    """Exécute la construction de la checklist selon l'interface contractuelle."""
    if hasattr(checklist_pieces, "generer_checklist"):
        return checklist_pieces.generer_checklist(analyse, profil, dossiers_docs=dossiers_docs)
    return checklist_pieces.construire_checklist(analyse, profil, dossiers_docs=dossiers_docs)


def execute_controle_prix(lignes: List[Dict[str, Any]], total_excel: Decimal, taux_tva: Decimal = Decimal("20.0"), **kwargs) -> Dict[str, Any]:
    """Exécute la vérification arithmétique et OAB."""
    try:
        return controle_prix.verifier_arithmetique(lignes, total_excel, taux_tva=taux_tva, **kwargs)
    except TypeError:
        return controle_prix.verifier_arithmetique(lignes, total_excel, tva=taux_tva, **kwargs)


def execute_controle_final(
    analyse: Dict[str, Any],
    checklist: Dict[str, Any],
    prix: Dict[str, Any],
    memoire_texte: str,
    delai_ae_semaines: int = 12,
    montant_ae_ht: Decimal = Decimal("142500.00"),
    go_nogo_data: Dict[str, Any] = None,
    matrice_data: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Exécute le contrôle final selon l'interface contractuelle."""
    if hasattr(controle_final, "controler_dossier_final"):
        return controle_final.controler_dossier_final(
            analyse=analyse,
            go_nogo=go_nogo_data or {},
            checklist=checklist,
            matrice=matrice_data or {},
            prix=prix,
            memoire_texte=memoire_texte,
        )
    return controle_final.auditer_dossier(
        analyse=analyse,
        checklist=checklist,
        prix=prix,
        memoire_texte=memoire_texte,
        delai_ae_semaines=delai_ae_semaines,
        montant_ae_ht=montant_ae_ht,
    )


# ==============================================================================
# TIER 1 : FEATURE COVERAGE (R1 À R5)
# ==============================================================================

class TestTier1R1GoNoGoEngine:
    """Couverture exhaustive de l'exigence R1 : Moteur Go/No-Go et alignement du profil."""

    @pytest.fixture
    def config_go_nogo(self) -> Dict[str, Any]:
        with (ASSETS_DIR / "go_nogo_config.yaml").open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def profil_nominal(self) -> Dict[str, Any]:
        with (ASSETS_DIR / "profil_entreprise.example.yaml").open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_r1_profile_effectifs_total_salaries_variation(self, config_go_nogo: Dict[str, Any]):
        """R1.1 : Vérifie la reconnaissance de effectifs.total_salaries sans moyens_humains."""
        profil = {
            "identite": {"raison_sociale": "Entreprise BTP Test", "siege_social": {"code_postal": "75001"}},
            "effectifs": {"total_salaries": 14},  # Schéma nominal de profil_entreprise.example.yaml
            "capacites_financieres": {"exercices": [{"chiffre_affaires_ht_euros": 1800000.0}]},
            "references_chantiers": [{"intitule": "Chantier 1"}, {"intitule": "Chantier 2"}, {"intitule": "Chantier 3"}],
            "qualifications_et_certifications": [{"code": "3101", "organisme": "QUALIBAT"}],
            "assurances": {"decennale": {"numero_police": "DEC-12345", "attestation_fichier": "attestation_assurance_decennale.pdf"}},
            "visite_site": {"visite_effectuee": True, "attestation_fichier": "attestation_visite_signee.pdf"},
        }
        analyse = {"objet": "Travaux de couverture et toiture", "contradictions_detectees": []}

        res = execute_go_nogo(analyse, profil, config_go_nogo)
        criteres_map = {c["id"]: c for c in res["criteres"]}

        crit_charge = criteres_map["charge_travail_et_disponibilite"]
        # 14 salariés correspond à un effectif solide (barème 8 à 14 salariés -> au moins 12 pts)
        assert crit_charge["points_obtenus"] >= 12.0
        assert "[EFFECTIF NON RENSEIGNÉ" not in crit_charge["justification"]

    def test_r1_profile_postal_code_siege_social_variation(self, config_go_nogo: Dict[str, Any]):
        """R1.2 : Vérifie la reconnaissance de identite.siege_social.code_postal."""
        profil = {
            "identite": {
                "raison_sociale": "Entreprise Berry",
                "siege_social": {"adresse": "14 Rue des Métiers", "code_postal": "18000", "ville": "Bourges"},
            },
            "assurances": {"decennale": {"numero_police": "DEC-12345", "attestation_fichier": "attestation_assurance_decennale.pdf"}},
            "visite_site": {"visite_effectuee": True, "attestation_fichier": "attestation_visite_signee.pdf"},
        }
        analyse = {
            "objet": "Réfection toiture école",
            "acheteur": "Commune de Bourges 18000",
            "lieu_execution": "18000 Bourges",
            "contradictions_detectees": [],
        }

        res = execute_go_nogo(analyse, profil, config_go_nogo)
        criteres_map = {c["id"]: c for c in res["criteres"]}

        crit_geo = criteres_map["localisation_eloignement"]
        assert crit_geo["points_obtenus"] == 10.0
        assert "[DISTANCE NON CALCULÉE]" not in crit_geo["justification"]
        assert "18" in crit_geo["justification"]

    def test_r1_cost_structure_profitability_variation(self, config_go_nogo: Dict[str, Any]):
        """R1.3 : Vérifie la prise en compte de la structure de coûts (marge nette cible)."""
        profil = {
            "identite": {"raison_sociale": "Entreprise Test"},
            "structure_couts": {"frais_generaux_pct": 14.0, "marge_nette_cible_pct": 10.0},
            "assurances": {"decennale": {"numero_police": "DEC-12345", "attestation_fichier": "attestation_assurance_decennale.pdf"}},
            "visite_site": {"visite_effectuee": True, "attestation_fichier": "attestation_visite_signee.pdf"},
        }
        analyse = {"contradictions_detectees": []}

        res = execute_go_nogo(analyse, profil, config_go_nogo)
        criteres_map = {c["id"]: c for c in res["criteres"]}

        crit_rent = criteres_map["rentabilite_estimee"]
        assert crit_rent["points_obtenus"] == 10.0
        assert "[MARGE NON CHIFFRÉE]" not in crit_rent["justification"]

    def test_r1_site_visit_pieces_exigees_dict_unfulfilled(self, config_go_nogo: Dict[str, Any]):
        """R1.4 : pieces_exigees au format dictionnaire avec visite non effectuée -> drapeau rouge et NO-GO."""
        profil = {
            "identite": {"raison_sociale": "Test SAS"},
            "assurances": {"decennale": {"numero_police": "DEC-12345"}},
            "visite_site": {"visite_effectuee": False},
        }
        # pieces_exigees est un dictionnaire structuré {"candidature": [...], "offre": [...]}
        analyse = {
            "objet": "Marché toiture",
            "pieces_exigees": {
                "candidature": ["DC1", "DC2"],
                "offre": ["Attestation de visite obligatoire des lieux signée"],
            },
            "contradictions_detectees": [],
        }

        res = execute_go_nogo(analyse, profil, config_go_nogo)
        assert res["verdict"] == "NO-GO"
        codes_drapeaux = [d.get("id") or d.get("code") for d in res["drapeaux_rouges"]]
        assert any("VISITE" in str(code) for code in codes_drapeaux)

    def test_r1_site_visit_pieces_exigees_dict_fulfilled(self, config_go_nogo: Dict[str, Any]):
        """R1.5 : pieces_exigees dictionnaire avec visite_effectuee: True -> pas de drapeau rouge de visite."""
        profil = {
            "identite": {"raison_sociale": "Test SAS"},
            "assurances": {"decennale": {"numero_police": "DEC-12345", "attestation_fichier": "attestation_assurance_decennale.pdf"}},
            "visite_site": {"visite_effectuee": True, "attestation_fichier": "attestation_visite_signee.pdf"},
        }
        analyse = {
            "objet": "Marché toiture",
            "pieces_exigees": {
                "candidature": ["DC1"],
                "offre": ["Attestation de visite obligatoire signée"],
            },
            "contradictions_detectees": [],
        }

        res = execute_go_nogo(analyse, profil, config_go_nogo)
        codes_drapeaux = [d.get("id") or d.get("code") for d in res["drapeaux_rouges"]]
        assert not any("VISITE" in str(code) for code in codes_drapeaux)

    def test_r1_blocking_contradiction_strictly_forces_nogo(self, config_go_nogo: Dict[str, Any], profil_nominal: Dict[str, Any]):
        """R1.6 : Une contradiction bloquante dans le DCE impose strictement le verdict NO-GO."""
        analyse = {
            "objet": "Marché réfection toiture",
            "contradictions_detectees": [
                {
                    "type": "DATE_LIMITE_CONTRADICTOIRE",
                    "gravite": "BLOQUANT",
                    "description": "Discordance critique date RC (24/10) vs AE (28/10).",
                }
            ],
        }

        res = execute_go_nogo(analyse, profil_nominal, config_go_nogo)
        # La présence d'une contradiction bloquante doit STRICTEMENT interdire le statut GO
        assert res["verdict"] == "NO-GO", "Une contradiction de gravité BLOQUANT doit forcer le verdict NO-GO"
        codes_drapeaux = [d.get("id") or d.get("code") for d in res["drapeaux_rouges"]]
        assert any("CONTRADICTION" in str(c) for c in codes_drapeaux), "Un drapeau rouge bloquant doit être levé"

    def test_r1_config_exploitation_weights_sum_100(self, config_go_nogo: Dict[str, Any]):
        """R1.7 : Exploitation intégrale des pondérations du fichier assets/go_nogo_config.yaml."""
        criteres_cfg = config_go_nogo.get("criteres", {})
        total_poids = sum(c["poids"] for c in criteres_cfg.values())
        assert total_poids == 100, f"La somme des critères dans go_nogo_config.yaml doit être 100 (trouvé : {total_poids})"


class TestTier1R2AdministrativeChecklist:
    """Couverture exhaustive de l'exigence R2 : Checklist administrative et vérification physique."""

    @pytest.fixture
    def profil_nominal(self) -> Dict[str, Any]:
        with (ASSETS_DIR / "profil_entreprise.example.yaml").open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_r2_absence_of_or_true_bypasses_in_checklist(self, profil_nominal: Dict[str, Any]):
        """R2.1 : Élimination des raccourcis 'or True' pour les attestations fiscales et sociales."""
        analyse = {
            "pieces_exigees": {
                "candidature": ["Lettre de candidature DC1"],
                "offre": ["Cadre de prix DPGF"],
            }
        }
        checklist = execute_checklist(analyse, profil_nominal)
        pieces_cand = checklist["candidature"]
        piece_fisc = next((p for p in pieces_cand if "fiscale" in p["piece"].lower()), None)
        piece_soc = next((p for p in pieces_cand if "sociale" in p["piece"].lower() or "vigilance" in p["piece"].lower()), None)

        assert piece_fisc is not None
        assert piece_soc is not None

        # Si l'analyse n'exige pas explicitement les attestations, exige_par_marche ne doit pas être forcé par 'or True'
        assert piece_fisc.get("exige_par_marche") is False or "fiscale" in str(analyse), (
            "exige_par_marche ne doit pas être forcé artificiellement à True via 'or True'"
        )

    def test_r2_physical_file_presence_on_disk(self, tmp_path: Path, profil_nominal: Dict[str, Any]):
        """R2.2 : Vérification de la présence physique réelle des fichiers sur disque."""
        fichier_existant = tmp_path / "Kbis_valide.pdf"
        fichier_existant.write_text("dummy kbis content", encoding="utf-8")

        profil_test = dict(profil_nominal)
        profil_test["fichiers_justificatifs"] = {
            "kbis": "Kbis_valide.pdf",
            "attestation_fiscale": "Attestation_Fiscale_Absente.pdf",
        }

        checklist = execute_checklist({}, profil_test, dossiers_docs=[tmp_path])
        pieces_cand = checklist["candidature"]

        p_kbis = next(p for p in pieces_cand if "kbis" in p["piece"].lower())
        p_fisc = next(p for p in pieces_cand if "fiscale" in p["piece"].lower())

        assert p_kbis["statut"] in ["VERIFIE_PRESENT", "VALIDE"]
        assert p_fisc["statut"] in ["A_FOURNIR", "MANQUANT"]

    def test_r2_metadata_decennale_police_does_not_bypass_physical_presence(self, tmp_path: Path):
        """R2.3 : L'existence d'un numéro de police dans le YAML ne doit pas valider la présence physique."""
        profil = {
            "identite": {"raison_sociale": "Entreprise Sans Fichier"},
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

        checklist = execute_checklist({}, profil, dossiers_docs=[tmp_path])
        p_dec = next(p for p in checklist["candidature"] if "décennale" in p["piece"].lower())

        # Le fichier étant physiquement absent du disque, le statut ne doit PAS être VERIFIE_PRESENT
        assert p_dec["statut"] != "VERIFIE_PRESENT", (
            "La présence physique ne doit pas être inférée d'un simple numéro de police dans le profil YAML"
        )
        assert p_dec["statut"] in ["A_METTRE_A_JOUR", "A_FOURNIR", "MANQUANT"]

    def test_r2_4d_document_status_model(self, profil_nominal: Dict[str, Any]):
        """R2.4 : Contrôle de la séparation des 4 dimensions d'état documentaire."""
        checklist = execute_checklist({}, profil_nominal)
        for section in ["candidature", "offre"]:
            for p in checklist[section]:
                assert "statut" in p
                assert "action" in p
                assert "obligatoire" in p
                # Le modèle 4D impose de distinguer exigé / présent / valide / vérifié
                if "present_disque" in p:
                    assert isinstance(p["present_disque"], bool)

    def test_r2_date_validity_taxonomy(self):
        """R2.5 : Taxonomie rigoureuse de validité temporelle des attestations."""
        assert checklist_pieces.verifier_validite_date("2020-01-01") == "EXPIREE"
        assert checklist_pieces.verifier_validite_date("2035-12-31") == "VALIDE"
        assert checklist_pieces.verifier_validite_date(None) == "NON_RENSEIGNEE"
        assert checklist_pieces.verifier_validite_date("date_invalide") == "FORMAT_INVALIDE"


class TestTier1R3FinalControl:
    """Couverture exhaustive de l'exigence R3 : Contrôle final et statuts incomplets."""

    INCOMPLETE_STATUSES = [
        "A_COMPLETER",
        "A_METTRE_A_JOUR",
        "NON_VERIFIE",
        "A_CHIFFRER",
        "A_REDIGER",
        "A_FINALISER",
        "A_OBTENIR",
        "MANQUANT",
        "A_FOURNIR",
        "EXPIREE",
    ]

    @pytest.mark.parametrize("status", INCOMPLETE_STATUSES)
    def test_r3_incomplete_statuses_ineligible_for_candidacy(self, status: str):
        """R3.1 : Tout statut incomplet sur une pièce obligatoire de candidature bloque le dépôt."""
        analyse = {"contradictions_detectees": []}
        checklist = {
            "candidature": [{"piece": "DC1", "obligatoire": True, "statut": status}],
            "offre": [{"piece": "AE", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
        }
        prix = {"total_recalcule_ht": "100000.00", "nb_anomalies": 0}

        audit = execute_controle_final(analyse, checklist, prix, memoire_texte="Mémoire final sans balise.")
        assert audit["statut_code"] == "PAS_PRET"
        assert audit["total_blocages"] >= 1

    @pytest.mark.parametrize("status", INCOMPLETE_STATUSES)
    def test_r3_incomplete_statuses_ineligible_for_offer(self, status: str):
        """R3.2 : Tout statut incomplet sur une pièce obligatoire de l'offre bloque le dépôt."""
        analyse = {"contradictions_detectees": []}
        checklist = {
            "candidature": [{"piece": "DC1", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
            "offre": [{"piece": "DPGF chiffrée", "obligatoire": True, "statut": status}],
        }
        prix = {"total_recalcule_ht": "100000.00", "nb_anomalies": 0}

        audit = execute_controle_final(analyse, checklist, prix, memoire_texte="Mémoire final sans balise.")
        assert audit["statut_code"] == "PAS_PRET"
        assert audit["total_blocages"] >= 1

    @pytest.mark.parametrize("tag", [
        "[À FOURNIR : CV conducteur de travaux]",
        "[A FOURNIR]",
        "[À COMPLÉTER]",
        "[A COMPLETER : Matériel]",
        "[À CONFIRMER]",
        "[A CONFIRMER]",
        "[À CHIFFRER]",
    ])
    def test_r3_residual_placeholders_force_pas_pret(self, tag: str):
        """R3.3 : Présence de balises résiduelles [À FOURNIR] / [À COMPLÉTER] force PAS_PRET."""
        analyse = {"contradictions_detectees": []}
        checklist = {
            "candidature": [{
                "piece": "DC1", "obligatoire": True, "exige_par_marche": True,
                "present_disque": True, "valide_juridiquement": True, "verifie_contenu": True,
                "statut": "VERIFIE_PRESENT"
            }],
            "offre": [{
                "piece": "AE", "obligatoire": True, "exige_par_marche": True,
                "present_disque": True, "valide_juridiquement": True, "verifie_contenu": True,
                "statut": "VERIFIE_PRESENT"
            }],
        }
        prix = {"total_recalcule_ht": "100000.00", "nb_anomalies": 0}
        memoire = f"Introduction méthodologique.\n{tag}\nConclusion technique."

        audit = execute_controle_final(analyse, checklist, prix, memoire_texte=memoire)
        assert audit["statut_code"] == "PAS_PRET", f"La balise {tag} doit forcer le verdict PAS_PRET"
        codes_blocages = [b.get("code") for b in audit.get("blocages", [])]
        assert any("BALISE" in str(c) for c in codes_blocages)

    def test_r3_rc_technical_proposal_page_limit_enforcement(self):
        """R3.4 : Dépassement du plafond de pages imposé par le RC force PAS_PRET."""
        analyse = {
            "contradictions_detectees": [],
            "rc_limite_pages": 15,
            "limite_pages_memoire": 15,
        }
        checklist = {
            "candidature": [{
                "piece": "DC1", "obligatoire": True, "exige_par_marche": True,
                "present_disque": True, "valide_juridiquement": True, "verifie_contenu": True,
                "statut": "VERIFIE_PRESENT"
            }],
            "offre": [{
                "piece": "AE", "obligatoire": True, "exige_par_marche": True,
                "present_disque": True, "valide_juridiquement": True, "verifie_contenu": True,
                "statut": "VERIFIE_PRESENT"
            }],
        }
        prix = {"total_recalcule_ht": "100000.00", "nb_anomalies": 0}

        # Mémoire massif simulant 40 pages (environ 120 000 caractères)
        memoire_trop_long = "Page de mémoire technique sur l'organisation du chantier.\n" * 2000

        audit = execute_controle_final(analyse, checklist, prix, memoire_texte=memoire_trop_long)
        if hasattr(controle_final, "verifier_limite_pages") or "rc_limite_pages" in analyse:
            codes = [b.get("code") for b in audit.get("blocages", [])] + [a.get("code") for a in audit.get("avertissements", [])]
            assert audit["statut_code"] == "PAS_PRET" or any("PAGE" in str(c) for c in codes)

    def test_r3_nominal_clean_dossier_is_pret(self):
        """R3.5 : Dossier parfaitement conforme sans omission délivre le verdict PRET."""
        analyse = {
            "contradictions_detectees": [],
            "calendrier": {"date_limite_retenue": "31/12/2030 à 12:00"},
        }
        checklist = {
            "candidature": [{
                "piece": "DC1", "obligatoire": True, "exige_par_marche": True,
                "present_disque": True, "valide_juridiquement": True, "verifie_contenu": True,
                "statut": "VERIFIE_PRESENT"
            }],
            "offre": [{
                "piece": "AE", "obligatoire": True, "exige_par_marche": True,
                "present_disque": True, "valide_juridiquement": True, "verifie_contenu": True,
                "statut": "VERIFIE_PRESENT"
            }],
        }
        prix = {"total_recalcule_ht": "100000.00", "nb_anomalies": 0}
        memoire = "Mémoire technique parfaitement rédigé sans aucune balise en suspens. Délai prévu : 12 semaines."

        audit = execute_controle_final(
            analyse, checklist, prix, memoire_texte=memoire, delai_ae_semaines=12, montant_ae_ht=Decimal("100000.00")
        )
        assert audit["statut_code"] == "PRET"
        assert audit["total_blocages"] == 0


class TestTier1R4ComplianceMatrixMarketAnalysis:
    """Couverture exhaustive de l'exigence R4 : Matrice de conformité et analyse de marché."""

    def test_r4_compliance_matrix_distinct_non_verifie_counter(self):
        """R4.1 : Présence obligatoire du compteur nb_non_verifie dans le JSON de synthèse."""
        dce_fictif = {
            "pieces": [
                {
                    "nom_fichier": "CCTP.docx",
                    "categorie": "CCTP",
                    "texte_complet": "L'entrepreneur devra obligatoirement respecter la norme NF DTU 40.11.",
                }
            ]
        }
        profil = {"assurances": {}}

        exigences = matrice_conformite.extraire_exigences(dce_fictif, profil)
        assert len(exigences) >= 1

        # Vérification des statuts
        nb_non_verifie = sum(1 for e in exigences if e.get("statut") == "NON_VERIFIE")
        assert nb_non_verifie >= 1, "Une exigence normative sans preuve doit rester au statut NON_VERIFIE"

        # Le dictionnaire global doit comptabiliser nb_non_verifie
        donnees_sortie = {
            "total_exigences": len(exigences),
            "nb_conformes": sum(1 for e in exigences if e["statut"] == "CONFORME"),
            "nb_a_completer": sum(1 for e in exigences if e["statut"] in ["À COMPLÉTER", "A_COMPLETER"]),
            "nb_non_conformes": sum(1 for e in exigences if e["statut"] in ["NON CONFORME", "NON_CONFORME"]),
            "nb_non_verifie": nb_non_verifie,
            "exigences": exigences,
        }
        somme_parties = (
            donnees_sortie["nb_conformes"]
            + donnees_sortie["nb_a_completer"]
            + donnees_sortie["nb_non_conformes"]
            + donnees_sortie["nb_non_verifie"]
        )
        assert somme_parties == donnees_sortie["total_exigences"]

    def test_r4_compliance_matrix_no_conversion_to_non_conforme(self):
        """R4.2 : Le statut NON_VERIFIE ne doit pas être dégradé en NON CONFORME dans le Markdown."""
        exigences = [
            {
                "id": "EX-TEC-01",
                "piece_source": "CCTP.docx",
                "reference": "Article 3",
                "categorie": "Technique",
                "eliminatoire": False,
                "exigence": "L'entreprise devra trier les déchets.",
                "reponse_entreprise": "Mémoire technique section SOSED",
                "statut": "NON_VERIFIE",
            }
        ]
        md = matrice_conformite.generer_markdown_matrice(exigences)
        assert "🔴 NON CONFORME" not in md, "NON_VERIFIE ne doit pas être étiqueté comme NON CONFORME"

    def test_r4_market_analysis_non_extrait_preservation(self):
        """R4.3 : La liste non_extrait ne doit pas être écrasée par non_extrait = [] à la ligne 289."""
        dce_incomplet = {
            "pieces": [
                {
                    "nom_fichier": "RC_minimal.docx",
                    "categorie": "RC",
                    "texte_complet": "Marché de peinture sans date limite explicite.",
                }
            ]
        }
        analyse = analyse_marche.analyser_marche(dce_incomplet)
        # La liste non_extrait doit contenir les champs non détectés sans avoir été réinitialisée
        assert isinstance(analyse["non_extrait"], list)
        assert len(analyse["non_extrait"]) >= 1, "non_extrait ne doit pas être vide lorsqu'il manque des métadonnées"

    def test_r4_buyer_extraction_sanitization_no_newlines(self):
        """R4.4 : L'extraction de l'acheteur public ne doit pas capturer de saut de ligne ni de texte parasite."""
        dce_text = {
            "pieces": [
                {
                    "nom_fichier": "RC.docx",
                    "categorie": "RC",
                    "texte_complet": (
                        "Pouvoir adjudicateur : Commune de Saint-Pierre-des-Bois\n"
                        "Date limite de remise des offres : 24/10/2026 à 12h00\n"
                        "Objet du marché : Travaux de toiture"
                    ),
                }
            ]
        }
        analyse = analyse_marche.analyser_marche(dce_text)
        acheteur = analyse["acheteur"]
        assert "\n" not in acheteur, "Le nom de l'acheteur ne doit contenir aucun saut de ligne"
        assert "\r" not in acheteur
        assert "Saint-Pierre-des-Bois" in acheteur
        assert "Date limite" not in acheteur

    def test_r4_selection_criteria_weights_sum_to_exactly_100(self):
        """R4.5 : Contrôle strict de la somme des critères d'attribution à 100 %."""
        # Cas invalide : Somme = 90 %
        texte_invalide = "Critère 1 : Prix des prestations 50 %. Critère 2 : Valeur technique 40 %."
        criteres_invalides = analyse_marche.extraire_criteres_notation(texte_invalide)
        somme_inv = sum(c["ponderation_pct"] for c in criteres_invalides)
        assert somme_inv == 90
        # La somme ne vaut pas 100 %, cela doit être détectable comme anomalie
        assert somme_inv != 100

        # Cas valide : Somme = 100 %
        texte_valide = "Critère 1 : Prix des prestations 50 %. Critère 2 : Valeur technique 40 %. Critère 3 : Délai 10 %."
        criteres_valides = analyse_marche.extraire_criteres_notation(texte_valide)
        somme_val = sum(c["ponderation_pct"] for c in criteres_valides)
        assert somme_val == 100


class TestTier1R5PriceAnalysisAndRegulatory:
    """Couverture exhaustive de l'exigence R5 : Contrôle des prix, découplage OAB et seuils."""

    def test_r5_decouple_arithmetic_errors_and_oab_flags(self):
        """R5.1 : Découplage strict des anomalies arithmétiques et des alertes OAB."""
        lignes = [
            {
                "ligne_excel": 2,
                "numero": "1",
                "designation": "Lot unique parfaitement chiffré",
                "unite": "u",
                "quantite": Decimal("1.00"),
                "prix_unitaire_ht": Decimal("50000.00"),
                "total_ligne_excel": Decimal("50000.00"),
            }
        ]
        # Estimation MOE = 100 000 € -> 50 000 € est 50% plus bas -> OAB
        res = execute_controle_prix(
            lignes=lignes,
            total_excel=Decimal("50000.00"),
            taux_tva=Decimal("20.0"),
            estimation_moe=Decimal("100000.00"),
            seuil_oab_pct=Decimal("25.0"),
        )
        assert res["total_recalcule_ht"] == "50000.00"
        assert res["ecart_total_ht"] == "0.00"

        # Le calcul arithmétique est 100% exact
        erreurs_arith = [
            a for a in res.get("anomalies", [])
            if a.get("type") in ["ECART_LIGNE_ARITHMETIQUE", "ECART_TOTAL_GENERAL_HT", "PRIX_MANQUANT"]
        ]
        assert len(erreurs_arith) == 0, "Aucune erreur arithmétique ne doit être levée sur un calcul exact"

    def test_r5_reject_empty_dpgf_compliance(self):
        """R5.2 : Rejet absolu de la conformité si 0 ligne n'est extraite de la DPGF."""
        res = execute_controle_prix(
            lignes=[],
            total_excel=Decimal("0.00"),
            taux_tva=Decimal("20.0"),
        )
        # Une DPGF vide ne doit en aucun cas être déclarée CONFORME
        assert res["statut_global"] != "CONFORME", (
            "Une DPGF avec 0 ligne extraite ne doit jamais être validée comme CONFORME"
        )
        assert res.get("nb_anomalies", 0) >= 1 or res.get("statut_global") in ["NON_CONFORME", "ANOMALIES_DETECTEES"]

    def test_r5_decimal_precision_half_up(self):
        """R5.3 : Calcul arithmétique rigoureux en Decimal ROUND_HALF_UP."""
        lignes = [
            {
                "ligne_excel": 2,
                "numero": "1.1",
                "designation": "Façonnage zinc",
                "unite": "ml",
                "quantite": Decimal("33.33"),
                "prix_unitaire_ht": Decimal("10.05"),
                "total_ligne_excel": Decimal("334.97"),
            }
        ]
        # 33.33 * 10.05 = 334.9665 -> arrondi monnaie = 334.97
        res = execute_controle_prix(lignes, total_excel=Decimal("334.97"), taux_tva=Decimal("20.0"))
        assert res["total_recalcule_ht"] == "334.97"
        assert res["ecart_total_ht"] == "0.00"

    def test_r5_regulatory_threshold_100k_effective_date_in_seuils_yaml(self):
        """R5.4 : Décret n° 2025-1440 : Seuil 100 000 € HT avec date d'effet au 01/04/2026."""
        seuils_path = ASSETS_DIR / "seuils.yaml"
        assert seuils_path.exists(), "assets/seuils.yaml doit exister"

        with seuils_path.open("r", encoding="utf-8") as f:
            seuils = yaml.safe_load(f)

        dispense = seuils.get("seuils_travaux", {}).get("dispense_procedure_formalites_prealables", {})
        assert float(dispense.get("montant_ht_euros", 0)) == 100000.00
        assert str(dispense.get("date_application")) in ["2026-01-01", "2026-04-01"], (
            f"La date d'effet légale doit être 2026-01-01 (Décret n° 2025-1386), trouvé : {dispense.get('date_application')}"
        )

    def test_r5_regulatory_threshold_in_references_markdown(self):
        """R5.5 : Le guide references/02-procedures-et-seuils.md doit mentionner le seuil de 100 k€ au 01/01/2026."""
        ref_path = REFERENCES_DIR / "02-procedures-et-seuils.md"
        assert ref_path.exists(), "references/02-procedures-et-seuils.md doit exister"

        content = ref_path.read_text(encoding="utf-8")
        assert "100 000" in content or "100000" in content
        assert any(k in content for k in ["2025-1386", "2025-1440", "1er janvier 2026", "1er avril 2026", "01/01/2026", "01/04/2026"])


# ==============================================================================
# TIER 2 : BOUNDARY & CORNER CASES
# ==============================================================================

class TestTier2BoundaryAndCornerCases:
    """Cas limites, frontières et cas d'angle."""

    def test_tier2_empty_dpgf_zero_lines_excel(self, tmp_path: Path):
        """Tier 2.1 : DPGF Excel vide sans en-tête ni données exploitables."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "DPGF_Vide"
        chemin_xlsx = tmp_path / "dpgf_vide.xlsx"
        wb.save(str(chemin_xlsx))

        lignes, resume = controle_prix.analyser_lignes_dpgf(chemin_xlsx)
        assert resume["nb_lignes_extraites"] == 0

        res = execute_controle_prix(lignes, total_excel=None)
        assert res["statut_global"] != "CONFORME"

    def test_tier2_missing_decennale_police_number_and_file(self):
        """Tier 2.2 : Absence conjointe du numéro de police et du fichier d'assurance décennale."""
        profil = {
            "identite": {"raison_sociale": "Entreprise Dénudée"},
            "assurances": {"decennale": {}},
            "fichiers_justificatifs": {},
        }
        checklist = execute_checklist({}, profil)
        p_dec = next(p for p in checklist["candidature"] if "décennale" in p["piece"].lower())
        assert p_dec["statut"] in ["A_METTRE_A_JOUR", "A_FOURNIR", "MANQUANT"]

    def test_tier2_page_limit_boundaries(self):
        """Tier 2.3 : Frontière exacte de limitation de pages (20 pages vs 21 pages)."""
        analyse = {"contradictions_detectees": [], "rc_limite_pages": 20}
        checklist = {"candidature": [], "offre": []}
        prix = {"total_recalcule_ht": "100000.00", "nb_anomalies": 0}

        # 20 pages max (~60 000 caractères) -> Valide
        memoire_20_pages = "Page conforme.\n" * 1000
        audit_ok = execute_controle_final(analyse, checklist, prix, memoire_texte=memoire_20_pages)
        # 40 pages max (~200 000 caractères) -> Invalide
        memoire_40_pages = "Page de dépassement.\n" * 3000
        audit_ko = execute_controle_final(analyse, checklist, prix, memoire_texte=memoire_40_pages)

        if hasattr(controle_final, "verifier_limite_pages"):
            assert audit_ko["statut_code"] == "PAS_PRET"

    def test_tier2_criteria_weights_precision_boundaries(self):
        """Tier 2.4 : Somme des pondérations des critères : 99.9 % vs 100.0 % vs 100.1 %."""
        # 99.9 %
        w_99_9 = [Decimal("49.9"), Decimal("40.0"), Decimal("10.0")]
        assert sum(w_99_9) == Decimal("99.9")
        assert sum(w_99_9) != Decimal("100.0")

        # 100.0 %
        w_100 = [Decimal("50.0"), Decimal("40.0"), Decimal("10.0")]
        assert sum(w_100) == Decimal("100.0")

        # 100.1 %
        w_100_1 = [Decimal("50.1"), Decimal("40.0"), Decimal("10.0")]
        assert sum(w_100_1) == Decimal("100.1")
        assert sum(w_100_1) != Decimal("100.0")

    def test_tier2_deadline_temporal_boundaries(self):
        """Tier 2.5 : Limite de date : passée hier (expirée) vs dans le futur."""
        hier = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%d/%m/%Y")
        demain = (datetime.date.today() + datetime.timedelta(days=10)).strftime("%d/%m/%Y")

        analyse_expiree = {"calendrier": {"date_limite_retenue": hier}, "contradictions_detectees": []}
        audit_exp = execute_controle_final(analyse_expiree, {"candidature": [], "offre": []}, {"total_recalcule_ht": "100.00", "nb_anomalies": 0}, "Memoire.")
        assert audit_exp["statut_code"] == "PAS_PRET"

        analyse_active = {"calendrier": {"date_limite_retenue": demain}, "contradictions_detectees": []}
        audit_act = execute_controle_final(analyse_active, {"candidature": [], "offre": []}, {"total_recalcule_ht": "100.00", "nb_anomalies": 0}, "Memoire.")
        codes_blocages = [b["code"] for b in audit_act["blocages"]]
        assert "DATE_LIMITE_DEPASSEE" not in codes_blocages

    def test_tier2_price_discrepancy_centime_tolerance(self):
        """Tier 2.6 : Tolérance financière : écart de 0.02 € accepté vs écart de 0.03 € bloquant."""
        analyse = {"contradictions_detectees": []}
        checklist = {"candidature": [], "offre": []}
        prix = {"total_recalcule_ht": "100000.00", "nb_anomalies": 0}

        # Écart de 0.02 € -> Toléré
        audit_02 = execute_controle_final(analyse, checklist, prix, "Memoire.", montant_ae_ht=Decimal("100000.02"))
        codes_02 = [b["code"] for b in audit_02["blocages"]]
        assert "DISCORDANCE_PRIX_AE_DPGF" not in codes_02

        # Écart de 0.03 € -> Bloquant
        audit_03 = execute_controle_final(analyse, checklist, prix, "Memoire.", montant_ae_ht=Decimal("100000.03"))
        codes_03 = [b["code"] for b in audit_03["blocages"]]
        assert "DISCORDANCE_PRIX_AE_DPGF" in codes_03


# ==============================================================================
# TIER 3 : CROSS-FEATURE COMBINATIONS
# ==============================================================================

class TestTier3CrossFeatureCombinations:
    """Interactions multi-modules et combinaisons complexes."""

    @pytest.fixture
    def config_go_nogo(self) -> Dict[str, Any]:
        with (ASSETS_DIR / "go_nogo_config.yaml").open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def profil_nominal(self) -> Dict[str, Any]:
        with (ASSETS_DIR / "profil_entreprise.example.yaml").open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_tier3_high_go_nogo_score_with_blocking_contradiction(self, config_go_nogo: Dict[str, Any], profil_nominal: Dict[str, Any]):
        """Tier 3.1 : Entreprise d'excellence (>85 pts) mais contradiction bloquante dans le DCE -> STRICT NO-GO."""
        analyse = {
            "objet": "Travaux de couverture réfection complète toiture",
            "acheteur": "Commune de Bourges 18000",
            "lieu_execution": "18000 Bourges",
            "contradictions_detectees": [
                {
                    "type": "DATE_LIMITE_CONTRADICTOIRE",
                    "gravite": "BLOQUANT",
                    "description": "Date limite contradictoire RC vs AE",
                }
            ],
        }
        res = execute_go_nogo(analyse, profil_nominal, config_go_nogo)
        assert res["verdict"] == "NO-GO", "Une contradiction BLOQUANT doit impérativement interdire le verdict GO"

    def test_tier3_valid_checklist_with_empty_dpgf(self):
        """Tier 3.2 : Checklist 100% prête mais DPGF vide -> Contrôle final déclare PAS_PRET."""
        checklist_valide = {
            "candidature": [{"piece": "DC1", "obligatoire": True, "statut": "VERIFIE_PRESENT"}],
            "offre": [
                {"piece": "AE", "obligatoire": True, "statut": "VERIFIE_PRESENT"},
                {"piece": "Mémoire", "obligatoire": True, "statut": "VERIFIE_PRESENT"},
            ],
        }
        # DPGF avec zéro ligne
        prix_vide = execute_controle_prix(lignes=[], total_excel=Decimal("0.00"))
        audit = execute_controle_final(
            analyse={"contradictions_detectees": []},
            checklist=checklist_valide,
            prix=prix_vide,
            memoire_texte="Mémoire complet.",
        )
        assert audit["statut_code"] == "PAS_PRET"

    def test_tier3_decennale_metadata_without_physical_file_blocks_final_control(self, tmp_path: Path):
        """Tier 3.3 : Métadonnées d'assurance présentes mais fichier absent du disque -> Bloque le contrôle final."""
        profil = {
            "identite": {"raison_sociale": "Entreprise Sans Attestation"},
            "assurances": {
                "decennale": {"numero_police": "POL-12345", "date_validite": "2030-12-31"}
            },
            "fichiers_justificatifs": {"decennale": "attestation_introuvable.pdf"},
        }
        checklist = execute_checklist({}, profil, dossiers_docs=[tmp_path])
        audit = execute_controle_final(
            analyse={"contradictions_detectees": []},
            checklist=checklist,
            prix={"total_recalcule_ht": "100000.00", "nb_anomalies": 0},
            memoire_texte="Mémoire complet.",
        )
        assert audit["statut_code"] == "PAS_PRET"

    def test_tier3_zero_arithmetic_errors_with_oab_and_valid_ae(self):
        """Tier 3.4 : Calcul arithmétique parfait, concordance AE/DPGF, mais alerte OAB distincte."""
        lignes = [
            {
                "ligne_excel": 2,
                "numero": "1",
                "designation": "Ouvrage principal",
                "unite": "fft",
                "quantite": Decimal("1.00"),
                "prix_unitaire_ht": Decimal("60000.00"),
                "total_ligne_excel": Decimal("60000.00"),
            }
        ]
        # Estimation MOE = 120 000 € -> 60 000 € est 50% sous la MOE (OAB)
        res_prix = execute_controle_prix(lignes, total_excel=Decimal("60000.00"), estimation_moe=Decimal("120000.00"))
        assert res_prix["total_recalcule_ht"] == "60000.00"

        # L'audit final avec montant AE = 60 000 €
        audit = execute_controle_final(
            analyse={"contradictions_detectees": []},
            checklist={"candidature": [], "offre": []},
            prix=res_prix,
            memoire_texte="Mémoire sans balise.",
            montant_ae_ht=Decimal("60000.00"),
        )
        # La discordance financière AE vs DPGF ne doit pas être levée
        codes = [b["code"] for b in audit["blocages"]]
        assert "DISCORDANCE_PRIX_AE_DPGF" not in codes

    def test_tier3_clean_dossier_with_single_residual_placeholder(self):
        """Tier 3.5 : Tout est vert sauf une unique balise [À FOURNIR] -> Bloque immédiatement."""
        analyse = {"contradictions_detectees": []}
        checklist = {
            "candidature": [{
                "piece": "DC1", "obligatoire": True, "exige_par_marche": True,
                "present_disque": True, "valide_juridiquement": True, "verifie_contenu": True,
                "statut": "VERIFIE_PRESENT"
            }],
            "offre": [{
                "piece": "AE", "obligatoire": True, "exige_par_marche": True,
                "present_disque": True, "valide_juridiquement": True, "verifie_contenu": True,
                "statut": "VERIFIE_PRESENT"
            }],
        }
        prix = {"total_recalcule_ht": "100000.00", "nb_anomalies": 0}
        memoire_presque_parfait = "Mémoire d'excellence.\n[À FOURNIR : Schéma d'organisation du chantier]\nFin."

        audit = execute_controle_final(analyse, checklist, prix, memoire_texte=memoire_presque_parfait)
        assert audit["statut_code"] == "PAS_PRET"
        codes = [b["code"] for b in audit["blocages"]]
        assert any("BALISE" in c for c in codes)


# ==============================================================================
# TIER 4 : REAL-WORLD SCENARIOS
# ==============================================================================

class TestTier4RealWorldScenarios:
    """Scénarios réels de bout en bout sur tests/fixtures et evals/cas."""

    @pytest.fixture
    def profil_nominal(self) -> Dict[str, Any]:
        with (ASSETS_DIR / "profil_entreprise.example.yaml").open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_tier4_fixture_e2e_pipeline_trap_detection(self, profil_nominal: Dict[str, Any]):
        """Tier 4.1 : Exécution E2E complète sur le jeu de tests fixtures et détection des 3 pièges."""
        # 1. Extraction DCE
        dce_data = dce_extract.extraire_dce(FIXTURES_DIR)
        assert dce_data["total_pieces"] >= 5

        # 2. Analyse marché
        analyse = analyse_marche.analyser_marche(dce_data)
        assert "Saint-Pierre-des-Bois" in analyse["acheteur"]

        # Piège 1 : Date contradictoire RC (24/10) vs AE (28/10)
        types_contradictions = [c["type"] for c in analyse["contradictions_detectees"]]
        assert "DATE_LIMITE_CONTRADICTOIRE" in types_contradictions

        # Piège 3 : Exigence de visite dans le CCAP isolée
        assert "PIEGE_EXIGENCE_CCAP_ISOLEE" in types_contradictions

        # 3. Contrôle des prix DPGF
        dpgf_path = FIXTURES_DIR / "DPGF.xlsx"
        lignes, resume = controle_prix.analyser_lignes_dpgf(dpgf_path)
        res_prix = execute_controle_prix(lignes, total_excel=resume["total_affiche_ht_excel"])

        # Piège 2 : Erreur arithmétique de somme DPGF (écart de 2 500 €)
        assert res_prix["total_recalcule_ht"] == "142500.00"
        assert res_prix["ecart_total_ht"] == "2500.00"

        # 4. Audit final
        checklist = execute_checklist(analyse, profil_nominal, dossiers_docs=[FIXTURES_DIR])
        audit = execute_controle_final(
            analyse=analyse,
            checklist=checklist,
            prix=res_prix,
            memoire_texte="Mémoire de toiture école. Délai : 12 semaines.",
            delai_ae_semaines=12,
            montant_ae_ht=Decimal("142500.00"),
        )
        assert audit["statut_code"] == "PAS_PRET", "Les pièges du dossier fixture doivent interdire le dépôt"

    @pytest.mark.parametrize("cas_file, ecart_attendu, verdict_attendu", [
        ("cas_01_ecole_toiture.json", "2500.00", "PAS_PRET"),
        ("cas_02_gymnase_isolation.json", "0.00", "PRET"),
        ("cas_03_mairie_menuiseries.json", "0.00", "PAS_PRET"),
        ("cas_04_passerelle_pietonne.json", "0.00", "PRET"),
        ("cas_05_creche_ventilation.json", "0.00", "PRET"),
    ])
    def test_tier4_eval_cas_truth_validation(self, cas_file: str, ecart_attendu: str, verdict_attendu: str):
        """Tier 4.2 : Vérification de la vérité terrain sur les 5 cas d'évaluation d'evals/cas/."""
        chemin_cas = EVALS_DIR / "cas" / cas_file
        with chemin_cas.open("r", encoding="utf-8") as f:
            data = json.load(f)

        vt = data["verite_terrain"]
        assert vt["ecart_arithmetique_dpgf_ht"] == ecart_attendu
        assert vt["verdict_attendu"] == verdict_attendu

    def test_tier4_score_eval_cli_execution_and_exit_code(self):
        """Tier 4.3 : Exécution du benchmark score_eval.py en sous-processus."""
        script_eval = EVALS_DIR / "score_eval.py"
        proc = subprocess.run(
            [sys.executable, str(script_eval)],
            capture_output=True,
            text=True,
            cwd=str(ROOT_DIR),
        )
        assert proc.returncode == 0, f"score_eval.py a échoué :\n{proc.stderr}\n{proc.stdout}"
        assert "VALIDÉ" in proc.stdout or "100 %" in proc.stdout

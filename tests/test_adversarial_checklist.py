"""Adversarial stress-testing suite for scripts/checklist_pieces.py.

Empirical challenge suite executed by challenger_m2_1:
- Challenge 1: Physical file presence requirement under adversarial metadata spoofing
- Challenge 2: Strict elimination of 'or True' fallbacks in fiscal & social requirements
- Challenge 3: Orthogonality & integrity of the 4D document status model
- Challenge 4: Edge cases, malformed payloads & boundary condition handling
"""

from __future__ import annotations

import datetime
from pathlib import Path
import sys
from typing import Any, Dict
import pytest
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
ASSETS_DIR = ROOT_DIR / "assets"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from checklist_pieces import (
    construire_checklist,
    generer_checklist,
    generer_markdown_checklist,
    verifier_presence_fichier,
    verifier_validite_date,
)


@pytest.fixture
def profil_complet() -> Dict[str, Any]:
    with (ASSETS_DIR / "profil_entreprise.example.yaml").open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ==============================================================================
# CHALLENGE 1 : TENTATIVES DE LEURRE SUR LA PRÉSENCE PHYSIQUE (METADATA SPOOFING)
# ==============================================================================

class TestAdversarialPhysicalPresence:
    """Tente de tromper le moteur de vérification physique avec des métadonnées déclaratives."""

    def test_challenge_decennale_police_and_valid_date_without_physical_file(self, tmp_path: Path):
        """Attaque : Numéro de police en or, assureur de premier plan, date 2035, mais fichier absent."""
        profil = {
            "identite": {"raison_sociale": "Entreprise Leurre SAS", "siret": "12345678900012"},
            "assurances": {
                "decennale": {
                    "compagnie": "SMABTP Assurance Décennale France",
                    "numero_police": "POLICE-DECENNALE-999999999",
                    "date_validite": "2035-12-31",
                    "fichier": "attestation_decennale_fantome_introuvable.pdf",
                }
            },
            "fichiers_justificatifs": {
                "decennale": "attestation_decennale_fantome_introuvable.pdf"
            },
        }
        analyse = {"pieces_exigees": {"candidature": ["assurance décennale obligatoire"]}}

        checklist = generer_checklist(dce_analyse=analyse, profil=profil, dossiers_docs=[tmp_path])
        p_dec = next(p for p in checklist["candidature"] if "décennale" in p["piece"].lower())

        assert p_dec["present_disque"] is False, "present_disque DOIT être False quand le fichier n'existe pas"
        assert p_dec["statut"] != "VERIFIE_PRESENT", "Le statut ne doit JAMAIS être VERIFIE_PRESENT sans fichier physique"
        assert p_dec["statut"] == "MANQUANT", "Une pièce exigée absente du disque doit avoir le statut MANQUANT"
        assert p_dec["valide_juridiquement"] is False, "La validité juridique requiert la présence physique"

    def test_challenge_rc_pro_police_and_valid_date_without_physical_file(self, tmp_path: Path):
        """Attaque : Police RC Pro déclarée valide avec assureur, sans fichier sur disque."""
        profil = {
            "identite": {"raison_sociale": "Entreprise Leurre SAS"},
            "assurances": {
                "responsabilite_civile": {
                    "compagnie": "AXA Entreprises",
                    "numero_police": "RC-PRO-888888888",
                    "date_validite": "2032-06-30",
                    "fichier": "rc_pro_fantome.pdf",
                }
            },
            "fichiers_justificatifs": {
                "rc_pro": "rc_pro_fantome.pdf"
            },
        }
        analyse = {"pieces_exigees": {"candidature": ["Attestation RC Pro"]}}

        checklist = generer_checklist(dce_analyse=analyse, profil=profil, dossiers_docs=[tmp_path])
        p_rc = next(p for p in checklist["candidature"] if "responsabilité" in p["piece"].lower() or "rc" in p["piece"].lower())

        assert p_rc["present_disque"] is False
        assert p_rc["statut"] != "VERIFIE_PRESENT"
        assert p_rc["statut"] == "MANQUANT"
        assert p_rc["valide_juridiquement"] is False

    def test_challenge_kbis_siret_and_rcs_without_physical_file(self, tmp_path: Path):
        """Attaque : Profil avec SIRET, RCS Ville et Greffe complets, mais sans fichier physique Kbis."""
        profil = {
            "identite": {
                "raison_sociale": "Entreprise Kbis Test",
                "siret": "99988877700019",
                "rcs_ville": "Paris",
            },
            "fichiers_justificatifs": {
                "kbis": "Extrait_Kbis_2026_Inexistant.pdf"
            },
        }
        analyse = {"pieces_exigees": {"candidature": ["Kbis de moins de 3 mois"]}}

        checklist = generer_checklist(dce_analyse=analyse, profil=profil, dossiers_docs=[tmp_path])
        p_kbis = next(p for p in checklist["candidature"] if "kbis" in p["piece"].lower())

        assert p_kbis["present_disque"] is False
        assert p_kbis["statut"] != "VERIFIE_PRESENT"
        assert p_kbis["statut"] == "MANQUANT"
        assert p_kbis["valide_juridiquement"] is False

    def test_challenge_visite_effectuee_true_without_signed_certificate(self, tmp_path: Path):
        """Attaque : visite_effectuee: True avec signataire et date, mais attestation fichier absente."""
        profil = {
            "identite": {"raison_sociale": "Entreprise Visite Test"},
            "visite_site": {
                "visite_effectuee": True,
                "date_visite": "2026-04-15",
                "signataire_mairie": "Jean Dupont, DGS",
                "attestation_fichier": "certificat_visite_signe_inexistant.pdf",
            },
            "fichiers_justificatifs": {
                "attestation_visite": "certificat_visite_signe_inexistant.pdf"
            },
        }
        analyse = {"pieces_exigees": {"offre": ["Attestation de visite des lieux obligatoire signée"]}}

        checklist = generer_checklist(dce_analyse=analyse, profil=profil, dossiers_docs=[tmp_path])
        p_visite = next(p for p in checklist["offre"] if "visite" in p["piece"].lower())

        assert p_visite["present_disque"] is False
        assert p_visite["statut"] != "VERIFIE_PRESENT"
        assert p_visite["statut"] == "MANQUANT"
        assert p_visite["valide_juridiquement"] is False

    def test_challenge_qualibat_certificates_metadata_without_file(self, tmp_path: Path):
        """Attaque : Certifications Qualibat listées avec codes et dates futures, sans fichier."""
        profil = {
            "identite": {"raison_sociale": "Entreprise Qualibat Test"},
            "qualifications_et_certifications": [
                {"organisme": "QUALIBAT", "code": "3101", "date_echeance": "2030-12-31", "fichier": "qualibat_3101.pdf"},
                {"organisme": "QUALIBAT", "code": "3111", "date_echeance": "2030-12-31", "fichier": "qualibat_3111.pdf"},
            ],
            "fichiers_justificatifs": {},
        }
        analyse = {"pieces_exigees": {"candidature": ["Certificats de qualification Qualibat"]}}

        checklist = generer_checklist(dce_analyse=analyse, profil=profil, dossiers_docs=[tmp_path])
        p_qual = next(p for p in checklist["candidature"] if "qualibat" in p["piece"].lower())

        assert p_qual["present_disque"] is False
        assert p_qual["statut"] != "VERIFIE_PRESENT"
        assert p_qual["statut"] == "MANQUANT"

    def test_challenge_directory_path_does_not_pass_as_file(self, tmp_path: Path):
        """Attaque : Fournir un répertoire existant comme nom de fichier justificatif."""
        dossier_existant = tmp_path / "faux_dossier_kbis"
        dossier_existant.mkdir()

        profil = {
            "identite": {"raison_sociale": "Test SAS", "siret": "12345678900012"},
            "fichiers_justificatifs": {
                "kbis": str(dossier_existant)
            },
        }
        analyse = {"pieces_exigees": {"candidature": ["DC1", "Kbis"]}}

        checklist = generer_checklist(dce_analyse=analyse, profil=profil, dossiers_docs=[tmp_path])
        p_kbis = next(p for p in checklist["candidature"] if "kbis" in p["piece"].lower())

        assert p_kbis["present_disque"] is False, "Un dossier ne doit PAS être considéré comme un fichier physique"
        assert p_kbis["statut"] == "MANQUANT"

    @pytest.mark.parametrize("nom_fichier_invalide", [
        None,
        "",
        "   ",
        "inexistant.pdf",
        "NUL",
        "COM1",
        "/chemin/absolu/totalement/fictif/fichier.pdf",
        r"C:\chemins_fictifs_adverses\fake.pdf",
    ])
    def test_challenge_verifier_presence_fichier_invalid_inputs(self, nom_fichier_invalide, tmp_path: Path):
        """Vérifie que verifier_presence_fichier rejette tous les chemins invalides ou inexistants."""
        assert verifier_presence_fichier(nom_fichier_invalide, dossiers=[tmp_path]) is False
        assert verifier_presence_fichier(nom_fichier_invalide, dossiers=None) is False


# ==============================================================================
# CHALLENGE 2 : ÉLIMINATION DU 'OR TRUE' POUR ATTESTATIONS FISCALES & SOCIALES
# ==============================================================================

class TestAdversarialOrTrueElimination:
    """Stress-test pour confirmer qu'aucun 'or True' ne subsiste dans l'évaluation des exigences."""

    def test_dce_without_fiscal_or_social_requirements(self, profil_complet: Dict[str, Any]):
        """DCE exigeant uniquement DC1 et DPGF : fiscale et sociale doivent avoir exige_par_marche=False."""
        analyse = {
            "pieces_exigees": {
                "candidature": ["DC1 - Lettre de candidature", "DC2 - Déclaration du candidat"],
                "offre": ["Cadre de décomposition du prix DPGF"],
            }
        }
        checklist = generer_checklist(dce_analyse=analyse, profil=profil_complet)

        p_fisc = next(p for p in checklist["candidature"] if "fiscale" in p["piece"].lower())
        p_soc = next(p for p in checklist["candidature"] if "sociale" in p["piece"].lower() or "urssaf" in p["piece"].lower())

        assert p_fisc["exige_par_marche"] is False, "L'attestation fiscale ne doit PAS être exigée si non stipulée"
        assert p_soc["exige_par_marche"] is False, "L'attestation sociale ne doit PAS être exigée si non stipulée"
        assert p_fisc["obligatoire"] is False
        assert p_soc["obligatoire"] is False

        # Si absent du disque mais non exigé, le statut doit être A_FOURNIR et NON MANQUANT
        if not p_fisc["present_disque"]:
            assert p_fisc["statut"] == "A_FOURNIR", "Non exigé + absent du disque -> A_FOURNIR (non bloquant immédiat)"
        if not p_soc["present_disque"]:
            assert p_soc["statut"] == "A_FOURNIR", "Non exigé + absent du disque -> A_FOURNIR (non bloquant immédiat)"

    def test_dce_with_only_fiscal_requirement(self, profil_complet: Dict[str, Any]):
        """DCE exigeant expressément l'attestation fiscale : fiscale=True, sociale=False."""
        mots_cles_fiscaux = [
            "Attestation de régularité fiscale",
            "Certificat fiscal (DGFiP)",
            "Attestation impôt sur les sociétés",
            "Bordereau de situation fiscale dgfip",
        ]
        for libelle in mots_cles_fiscaux:
            analyse = {"pieces_exigees": {"candidature": [libelle]}}
            checklist = generer_checklist(dce_analyse=analyse, profil=profil_complet)

            p_fisc = next(p for p in checklist["candidature"] if "fiscale" in p["piece"].lower())
            p_soc = next(p for p in checklist["candidature"] if "sociale" in p["piece"].lower() or "urssaf" in p["piece"].lower())

            assert p_fisc["exige_par_marche"] is True, f"Doit reconnaître '{libelle}'"
            assert p_soc["exige_par_marche"] is False, f"Ne doit PAS exiger l'attestation sociale pour '{libelle}'"

    def test_dce_with_only_social_requirement(self, profil_complet: Dict[str, Any]):
        """DCE exigeant expressément l'attestation sociale : sociale=True, fiscale=False."""
        mots_cles_sociaux = [
            "Attestation de vigilance sociale URSSAF",
            "Certificat de vigilance travail dissimulé",
            "Attestation sociale de moins de 6 mois",
            "Déclaration de lutte contre le travail dissimule",
        ]
        for libelle in mots_cles_sociaux:
            analyse = {"pieces_exigees": {"candidature": [libelle]}}
            checklist = generer_checklist(dce_analyse=analyse, profil=profil_complet)

            p_fisc = next(p for p in checklist["candidature"] if "fiscale" in p["piece"].lower())
            p_soc = next(p for p in checklist["candidature"] if "sociale" in p["piece"].lower() or "urssaf" in p["piece"].lower())

            assert p_soc["exige_par_marche"] is True, f"Doit reconnaître '{libelle}'"
            assert p_fisc["exige_par_marche"] is False, f"Ne doit PAS exiger l'attestation fiscale pour '{libelle}'"

    def test_empty_dce_analyse_does_not_force_fiscal_or_social(self, profil_complet: Dict[str, Any]):
        """DCE vide ({}) : ni fiscale ni sociale ne doivent être exigées."""
        checklist = generer_checklist(dce_analyse={}, profil=profil_complet)

        p_fisc = next(p for p in checklist["candidature"] if "fiscale" in p["piece"].lower())
        p_soc = next(p for p in checklist["candidature"] if "sociale" in p["piece"].lower() or "urssaf" in p["piece"].lower())

        assert p_fisc["exige_par_marche"] is False
        assert p_soc["exige_par_marche"] is False


# ==============================================================================
# CHALLENGE 3 : INTÉGRITÉ ET INVARIANTS DU MODÈLE 4D
# ==============================================================================

class TestAdversarial4DModelInvariants:
    """Vérifie le respect strict des invariants logiques entre les 4 dimensions."""

    def test_invariant_no_verifie_present_without_physical_file(self, tmp_path: Path):
        """Invariant : Si present_disque est False, statut ne peut JAMAIS être VERIFIE_PRESENT."""
        # Création d'un profil sans aucun fichier physique
        profil_vide = {
            "identite": {"raison_sociale": "Ghost Enterprise SAS", "siret": "12345678900012"},
            "fichiers_justificatifs": {
                "dc1": "dc1.pdf",
                "dc2": "dc2.pdf",
                "kbis": "kbis.pdf",
                "attestation_fiscale": "fisc.pdf",
                "attestation_urssaf": "soc.pdf",
                "decennale": "dec.pdf",
                "rc_pro": "rc.pdf",
                "ae": "ae.pdf",
                "dpgf": "dpgf.xlsx",
                "memoire": "memoire.pdf",
                "planning": "planning.pdf",
            },
            "assurances": {
                "decennale": {"compagnie": "SMABTP", "numero_police": "123", "date_validite": "2030-01-01"},
                "responsabilite_civile": {"compagnie": "AXA", "numero_police": "456", "date_validite": "2030-01-01"},
            },
        }

        checklist = generer_checklist(
            dce_analyse={"pieces_exigees": {"candidature": ["DC1", "DC2", "kbis", "assurance decennale"], "offre": ["AE", "DPGF"]}},
            profil=profil_vide,
            dossiers_docs=[tmp_path],  # dossier vide
        )

        for section in ["candidature", "offre"]:
            for piece in checklist[section]:
                assert piece["present_disque"] is False
                assert piece["statut"] != "VERIFIE_PRESENT", (
                    f"Violation d'invariant sur {piece['piece']} : statut VERIFIE_PRESENT alors que présent disque est False"
                )
                assert piece["valide_juridiquement"] is False, (
                    f"Violation d'invariant sur {piece['piece']} : valide_juridiquement True alors que présent disque est False"
                )
                assert piece["verifie_contenu"] is False, (
                    f"Violation d'invariant sur {piece['piece']} : verifie_contenu True alors que présent disque est False"
                )

    def test_invariant_manquant_when_exige_and_absent(self, tmp_path: Path):
        """Invariant : Si exige_par_marche est True et present_disque est False, statut DOIT être MANQUANT."""
        profil_sans_fichiers = {
            "identite": {"raison_sociale": "SAS Sans Fichiers"},
            "assurances": {
                "decennale": {"compagnie": "SMABTP", "numero_police": "POL-1", "date_validite": "2030-01-01"},
                "responsabilite_civile": {"compagnie": "AXA", "numero_police": "POL-2", "date_validite": "2030-01-01"},
            },
        }
        analyse_exhaustive = {
            "pieces_exigees": {
                "candidature": [
                    "Lettre DC1",
                    "Déclaration DC2",
                    "Kbis",
                    "Attestation fiscale",
                    "Attestation sociale",
                    "Assurance décennale",
                    "Assurance RC",
                ],
                "offre": [
                    "Acte d'engagement",
                    "DPGF",
                    "Mémoire technique",
                    "Planning",
                    "Visite obligatoire",
                ],
            }
        }

        checklist = generer_checklist(dce_analyse=analyse_exhaustive, profil=profil_sans_fichiers, dossiers_docs=[tmp_path])

        for section in ["candidature", "offre"]:
            for piece in checklist[section]:
                if piece["exige_par_marche"] and not piece["present_disque"]:
                    assert piece["statut"] == "MANQUANT", (
                        f"Pour {piece['piece']}, exige_par_marche=True et present_disque=False doit donner statut MANQUANT, trouvé : {piece['statut']}"
                    )

    def test_physical_file_found_in_second_folder(self, tmp_path: Path):
        """Vérifie la résolution de présence dans une liste multi-dossiers."""
        dir1 = tmp_path / "dossier_vide"
        dir1.mkdir()
        dir2 = tmp_path / "dossier_avec_pieces"
        dir2.mkdir()

        kbis_file = dir2 / "kbis_officiel.pdf"
        kbis_file.write_text("dummy kbis", encoding="utf-8")

        profil = {
            "identite": {"raison_sociale": "Test SAS", "siret": "12345678900012", "rcs_ville": "Lyon"},
            "fichiers_justificatifs": {"kbis": "kbis_officiel.pdf"},
        }
        checklist = generer_checklist(dce_analyse={}, profil=profil, dossiers_docs=[dir1, dir2])
        p_kbis = next(p for p in checklist["candidature"] if "kbis" in p["piece"].lower())

        assert p_kbis["present_disque"] is True
        assert p_kbis["statut"] == "VERIFIE_PRESENT"
        assert p_kbis["valide_juridiquement"] is True


# ==============================================================================
# CHALLENGE 4 : GESTION DES CAS LIMITES ET ENTRÉES ADVERSES
# ==============================================================================

class TestAdversarialEdgeCasesAndRobustness:
    """Stress-test sur les entrées malformées, types inattendus et structures dégradées."""

    def test_null_and_empty_payloads(self):
        """Tolérance aux payloads dce_analyse et profil None ou vides."""
        res1 = generer_checklist(dce_analyse=None, profil=None, dossiers_docs=None)
        assert isinstance(res1, dict)
        assert "candidature" in res1
        assert "offre" in res1
        assert res1["total_pieces_candidature"] > 0
        assert res1["total_pieces_offre"] > 0

        res2 = generer_checklist(dce_analyse={}, profil={}, dossiers_docs=[])
        assert isinstance(res2, dict)
        assert len(res2["candidature"]) == res1["total_pieces_candidature"]

    def test_degraded_pieces_exigees_structures(self):
        """Tolérance lorsque pieces_exigees contient des valeurs None ou inattendues."""
        dce_degrade = {
            "pieces_exigees": {
                "candidature": None,
                "offre": None,
            }
        }
        # Ne doit pas lever d'exception
        res = generer_checklist(dce_analyse=dce_degrade, profil={})
        assert isinstance(res, dict)

    def test_degraded_profil_assurances_and_fichiers(self):
        """Tolérance quand assurances ou fichiers_justificatifs sont None ou malformés."""
        profil_degrade = {
            "identite": {"raison_sociale": "Test SAS"},
            "assurances": None,
            "fichiers_justificatifs": None,
            "visite_site": "non_un_dict",
        }
        res = generer_checklist(dce_analyse={}, profil=profil_degrade)
        assert isinstance(res, dict)
        p_dec = next(p for p in res["candidature"] if "décennale" in p["piece"].lower())
        assert p_dec["present_disque"] is False
        assert p_dec["statut"] == "MANQUANT"

    def test_finding_empirical_crash_when_identite_is_none(self):
        """Vérifie la robustesse face à profil['identite'] = None."""
        profil_identite_none = {"identite": None}
        res = generer_checklist(dce_analyse={}, profil=profil_identite_none)
        assert isinstance(res, dict)
        assert len(res["candidature"]) >= 7

    def test_finding_empirical_crash_when_pieces_exigees_is_none(self):
        """Vérifie la robustesse face à dce['pieces_exigees'] = None."""
        dce_pieces_none = {"pieces_exigees": None}
        res = generer_checklist(dce_analyse=dce_pieces_none, profil={})
        assert isinstance(res, dict)
        assert len(res["candidature"]) >= 7

    def test_date_validite_taxonomy_boundaries(self):
        """Cas limites temporels pour verifier_validite_date."""
        today = datetime.date.today()
        dans_15_jours = (today + datetime.timedelta(days=15)).strftime("%Y-%m-%d")
        dans_29_jours = (today + datetime.timedelta(days=29)).strftime("%Y-%m-%d")
        dans_31_jours = (today + datetime.timedelta(days=31)).strftime("%Y-%m-%d")
        hier = (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        assert verifier_validite_date(dans_15_jours) == "A_RENOUVELER_SOUS_30J"
        assert verifier_validite_date(dans_29_jours) == "A_RENOUVELER_SOUS_30J"
        assert verifier_validite_date(dans_31_jours) == "VALIDE"
        assert verifier_validite_date(hier) == "EXPIREE"

        # Formats exotiques / invalides
        assert verifier_validite_date(12345) == "FORMAT_INVALIDE"
        assert verifier_validite_date([]) == "NON_RENSEIGNEE"  # Falsy input
        assert verifier_validite_date("99/99/9999") == "FORMAT_INVALIDE"
        assert verifier_validite_date("   ") == "NON_RENSEIGNEE"


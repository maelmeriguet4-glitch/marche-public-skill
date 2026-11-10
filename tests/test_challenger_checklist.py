"""Test suite adversarial pour scripts/checklist_pieces.py.

Conçu par challenger_m2_2 (teamwork_challenger).
Teste empiriquement :
1. Le modèle 4D (exige_par_marche, present_disque, valide_juridiquement, verifie_contenu, statut).
2. Toutes les combinaisons d'état et transitions.
3. Les cas limites (None, dicts corrompus, types inattendus, dossiers_docs vides ou invalides).
4. La robustesse aux tentatives de traversée de chemin (path traversal).
5. La robustesse aux dates invalides et formats exotiques.
"""

from __future__ import annotations

import datetime
from pathlib import Path
import sys
from typing import Any, Dict, List
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import checklist_pieces
from checklist_pieces import (
    construire_checklist,
    generer_checklist,
    generer_markdown_checklist,
    verifier_presence_fichier,
    verifier_validite_date,
)


# ==============================================================================
# 1. TEST ADVERSARIAL : DATES INVALIDES ET CAS LIMITES TEMPORELS
# ==============================================================================

class TestDateValidationAdversarial:
    """Stress-test de verifier_validite_date avec entrées hostiles."""

    @pytest.mark.parametrize("valeur,attendu", [
        (None, "NON_RENSEIGNEE"),
        ("", "NON_RENSEIGNEE"),
        ("   ", "NON_RENSEIGNEE"),
        ("\t\n", "NON_RENSEIGNEE"),
        ("not-a-date", "FORMAT_INVALIDE"),
        ("2026-02-31", "FORMAT_INVALIDE"),
        ("31-02-2026", "FORMAT_INVALIDE"),
        ("2026/12/31", "FORMAT_INVALIDE"),
        ("2026-13-01", "FORMAT_INVALIDE"),
        ("2026-00-01", "FORMAT_INVALIDE"),
        ("00/00/0000", "FORMAT_INVALIDE"),
        ("99999-99-99", "FORMAT_INVALIDE"),
        (123456, "FORMAT_INVALIDE"),
        (123.456, "FORMAT_INVALIDE"),
        (True, "FORMAT_INVALIDE"),
        (False, "NON_RENSEIGNEE"),
        (["2026-12-31"], "FORMAT_INVALIDE"),
        ({"date": "2026-12-31"}, "FORMAT_INVALIDE"),
    ])
    def test_dates_invalides_ou_corrompues(self, valeur: Any, attendu: str):
        res = verifier_validite_date(valeur)
        assert res == attendu, f"Pour {valeur!r}, attendu {attendu}, obtenu {res}"

    def test_dates_frontieres_relatives(self):
        """Teste les frontières exactes : hier, aujourd'hui, j+29, j+30, j+31."""
        today = datetime.date.today()
        hier = (today - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        auj = today.strftime("%Y-%m-%d")
        j29 = (today + datetime.timedelta(days=29)).strftime("%Y-%m-%d")
        j30 = (today + datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        j31 = (today + datetime.timedelta(days=31)).strftime("%Y-%m-%d")

        assert verifier_validite_date(hier) == "EXPIREE"
        assert verifier_validite_date(auj) == "A_RENOUVELER_SOUS_30J"
        assert verifier_validite_date(j29) == "A_RENOUVELER_SOUS_30J"
        assert verifier_validite_date(j30) == "VALIDE"
        assert verifier_validite_date(j31) == "VALIDE"

    def test_formats_acceptes(self):
        """Vérifie les formats ISO %Y-%m-%d et français %d/%m/%Y avec espaces superflus."""
        assert verifier_validite_date(" 2030-06-15 ") == "VALIDE"
        assert verifier_validite_date(" 15/06/2030 ") == "VALIDE"
        assert verifier_validite_date(" 2010-06-15 ") == "EXPIREE"
        assert verifier_validite_date(" 15/06/2010 ") == "EXPIREE"


# ==============================================================================
# 2. TEST ADVERSARIAL : PRESENCE PHYSIQUE, CHEMINS ET PATH TRAVERSAL
# ==============================================================================

class TestPresenceFichierAdversarial:
    """Stress-test de verifier_presence_fichier avec chemins hostiles."""

    def test_entrees_nulles_et_vides(self):
        assert verifier_presence_fichier(None) is False
        assert verifier_presence_fichier("") is False
        assert verifier_presence_fichier("   ") is False
        assert verifier_presence_fichier(False) is False
        assert verifier_presence_fichier(12345) is False
        assert verifier_presence_fichier([]) is False
        assert verifier_presence_fichier({}) is False

    def test_dossiers_invalides(self, tmp_path: Path):
        fichier = tmp_path / "test.pdf"
        fichier.write_text("ok", encoding="utf-8")

        # Dossiers contenant None, int, chemins inexistants
        assert verifier_presence_fichier("test.pdf", [None, "", tmp_path, "dossier_inexistant_99999"]) is True
        assert verifier_presence_fichier("absent.pdf", [None, "", "inexistant"]) is False
        assert verifier_presence_fichier("test.pdf", None) is False

    def test_repertoire_au_lieu_de_fichier(self, tmp_path: Path):
        """Un répertoire ne doit PAS être considéré comme un fichier présent."""
        sous_dossier = tmp_path / "sous_rep"
        sous_dossier.mkdir()
        assert verifier_presence_fichier("sous_rep", [tmp_path]) is False
        assert verifier_presence_fichier(str(sous_dossier), []) is False

    def test_caracteres_speciaux_et_octets_nuls(self, tmp_path: Path):
        """Vérifie que les caractères illégaux sous Windows ne provoquent pas de crash non géré."""
        try:
            assert verifier_presence_fichier("fichier\x00nul.pdf", [tmp_path]) is False
        except (ValueError, OSError):
            pytest.fail("Crash non intercepté sur octet nul dans le chemin")

        assert verifier_presence_fichier("???:::***.pdf", [tmp_path]) is False

    def test_path_traversal_detection(self, tmp_path: Path):
        """Vérifie que verifier_presence_fichier bloque les traversées de chemin avec .."""
        # Un fichier existant en dehors du dossier de travail (ex: hosts Windows)
        hosts_path = "C:/Windows/System32/drivers/etc/hosts"
        if Path(hosts_path).is_file():
            # Résolution directe d'un chemin absolu externe
            assert verifier_presence_fichier(hosts_path, []) is True
            # Rejet strict de la traversée relative avec ..
            assert verifier_presence_fichier("../System32/drivers/etc/hosts", [Path("C:/Windows/System32")]) is False


# ==============================================================================
# 3. TEST ADVERSARIAL : CAS LIMITES ET DICTS CORROMPUS DANS GENERER_CHECKLIST
# ==============================================================================

class TestGenererChecklistCorruptInputs:
    """Vérification de la robustesse de generer_checklist face aux valeurs nulles et corrompues YAML."""

    def test_entrees_completement_vides_ou_none(self):
        res1 = generer_checklist(None, None, None)
        assert isinstance(res1, dict)
        assert len(res1["candidature"]) >= 7
        assert len(res1["offre"]) >= 4

        res2 = generer_checklist({}, {}, [])
        assert isinstance(res2, dict)
        assert res1 == res2

    def test_safe_pieces_exigees_none(self):
        """Vérifie que pieces_exigees=None ne provoque pas de crash et renvoie une checklist valide."""
        res = generer_checklist({"pieces_exigees": None}, {})
        assert isinstance(res, dict)
        assert len(res["candidature"]) >= 7

    def test_safe_pieces_exigees_string(self):
        """Vérifie que pieces_exigees='string' ne provoque pas de crash et renvoie une checklist valide."""
        res = generer_checklist({"pieces_exigees": "candidature"}, {})
        assert isinstance(res, dict)
        assert len(res["candidature"]) >= 7

    def test_safe_identite_none(self):
        """Vérifie que profil['identite']=None ne provoque pas de crash."""
        res = generer_checklist({}, {"identite": None})
        assert isinstance(res, dict)
        assert len(res["candidature"]) >= 7

    def test_safe_assurances_decennale_none(self):
        """Vérifie que profil['assurances']['decennale']=None ne provoque pas de crash."""
        res = generer_checklist({}, {"assurances": {"decennale": None}})
        assert isinstance(res, dict)
        assert len(res["candidature"]) >= 7

    def test_safe_assurances_rc_pro_none(self):
        """Vérifie que profil['assurances']['responsabilite_civile']=None ne provoque pas de crash."""
        res = generer_checklist({}, {"assurances": {"responsabilite_civile": None}})
        assert isinstance(res, dict)
        assert len(res["candidature"]) >= 7

    def test_safe_qualifications_none(self):
        """Vérifie que profil['qualifications_et_certifications']=None ne provoque pas de crash."""
        res = generer_checklist({}, {"qualifications_et_certifications": None})
        assert isinstance(res, dict)
        assert len(res["candidature"]) >= 7

    def test_safe_references_none(self):
        """Vérifie que profil['references_chantiers']=None ne provoque pas de crash."""
        res = generer_checklist({}, {"references_chantiers": None})
        assert isinstance(res, dict)
        assert len(res["candidature"]) >= 7

    def test_safe_dossiers_docs_non_path_in_list(self, tmp_path: Path):
        """Vérifie que des éléments non-chemin dans dossiers_docs sont filtrés sans crash."""
        res = generer_checklist({}, {}, dossiers_docs=[None, "", tmp_path, 12345])
        assert isinstance(res, dict)
        assert len(res["candidature"]) >= 7

    def test_safe_dossiers_docs_scalar_int(self):
        """Vérifie qu'un entier scalaire pour dossiers_docs est géré sans crash."""
        res = generer_checklist({}, {}, dossiers_docs=12345)
        assert isinstance(res, dict)
        assert len(res["candidature"]) >= 7


# ==============================================================================
# 4. TEST ADVERSARIAL : MODELE 4D ET SEMANTIQUE DES STATUTS
# ==============================================================================

class TestModele4DCompletude:
    """Challenge la cohérence du modèle 4D sur l'ensemble des 16 pièces."""

    def test_invariance_absence_disque_interdit_validite_et_verification(self, tmp_path: Path):
        """Invariant fondamental : Si un fichier est absent du disque,
        valide_juridiquement et verifie_contenu doivent TOUJOURS être False.
        """
        profil = {
            "identite": {"raison_sociale": "Entreprise Totale SAS", "siret": "12345678900012", "rcs_ville": "Paris"},
            "assurances": {
                "decennale": {"compagnie": "SMABTP", "numero_police": "POL-1", "date_validite": "2035-01-01"},
                "responsabilite_civile": {"compagnie": "AXA", "numero_police": "RC-1", "date_validite": "2035-01-01"},
            },
            "qualifications_et_certifications": [{"code": "3101", "organisme": "QUALIBAT", "date_echeance": "2035-01-01"}],
            "references_chantiers": [{"intitule": f"Chantier {i}"} for i in range(5)],
            "visite_site": {"visite_effectuee": True, "signataire_mairie": "M. Le Maire", "date_visite": "2026-04-01"},
            "capacites_financieres": {"exercices": [{"chiffre_affaires_ht_euros": 1000000.0}]},
            "fichiers_justificatifs": {
                "dc1": "fantome_dc1.pdf",
                "dc2": "fantome_dc2.pdf",
                "kbis": "fantome_kbis.pdf",
                "attestation_fiscale": "fantome_fisc.pdf",
                "attestation_urssaf": "fantome_soc.pdf",
                "attestation_cibtp": "fantome_cibtp.pdf",
                "decennale": "fantome_dec.pdf",
                "rc_pro": "fantome_rc.pdf",
                "qualibat": "fantome_qual.pdf",
                "references": "fantome_refs.pdf",
                "ae": "fantome_ae.pdf",
                "dpgf": "fantome_dpgf.pdf",
                "memoire": "fantome_memoire.pdf",
                "planning": "fantome_planning.pdf",
                "attestation_visite": "fantome_visite.pdf",
                "fiches_techniques": "fantome_fiches.pdf",
            }
        }

        res = generer_checklist(dce_analyse={}, profil=profil, dossiers_docs=[tmp_path])

        for section in ["candidature", "offre"]:
            for item in res[section]:
                assert item["present_disque"] is False, f"{item['piece']} ne devrait pas être présent sur disque"
                assert item["valide_juridiquement"] is False, (
                    f"{item['piece']} a valide_juridiquement=True alors que le fichier est absent du disque !"
                )
                assert item["verifie_contenu"] is False, (
                    f"{item['piece']} a verifie_contenu=True alors que le fichier est absent du disque !"
                )
                assert item["statut"] != "VERIFIE_PRESENT", (
                    f"{item['piece']} a statut=VERIFIE_PRESENT alors que le fichier est absent du disque !"
                )
                assert item["statut"] != "VALIDE", (
                    f"{item['piece']} a statut=VALIDE alors que le fichier est absent du disque !"
                )

    def test_statuts_pieces_exigees_absentes_sont_toutes_manquant(self, tmp_path: Path):
        """Toute pièce expressément exigée par le marché et absente du disque DOIT avoir statut == MANQUANT."""
        analyse_totale = {
            "pieces_exigees": {
                "candidature": [
                    "DC1 lettre de candidature",
                    "DC2 declaration candidat",
                    "Extrait Kbis",
                    "Attestation fiscale dgfip",
                    "Attestation sociale urssaf vigilance",
                    "Attestation cibtp conges payes",
                    "Attestation assurance decennale",
                    "Attestation assurance responsabilite civile rc pro",
                    "Certificats qualification qualibat",
                    "Dossier references chantiers",
                ],
                "offre": [
                    "Acte engagement AE",
                    "Cadre de decomposition prix dpgf bpu",
                    "Memoire technique",
                    "Planning previsionnel",
                    "Attestation visite lieux",
                    "Fiches techniques avis cstb",
                ]
            }
        }
        res = generer_checklist(dce_analyse=analyse_totale, profil={}, dossiers_docs=[tmp_path])

        for section in ["candidature", "offre"]:
            for item in res[section]:
                assert item["exige_par_marche"] is True, f"{item['piece']} devrait être exigé"
                assert item["present_disque"] is False
                assert item["statut"] == "MANQUANT", (
                    f"Pièce exigée absente {item['piece']} a statut '{item['statut']}', attendu 'MANQUANT'"
                )

    def test_statuts_pieces_non_exigees_absentes_ne_sont_pas_manquant(self, tmp_path: Path):
        """Pour les pièces facultatives non exigées par le marché, le statut d'absence est nuancé (ex: A_FOURNIR, A_RASSEMBLER...)."""
        analyse_minimale = {
            "pieces_exigees": {
                "candidature": ["DC1"],
                "offre": ["DPGF"],
            }
        }
        res = generer_checklist(dce_analyse=analyse_minimale, profil={}, dossiers_docs=[tmp_path])

        # Fiscale non exigée -> A_FOURNIR
        p_fisc = next(p for p in res["candidature"] if "fiscale" in p["piece"].lower())
        assert p_fisc["exige_par_marche"] is False
        assert p_fisc["statut"] == "A_FOURNIR"

        # Fiches techniques non exigées -> A_RASSEMBLER
        p_fiches = next(p for p in res["offre"] if "fiches" in p["piece"].lower())
        assert p_fiches["exige_par_marche"] is False
        assert p_fiches["statut"] == "A_RASSEMBLER"

    def test_statut_expire_quand_fichier_present_mais_date_depassee(self, tmp_path: Path):
        """Quand le fichier physique est présent mais que la date d'échéance est expirée, le statut DOIT être EXPIREE."""
        f_dec = tmp_path / "decennale.pdf"
        f_dec.write_text("assurance", encoding="utf-8")
        f_rc = tmp_path / "rc_pro.pdf"
        f_rc.write_text("assurance", encoding="utf-8")
        f_qual = tmp_path / "qualibat.pdf"
        f_qual.write_text("qualibat", encoding="utf-8")

        profil = {
            "identite": {"raison_sociale": "Entreprise Test"},
            "assurances": {
                "decennale": {"compagnie": "SMABTP", "numero_police": "POL-1", "date_validite": "2020-01-01"},
                "responsabilite_civile": {"compagnie": "AXA", "numero_police": "RC-1", "date_validite": "2020-01-01"},
            },
            "qualifications_et_certifications": [
                {"code": "3101", "organisme": "QUALIBAT", "date_echeance": "2020-01-01", "fichier": "qualibat.pdf"}
            ],
            "fichiers_justificatifs": {
                "decennale": "decennale.pdf",
                "rc_pro": "rc_pro.pdf",
            }
        }

        res = generer_checklist(dce_analyse={}, profil=profil, dossiers_docs=[tmp_path])

        p_dec = next(p for p in res["candidature"] if "décennale" in p["piece"].lower())
        assert p_dec["present_disque"] is True
        assert p_dec["valide_juridiquement"] is False
        assert p_dec["statut"] == "EXPIREE"

        p_rc = next(p for p in res["candidature"] if "responsabilité civile" in p["piece"].lower())
        assert p_rc["present_disque"] is True
        assert p_rc["valide_juridiquement"] is False
        assert p_rc["statut"] == "EXPIREE"

        p_qual = next(p for p in res["candidature"] if "qualification" in p["piece"].lower())
        assert p_qual["present_disque"] is True
        assert p_qual["valide_juridiquement"] is False
        assert p_qual["statut"] == "EXPIREE"

    def test_visite_presente_mais_non_effectuee(self, tmp_path: Path):
        """Si un fichier attestation_visite existe sur le disque mais que visite_effectuee est False."""
        f_visite = tmp_path / "visite.pdf"
        f_visite.write_text("visite", encoding="utf-8")

        profil = {
            "visite_site": {
                "visite_effectuee": False,
                "attestation_fichier": "visite.pdf",
            }
        }
        res = generer_checklist(
            dce_analyse={"pieces_exigees": {"offre": ["Attestation de visite"]}},
            profil=profil,
            dossiers_docs=[tmp_path]
        )
        p_visite = next(p for p in res["offre"] if "visite" in p["piece"].lower())
        assert p_visite["present_disque"] is True
        assert p_visite["valide_juridiquement"] is False
        assert p_visite["statut"] == "A_OBTENIR"
        assert p_visite["statut"] != "VERIFIE_PRESENT"

    def test_markdown_rendu_badges_exhaustif(self, tmp_path: Path):
        """Vérifie que tous les badges de statuts sont supportés par generer_markdown_checklist."""
        profil_dummy = {
            "identite": {"raison_sociale": "Test Markdown"},
        }
        checklist = generer_checklist(dce_analyse={}, profil=profil_dummy, dossiers_docs=[tmp_path])
        md = generer_markdown_checklist(checklist)
        assert isinstance(md, str)
        assert len(md) > 200
        assert "None" not in md

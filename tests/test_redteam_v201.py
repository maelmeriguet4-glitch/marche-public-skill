"""
Tests adversariaux et de robustesse Red Team pour la version 2.0.1.
Couvre exhaustivement les 20 scénarios critiques d'attaque et de robustesse.
"""
import io
import json
import pytest
from decimal import Decimal
from unittest.mock import patch

from scripts.controle_final import auditer_dossier
from scripts.moteur_conformite import MoteurConformite, StatutConformite, VerdictConformite
from scripts.controle_prix import verifier_arithmetique, auditer_fichier_dpgf
from scripts.go_nogo import (
    verifier_visite_effectuee_profil,
    verifier_adequation_activites_assurance,
    verifier_assurances_go_nogo,
)
from scripts.checklist_pieces import generer_checklist
from scripts.dce_extract import extraire_dce, extraire_pdf
from scripts.api import resoudre_et_securiser_chemin


# Scénario 1 : Pièce obligatoire manquante déclarée conforme
def test_scenario_01_piece_obligatoire_manquante_declaree_conforme():
    analyse = {"calendrier": {"date_limite_retenue": "31/12/2030 à 12:00"}}
    checklist = {
        "candidature": [
            {
                "piece": "DC1",
                "obligatoire": True,
                "exige_par_marche": True,
                "present_disque": False,  # Manquante sur disque
                "valide_juridiquement": True,
                "verifie_contenu": True,
                "statut": "VERIFIE_PRESENT"  # Tentative de falsification de statut
            }
        ],
        "offre": [
            {
                "piece": "Acte d'engagement",
                "obligatoire": True,
                "exige_par_marche": True,
                "present_disque": True,
                "valide_juridiquement": True,
                "verifie_contenu": True,
                "statut": "VERIFIE_PRESENT"
            }
        ]
    }
    audit = auditer_dossier(
        analyse=analyse,
        checklist=checklist,
        prix={"total_recalcule_ht": "10000.00"},
        memoire_texte="Mémoire sans balise",
        delai_ae_semaines=4,
        montant_ae_ht=Decimal("10000.00")
    )
    assert audit["statut_code"] == "PAS_PRET"
    assert any(b["code"] == "INCOHERENCE_STATUT_4D" for b in audit["blocages"])


# Scénario 2 : Exigence éliminatoire ignorée
def test_scenario_02_exigence_eliminatoire_ignoree():
    analyse = {"calendrier": {"date_limite_retenue": "31/12/2030 à 12:00"}}
    checklist = {
        "candidature": [{
            "piece": "DC1", "obligatoire": True, "present_disque": True,
            "valide_juridiquement": True, "verifie_contenu": True, "statut": "VERIFIE_PRESENT"
        }],
        "offre": [{
            "piece": "AE", "obligatoire": True, "present_disque": True,
            "valide_juridiquement": True, "verifie_contenu": True, "statut": "VERIFIE_PRESENT"
        }]
    }
    matrice = {
        "exigences": [
            {
                "id": "EX-ELIM-01",
                "intitule": "Certification Qualibat 1413 obligatoire sous peine de rejet",
                "eliminatoire": True,
                "statut": "NON_VERIFIE"
            }
        ]
    }
    audit = auditer_dossier(
        analyse=analyse,
        checklist=checklist,
        prix={"total_recalcule_ht": "10000.00"},
        memoire_texte="Mémoire sans balise",
        matrice=matrice,
        delai_ae_semaines=4,
        montant_ae_ht=Decimal("10000.00")
    )
    assert audit["statut_code"] == "PAS_PRET"
    assert any(b["code"] == "EXIGENCES_ELIMINATOIRES_NON_VERIFIEES" for b in audit["blocages"])


# Scénario 3 : Attestation de visite sans date
def test_scenario_03_attestation_visite_sans_date(tmp_path):
    fich = tmp_path / "attestation_visite.pdf"
    fich.write_text("preuve de visite")
    profil = {
        "visite_site": {
            "effectuee": True,
            "attestation_fichier": str(fich),  # Preuve présente physiquement sur disque
            "date_visite": "",  # Date manquante
            "signee_acheteur": True
        }
    }
    valide, motif, code = verifier_visite_effectuee_profil(profil, dossiers_docs=[str(tmp_path)])
    assert not valide
    assert "date" in motif.lower() or code == "DATE_VISITE_MANQUANTE"


# Scénario 4 : Attestation de visite sans preuve exploitable
def test_scenario_04_attestation_visite_sans_preuve():
    profil = {
        "visite_site": {
            "effectuee": True,
            "attestation_fichier": "",  # Preuve absente
            "date_visite": "15/10/2026",
            "signee_acheteur": True
        }
    }
    valide, motif, code = verifier_visite_effectuee_profil(profil)
    assert not valide
    assert "justificatif" in motif.lower() or "fichier" in motif.lower() or "attestation" in motif.lower() or code == "ATTESTATION_NON_FOURNIE"


# Scénario 5 : Assurance périmée
def test_scenario_05_assurance_perimee(tmp_path):
    pdf = tmp_path / "decennale.pdf"
    pdf.write_text("assurance")
    analyse = {"objet": "Travaux de couverture", "est_travaux": True}
    profil = {
        "assurances": {
            "decennale": {
                "fichier": str(pdf),
                "date_validite": "01/01/2020",  # Périmée
                "activites_couvertes": ["Peinture", "Plâtrerie"]
            }
        }
    }
    drapeaux = verifier_assurances_go_nogo(analyse, profil, dossiers_docs=[str(tmp_path)])
    assert len(drapeaux) > 0
    assert any("périm" in d["motif"].lower() or "expir" in d["motif"].lower() or d["code"] == "ASSURANCE_DECENNALE_EXPIREE" for d in drapeaux)


# Scénario 6 : Assurance couvrant un métier différent
def test_scenario_06_assurance_metier_different():
    adéquat, msg = verifier_adequation_activites_assurance(
        activites_couvertes=["Peinture", "Plâtrerie"],
        objet_marche="Réfection de la charpente et couverture métallique du gymnase"
    )
    assert not adéquat
    assert "couverture" in msg.lower() or "charpente" in msg.lower()


# Scénario 7 : Extrait Kbis sans date ou périmé
def test_scenario_07_kbis_sans_date():
    profil = {
        "identite": {"date_kbis": None, "siret": "12345678900012", "rcs_ville": "Paris"},
        "fichiers": {"kbis": "kbis.pdf"}
    }
    checklist = generer_checklist(profil=profil, dce_analyse={"rc_texte": "Extrait Kbis obligatoire"})
    piece_kbis = next(p for p in checklist["candidature"] if "kbis" in p["piece"].lower())
    assert piece_kbis["statut"] != "VERIFIE_PRESENT"


# Scénario 8 : Document présent mais illisible (corrompu ou vide)
def test_scenario_08_document_illisible():
    from pathlib import Path
    res = extraire_pdf(Path("fichier_inexistant_ou_illisible.pdf"))
    assert res["texte_complet"] == ""
    assert len(res["alertes"]) > 0


# Scénario 9 : DPGF incohérente (incohérence prix x qté = total)
def test_scenario_09_dpgf_incoherente():
    lignes = [
        {"ligne_excel": 1, "numero": "01", "designation": "Démolition", "unite": "u", "quantite": Decimal("10"), "prix_unitaire_ht": Decimal("100"), "total_ligne_excel": Decimal("1500")}  # 10x100 = 1000 != 1500
    ]
    res = verifier_arithmetique(lignes, Decimal("1500"), taux_tva=Decimal("20.0"))
    assert res["statut_arithmetique"] != "CONFORME"
    assert len(res["erreurs_arithmetiques"]) > 0


# Scénario 10 : BPU incomplet (prix unitaire manquant / non renseigné)
def test_scenario_10_bpu_incomplet():
    lignes = [
        {"ligne_excel": 1, "numero": "BPU-01", "designation": "Pose robinet", "unite": "u", "quantite": Decimal("1"), "prix_unitaire_ht": Decimal("0"), "total_ligne_excel": Decimal("0")}
    ]
    res = verifier_arithmetique(lignes, Decimal("0"), taux_tva=Decimal("20.0"))
    assert res["statut_arithmetique"] != "CONFORME"
    assert any("PRIX_MANQUANT" in a["type"] for a in res["erreurs_arithmetiques"])


# Scénario 11 : Deux documents contradictoires dans le DCE
def test_scenario_11_documents_contradictoires():
    analyse = {
        "calendrier": {"date_limite_retenue": "31/12/2030 à 12:00"},
        "contradictions_detectees": [
            {
                "code": "CONTRADICTION_DCE_BLOQUANTE",
                "gravite": "BLOQUANT",
                "description": "Le RC impose 12 semaines alors que le CCTP fixe 24 semaines impératives."
            }
        ]
    }
    checklist = {
        "candidature": [{"piece": "DC1", "obligatoire": True, "present_disque": True, "valide_juridiquement": True, "verifie_contenu": True, "statut": "VERIFIE_PRESENT"}],
        "offre": [{"piece": "AE", "obligatoire": True, "present_disque": True, "valide_juridiquement": True, "verifie_contenu": True, "statut": "VERIFIE_PRESENT"}]
    }
    audit = auditer_dossier(
        analyse=analyse,
        checklist=checklist,
        prix={"total_recalcule_ht": "10000.00"},
        memoire_texte="Mémoire sans balise",
        delai_ae_semaines=12,
        montant_ae_ht=Decimal("10000.00")
    )
    assert audit["statut_code"] == "PAS_PRET"
    assert any("CONTRADICTION_DCE_BLOQUANTE" in b["code"] for b in audit["blocages"])


# Scénario 12 : Mauvaise version de document
def test_scenario_12_mauvaise_version_document():
    checklist = {
        "candidature": [
            {
                "piece": "DC1",
                "statut": "A_METTRE_A_JOUR",
                "obligatoire": True,
                "version_detectee": "v1.0-obsolete",
                "present_disque": True,
                "valide_juridiquement": False,
                "verifie_contenu": True
            }
        ],
        "offre": [{"piece": "AE", "obligatoire": True, "present_disque": True, "valide_juridiquement": True, "verifie_contenu": True, "statut": "VERIFIE_PRESENT"}]
    }
    audit = auditer_dossier(
        analyse={"calendrier": {"date_limite_retenue": "31/12/2030"}},
        checklist=checklist,
        prix={"total_recalcule_ht": "10000.00"},
        memoire_texte="Mémoire",
        delai_ae_semaines=4,
        montant_ae_ht=Decimal("10000.00")
    )
    assert audit["statut_code"] == "PAS_PRET"


# Scénario 13 : Fichier PDF malformé
def test_scenario_13_pdf_malforme(tmp_path):
    from pathlib import Path
    pdf_corrompu = tmp_path / "corrompu.pdf"
    pdf_corrompu.write_bytes(b"%PDF-1.4\n%%EOF\x00\xff\xfeTRUNCATED_GARBAGE")
    res = extraire_pdf(pdf_corrompu)
    assert res["texte_complet"] == ""
    assert len(res["alertes"]) > 0


# Scénario 14 : Fichier XLSX complexe avec lignes masquées
def test_scenario_14_xlsx_lignes_masquees(tmp_path):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DPGF"
    ws.append(["Code", "Désignation", "Quantité", "Prix Unitaire", "Montant HT"])
    ws.append(["01", "Travaux visibles", 1, 100, 100])
    ws.append(["02", "Travaux cachés masqués", 10, 500, 5000])
    ws.row_dimensions[3].hidden = True
    wb_path = tmp_path / "dpgf_hidden.xlsx"
    wb.save(wb_path)

    res = auditer_fichier_dpgf(str(wb_path))
    assert res["lignes_masquees"] == [3]
    assert any("LIGNE_MASQUEE" in a.get("type", "") for a in res["anomalies"])


# Scénario 15 : Données malformées passées au moteur de conformité
def test_scenario_15_json_malforme_moteur():
    moteur = MoteurConformite()
    moteur.charger_depuis_checklist(["liste", "invalide"])
    assert any("CHECKLIST_STRUCTURE_INVALIDE" in a["code"] for a in moteur.anomalies_externes)


# Scénario 16 : Chemin de fichier malveillant (Path Traversal / Répertoire système)
def test_scenario_16_chemin_malveillant():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        resoudre_et_securiser_chemin("../../../etc/passwd")

    with pytest.raises(HTTPException):
        resoudre_et_securiser_chemin("C:\\Windows\\System32\\cmd.exe")


# Scénario 17 : Fausse preuve déclarée valide (preuve vide ou whitespace)
def test_scenario_17_fausse_preuve_declaree_valide():
    checklist = {
        "candidature": [
            {
                "piece": "Attestation fiscale",
                "obligatoire": True,
                "present_disque": True,
                "valide_juridiquement": True,
                "verifie_contenu": True,
                "statut": "VERIFIE_PRESENT",
                "chemin_fichier": "   "  # Whitespace / faux chemin
            }
        ],
        "offre": [{"piece": "AE", "obligatoire": True, "present_disque": True, "valide_juridiquement": True, "verifie_contenu": True, "statut": "VERIFIE_PRESENT"}]
    }
    audit = auditer_dossier(
        analyse={"calendrier": {"date_limite_retenue": "31/12/2030"}},
        checklist=checklist,
        prix={"total_recalcule_ht": "10000.00"},
        memoire_texte="Mémoire",
        delai_ae_semaines=4,
        montant_ae_ht=Decimal("10000.00")
    )
    assert audit["statut_code"] == "PAS_PRET"
    assert any(b["code"] == "EXIGENCE_OBLIGATOIRE_SANS_PREUVE" for b in audit["blocages"])


# Scénario 18 : Extraction erronée de date limite (date dépassée)
def test_scenario_18_date_limite_depassee():
    analyse = {"calendrier": {"date_limite_retenue": "01/01/2020 à 12:00"}}  # Dans le passé
    checklist = {
        "candidature": [{"piece": "DC1", "obligatoire": True, "present_disque": True, "valide_juridiquement": True, "verifie_contenu": True, "statut": "VERIFIE_PRESENT"}],
        "offre": [{"piece": "AE", "obligatoire": True, "present_disque": True, "valide_juridiquement": True, "verifie_contenu": True, "statut": "VERIFIE_PRESENT"}]
    }
    audit = auditer_dossier(
        analyse=analyse,
        checklist=checklist,
        prix={"total_recalcule_ht": "10000.00"},
        memoire_texte="Mémoire",
        delai_ae_semaines=4,
        montant_ae_ht=Decimal("10000.00")
    )
    assert audit["statut_code"] == "PAS_PRET"
    assert any(b["code"] == "DATE_LIMITE_DEPASSEE" for b in audit["blocages"])


# Scénario 19 : Exigence obligatoire traitée comme facultative
def test_scenario_19_exigence_obligatoire_traitee_facultative():
    checklist = {
        "candidature": [
            {
                "piece": "DC1",
                "exige_par_marche": True,
                "obligatoire": True,
                "statut": "FACULTATIF"  # Contournement interdit
            }
        ],
        "offre": [{"piece": "AE", "obligatoire": True, "present_disque": True, "valide_juridiquement": True, "verifie_contenu": True, "statut": "VERIFIE_PRESENT"}]
    }
    audit = auditer_dossier(
        analyse={"calendrier": {"date_limite_retenue": "31/12/2030"}},
        checklist=checklist,
        prix={"total_recalcule_ht": "10000.00"},
        memoire_texte="Mémoire",
        delai_ae_semaines=4,
        montant_ae_ht=Decimal("10000.00")
    )
    assert audit["statut_code"] == "PAS_PRET"
    assert any(b["code"] == "PIECE_OBLIGATOIRE_STATUT_FACULTATIF" for b in audit["blocages"])


# Scénario 20 : Exception interne lors de l'analyse (résilience fail-closed)
def test_scenario_20_resilience_exception_moteur():
    from scripts.moteur_conformite import ExigenceConformite, CategorieExigence
    moteur = MoteurConformite()
    # Forcer une rupture d'invariant interne
    moteur.ajouter_exigence(
        ExigenceConformite(
            id="EX-01",
            categorie=CategorieExigence.ADMINISTRATIVE,
            description="Exigence critique",
            source_reglementaire_ou_dce="DCE",
            statut=StatutConformite.VERIFIE_PRESENT,
            obligatoire=True,
            eliminatoire=True,
            present_disque=False,  # Violation d'invariant
            valide_juridiquement=True,
            verifie_contenu=True
        )
    )
    verdict = moteur.synthetiser()
    assert verdict["verdict"] in [VerdictConformite.NO_GO.value, VerdictConformite.NON_EVALUABLE.value]
    assert len(verdict["anomalies"]) > 0

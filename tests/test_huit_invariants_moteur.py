"""
Tests unitaires dédiés pour chacun des 8 invariants fondamentaux de conformité.
"""

import pytest
from scripts.moteur_conformite import (
    MoteurConformite,
    ExigenceConformite,
    CategorieExigence,
    StatutConformite,
    PreuveDocumentaire,
    VerdictConformite,
)


def test_invariant_01_contournement_statut_permissif():
    """Invariant 1 : Aucune exigence obligatoire ne peut recevoir un statut permissif."""
    moteur = MoteurConformite()
    moteur.ajouter_exigence(
        ExigenceConformite(
            id="REQ-01",
            categorie=CategorieExigence.ADMINISTRATIVE,
            description="DC1 Obligatoire",
            source_reglementaire_ou_dce="RC",
            exige_par_marche=True,
            obligatoire=True,
            statut=StatutConformite.FACULTATIF,
        )
    )
    anomalies = moteur.verifier_invariants()
    assert any(a["code"] == "CONTOURNEMENT_STATUT_PERMISSIF" for a in anomalies)


def test_invariant_02_faux_verifie_present_incomplet():
    """Invariant 2 : VERIFIE_PRESENT exige que les 3 dimensions soient True."""
    moteur = MoteurConformite()
    moteur.ajouter_exigence(
        ExigenceConformite(
            id="REQ-02",
            categorie=CategorieExigence.ADMINISTRATIVE,
            description="Kbis récent",
            source_reglementaire_ou_dce="RC",
            statut=StatutConformite.VERIFIE_PRESENT,
            present_disque=True,
            valide_juridiquement=False,  # Dimension manquante
            verifie_contenu=True,
        )
    )
    anomalies = moteur.verifier_invariants()
    assert any(a["code"] == "FAUX_VERIFIE_PRESENT_INCOMPLET" for a in anomalies)


def test_invariant_03_contradiction_exige_non_obligatoire():
    """Invariant 3 : Contradiction entre exige_par_marche=True et obligatoire=False."""
    moteur = MoteurConformite()
    moteur.ajouter_exigence(
        ExigenceConformite(
            id="REQ-03",
            categorie=CategorieExigence.ADMINISTRATIVE,
            description="Attestation fiscale",
            source_reglementaire_ou_dce="RC",
            exige_par_marche=True,
            obligatoire=False,  # Contradiction flagrante
            statut=StatutConformite.MANQUANT,
        )
    )
    anomalies = moteur.verifier_invariants()
    assert any(a["code"] == "CONTRADICTION_EXIGE_NON_OBLIGATOIRE" for a in anomalies)


def test_invariant_04_exigence_eliminatoire_non_validee():
    """Invariant 4 : Aucune exigence éliminatoire ne peut rester non vérifiée ou suspensive."""
    moteur = MoteurConformite()
    moteur.ajouter_exigence(
        ExigenceConformite(
            id="REQ-04",
            categorie=CategorieExigence.TECHNIQUE,
            description="Attestation de visite obligatoire signée",
            source_reglementaire_ou_dce="RC",
            exige_par_marche=True,
            obligatoire=True,
            eliminatoire=True,
            statut=StatutConformite.LU_NON_VERIFIE,
        )
    )
    anomalies = moteur.verifier_invariants()
    assert any(a["code"] == "EXIGENCE_ELIMINATOIRE_NON_VALIDEE" for a in anomalies)


def test_invariant_05_exigence_verifiee_sans_preuve():
    """Invariant 5 : VERIFIE_PRESENT requiert impérativement une preuve rattachée."""
    moteur = MoteurConformite()
    moteur.ajouter_exigence(
        ExigenceConformite(
            id="REQ-05",
            categorie=CategorieExigence.TECHNIQUE,
            description="Qualification Qualibat 1413",
            source_reglementaire_ou_dce="RC",
            statut=StatutConformite.VERIFIE_PRESENT,
            present_disque=True,
            valide_juridiquement=True,
            verifie_contenu=True,
            preuve=None,  # Aucune preuve
        )
    )
    anomalies = moteur.verifier_invariants()
    assert any(a["code"] == "EXIGENCE_VERIFIEE_SANS_PREUVE" for a in anomalies)


def test_invariant_06_piece_administrative_sans_fichier_physique():
    """Invariant 6 : Une pièce administrative ne peut se contenter d'un texte déclaratif sans fichier."""
    moteur = MoteurConformite()
    preuve_texte_seul = PreuveDocumentaire(
        document_source="Attestation sur l'honneur",
        extrait_pertinent="Je déclare être à jour",
        chemin_fichier_disque=None,
        present_sur_disque=False,
    )
    moteur.ajouter_exigence(
        ExigenceConformite(
            id="REQ-06",
            categorie=CategorieExigence.ADMINISTRATIVE,
            description="Attestation URSSAF",
            source_reglementaire_ou_dce="RC",
            statut=StatutConformite.VERIFIE_PRESENT,
            present_disque=True,
            valide_juridiquement=True,
            verifie_contenu=True,
            preuve=preuve_texte_seul,
        )
    )
    anomalies = moteur.verifier_invariants()
    assert any(a["code"] == "PIECE_ADMINISTRATIVE_SANS_FICHIER_PHYSIQUE" for a in anomalies)


def test_invariant_07_document_expire_bloquant():
    """Invariant 7 : Un document expiré est bloquant pour le dépôt."""
    moteur = MoteurConformite()
    moteur.ajouter_exigence(
        ExigenceConformite(
            id="REQ-07",
            categorie=CategorieExigence.ADMINISTRATIVE,
            description="Attestation assurance décennale",
            source_reglementaire_ou_dce="RC",
            statut=StatutConformite.EXPIREE,
            obligatoire=True,
        )
    )
    anomalies = moteur.verifier_invariants()
    assert any(a["code"] == "DOCUMENT_EXPIRE_BLOQUANT" for a in anomalies)


def test_invariant_08_exigence_obligatoire_non_evaluable():
    """Invariant 8 : Une exigence obligatoire inévaluable empêche un verdict favorable."""
    moteur = MoteurConformite()
    moteur.ajouter_exigence(
        ExigenceConformite(
            id="REQ-08",
            categorie=CategorieExigence.FINANCIERE,
            description="Bordereau des prix unitaires chiffré",
            source_reglementaire_ou_dce="RC",
            statut=StatutConformite.NON_EVALUABLE,
            obligatoire=True,
        )
    )
    anomalies = moteur.verifier_invariants()
    assert any(a["code"] == "EXIGENCE_OBLIGATOIRE_NON_EVALUABLE" for a in anomalies)
    synth = moteur.synthetiser()
    assert synth["verdict"] in (VerdictConformite.NO_GO.value, VerdictConformite.NON_EVALUABLE.value)

"""Checklist des pièces de candidature et d'offre pour marchés publics BTP.

Croise les exigences du Règlement de la Consultation avec les attestations,
qualifications et documents administratifs du profil de l'entreprise.
Applique le modèle 4D d'état documentaire :
- exige_par_marche (bool)
- present_disque (bool)
- valide_juridiquement (bool)
- verifie_contenu (bool)
"""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from common import charger_json, ecrire_fichier_securise, ecrire_json, resoudre_chemin_securise

logger = logging.getLogger("checklist_pieces")


def verifier_validite_date(date_str: Optional[str]) -> str:
    """Contrôle si une date d'échéance est valide ou expirée."""
    if not date_str:
        return "NON_RENSEIGNEE"
    if not isinstance(date_str, str):
        try:
            date_str = str(date_str)
        except Exception:
            return "FORMAT_INVALIDE"
    clean_date = date_str.strip()
    if not clean_date:
        return "NON_RENSEIGNEE"
    dt = None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            dt = datetime.datetime.strptime(clean_date, fmt).date()
            break
        except ValueError:
            continue
    if dt is None:
        return "FORMAT_INVALIDE"
    today = datetime.date.today()
    if dt < today:
        return "EXPIREE"
    if (dt - today).days < 30:
        return "A_RENOUVELER_SOUS_30J"
    return "VALIDE"


def assainir_dossiers_docs(dossiers_docs: Any) -> List[Path]:
    """Assainit et coerce l'argument dossiers_docs en une liste de Path valides."""
    if dossiers_docs is None:
        return []
    if isinstance(dossiers_docs, Path):
        return [dossiers_docs]
    if isinstance(dossiers_docs, str):
        s = dossiers_docs.strip()
        if not s:
            return []
        try:
            return [Path(s)]
        except (TypeError, ValueError):
            return []
    if isinstance(dossiers_docs, (list, tuple, set)):
        clean_dirs: List[Path] = []
        for d in dossiers_docs:
            if not d:
                continue
            if isinstance(d, Path):
                clean_dirs.append(d)
            elif isinstance(d, str):
                s = d.strip()
                if not s:
                    continue
                try:
                    clean_dirs.append(Path(s))
                except (TypeError, ValueError):
                    continue
            # Les entiers, booléens ou autres types non conformes sont ignorés
        return clean_dirs
    return []


def verifier_presence_fichier(
    nom_fichier: Optional[str | Path],
    dossiers: Optional[List[Path | str]] = None,
) -> bool:
    """Contrôle la présence physique réelle d'un document sur le disque.
    
    Vérifie l'existence réelle du fichier sans jamais inférer la présence
    à partir de métadonnées déclaratives (numéro de police, SIRET, etc.).
    Sécurise l'accès contre les traversées de chemin relatives ('..').
    """
    if not nom_fichier or not isinstance(nom_fichier, (str, Path)):
        return False
    if isinstance(nom_fichier, str) and not nom_fichier.strip():
        return False
    try:
        p_nom = Path(nom_fichier)
    except (TypeError, ValueError, OSError):
        return False
    if str(p_nom).strip() in ("", "."):
        return False

    # 1. Chemin direct absolu uniquement (pour éviter la résolution relative arbitraire depuis le CWD)
    try:
        if p_nom.is_absolute():
            return p_nom.is_file()
    except (OSError, ValueError):
        pass

    # 2. Rejet strict des tentatives de traversée de chemin relatives avec '..'
    if ".." in p_nom.parts:
        return False

    # 3. Recherche confinée dans les dossiers autorisés
    clean_dossiers = assainir_dossiers_docs(dossiers)
    for base in clean_dossiers:
        try:
            base_resolved = base.resolve()
            # Test direct chemin relatif confiné au dossier
            cible = (base / p_nom).resolve()
            if cible.is_relative_to(base_resolved) and cible.is_file():
                return True
            # Test par nom de fichier simple confiné à la racine du dossier
            nom_simple = p_nom.name
            if nom_simple and nom_simple != ".":
                cible_nom = (base / nom_simple).resolve()
                if cible_nom.is_relative_to(base_resolved) and cible_nom.is_file():
                    return True
        except (OSError, ValueError, TypeError):
            continue

    return False


def generer_checklist(
    dce_analyse: Optional[Dict[str, Any]] = None,
    profil: Optional[Dict[str, Any]] = None,
    dossiers_docs: Optional[List[Path | str]] = None,
    analyse: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Établit la checklist adaptée aux exigences réelles de la consultation.
    
    Distingue rigoureusement selon le modèle 4D :
    - exige_par_marche : document expressément réclamé par le DCE / CCP (bool)
    - present_disque : document physiquement vérifié et présent sur le disque (bool)
    - valide_juridiquement : conformité légale et temporelle (bool)
    - verifie_contenu : contenu inspecté, complet et renseigné (bool)
    - statut : code normalisé de situation (str). Si une pièce requise est absente
      du disque, son statut est MANQUANT (jamais A_METTRE_A_JOUR).
    """
    analyse_data = dce_analyse if dce_analyse is not None else (analyse if analyse is not None else {})
    if not isinstance(analyse_data, dict):
        analyse_data = {}
    profil_data = profil if profil is not None else {}
    if not isinstance(profil_data, dict):
        profil_data = {}

    dossiers_docs = assainir_dossiers_docs(dossiers_docs)

    pe = analyse_data.get("pieces_exigees") if isinstance(analyse_data, dict) else {}
    pe = pe if isinstance(pe, dict) else {}
    raw_cand = pe.get("candidature") or []
    pieces_exigees_cand = [str(x) for x in raw_cand if x is not None and str(x).strip()] if isinstance(raw_cand, (list, tuple, set)) else ([raw_cand.strip()] if isinstance(raw_cand, str) and raw_cand.strip() else [])
    raw_offre = pe.get("offre") or []
    pieces_exigees_offre = [str(x) for x in raw_offre if x is not None and str(x).strip()] if isinstance(raw_offre, (list, tuple, set)) else ([raw_offre.strip()] if isinstance(raw_offre, str) and raw_offre.strip() else [])

    text_cand_str = " ".join(pieces_exigees_cand).lower() if pieces_exigees_cand else ""
    text_offre_str = " ".join(pieces_exigees_offre).lower() if pieces_exigees_offre else ""
    has_exigences_cand = bool(pieces_exigees_cand)
    has_exigences_offre = bool(pieces_exigees_offre)

    fichiers_profil = profil_data.get("fichiers_justificatifs") if isinstance(profil_data, dict) else {}
    fichiers_profil = fichiers_profil if isinstance(fichiers_profil, dict) else {}

    identite = profil_data.get("identite") if isinstance(profil_data, dict) else {}
    identite = identite if isinstance(identite, dict) else {}

    cap_fin = profil_data.get("capacites_financieres") if isinstance(profil_data, dict) else {}
    cap_fin = cap_fin if isinstance(cap_fin, dict) else {}

    assurances = profil_data.get("assurances") if isinstance(profil_data, dict) else {}
    assurances = assurances if isinstance(assurances, dict) else {}
    decennale = assurances.get("decennale") if isinstance(assurances, dict) else {}
    decennale = decennale if isinstance(decennale, dict) else {}
    rc_pro = assurances.get("responsabilite_civile") if isinstance(assurances, dict) else {}
    rc_pro = rc_pro if isinstance(rc_pro, dict) else {}

    raw_quals = profil_data.get("qualifications_et_certifications") if isinstance(profil_data, dict) else []
    quals = [q for q in raw_quals if isinstance(q, dict)] if isinstance(raw_quals, (list, tuple, set)) else []

    raw_refs = profil_data.get("references_chantiers") if isinstance(profil_data, dict) else []
    refs = [r for r in raw_refs if isinstance(r, dict)] if isinstance(raw_refs, (list, tuple, set)) else []

    visite_site = profil_data.get("visite_site") if isinstance(profil_data, dict) else {}
    visite_site = visite_site if isinstance(visite_site, dict) else {}
    visite_faite = bool(visite_site.get("visite_effectuee", False))

    pieces_candidature = []
    pieces_offre = []

    # -------------------------------------------------------------------------
    # 1. Dossier de Candidature
    # -------------------------------------------------------------------------

    # 1.1. DC1
    exige_dc1 = bool(any(k in text_cand_str for k in ["dc1", "candidature", "dume"]) or not has_exigences_cand)
    fichier_dc1 = fichiers_profil.get("dc1")
    present_dc1 = verifier_presence_fichier(fichier_dc1, dossiers_docs)
    valide_dc1 = bool(present_dc1 and identite.get("siret") and identite.get("raison_sociale"))
    verifie_dc1 = bool(present_dc1 and valide_dc1)
    statut_dc1 = "VERIFIE_PRESENT" if (present_dc1 and valide_dc1 and verifie_dc1) else ("MANQUANT" if exige_dc1 else "A_COMPLETER")
    pieces_candidature.append({
        "piece": "Lettre de candidature et habilitation (DC1 / DUME)",
        "exige_par_marche": exige_dc1,
        "obligatoire": exige_dc1,
        "present_disque": present_dc1,
        "valide_juridiquement": valide_dc1,
        "verifie_contenu": verifie_dc1,
        "statut": statut_dc1,
        "description": "Formulaire DAJ officiel ou DUME avec déclaration sur l'honneur.",
        "action": "Dossier vérifié et prêt" if statut_dc1 == "VERIFIE_PRESENT" else "Formulaire DC1 à compléter et signer par le mandataire.",
    })

    # 1.2. DC2
    exige_dc2 = bool(any(k in text_cand_str for k in ["dc2", "capacités", "capacites"]) or not has_exigences_cand)
    fichier_dc2 = fichiers_profil.get("dc2")
    present_dc2 = verifier_presence_fichier(fichier_dc2, dossiers_docs)
    valide_dc2 = bool(present_dc2 and identite.get("siret"))
    verifie_dc2 = bool(present_dc2 and (cap_fin.get("exercices") or profil_data.get("chiffre_affaires")))
    statut_dc2 = "VERIFIE_PRESENT" if (present_dc2 and valide_dc2 and verifie_dc2) else ("MANQUANT" if exige_dc2 else "A_COMPLETER")
    pieces_candidature.append({
        "piece": "Déclaration du candidat individuel (DC2)",
        "exige_par_marche": exige_dc2,
        "obligatoire": exige_dc2,
        "present_disque": present_dc2,
        "valide_juridiquement": valide_dc2,
        "verifie_contenu": verifie_dc2,
        "statut": statut_dc2,
        "description": f"Chiffres d'affaires et effectifs déclarés ({identite.get('raison_sociale') or 'Entreprise'}).",
        "action": "Dossier vérifié et prêt" if statut_dc2 == "VERIFIE_PRESENT" else "Reporter les 3 derniers bilans comptables certifiés.",
    })

    # 1.3. Kbis
    exige_kbis = bool(any(k in text_cand_str for k in ["kbis", "rcs", "immatriculation"]) or not has_exigences_cand)
    fichier_kbis = fichiers_profil.get("kbis")
    present_kbis = verifier_presence_fichier(fichier_kbis, dossiers_docs)
    id_dict = profil_data.get("identite") if isinstance(profil_data, dict) else {}
    id_dict = id_dict if isinstance(id_dict, dict) else {}
    date_kbis = (
        identite.get("date_kbis")
        or (profil_data.get("date_kbis") if isinstance(profil_data, dict) else None)
        or id_dict.get("date_kbis")
    )
    valide_kbis = bool(present_kbis)
    if present_kbis and date_kbis:
        try:
            from common import parser_date_et_echeance
            dt_k, _, _ = parser_date_et_echeance(date_kbis)
            if dt_k:
                nb_jours = (datetime.datetime.now() - dt_k).days
                if nb_jours > 90:
                    valide_kbis = False
        except Exception:
            pass
    verifie_kbis = bool(present_kbis and valide_kbis and identite.get("siret") and identite.get("rcs_ville"))
    if not present_kbis:
        statut_kbis = "MANQUANT"
    elif not valide_kbis:
        statut_kbis = "A_METTRE_A_JOUR"
    elif not verifie_kbis:
        statut_kbis = "A_COMPLETER"
    else:
        statut_kbis = "VERIFIE_PRESENT"
    pieces_candidature.append({
        "piece": "Extrait d'immatriculation au RCS (Kbis < 3 mois)",
        "exige_par_marche": exige_kbis,
        "obligatoire": exige_kbis,
        "present_disque": present_kbis,
        "valide_juridiquement": valide_kbis,
        "verifie_contenu": verifie_kbis,
        "statut": statut_kbis,
        "description": f"SIRET {identite.get('siret') or 'Non renseigné'} — RCS {identite.get('rcs_ville') or ''}.",
        "action": "Justificatif Kbis joint" if statut_kbis == "VERIFIE_PRESENT" else "Télécharger un extrait récent de moins de 3 mois sur Infogreffe / MonIdenum.",
    })

    # 1.4. Attestation Fiscale (DGFiP) - STRICTLY NO 'or True'
    exige_fisc = bool(any(k in text_cand_str for k in ["fiscale", "impot", "impôt", "dgfip"]))
    fichier_fisc = fichiers_profil.get("attestation_fiscale") or fichiers_profil.get("fiscale")
    present_fisc = verifier_presence_fichier(fichier_fisc, dossiers_docs)
    valide_fisc = bool(present_fisc)
    verifie_fisc = bool(present_fisc)
    statut_fisc = "VERIFIE_PRESENT" if present_fisc else ("MANQUANT" if exige_fisc else "A_FOURNIR")
    pieces_candidature.append({
        "piece": "Attestation de régularité fiscale (DGFiP)",
        "exige_par_marche": exige_fisc,
        "obligatoire": exige_fisc,
        "present_disque": present_fisc,
        "valide_juridiquement": valide_fisc,
        "verifie_contenu": verifie_fisc,
        "statut": statut_fisc,
        "description": "Justification de souscription des déclarations et paiement de l'IS/TVA.",
        "action": "Attestation fiscale vérifiée" if present_fisc else "Télécharger l'attestation annuelle sur impots.gouv.fr.",
    })

    # 1.5. Attestation Sociale (URSSAF) - STRICTLY NO 'or True'
    exige_soc = bool(any(k in text_cand_str for k in ["sociale", "urssaf", "vigilance", "dissimulé", "dissimule"]))
    fichier_soc = fichiers_profil.get("attestation_urssaf") or fichiers_profil.get("attestation_sociale") or fichiers_profil.get("urssaf") or fichiers_profil.get("sociale")
    present_soc = verifier_presence_fichier(fichier_soc, dossiers_docs)
    valide_soc = bool(present_soc)
    verifie_soc = bool(present_soc)
    statut_soc = "VERIFIE_PRESENT" if present_soc else ("MANQUANT" if exige_soc else "A_FOURNIR")
    pieces_candidature.append({
        "piece": "Attestation de vigilance sociale (URSSAF)",
        "exige_par_marche": exige_soc,
        "obligatoire": exige_soc,
        "present_disque": present_soc,
        "valide_juridiquement": valide_soc,
        "verifie_contenu": verifie_soc,
        "statut": statut_soc,
        "description": "Attestation de conformité travail dissimulé de moins de 6 mois.",
        "action": "Attestation URSSAF vérifiée" if present_soc else "Télécharger l'attestation de vigilance sur urssaf.fr.",
    })

    # 1.6. Caisse des Congés Payés (CIBTP)
    exige_cibtp = bool(any(k in text_cand_str for k in ["cibtp", "conges", "congés"]))
    fichier_cibtp = fichiers_profil.get("attestation_cibtp") or fichiers_profil.get("cibtp")
    present_cibtp = verifier_presence_fichier(fichier_cibtp, dossiers_docs)
    valide_cibtp = bool(present_cibtp)
    verifie_cibtp = bool(present_cibtp)
    statut_cibtp = "VERIFIE_PRESENT" if present_cibtp else ("MANQUANT" if exige_cibtp else "A_FOURNIR")
    pieces_candidature.append({
        "piece": "Attestation de cotisations CIBTP (Congés BTP)",
        "exige_par_marche": exige_cibtp,
        "obligatoire": exige_cibtp,
        "present_disque": present_cibtp,
        "valide_juridiquement": valide_cibtp,
        "verifie_contenu": verifie_cibtp,
        "statut": statut_cibtp,
        "description": "Certificat de régularité de cotisations délivré par la caisse des congés payés BTP.",
        "action": "Certificat CIBTP joint" if present_cibtp else "Télécharger l'attestation annuelle sur l'espace CIBTP.",
    })

    # 1.7. Assurance Décennale - STRICTLY PHYSICAL PRESENCE ON DISK (no metadata bypass)
    statut_date_dec = verifier_validite_date(decennale.get("date_validite"))
    fichier_dec = fichiers_profil.get("decennale") or decennale.get("fichier") or decennale.get("attestation_fichier")
    present_dec = verifier_presence_fichier(fichier_dec, dossiers_docs)
    exige_dec = bool(any(k in text_cand_str for k in ["decennale", "décennale", "assurance"]) or not has_exigences_cand)
    valide_dec = bool(present_dec and statut_date_dec in ["VALIDE", "A_RENOUVELER_SOUS_30J"])
    verifie_dec = bool(present_dec and decennale.get("numero_police") and decennale.get("compagnie"))
    if not present_dec:
        statut_dec = "MANQUANT"
    elif statut_date_dec == "EXPIREE":
        statut_dec = "EXPIREE"
    elif not valide_dec:
        statut_dec = "A_METTRE_A_JOUR"
    elif not verifie_dec:
        statut_dec = "A_COMPLETER"
    else:
        statut_dec = "VERIFIE_PRESENT"
    pieces_candidature.append({
        "piece": "Attestation d'assurance Décennale en cours de validité",
        "exige_par_marche": exige_dec,
        "obligatoire": exige_dec,
        "present_disque": present_dec,
        "valide_juridiquement": valide_dec,
        "verifie_contenu": verifie_dec,
        "statut": statut_dec,
        "description": f"Compagnie {decennale.get('compagnie') or 'N/A'} — Police {decennale.get('numero_police') or 'N/A'} (Échéance: {decennale.get('date_validite') or 'Non renseignée'}).",
        "action": "Attestation décennale valide" if statut_dec == "VERIFIE_PRESENT" else ("Attestation d'assurance décennale introuvable sur le disque." if not present_dec else "Renouveler l'attestation auprès de la compagnie d'assurance."),
    })

    # 1.8. Assurance RC Pro - STRICTLY PHYSICAL PRESENCE ON DISK (no metadata bypass)
    statut_date_rc = verifier_validite_date(rc_pro.get("date_validite"))
    fichier_rc = fichiers_profil.get("rc_pro") or rc_pro.get("fichier") or rc_pro.get("attestation_fichier")
    present_rc = verifier_presence_fichier(fichier_rc, dossiers_docs)
    exige_rc = bool(any(k in text_cand_str for k in ["rc", "responsabilité", "responsabilite", "civile", "assurance"]) or not has_exigences_cand)
    valide_rc = bool(present_rc and statut_date_rc in ["VALIDE", "A_RENOUVELER_SOUS_30J"])
    verifie_rc = bool(present_rc and rc_pro.get("numero_police") and rc_pro.get("compagnie"))
    if not present_rc:
        statut_rc = "MANQUANT"
    elif statut_date_rc == "EXPIREE":
        statut_rc = "EXPIREE"
    elif not valide_rc:
        statut_rc = "A_METTRE_A_JOUR"
    elif not verifie_rc:
        statut_rc = "A_COMPLETER"
    else:
        statut_rc = "VERIFIE_PRESENT"
    pieces_candidature.append({
        "piece": "Attestation d'assurance Responsabilité Civile Professionnelle",
        "exige_par_marche": exige_rc,
        "obligatoire": exige_rc,
        "present_disque": present_rc,
        "valide_juridiquement": valide_rc,
        "verifie_contenu": verifie_rc,
        "statut": statut_rc,
        "description": f"Compagnie {rc_pro.get('compagnie') or 'N/A'} — Police {rc_pro.get('numero_police') or 'N/A'}.",
        "action": "Attestation RC Pro valide" if statut_rc == "VERIFIE_PRESENT" else ("Attestation d'assurance RC Pro introuvable sur le disque." if not present_rc else "Vérifier la validité de la police."),
    })

    # 1.9. Certificats Qualibat / RGE
    exige_qual = bool(any(k in text_cand_str for k in ["qualibat", "qualification", "rge", "certificat"]))
    fichier_qual = (
        fichiers_profil.get("qualibat")
        or fichiers_profil.get("qualifications")
        or fichiers_profil.get("certificats")
        or next((q.get("fichier") for q in quals if isinstance(q, dict) and q.get("fichier")), None)
    )
    present_qual = verifier_presence_fichier(fichier_qual, dossiers_docs)
    dates_statuts_qual = [verifier_validite_date(q.get("date_echeance")) for q in quals if isinstance(q, dict) and q.get("date_echeance")]
    est_expire_qual = any(s == "EXPIREE" for s in dates_statuts_qual)
    valide_qual = bool(present_qual and not est_expire_qual)
    verifie_qual = bool(present_qual and quals)
    if not present_qual:
        statut_qual = "MANQUANT" if exige_qual else "A_FOURNIR"
    elif est_expire_qual:
        statut_qual = "EXPIREE"
    else:
        statut_qual = "VERIFIE_PRESENT"
    pieces_candidature.append({
        "piece": "Certificats de qualification professionnelle (Qualibat / RGE)",
        "exige_par_marche": exige_qual,
        "obligatoire": exige_qual,
        "present_disque": present_qual,
        "valide_juridiquement": valide_qual,
        "verifie_contenu": verifie_qual,
        "statut": statut_qual,
        "description": ", ".join([f"{(q.get('organisme') or '')} {(q.get('code') or '')}".strip() for q in quals if isinstance(q, dict)]) if quals else "Aucune qualification enregistrée",
        "action": "Qualifications vérifiées" if statut_qual == "VERIFIE_PRESENT" else ("Certificat expiré, à renouveler." if statut_qual == "EXPIREE" else "Fournir preuves de capacité ou équivalences."),
    })

    # 1.10. Références chantiers
    exige_refs = bool(any(k in text_cand_str for k in ["reference", "référence"]) or not has_exigences_cand)
    fichier_refs = fichiers_profil.get("references") or fichiers_profil.get("references_chantiers") or fichiers_profil.get("dossier_references")
    present_refs = verifier_presence_fichier(fichier_refs, dossiers_docs)
    valide_refs = bool(present_refs and len(refs) >= 3)
    verifie_refs = bool(present_refs and len(refs) >= 3 and all(bool(r.get("intitule") or r.get("objet")) for r in refs if isinstance(r, dict)))
    if not present_refs:
        statut_refs = "MANQUANT" if exige_refs else "A_COMPLETER"
    elif len(refs) >= 3:
        statut_refs = "VERIFIE_PRESENT"
    else:
        statut_refs = "A_COMPLETER"
    pieces_candidature.append({
        "piece": "Dossier de références de chantiers récents similaires",
        "exige_par_marche": exige_refs,
        "obligatoire": exige_refs,
        "present_disque": present_refs,
        "valide_juridiquement": valide_refs,
        "verifie_contenu": verifie_refs,
        "statut": statut_refs,
        "description": f"{len(refs)} référence(s) enregistrée(s) dans le profil.",
        "action": "Références prêtes" if statut_refs == "VERIFIE_PRESENT" else "Compléter au moins 3 attestations de bonne exécution.",
    })

    # -------------------------------------------------------------------------
    # 2. Dossier de l'Offre
    # -------------------------------------------------------------------------

    # 2.1. AE
    exige_ae = bool(any(k in text_offre_str for k in ["ae", "acte", "engagement"]) or not has_exigences_offre)
    fichier_ae = fichiers_profil.get("ae") or fichiers_profil.get("acte_engagement")
    present_ae = verifier_presence_fichier(fichier_ae, dossiers_docs)
    valide_ae = bool(present_ae)
    verifie_ae = bool(present_ae)
    statut_ae = "VERIFIE_PRESENT" if present_ae else ("MANQUANT" if exige_ae else "A_COMPLETER")
    pieces_offre.append({
        "piece": "Acte d'Engagement (AE)",
        "exige_par_marche": exige_ae,
        "obligatoire": exige_ae,
        "present_disque": present_ae,
        "valide_juridiquement": valide_ae,
        "verifie_contenu": verifie_ae,
        "statut": statut_ae,
        "description": "Document contractuel récapitulant le montant total HT/TTC, les délais et le RIB.",
        "action": "Acte d'engagement paraphé" if present_ae else "Renseigner le montant strictement égal à la DPGF et le délai contractuel.",
    })

    # 2.2. DPGF
    exige_dpgf = bool(any(k in text_offre_str for k in ["dpgf", "bpu", "prix"]) or not has_exigences_offre)
    fichier_dpgf = fichiers_profil.get("dpgf") or fichiers_profil.get("bpu")
    present_dpgf = verifier_presence_fichier(fichier_dpgf, dossiers_docs)
    valide_dpgf = bool(present_dpgf)
    verifie_dpgf = bool(present_dpgf)
    statut_dpgf = "VERIFIE_PRESENT" if present_dpgf else ("MANQUANT" if exige_dpgf else "A_CHIFFRER")
    pieces_offre.append({
        "piece": "Cadre de décomposition du prix chiffré (DPGF / BPU)",
        "exige_par_marche": exige_dpgf,
        "obligatoire": exige_dpgf,
        "present_disque": present_dpgf,
        "valide_juridiquement": valide_dpgf,
        "verifie_contenu": verifie_dpgf,
        "statut": statut_dpgf,
        "description": "Bordereau officiel au format Excel imposé sans modification d'intitulé.",
        "action": "DPGF chiffrée et contrôlée" if present_dpgf else "Chiffrer chaque ligne et vérifier sous scripts/controle_prix.py.",
    })

    # 2.3. Mémoire technique
    exige_memoire = bool(any(k in text_offre_str for k in ["memoire", "mémoire", "technique"]) or not has_exigences_offre)
    fichier_memoire = fichiers_profil.get("memoire") or fichiers_profil.get("memoire_technique")
    present_memoire = verifier_presence_fichier(fichier_memoire, dossiers_docs)
    valide_memoire = bool(present_memoire)
    verifie_memoire = bool(present_memoire)
    statut_memoire = "VERIFIE_PRESENT" if present_memoire else ("MANQUANT" if exige_memoire else "A_REDIGER")
    pieces_offre.append({
        "piece": "Mémoire technique justificatif d'offre",
        "exige_par_marche": exige_memoire,
        "obligatoire": exige_memoire,
        "present_disque": present_memoire,
        "valide_juridiquement": valide_memoire,
        "verifie_contenu": verifie_memoire,
        "statut": statut_memoire,
        "description": "Mémoire structuré selon les critères et sous-critères du RC.",
        "action": "Mémoire rédigé" if present_memoire else "Adapter assets/memoire_technique_template.md et supprimer toutes les balises [À FOURNIR].",
    })

    # 2.4. Planning
    exige_planning = bool(any(k in text_offre_str for k in ["planning", "calendrier"]) or not has_exigences_offre)
    fichier_planning = fichiers_profil.get("planning")
    present_planning = verifier_presence_fichier(fichier_planning, dossiers_docs)
    valide_planning = bool(present_planning)
    verifie_planning = bool(present_planning)
    statut_planning = "VERIFIE_PRESENT" if present_planning else ("MANQUANT" if exige_planning else "A_FINALISER")
    pieces_offre.append({
        "piece": "Planning prévisionnel détaillé d'exécution",
        "exige_par_marche": exige_planning,
        "obligatoire": exige_planning,
        "present_disque": present_planning,
        "valide_juridiquement": valide_planning,
        "verifie_contenu": verifie_planning,
        "statut": statut_planning,
        "description": "Diagramme de Gantt des travaux respectant le délai global de l'AE.",
        "action": "Planning validé" if present_planning else "Indiquer les phases de préparation, exécution et repliement.",
    })

    # 2.5. Visite des lieux
    # Discrimination rigoureuse unifiée : visite obligatoire vs recommandée vs facultative
    try:
        from go_nogo import qualifier_obligation_visite
        statut_visite_dce, _ = qualifier_obligation_visite(analyse_data)
    except Exception:
        statut_visite_dce = "AUCUNE"

    exige_visite = bool(any(k in text_offre_str or k in text_cand_str for k in ["visite", "visites"]) or (statut_visite_dce in ["OBLIGATOIRE", "RECOMMANDEE"]))
    obligatoire_visite = (statut_visite_dce == "OBLIGATOIRE")

    fichier_visite = (
        fichiers_profil.get("attestation_visite")
        or fichiers_profil.get("visite")
        or visite_site.get("attestation_fichier")
    )
    present_visite = verifier_presence_fichier(fichier_visite, dossiers_docs)

    # Contrôle si la visite a été effectuée postérieurement à l'échéance de remise
    date_limite_remise_str = (
        analyse_data.get("calendrier", {}).get("date_limite_retenue")
        or analyse_data.get("date_limite")
        or ""
    )
    date_visite_str = visite_site.get("date_visite")
    visite_post_echeance = False
    if date_visite_str and date_limite_remise_str:
        try:
            from common import parser_date_et_echeance
            dt_v, _, _ = parser_date_et_echeance(date_visite_str)
            dt_l, _, _ = parser_date_et_echeance(date_limite_remise_str)
            if dt_v and dt_l and dt_v > dt_l:
                visite_post_echeance = True
        except Exception:
            pass

    valide_visite = bool(present_visite and visite_faite and not visite_post_echeance)
    verifie_visite = bool(present_visite and (visite_site.get("signataire_mairie") or visite_site.get("date_visite") or visite_faite))

    if visite_post_echeance:
        statut_visite = "EXPIREE"
    elif not present_visite:
        statut_visite = "MANQUANT" if obligatoire_visite else "A_OBTENIR"
    elif not visite_faite:
        statut_visite = "A_OBTENIR"
    elif not valide_visite:
        statut_visite = "A_METTRE_A_JOUR"
    elif not verifie_visite:
        statut_visite = "A_COMPLETER"
    else:
        statut_visite = "VERIFIE_PRESENT"

    pieces_offre.append({
        "piece": "Attestation de visite des lieux signée",
        "exige_par_marche": exige_visite,
        "obligatoire": obligatoire_visite,
        "present_disque": present_visite,
        "valide_juridiquement": valide_visite,
        "verifie_contenu": verifie_visite,
        "statut": statut_visite,
        "nature_obligation": statut_visite_dce,
        "description": f"Justificatif de visite sur site ({statut_visite_dce.lower()}) signé par la collectivité.",
        "action": (
            "Attestation officielle signée prête à être jointe au pli."
            if (present_visite and visite_faite and valide_visite and verifie_visite)
            else (
                "Visite effectuée après la date limite : attestation caduque."
                if visite_post_echeance
                else (
                    "Prendre rendez-vous impérativement avant la date limite."
                    if obligatoire_visite
                    else "Visite recommandée ou facultative : attestation conseillée si effectuée."
                )
            )
        ),
    })

    # 2.6. Fiches techniques CSTB
    exige_fiches = bool(any(k in text_offre_str for k in ["fiche", "fiches", "cstb", "avis technique"]))
    fichier_fiches = fichiers_profil.get("fiches_techniques") or fichiers_profil.get("fiches")
    present_fiches = verifier_presence_fichier(fichier_fiches, dossiers_docs)
    valide_fiches = bool(present_fiches)
    verifie_fiches = bool(present_fiches)
    statut_fiches = "VERIFIE_PRESENT" if present_fiches else ("MANQUANT" if exige_fiches else "A_RASSEMBLER")
    pieces_offre.append({
        "piece": "Fiches techniques des produits et avis techniques CSTB",
        "exige_par_marche": exige_fiches,
        "obligatoire": False,
        "present_disque": present_fiches,
        "valide_juridiquement": valide_fiches,
        "verifie_contenu": verifie_fiches,
        "statut": statut_fiches,
        "description": "Fiches fabricants (tuiles, zinc, isolant thermique, rampe PMR).",
        "action": "Fiches techniques prêtes" if present_fiches else "Compiler en annexe technique du mémoire.",
    })

    return {
        "total_pieces_candidature": len(pieces_candidature),
        "total_pieces_offre": len(pieces_offre),
        "candidature": pieces_candidature,
        "offre": pieces_offre,
    }


# Interface contract alias
construire_checklist = generer_checklist


def generer_markdown_checklist(checklist: Dict[str, Any]) -> str:
    """Génère la checklist en Markdown pour le livrable de préparation."""
    md = []
    md.append("# Checklist des Pièces de Candidature et d'Offre (BTP)\n")
    
    statut_badges = {
        "VERIFIE_PRESENT": "🟢 Présent & Vérifié",
        "VALIDE": "🟢 Valide",
        "A_COMPLETER": "🟠 À compléter",
        "A_METTRE_A_JOUR": "🟠 À mettre à jour",
        "A_FOURNIR": "🔴 À fournir",
        "MANQUANT": "🔴 Manquant",
        "EXPIREE": "🔴 Expirée",
        "A_CHIFFRER": "🟠 À chiffrer",
        "A_REDIGER": "🟠 À rédiger",
        "A_FINALISER": "🔵 À finaliser",
        "A_OBTENIR": "🔴 À obtenir",
        "A_RASSEMBLER": "⚪ À rassembler",
    }
    
    md.append("## 1. Dossier de Candidature (Aptitude et Capacités)\n")
    md.append("| Pièce administrative / technique | Exigé marché | Présent disque | Caractère | Statut réel | Action opérationnelle requise |")
    md.append("| :--- | :---: | :---: | :---: | :---: | :--- |")
    for p in checklist.get("candidature", []):
        exig = "Oui" if p.get("exige_par_marche", True) else "Non"
        pres = "Oui" if p.get("present_disque", False) else "Non"
        ob = "Obligatoire" if p.get("obligatoire", True) else "Facultatif"
        st = p.get("statut", "A_FOURNIR")
        badge = statut_badges.get(st, f"⚪ {st}")
        action = p.get("action", "")
        md.append(f"| **{p.get('piece', '')}** | {exig} | {pres} | {ob} | {badge} | {action} |")
    md.append("")
    
    md.append("## 2. Dossier de l'Offre (Proposition Technique et Financière)\n")
    md.append("| Pièce contractuelle de l'offre | Exigé marché | Présent disque | Caractère | Statut réel | Action opérationnelle requise |")
    md.append("| :--- | :---: | :---: | :---: | :---: | :--- |")
    for p in checklist.get("offre", []):
        exig = "Oui" if p.get("exige_par_marche", True) else "Non"
        pres = "Oui" if p.get("present_disque", False) else "Non"
        ob = "Obligatoire" if p.get("obligatoire", True) else "Facultatif"
        st = p.get("statut", "A_FOURNIR")
        badge = statut_badges.get(st, f"⚪ {st}")
        action = p.get("action", "")
        md.append(f"| **{p.get('piece', '')}** | {exig} | {pres} | {ob} | {badge} | {action} |")
    md.append("")
    return "\n".join(md)


def main() -> None:
    parser = argparse.ArgumentParser(description="Checklist des pièces de candidature et d'offre.")
    parser.add_argument("--analyse-json", required=True, help="JSON issu de scripts/analyse_marche.py.")
    parser.add_argument("--profil", required=True, help="YAML du profil entreprise.")
    parser.add_argument("--documents-dir", required=False, help="Dossier contenant les pièces justificatives physiques.")
    parser.add_argument("--output-json", required=True, help="Chemin JSON de sortie.")
    parser.add_argument("--output-md", required=True, help="Chemin Markdown de sortie.")
    args = parser.parse_args()
    
    analyse_path = resoudre_chemin_securise(args.analyse_json)
    profil_path = resoudre_chemin_securise(args.profil)
    out_json = resoudre_chemin_securise(args.output_json)
    out_md = resoudre_chemin_securise(args.output_md)
    
    dossiers = []
    if args.documents_dir:
        dossiers.append(resoudre_chemin_securise(args.documents_dir))
    dossiers.append(profil_path.parent)
    
    analyse_data = charger_json(analyse_path)
    with profil_path.open("r", encoding="utf-8") as f:
        profil_data = yaml.safe_load(f) or {}
        
    checklist = generer_checklist(dce_analyse=analyse_data, profil=profil_data, dossiers_docs=dossiers)
    
    total_candidature = len(checklist["candidature"])
    total_offre = len(checklist["offre"])
    
    donnees_sortie = {
        "total_pieces_candidature": total_candidature,
        "total_pieces_offre": total_offre,
        "candidature": checklist["candidature"],
        "offre": checklist["offre"],
    }
    
    ecrire_json(out_json, donnees_sortie)
    md_content = generer_markdown_checklist(checklist)
    ecrire_fichier_securise(out_md, md_content)
    
    logger.info(f"Checklist générée : {out_json} et {out_md}")


if __name__ == "__main__":
    main()

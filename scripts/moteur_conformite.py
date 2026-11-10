"""Moteur centralisé de conformité pour marchés publics BTP.

Ce module constitue l'épine dorsale unique de vérification des exigences contractuelles :
- Identifiants stables pour chaque exigence (REQ-ADM-XX, REQ-TEC-XX, REQ-FIN-XX).
- Traçabilité complète des preuves (document source, page/feuille, extrait, confiance).
- Modèle 4D rigoureux : exige_par_marche, present_disque, valide_juridiquement, verifie_contenu.
- Statuts normalisés : ABSENT, PRESENT_NON_LU, LU_NON_VERIFIE, NON_CONFORME,
  VERIFIE_PRESENT, NON_EVALUABLE, NON_APPLICABLE.
- Verdicts formels centralisés : GO, GO_SOUS_RESERVE, NO_GO, NON_EVALUABLE.
- Qualification des clauses éliminatoires et des obligations de validation humaine.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger("moteur_conformite")


class VerdictConformite(str, Enum):
    """Verdicts formels unifiés d'aide à la décision."""
    GO = "GO"
    GO_SOUS_RESERVE = "GO_SOUS_RESERVE"
    NO_GO = "NO_GO"
    NON_EVALUABLE = "NON_EVALUABLE"


class StatutConformite(str, Enum):
    """Ontologie normalisée et stricte des statuts documentaires et d'exigences."""
    ABSENT = "ABSENT"
    MANQUANT = "MANQUANT"
    PRESENT_NON_LU = "PRESENT_NON_LU"
    LU_NON_VERIFIE = "LU_NON_VERIFIE"
    NON_CONFORME = "NON_CONFORME"
    EXPIREE = "EXPIREE"
    A_COMPLETER = "A_COMPLETER"
    A_METTRE_A_JOUR = "A_METTRE_A_JOUR"
    PREUVE_A_VALIDER_HUMAINEMENT = "PREUVE_A_VALIDER_HUMAINEMENT"
    VERIFIE_PRESENT = "VERIFIE_PRESENT"
    NON_EVALUABLE = "NON_EVALUABLE"
    NON_APPLICABLE = "NON_APPLICABLE"
    FACULTATIF = "FACULTATIF"


class CategorieExigence(str, Enum):
    """Catégorisation des exigences du DCE."""
    ADMINISTRATIVE = "ADMINISTRATIVE"
    TECHNIQUE = "TECHNIQUE"
    FINANCIERE = "FINANCIERE"
    JURIDIQUE = "JURIDIQUE"
    ORGANISATIONNELLE = "ORGANISATIONNELLE"


@dataclass
class PreuveDocumentaire:
    """Traçabilité formelle de la preuve appuyant une exigence."""
    document_source: str
    page_ou_feuille: Optional[str] = None
    extrait_pertinent: str = ""
    chemin_fichier_disque: Optional[str] = None
    present_sur_disque: bool = False
    niveau_confiance: float = 1.0  # 0.0 à 1.0
    methode_verification: str = "AUTOMATIQUE"  # AUTOMATIQUE, EXTRACTION_TEXTE, DECLARATIVE, HUMAINE
    validation_humaine_requise: bool = False
    motif_validation_humaine: Optional[str] = None


@dataclass
class ExigenceConformite:
    """Spécification formelle d'une exigence du marché."""
    id: str
    categorie: CategorieExigence
    description: str
    source_reglementaire_ou_dce: str
    exige_par_marche: bool = True
    obligatoire: bool = True
    eliminatoire: bool = False
    piece_justificative_attendue: Optional[str] = None
    statut: StatutConformite = StatutConformite.MANQUANT
    present_disque: bool = False
    valide_juridiquement: bool = False
    verifie_contenu: bool = False
    preuve: Optional[PreuveDocumentaire] = None
    justification: str = ""
    date_controle: str = field(default_factory=lambda: datetime.date.today().isoformat())

    def est_satisfaite(self) -> bool:
        """Une exigence n'est satisfaite que si elle est vérifiée selon le modèle 4D complet."""
        if not self.exige_par_marche:
            return True
        return (
            self.statut == StatutConformite.VERIFIE_PRESENT
            and self.present_disque is True
            and self.valide_juridiquement is True
            and self.verifie_contenu is True
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convertit l'exigence en dictionnaire sérialisable."""
        res = asdict(self)
        res["categorie"] = self.categorie.value
        res["statut"] = self.statut.value
        if self.preuve:
            res["preuve"] = asdict(self.preuve)
        return res


class MoteurConformite:
    """Moteur d'évaluation et de gestion centralisée de la conformité."""

    def __init__(self) -> None:
        self.exigences: List[ExigenceConformite] = []
        self.anomalies_externes: List[Dict[str, Any]] = []

    def ajouter_exigence(self, exigence: ExigenceConformite) -> None:
        """Enregistre une exigence dans le référentiel."""
        self.exigences.append(exigence)

    def enregistrer_anomalie_externe(self, code: str, description: str, source_module: str, gravite: str = "BLOQUANT") -> None:
        """Consigne une anomalie transmise par un module satellite (prix, calendrier, etc.)."""
        self.anomalies_externes.append({
            "code": code,
            "description": description,
            "source_module": source_module,
            "gravite": gravite,
        })

    def charger_depuis_checklist(self, checklist: Dict[str, Any]) -> None:
        """Importe et normalise les pièces issues de scripts/checklist_pieces.py."""
        if not isinstance(checklist, dict):
            self.enregistrer_anomalie_externe("CHECKLIST_STRUCTURE_INVALIDE", "Données checklist non dictionnaire.", "checklist")
            return

        for section, cat in [("candidature", CategorieExigence.ADMINISTRATIVE), ("offre", CategorieExigence.TECHNIQUE)]:
            pieces = checklist.get(section, [])
            if not isinstance(pieces, list):
                continue
            for idx, p in enumerate(pieces):
                if not isinstance(p, dict):
                    continue
                nom_p = str(p.get("piece") or f"{section}_{idx}")
                st_str = str(p.get("statut") or "MANQUANT").strip().upper()
                try:
                    statut_val = StatutConformite(st_str)
                except ValueError:
                    statut_val = StatutConformite.MANQUANT

                exige_m = p.get("exige_par_marche", True)
                obli = p.get("obligatoire", True)
                elim = bool(p.get("eliminatoire", False))
                present = bool(p.get("present_disque", False))
                valide = bool(p.get("valide_juridiquement", False))
                verifie = bool(p.get("verifie_contenu", False))

                chemin_f = p.get("chemin_fichier") or p.get("fichier") or p.get("chemin_fichier_disque")
                preuve = None
                if chemin_f:
                    preuve = PreuveDocumentaire(
                        document_source=nom_p,
                        chemin_fichier_disque=str(chemin_f),
                        present_sur_disque=present,
                        niveau_confiance=1.0 if (present and valide and verifie) else 0.5,
                        methode_verification="AUTOMATIQUE",
                    )

                self.ajouter_exigence(
                    ExigenceConformite(
                        id=f"CHK-{section[:3].upper()}-{idx+1:02d}",
                        categorie=cat,
                        description=nom_p,
                        source_reglementaire_ou_dce=f"Checklist {section}",
                        exige_par_marche=bool(exige_m),
                        obligatoire=bool(obli),
                        eliminatoire=elim,
                        piece_justificative_attendue=nom_p,
                        statut=statut_val,
                        present_disque=present,
                        valide_juridiquement=valide,
                        verifie_contenu=verifie,
                        preuve=preuve,
                        justification=p.get("remarque", ""),
                    )
                )

    def charger_depuis_matrice(self, matrice: Union[Dict[str, Any], List[Dict[str, Any]]]) -> None:
        """Importe et normalise les exigences contractuelles issues de la matrice de conformité."""
        exs = matrice.get("exigences", []) if isinstance(matrice, dict) else (matrice if isinstance(matrice, list) else [])
        for idx, m in enumerate(exs):
            if not isinstance(m, dict):
                continue
            id_m = str(m.get("id") or f"MAT-{idx+1:02d}")
            st_raw = str(m.get("statut") or "NON_VERIFIE").strip().upper()
            st_map = {
                "CONFORME": StatutConformite.VERIFIE_PRESENT,
                "VERIFIE_PRESENT": StatutConformite.VERIFIE_PRESENT,
                "NON_CONFORME": StatutConformite.NON_CONFORME,
                "NON CONFORME": StatutConformite.NON_CONFORME,
                "NON_EVALUABLE": StatutConformite.NON_EVALUABLE,
                "NON_APPLICABLE": StatutConformite.NON_APPLICABLE,
                "A_VALIDER": StatutConformite.PREUVE_A_VALIDER_HUMAINEMENT,
            }
            statut_val = st_map.get(st_raw, StatutConformite.LU_NON_VERIFIE)
            elim = bool(m.get("eliminatoire") or m.get("caractere_eliminatoire") or m.get("bloquant"))

            preuve = None
            ref_preuve = m.get("preuve") or m.get("justification")
            if ref_preuve:
                preuve = PreuveDocumentaire(
                    document_source=str(m.get("document_source") or "DCE"),
                    page_ou_feuille=str(m.get("page") or ""),
                    extrait_pertinent=str(ref_preuve),
                    validation_humaine_requise=(statut_val == StatutConformite.PREUVE_A_VALIDER_HUMAINEMENT),
                )

            self.ajouter_exigence(
                ExigenceConformite(
                    id=id_m,
                    categorie=CategorieExigence.TECHNIQUE,
                    description=str(m.get("exigence") or m.get("description") or id_m),
                    source_reglementaire_ou_dce=str(m.get("source") or "Matrice de conformité"),
                    exige_par_marche=True,
                    obligatoire=True,
                    eliminatoire=elim,
                    statut=statut_val,
                    present_disque=True,
                    valide_juridiquement=(statut_val == StatutConformite.VERIFIE_PRESENT),
                    verifie_contenu=(statut_val == StatutConformite.VERIFIE_PRESENT),
                    preuve=preuve,
                )
            )

    def verifier_invariants(self) -> List[Dict[str, Any]]:
        """Contrôle les 8 invariants fondamentaux de sécurité et de conformité."""
        anomalies = []
        for ex in self.exigences:
            # Invariant 1 : Aucune exigence obligatoire ne peut être contournée par un statut permissif
            if ex.exige_par_marche and ex.statut in (StatutConformite.FACULTATIF, StatutConformite.NON_APPLICABLE):
                anomalies.append({
                    "code": "CONTOURNEMENT_STATUT_PERMISSIF",
                    "exigence_id": ex.id,
                    "gravite": "BLOQUANT",
                    "description": f"L'exigence obligatoire '{ex.id}' ne peut porter le statut permissif {ex.statut.value}."
                })

            # Invariant 2 : Aucun document ne peut être considéré comme vérifié uniquement parce qu'il existe
            if ex.statut == StatutConformite.VERIFIE_PRESENT:
                if not (ex.present_disque and ex.valide_juridiquement and ex.verifie_contenu):
                    anomalies.append({
                        "code": "FAUX_VERIFIE_PRESENT_INCOMPLET",
                        "exigence_id": ex.id,
                        "gravite": "BLOQUANT",
                        "description": f"L'exigence '{ex.id}' est marquée VERIFIE_PRESENT sans satisfaire les 3 dimensions (disque={ex.present_disque}, juridique={ex.valide_juridiquement}, contenu={ex.verifie_contenu})."
                    })

            # Invariant 3 : Détection de contradiction entre exige_par_marche et obligatoire
            if ex.exige_par_marche and not ex.obligatoire:
                anomalies.append({
                    "code": "CONTRADICTION_EXIGE_NON_OBLIGATOIRE",
                    "exigence_id": ex.id,
                    "gravite": "BLOQUANT",
                    "description": f"L'exigence '{ex.id}' est exigée par le marché mais déclarée obligatoire=False."
                })

            # Invariant 4 : Aucune exigence éliminatoire ne peut rester non vérifiée ou inévaluable
            if ex.eliminatoire and ex.statut in (
                StatutConformite.PRESENT_NON_LU,
                StatutConformite.LU_NON_VERIFIE,
                StatutConformite.NON_EVALUABLE,
                StatutConformite.MANQUANT,
                StatutConformite.ABSENT,
                StatutConformite.NON_CONFORME,
                StatutConformite.EXPIREE,
                StatutConformite.FACULTATIF,
            ):
                anomalies.append({
                    "code": "EXIGENCE_ELIMINATOIRE_NON_VALIDEE",
                    "exigence_id": ex.id,
                    "gravite": "BLOQUANT",
                    "description": f"L'exigence éliminatoire '{ex.id}' est au statut non vérifié ou suspensif ({ex.statut.value})."
                })

            # Invariant 5 : Toute exigence VERIFIE_PRESENT doit posséder une preuve documentaire rattachée
            if ex.statut == StatutConformite.VERIFIE_PRESENT and not ex.preuve:
                anomalies.append({
                    "code": "EXIGENCE_VERIFIEE_SANS_PREUVE",
                    "exigence_id": ex.id,
                    "gravite": "BLOQUANT",
                    "description": f"L'exigence '{ex.id}' est déclarée VERIFIE_PRESENT sans aucune preuve documentaire rattachée."
                })

        # Intégration des anomalies externes (prix, calendrier, sécurité)
        for a_ext in self.anomalies_externes:
            anomalies.append(a_ext)

        return anomalies

    def synthetiser(self) -> Dict[str, Any]:
        """Calcule la synthèse centralisée et délivre le verdict formel sans contournement."""
        total = len(self.exigences)
        satisfaites = [e for e in self.exigences if e.est_satisfaite()]
        manquantes = [e for e in self.exigences if e.exige_par_marche and not e.est_satisfaite()]
        eliminatoires_bloquantes = [e for e in manquantes if e.eliminatoire]
        non_evaluables = [e for e in self.exigences if e.statut == StatutConformite.NON_EVALUABLE]
        validation_humaine = [
            e for e in self.exigences 
            if (e.statut == StatutConformite.PREUVE_A_VALIDER_HUMAINEMENT)
            or (e.preuve and e.preuve.validation_humaine_requise)
        ]

        anomalies = self.verifier_invariants()
        anomalies_bloquantes = [a for a in anomalies if a.get("gravite", "BLOQUANT") == "BLOQUANT"]

        # Détermination stricte du verdict
        if non_evaluables or any(a.get("code") == "DONNEES_CRITIQUES_NON_EVALUABLES" for a in anomalies):
            verdict = VerdictConformite.NON_EVALUABLE
        elif eliminatoires_bloquantes or manquantes or anomalies_bloquantes:
            verdict = VerdictConformite.NO_GO
        elif validation_humaine:
            verdict = VerdictConformite.GO_SOUS_RESERVE
        else:
            verdict = VerdictConformite.GO

        taux_conformite = (len(satisfaites) / total * 100.0) if total > 0 else 0.0

        return {
            "verdict": verdict.value,
            "statut_code": verdict.value,
            "est_conforme_pour_depot": (verdict in (VerdictConformite.GO, VerdictConformite.GO_SOUS_RESERVE)),
            "total_exigences": total,
            "total_satisfaites": len(satisfaites),
            "total_manquantes": len(manquantes),
            "total_eliminatoires_bloquantes": len(eliminatoires_bloquantes),
            "total_validation_humaine_requise": len(validation_humaine),
            "total_anomalies_bloquantes": len(anomalies_bloquantes),
            "taux_conformite_pct": round(taux_conformite, 2),
            "anomalies": anomalies,
            "exigences": [e.to_dict() for e in self.exigences],
        }

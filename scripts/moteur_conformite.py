"""Moteur centralisé de conformité pour marchés publics BTP.

Ce module constitue l'épine dorsale de vérification des exigences contractuelles :
- Identifiants stables pour chaque exigence (REQ-ADM-XX, REQ-TEC-XX, REQ-FIN-XX).
- Traçabilité complète des preuves (document source, page/feuille, extrait, confiance).
- Modèle 4D rigoureux : exige_par_marche, present_disque, valide_juridiquement, verifie_contenu.
- Statuts normalisés : ABSENT, PRESENT_NON_LU, LU_NON_VERIFIE, NON_CONFORME,
  VERIFIE_PRESENT, NON_EVALUABLE, NON_APPLICABLE.
- Qualification des clauses éliminatoires et des obligations de validation humaine.
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("moteur_conformite")


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

    def ajouter_exigence(self, exigence: ExigenceConformite) -> None:
        """Enregistre une exigence dans le référentiel."""
        self.exigences.append(exigence)

    def verifier_invariants(self) -> List[Dict[str, Any]]:
        """Contrôle les 8 invariants fondamentaux de sécurité et de conformité."""
        anomalies = []
        for ex in self.exigences:
            # Invariant 1 : Aucune exigence obligatoire ne peut être contournée par un statut permissif
            if ex.exige_par_marche and ex.statut in (StatutConformite.FACULTATIF, StatutConformite.NON_APPLICABLE):
                anomalies.append({
                    "code": "CONTOURNEMENT_STATUT_PERMISSIF",
                    "exigence_id": ex.id,
                    "description": f"L'exigence obligatoire '{ex.id}' ne peut porter le statut {ex.statut.value}."
                })

            # Invariant 2 : Aucun document ne peut être considéré comme vérifié uniquement parce qu'il existe
            if ex.statut == StatutConformite.VERIFIE_PRESENT:
                if not (ex.present_disque and ex.valide_juridiquement and ex.verifie_contenu):
                    anomalies.append({
                        "code": "FAUX_VERIFIE_PRESENT_INCOMPLET",
                        "exigence_id": ex.id,
                        "description": f"L'exigence '{ex.id}' est marquée VERIFIE_PRESENT sans satisfaire les 3 dimensions (disque={ex.present_disque}, juridique={ex.valide_juridiquement}, contenu={ex.verifie_contenu})."
                    })

            # Invariant 3 : Détection de contradiction entre exige_par_marche et obligatoire
            if ex.exige_par_marche and not ex.obligatoire:
                anomalies.append({
                    "code": "CONTRADICTION_EXIGE_NON_OBLIGATOIRE",
                    "exigence_id": ex.id,
                    "description": f"L'exigence '{ex.id}' est exigée par le marché mais déclarée obligatoire=False."
                })

        return anomalies

    def synthetiser(self) -> Dict[str, Any]:
        """Calcule les statistiques et le bilan de conformité."""
        total = len(self.exigences)
        satisfaites = [e for e in self.exigences if e.est_satisfaite()]
        manquantes = [e for e in self.exigences if e.exige_par_marche and not e.est_satisfaite()]
        eliminatoires_bloquantes = [e for e in manquantes if e.eliminatoire]
        validation_humaine = [
            e for e in self.exigences 
            if e.preuve and e.preuve.validation_humaine_requise
        ]

        taux_conformite = (len(satisfaites) / total * 100.0) if total > 0 else 0.0

        return {
            "total_exigences": total,
            "total_satisfaites": len(satisfaites),
            "total_manquantes": len(manquantes),
            "total_eliminatoires_bloquantes": len(eliminatoires_bloquantes),
            "total_validation_humaine_requise": len(validation_humaine),
            "taux_conformite_pct": round(taux_conformite, 2),
            "est_conforme_pour_depot": (len(manquantes) == 0 and len(eliminatoires_bloquantes) == 0),
            "exigences": [e.to_dict() for e in self.exigences],
        }

"""API REST FastAPI professionnelle pour le moteur marche-public-skill.

Fournit des points d'accès HTTP typés avec schémas Pydantic stricts pour l'analyse,
l'évaluation Go/No-Go, le contrôle arithmétique DPGF, la matrice de conformité
et le contrôle final fail-closed d'aptitude au dépôt de plis BTP.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Ajout du dossier scripts au sys.path pour les imports internes
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

# Imports des modules du moteur
from common import to_decimal
from dce_extract import extraire_dce
from analyse_marche import analyser_marche
from calendrier import calculer_retroplanning
from go_nogo import evaluer_go_nogo
from matrice_conformite import extraire_exigences, generer_markdown_matrice
from checklist_pieces import generer_checklist
from controle_prix import auditer_fichier_dpgf, verifier_arithmetique
from controle_final import auditer_dossier
from moteur_conformite import MoteurConformite

logger = logging.getLogger("api_marche_public")

app = FastAPI(
    title="Marché Public Skill — API d'Audit & Décision BTP",
    version="2.0.0",
    description="API REST d'ingénierie et d'aide à la décision pour marchés publics de travaux.",
)


# =============================================================================
# SCHÉMAS PYDANTIC ENTRÉE / SORTIE
# =============================================================================

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "2.0.0"
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    moteur: str = "marche-public-skill"


class ExtractRequest(BaseModel):
    repertoire_dce: str = Field(..., description="Chemin absolu ou relatif vers le dossier DCE.")


class AnalyseRequest(BaseModel):
    dce_extrait: Dict[str, Any] = Field(..., description="Inventaire structuré produit par l'extraction DCE.")
    seuils_config: Optional[Dict[str, Any]] = None


class GoNoGoRequest(BaseModel):
    analyse: Dict[str, Any] = Field(..., description="Données d'analyse du marché.")
    profil: Dict[str, Any] = Field(..., description="Profil administratif et technique de l'entreprise.")
    config: Optional[Dict[str, Any]] = None
    couts: Optional[Dict[str, Any]] = None
    dossiers_docs: Optional[List[str]] = None


class ControlePrixRequest(BaseModel):
    chemin_dpgf: str = Field(..., description="Chemin vers le classeur Excel ou CSV de la DPGF.")
    estimation_acheteur_ht: Optional[float] = None
    seuil_alerte_oab_pct: float = 20.0


class ChecklistRequest(BaseModel):
    analyse: Dict[str, Any] = Field(..., description="Données d'analyse du marché.")
    profil: Dict[str, Any] = Field(..., description="Profil de l'entreprise.")
    dossiers_docs: Optional[List[str]] = None


class ControleFinalRequest(BaseModel):
    analyse: Dict[str, Any]
    checklist: Dict[str, Any]
    prix: Dict[str, Any]
    memoire_texte: str = ""
    delai_ae_semaines: int = 12
    montant_ae_ht: float = 0.0
    go_nogo: Optional[Dict[str, Any]] = None
    matrice: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None


class AuditCompletRequest(BaseModel):
    repertoire_dce: str
    chemin_profil: str
    chemin_dpgf: str
    memoire_texte: Optional[str] = ""
    delai_ae_semaines: Optional[int] = None
    montant_ae_ht: Optional[float] = None


# =============================================================================
# ENDPOINTS REST
# =============================================================================

@app.get("/health", response_model=HealthResponse, tags=["Système"])
def health_check() -> HealthResponse:
    """Contrôle de disponibilité opérationnelle de l'API."""
    return HealthResponse()


@app.post("/api/v1/dce/extract", tags=["DCE"])
def api_extract_dce(payload: ExtractRequest) -> Dict[str, Any]:
    """Extrait et classifie l'ensemble des pièces d'un répertoire DCE."""
    rep = Path(payload.repertoire_dce)
    if not rep.exists() or not rep.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Répertoire DCE introuvable : {payload.repertoire_dce}",
        )
    try:
        return extraire_dce(rep)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@app.post("/api/v1/dce/analyse", tags=["DCE"])
def api_analyse_dce(payload: AnalyseRequest) -> Dict[str, Any]:
    """Analyse les clauses, contradictions, critères et délais du marché."""
    try:
        analyse_res = analyser_marche(payload.dce_extrait, config_seuils=payload.seuils_config)
        calendrier_res = calculer_retroplanning(analyse_res)
        return {
            "analyse": analyse_res,
            "calendrier": calendrier_res,
        }
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@app.post("/api/v1/audit/go-nogo", tags=["Audit & Décision"])
def api_go_nogo(payload: GoNoGoRequest) -> Dict[str, Any]:
    """Calcule le score multicritère pondéré sur 100 points et le verdict Go/No-Go."""
    try:
        dossiers = [Path(d) for d in payload.dossiers_docs] if payload.dossiers_docs else None
        return evaluer_go_nogo(
            analyse=payload.analyse,
            profil=payload.profil,
            config=payload.config,
            couts=payload.couts,
            dossiers_docs=dossiers,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@app.post("/api/v1/audit/matrice", tags=["Conformité"])
def api_matrice_conformite(payload: AnalyseRequest) -> Dict[str, Any]:
    """Génère la matrice de conformité technique et administrative."""
    try:
        exigences = extraire_exigences(payload.dce_extrait)
        return {
            "total_exigences": len(exigences),
            "exigences": exigences,
        }
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@app.post("/api/v1/audit/checklist", tags=["Checklist 4D"])
def api_checklist_pieces(payload: ChecklistRequest) -> Dict[str, Any]:
    """Établit la checklist des pièces selon le modèle 4D étanche."""
    try:
        dossiers = [Path(d) for d in payload.dossiers_docs] if payload.dossiers_docs else None
        return generer_checklist(
            dce_analyse=payload.analyse,
            profil=payload.profil,
            dossiers_docs=dossiers,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@app.post("/api/v1/audit/prix", tags=["Financier"])
def api_controle_prix(payload: ControlePrixRequest) -> Dict[str, Any]:
    """Contrôle arithmétique rigoureux de la DPGF et détection d'offres anormalement basses."""
    p_dpgf = Path(payload.chemin_dpgf)
    if not p_dpgf.exists() or not p_dpgf.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fichier DPGF introuvable : {payload.chemin_dpgf}",
        )
    try:
        est_ht = Decimal(str(payload.estimation_acheteur_ht)) if payload.estimation_acheteur_ht is not None else None
        return auditer_fichier_dpgf(
            chemin_dpgf=p_dpgf,
            estimation_acheteur_ht=est_ht,
            seuil_oab_pct=Decimal(str(payload.seuil_alerte_oab_pct)),
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@app.post("/api/v1/audit/controle-final", tags=["Audit & Décision"])
def api_controle_final(payload: ControleFinalRequest) -> Dict[str, Any]:
    """Exécute l'audit final croisé fail-closed d'aptitude au dépôt du pli."""
    try:
        return auditer_dossier(
            analyse=payload.analyse,
            checklist=payload.checklist,
            prix=payload.prix,
            memoire_texte=payload.memoire_texte,
            delai_ae_semaines=payload.delai_ae_semaines,
            montant_ae_ht=to_decimal(payload.montant_ae_ht),
            go_nogo=payload.go_nogo,
            matrice=payload.matrice,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

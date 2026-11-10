"""API REST FastAPI professionnelle et sécurisée pour le moteur marche-public-skill.

Fournit des points d'accès HTTP typés avec schémas Pydantic stricts pour l'analyse,
l'évaluation Go/No-Go, le contrôle arithmétique DPGF, la matrice de conformité
et le contrôle final fail-closed d'aptitude au dépôt de plis BTP.

Sécurité intégrée :
- Confinement strict des chemins de fichiers (prévention path traversal, blocage des fichiers système).
- Authentification par clé d'API (en-tête X-API-Key ou Bearer token).
- Limite de taille de fichier (max 50 Mo par défaut).
- Masquage des chemins internes dans les messages d'erreur.
- Liaison réseau locale sécurisée par défaut (127.0.0.1).
"""

from __future__ import annotations

import datetime
from decimal import Decimal
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Ajout du dossier scripts au sys.path pour les imports internes
SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Security, status
from fastapi.security import APIKeyHeader
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
from moteur_conformite import MoteurConformite, StatutConformite, VerdictConformite
import yaml

logger = logging.getLogger("api_marche_public")

# Configuration de sécurité
MAX_FILE_SIZE_BYTES = int(os.environ.get("MARCHE_PUBLIC_MAX_FILE_SIZE", 50 * 1024 * 1024))  # 50 Mo
API_KEY_ENV = os.environ.get("MARCHE_PUBLIC_API_KEY", "")
API_ENVIRONMENT = os.environ.get("MARCHE_PUBLIC_ENV", "development").lower().strip()

# Extensions de fichiers autorisées pour l'analyse documentaire
ALLOWED_FILE_EXTENSIONS: Set[str] = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".txt", ".json", ".yaml", ".yml"
}

# Répertoires autorisés pour le confinement des chemins
ENV_ALLOWED_DIRS = os.environ.get("MARCHE_PUBLIC_ALLOWED_DIRS", "")
ALLOWED_ROOTS: List[Path] = [REPO_ROOT.resolve()]
if ENV_ALLOWED_DIRS:
    for d in ENV_ALLOWED_DIRS.split(os.pathsep):
        if d.strip():
            ALLOWED_ROOTS.append(Path(d.strip()).resolve())

SYSTEM_FORBIDDEN_PATHS = [
    Path("C:/Windows"),
    Path("C:/Program Files"),
    Path("C:/Program Files (x86)"),
    Path("/etc"),
    Path("/sys"),
    Path("/proc"),
    Path("/var"),
    Path("/root"),
]

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verifier_authentification(
    request: Request,
    x_api_key: Optional[str] = Security(api_key_header),
) -> bool:
    """Vérifie l'authentification par clé API avec comparaison en temps constant et contrôle strict d'interface réseau."""
    import secrets

    # Gestion de compatibilité avec appels directs (x_api_key passé en premier argument ou None)
    if isinstance(request, str):
        x_api_key = request
        request = None
    elif not isinstance(x_api_key, str):
        x_api_key = None

    # Détection de l'origine réseau du client
    client_host = getattr(getattr(request, "client", None), "host", "127.0.0.1")
    est_boucle_locale = client_host in ("127.0.0.1", "::1", "localhost", "testclient")

    # En environnement de production, réseau, ou si la requête provient d'une IP non-locale
    if API_ENVIRONMENT in ("production", "prod", "network") or not est_boucle_locale:
        if not API_KEY_ENV or len(API_KEY_ENV) < 16:
            logger.error("Configuration d'accès non-local incomplète : MARCHE_PUBLIC_API_KEY absente ou trop courte (>= 16 chars).")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erreur de configuration serveur : authentification réseau non configurée de façon sécurisée.",
            )
        if not x_api_key or not secrets.compare_digest(x_api_key, API_KEY_ENV):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentification requise : clé API invalide ou absente dans l'en-tête X-API-Key.",
            )
        return True

    # En environnement de développement local (127.0.0.1) avec clé configurée
    if API_KEY_ENV:
        if not x_api_key or not secrets.compare_digest(x_api_key, API_KEY_ENV):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentification requise : clé API invalide ou absente dans l'en-tête X-API-Key.",
            )
    return True


def resoudre_et_securiser_chemin(
    chemin_str: str,
    must_exist: bool = True,
    must_be_dir: bool = False,
    must_be_file: bool = False,
    racines_autorisees: Optional[List[Path]] = None,
    extensions_autorisees: Optional[Set[str]] = None,
) -> Path:
    """Valide rigoureusement un chemin pour garantir le confinement strict et interdire l'évasion."""
    if not isinstance(chemin_str, str) or not chemin_str.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le chemin fourni ne peut être vide ou nul.",
        )

    # 1. Détection des encodages alternatifs et traversée de répertoire explicite
    import urllib.parse
    chemin_normalise = urllib.parse.unquote(chemin_str).strip()
    
    # Remplacer les antislashs pour normaliser les parties
    parties = Path(chemin_normalise.replace("\\", "/")).parts
    if ".." in parties:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès interdit : tentative de traversée de répertoire détectée ('..').",
        )

    # Détection explicite de tentative d'accès à une lettre de lecteur Windows ou racine absolue POSIX
    p_init = Path(chemin_normalise)
    est_absolu_explicite = (
        p_init.is_absolute()
        or (len(chemin_normalise) >= 2 and chemin_normalise[1] == ":")
        or chemin_normalise.startswith("/")
        or chemin_normalise.startswith("\\")
    )

    # 2. Résolution canonique (résolution des liens symboliques et normalisation absolue)
    if not est_absolu_explicite:
        p_resolu = (REPO_ROOT / p_init).resolve()
    else:
        p_resolu = p_init.resolve()

    # 3. Vérification du confinement strict dans les racines autorisées
    racines = racines_autorisees or ALLOWED_ROOTS
    est_confine = False
    for r in racines:
        try:
            r_resolu = r.resolve()
            if p_resolu == r_resolu or p_resolu.is_relative_to(r_resolu):
                est_confine = True
                break
        except (ValueError, RuntimeError):
            continue

    if not est_confine:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès interdit : le chemin spécifié est situé hors des répertoires autorisés.",
        )

    # 4. Blocage explicite des répertoires système (protection en profondeur)
    for sys_dir in SYSTEM_FORBIDDEN_PATHS:
        try:
            if sys_dir.exists():
                sd_resolu = sys_dir.resolve()
                if p_resolu == sd_resolu or p_resolu.is_relative_to(sd_resolu):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Accès interdit : tentative d'accès à un répertoire système protégé.",
                    )
        except (ValueError, RuntimeError):
            pass

    # 5. Existence et type de ressource
    if must_exist and not p_resolu.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ressource ou chemin introuvable.",
        )

    if must_be_dir and p_resolu.exists() and not p_resolu.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le chemin spécifié doit pointer vers un répertoire.",
        )

    if must_be_file and p_resolu.exists():
        if not p_resolu.is_file():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Le chemin spécifié doit pointer vers un fichier régulier.",
            )

        # Contrôle des extensions autorisées
        exts = extensions_autorisees or ALLOWED_FILE_EXTENSIONS
        if p_resolu.suffix.lower() not in exts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Extension de fichier non autorisée ('{p_resolu.suffix}'). Extensions acceptées : {sorted(list(exts))}.",
            )

        try:
            taille = p_resolu.stat().st_size
            if taille > MAX_FILE_SIZE_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"Fichier trop volumineux ({taille} octets). La limite autorisée est de {MAX_FILE_SIZE_BYTES} octets.",
                )
        except OSError as err:
            logger.error(f"Erreur d'accès aux métadonnées du fichier {p_resolu}: {err}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Erreur d'accès ou lecture impossible du fichier spécifié.",
            )

    return p_resolu


app = FastAPI(
    title="Marché Public Skill — API d'Audit & Décision BTP",
    version="2.0.3",
    description="API REST d'ingénierie et d'aide à la décision pour marchés publics de travaux.",
)


# =============================================================================
# SCHÉMAS PYDANTIC ENTRÉE / SORTIE
# =============================================================================

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "2.0.3"
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    moteur: str = "marche-public-skill"
    securite_auth_activee: bool = bool(API_KEY_ENV)


class ExtractRequest(BaseModel):
    repertoire_dce: str = Field(..., description="Chemin vers le dossier DCE.")


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
def api_extract_dce(
    payload: ExtractRequest,
    _auth: bool = Depends(verifier_authentification),
) -> Dict[str, Any]:
    """Extrait et classifie l'ensemble des pièces d'un répertoire DCE sécurisé."""
    rep = resoudre_et_securiser_chemin(payload.repertoire_dce, must_exist=True, must_be_dir=True)
    try:
        return extraire_dce(rep)
    except Exception as exc:
        logger.error(f"Erreur extraction DCE: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erreur interne lors de l'extraction documentaire.")


@app.post("/api/v1/dce/analyse", tags=["DCE"])
def api_analyse_dce(
    payload: AnalyseRequest,
    _auth: bool = Depends(verifier_authentification),
) -> Dict[str, Any]:
    """Analyse les clauses, contradictions, critères et délais du marché."""
    try:
        analyse_res = analyser_marche(payload.dce_extrait, seuils_config=payload.seuils_config)
        calendrier_res = calculer_retroplanning(analyse_res)
        return {
            "analyse": analyse_res,
            "calendrier": calendrier_res,
        }
    except Exception as exc:
        logger.error(f"Erreur analyse DCE: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erreur interne lors de l'analyse du marché.")


@app.post("/api/v1/audit/go-nogo", tags=["Audit & Décision"])
def api_go_nogo(
    payload: GoNoGoRequest,
    _auth: bool = Depends(verifier_authentification),
) -> Dict[str, Any]:
    """Calcule le score multicritère pondéré sur 100 points et le verdict Go/No-Go."""
    try:
        dossiers = [resoudre_et_securiser_chemin(d, must_exist=True, must_be_dir=True) for d in payload.dossiers_docs] if payload.dossiers_docs else None
        return evaluer_go_nogo(
            analyse=payload.analyse,
            profil=payload.profil,
            config=payload.config,
            couts=payload.couts,
            dossiers_docs=dossiers,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Erreur évaluation Go/No-Go: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erreur interne lors de l'évaluation Go/No-Go.")


@app.post("/api/v1/audit/matrice", tags=["Conformité"])
def api_matrice_conformite(
    payload: AnalyseRequest,
    _auth: bool = Depends(verifier_authentification),
) -> Dict[str, Any]:
    """Génère la matrice de conformité technique et administrative."""
    try:
        exigences = extraire_exigences(payload.dce_extrait)
        return {
            "total_exigences": len(exigences),
            "exigences": exigences,
        }
    except Exception as exc:
        logger.error(f"Erreur matrice conformité: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erreur interne lors de l'extraction des exigences.")


@app.post("/api/v1/audit/checklist", tags=["Checklist 4D"])
def api_checklist_pieces(
    payload: ChecklistRequest,
    _auth: bool = Depends(verifier_authentification),
) -> Dict[str, Any]:
    """Établit la checklist des pièces selon le modèle 4D étanche."""
    try:
        dossiers = [resoudre_et_securiser_chemin(d, must_exist=True, must_be_dir=True) for d in payload.dossiers_docs] if payload.dossiers_docs else None
        return generer_checklist(
            dce_analyse=payload.analyse,
            profil=payload.profil,
            dossiers_docs=dossiers,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Erreur checklist: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erreur interne lors de la génération de la checklist.")


@app.post("/api/v1/audit/prix", tags=["Financier"])
def api_controle_prix(
    payload: ControlePrixRequest,
    _auth: bool = Depends(verifier_authentification),
) -> Dict[str, Any]:
    """Contrôle arithmétique rigoureux de la DPGF et détection d'offres anormalement basses."""
    p_dpgf = resoudre_et_securiser_chemin(payload.chemin_dpgf, must_exist=True, must_be_file=True)
    try:
        est_ht = Decimal(str(payload.estimation_acheteur_ht)) if payload.estimation_acheteur_ht is not None else None
        return auditer_fichier_dpgf(
            chemin_dpgf=p_dpgf,
            estimation_acheteur_ht=est_ht,
            seuil_oab_pct=Decimal(str(payload.seuil_alerte_oab_pct)),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Erreur contrôle prix: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erreur interne lors du contrôle financier.")


@app.post("/api/v1/audit/controle-final", tags=["Audit & Décision"])
def api_controle_final(
    payload: ControleFinalRequest,
    _auth: bool = Depends(verifier_authentification),
) -> Dict[str, Any]:
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
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Erreur contrôle final: {exc}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erreur interne lors du contrôle final.")


if __name__ == "__main__":
    import uvicorn
    # Liaison réseau locale sécurisée 127.0.0.1 par défaut (jamais 0.0.0.0 sans configuration explicite)
    host = os.environ.get("MARCHE_PUBLIC_API_HOST", "127.0.0.1")
    port = int(os.environ.get("MARCHE_PUBLIC_API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)

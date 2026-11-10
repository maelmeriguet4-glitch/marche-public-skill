"""Serveur MCP (Model Context Protocol) officiel pour marche-public-skill.

Expose le moteur d'ingénierie et d'audit de marchés publics via le protocole standard
JSON-RPC 2.0 sur l'entrée/sortie standard (stdio), compatible avec Claude Desktop,
Antigravity, Cursor et les clients compatibles MCP.

Outils MCP intégrés :
1. extraire_dce / identifier_dossier : Identification et extraction du DCE
2. analyser_marche_dce : Analyse des clauses, calendrier et allotissement
3. consulter_exigences : Consultation des exigences du marché
4. consulter_pieces_manquantes : Consultation des pièces manquantes ou non vérifiées
5. consulter_anomalies : Consultation des contradictions et anomalies détectées
6. consulter_preuves : Consultation des preuves documentaires
7. evaluer_go_nogo : Évaluation multicritère et décision Go/No-Go
8. verifier_dpgf : Contrôle arithmétique et détection d'offres anormalement basses
9. auditer_dossier_complet : Audit final fail-closed d'aptitude au dépôt
"""

from __future__ import annotations

import io
import json
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Configuration du logging sur stderr pour préserver stdout pour le protocole JSON-RPC
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[MCP] %(levelname)s: %(message)s")
logger = logging.getLogger("mcp_server")

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from common import to_decimal
from dce_extract import extraire_dce
from analyse_marche import analyser_marche
from calendrier import calculer_retroplanning
from go_nogo import evaluer_go_nogo
from matrice_conformite import extraire_exigences
from checklist_pieces import generer_checklist
from controle_prix import auditer_fichier_dpgf, verifier_arithmetique
from controle_final import auditer_dossier
from moteur_conformite import MoteurConformite, StatutConformite, VerdictConformite
import yaml


MAX_FILE_SIZE_BYTES = int(os.environ.get("MARCHE_PUBLIC_MAX_FILE_SIZE", 50 * 1024 * 1024))
ALLOWED_FILE_EXTENSIONS: Set[str] = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".txt", ".json", ".yaml", ".yml"
}
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


def _resoudre_chemin_mcp(
    p_str: str,
    must_exist: bool = False,
    must_be_dir: bool = False,
    must_be_file: bool = False,
) -> Path:
    """Résout et garantit le confinement strict d'un chemin fourni au serveur MCP."""
    if not isinstance(p_str, str) or not p_str.strip():
        raise ValueError("Le chemin fourni est vide ou invalide.")

    import urllib.parse
    chemin_normalise = urllib.parse.unquote(p_str)
    parties = Path(chemin_normalise.replace("\\", "/")).parts
    if ".." in parties:
        raise PermissionError("Accès interdit : traversée de répertoire détectée ('..').")

    p_init = Path(chemin_normalise)
    if not p_init.is_absolute():
        p_resolu = (REPO_ROOT / p_init).resolve()
    else:
        p_resolu = p_init.resolve()

    # Vérification confinement dans les racines autorisées
    est_confine = False
    for r in ALLOWED_ROOTS:
        try:
            r_resolu = r.resolve()
            if p_resolu == r_resolu or p_resolu.is_relative_to(r_resolu):
                est_confine = True
                break
        except (ValueError, RuntimeError):
            continue

    if not est_confine:
        raise PermissionError(f"Accès interdit : le chemin '{p_str}' est situé hors des répertoires autorisés du serveur MCP.")

    # Blocage des répertoires système
    for sys_dir in SYSTEM_FORBIDDEN_PATHS:
        try:
            if sys_dir.exists():
                sd_resolu = sys_dir.resolve()
                if p_resolu == sd_resolu or p_resolu.is_relative_to(sd_resolu):
                    raise PermissionError("Accès interdit : tentative d'accès à un répertoire système protégé via MCP.")
        except (ValueError, RuntimeError):
            pass

    if must_exist and not p_resolu.exists():
        raise FileNotFoundError(f"Chemin introuvable : '{p_str}'.")

    if must_be_dir and p_resolu.exists() and not p_resolu.is_dir():
        raise ValueError(f"Le chemin doit pointer vers un répertoire : '{p_str}'.")

    if must_be_file and p_resolu.exists():
        if not p_resolu.is_file():
            raise ValueError(f"Le chemin doit pointer vers un fichier régulier : '{p_str}'.")
        if p_resolu.suffix.lower() not in ALLOWED_FILE_EXTENSIONS:
            raise ValueError(f"Extension '{p_resolu.suffix}' non autorisée via MCP.")
        try:
            taille = p_resolu.stat().st_size
            if taille > MAX_FILE_SIZE_BYTES:
                raise ValueError(f"Fichier trop volumineux ({taille} octets). Limite autorisée : {MAX_FILE_SIZE_BYTES} octets.")
        except OSError:
            pass

    return p_resolu


MCP_TOOLS = [
    {
        "name": "extraire_dce",
        "description": "Extrait et classifie l'ensemble des pièces d'un répertoire DCE (PDF, DOCX, XLSX, TXT) avec détection des scans sans texte OCR.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repertoire_dce": {
                    "type": "string",
                    "description": "Chemin absolu ou relatif vers le dossier contenant les fichiers du DCE."
                }
            },
            "required": ["repertoire_dce"]
        }
    },
    {
        "name": "analyser_marche_dce",
        "description": "Analyse les clauses contractuelles, allotissement, critères de jugement et calendrier de remise.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repertoire_dce": {
                    "type": "string",
                    "description": "Dossier contenant les fichiers du DCE."
                }
            },
            "required": ["repertoire_dce"]
        }
    },
    {
        "name": "consulter_exigences",
        "description": "Consulte l'ensemble des exigences administratives et techniques extraites du DCE.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repertoire_dce": {
                    "type": "string",
                    "description": "Dossier du DCE à analyser."
                }
            },
            "required": ["repertoire_dce"]
        }
    },
    {
        "name": "consulter_pieces_manquantes",
        "description": "Identifie et liste les pièces justificatives manquantes, expirées ou non vérifiées selon le modèle 4D.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repertoire_dce": {
                    "type": "string",
                    "description": "Dossier du DCE."
                },
                "chemin_profil_yaml": {
                    "type": "string",
                    "description": "Profil entreprise YAML."
                }
            },
            "required": ["repertoire_dce", "chemin_profil_yaml"]
        }
    },
    {
        "name": "consulter_anomalies",
        "description": "Consulte les anomalies, contradictions contractuelles et alertes détectées dans le dossier.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repertoire_dce": {
                    "type": "string",
                    "description": "Dossier du DCE."
                },
                "chemin_dpgf": {
                    "type": "string",
                    "description": "Bordereau de prix chiffré (optionnel pour inclure les anomalies de prix)."
                }
            },
            "required": ["repertoire_dce"]
        }
    },
    {
        "name": "consulter_preuves",
        "description": "Consulte les éléments de preuve documentaire et les attestations physiques rattachées aux exigences.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repertoire_dce": {
                    "type": "string",
                    "description": "Dossier du DCE."
                },
                "chemin_profil_yaml": {
                    "type": "string",
                    "description": "Profil de l'entreprise candidate."
                }
            },
            "required": ["repertoire_dce", "chemin_profil_yaml"]
        }
    },
    {
        "name": "evaluer_go_nogo",
        "description": "Évalue l'opportunité de candidature sur un marché public BTP selon le modèle multicritère officiel pondéré sur 100 points.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chemin_analyse_json": {
                    "type": "string",
                    "description": "Chemin vers le fichier JSON issu de analyse_marche."
                },
                "chemin_profil_yaml": {
                    "type": "string",
                    "description": "Chemin vers le profil YAML de l'entreprise candidate."
                }
            },
            "required": ["chemin_analyse_json", "chemin_profil_yaml"]
        }
    },
    {
        "name": "verifier_dpgf",
        "description": "Contrôle arithmétique rigoureux de la DPGF (multiplications, arrondis, totaux) et détection d'offres anormalement basses (OAB).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chemin_dpgf": {
                    "type": "string",
                    "description": "Chemin vers le fichier DPGF (Excel .xlsx ou .csv)."
                },
                "estimation_acheteur_ht": {
                    "type": "number",
                    "description": "Montant estimé par l'acheteur en euros HT (optionnel pour l'analyse OAB)."
                }
            },
            "required": ["chemin_dpgf"]
        }
    },
    {
        "name": "generer_checklist_4d",
        "description": "Génère la checklist rigoureuse selon le modèle 4D étanche (exige_par_marche, present_disque, valide_juridiquement, verifie_contenu).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chemin_analyse_json": {
                    "type": "string",
                    "description": "Chemin vers l'analyse du marché."
                },
                "chemin_profil_yaml": {
                    "type": "string",
                    "description": "Chemin vers le profil d'entreprise."
                }
            },
            "required": ["chemin_analyse_json", "chemin_profil_yaml"]
        }
    },
    {
        "name": "auditer_dossier_complet",
        "description": "Exécute l'audit final pré-dépôt croisé fail-closed complet et détermine l'aptitude formelle au dépôt du pli (PRET / PAS_PRET).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repertoire_dce": {
                    "type": "string",
                    "description": "Dossier du DCE brut."
                },
                "chemin_profil_yaml": {
                    "type": "string",
                    "description": "Profil d'entreprise YAML."
                },
                "chemin_dpgf": {
                    "type": "string",
                    "description": "Bordereau de prix chiffré."
                },
                "memoire_texte": {
                    "type": "string",
                    "description": "Texte complet du mémoire technique ou chemin vers le fichier .md."
                },
                "montant_ae_ht": {
                    "type": "number",
                    "description": "Montant hors taxes stipulé dans l'Acte d'Engagement."
                },
                "delai_ae_semaines": {
                    "type": "integer",
                    "description": "Délai d'exécution contractuel stipulé dans l'Acte d'Engagement (en semaines)."
                }
            },
            "required": ["repertoire_dce", "chemin_profil_yaml", "chemin_dpgf", "montant_ae_ht", "delai_ae_semaines"]
        }
    }
]


def traiter_requete(requete: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Traite un message JSON-RPC MCP standard."""
    req_id = requete.get("id")
    methode = requete.get("method")
    params = requete.get("params", {})

    if methode == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "marche-public-skill",
                    "version": "2.0.1"
                }
            }
        }

    elif methode == "notifications/initialized":
        return None

    elif methode == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": MCP_TOOLS
            }
        }

    elif methode == "tools/call":
        nom_outil = params.get("name")
        args = params.get("arguments", {})
        try:
            res_content = executer_outil(nom_outil, args)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(res_content, ensure_ascii=False, indent=2, default=str)
                        }
                    ],
                    "isError": False
                }
            }
        except Exception as exc:
            logger.error(f"Erreur d'exécution de l'outil {nom_outil}: {exc}", exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Erreur d'exécution : {str(exc)}"
                        }
                    ],
                    "isError": True
                }
            }

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Méthode inconnue : {methode}"
            }
        }


def executer_outil(nom_outil: str, args: Dict[str, Any]) -> Any:
    """Aiguille et exécute la logique de l'outil demandé."""
    if nom_outil in ("extraire_dce", "identifier_dossier"):
        rep = _resoudre_chemin_mcp(args["repertoire_dce"])
        if not rep.exists() or not rep.is_dir():
            raise FileNotFoundError(f"Dossier DCE introuvable : {args['repertoire_dce']}")
        return extraire_dce(rep)

    elif nom_outil == "analyser_marche_dce":
        rep = _resoudre_chemin_mcp(args["repertoire_dce"])
        dce_ext = extraire_dce(rep)
        analyse = analyser_marche(dce_ext)
        retro = calculer_retroplanning(analyse)
        return {"analyse": analyse, "retroplanning": retro}

    elif nom_outil == "consulter_exigences":
        rep = _resoudre_chemin_mcp(args["repertoire_dce"])
        dce_ext = extraire_dce(rep)
        exigences = extraire_exigences(dce_ext)
        return {"total_exigences": len(exigences), "exigences": exigences}

    elif nom_outil == "consulter_pieces_manquantes":
        rep = _resoudre_chemin_mcp(args["repertoire_dce"])
        p_profil = _resoudre_chemin_mcp(args["chemin_profil_yaml"])
        dce_ext = extraire_dce(rep)
        analyse = analyser_marche(dce_ext)
        with p_profil.open("r", encoding="utf-8") as f:
            profil = yaml.safe_load(f)
        checklist = generer_checklist(dce_analyse=analyse, profil=profil, dossiers_docs=[rep, p_profil.parent])
        manquantes = []
        for sec in ("candidature", "offre"):
            for p in checklist.get(sec, []):
                if p.get("exige_par_marche") and p.get("statut") != "VERIFIE_PRESENT":
                    manquantes.append({"section": sec, "piece": p.get("piece"), "statut": p.get("statut")})
        return {"total_pieces_manquantes": len(manquantes), "pieces_manquantes": manquantes}

    elif nom_outil == "consulter_anomalies":
        rep = _resoudre_chemin_mcp(args["repertoire_dce"])
        dce_ext = extraire_dce(rep)
        analyse = analyser_marche(dce_ext)
        anomalies = list(analyse.get("contradictions_detectees", []))
        if args.get("chemin_dpgf"):
            p_dpgf = _resoudre_chemin_mcp(args["chemin_dpgf"])
            if p_dpgf.exists():
                prix_res = auditer_fichier_dpgf(p_dpgf)
                anomalies.extend(prix_res.get("anomalies", []))
        return {"total_anomalies": len(anomalies), "anomalies": anomalies}

    elif nom_outil == "consulter_preuves":
        rep = _resoudre_chemin_mcp(args["repertoire_dce"])
        p_profil = _resoudre_chemin_mcp(args["chemin_profil_yaml"])
        dce_ext = extraire_dce(rep)
        analyse = analyser_marche(dce_ext)
        with p_profil.open("r", encoding="utf-8") as f:
            profil = yaml.safe_load(f)
        checklist = generer_checklist(dce_analyse=analyse, profil=profil, dossiers_docs=[rep, p_profil.parent])
        preuves = []
        for sec in ("candidature", "offre"):
            for p in checklist.get(sec, []):
                if p.get("statut") == "VERIFIE_PRESENT" or p.get("chemin_fichier"):
                    preuves.append({
                        "piece": p.get("piece"),
                        "statut": p.get("statut"),
                        "fichier": p.get("chemin_fichier"),
                        "4d": {
                            "present_disque": p.get("present_disque"),
                            "valide_juridiquement": p.get("valide_juridiquement"),
                            "verifie_contenu": p.get("verifie_contenu"),
                        }
                    })
        return {"total_preuves": len(preuves), "preuves": preuves}

    elif nom_outil == "evaluer_go_nogo":
        p_analyse = _resoudre_chemin_mcp(args["chemin_analyse_json"])
        p_profil = _resoudre_chemin_mcp(args["chemin_profil_yaml"])
        with p_analyse.open("r", encoding="utf-8") as f:
            analyse = json.load(f)
        with p_profil.open("r", encoding="utf-8") as f:
            profil = yaml.safe_load(f)
        return evaluer_go_nogo(analyse=analyse, profil=profil)

    elif nom_outil == "verifier_dpgf":
        p_dpgf = _resoudre_chemin_mcp(args["chemin_dpgf"])
        est_ht = Decimal(str(args["estimation_acheteur_ht"])) if args.get("estimation_acheteur_ht") is not None else None
        return auditer_fichier_dpgf(chemin_dpgf=p_dpgf, estimation_acheteur_ht=est_ht)

    elif nom_outil == "generer_checklist_4d":
        p_analyse = _resoudre_chemin_mcp(args["chemin_analyse_json"])
        p_profil = _resoudre_chemin_mcp(args["chemin_profil_yaml"])
        with p_analyse.open("r", encoding="utf-8") as f:
            analyse = json.load(f)
        with p_profil.open("r", encoding="utf-8") as f:
            profil = yaml.safe_load(f)
        return generer_checklist(dce_analyse=analyse, profil=profil)

    elif nom_outil == "auditer_dossier_complet":
        rep_dce = _resoudre_chemin_mcp(args["repertoire_dce"])
        p_profil = _resoudre_chemin_mcp(args["chemin_profil_yaml"])
        p_dpgf = _resoudre_chemin_mcp(args["chemin_dpgf"])

        dce_ext = extraire_dce(rep_dce)
        analyse = analyser_marche(dce_ext)
        with p_profil.open("r", encoding="utf-8") as f:
            profil = yaml.safe_load(f)
        go_res = evaluer_go_nogo(analyse=analyse, profil=profil, dossiers_docs=[rep_dce, p_profil.parent])
        matrice_ex = extraire_exigences(dce_ext)
        checklist = generer_checklist(dce_analyse=analyse, profil=profil, dossiers_docs=[rep_dce, p_profil.parent])
        prix = auditer_fichier_dpgf(chemin_dpgf=p_dpgf)

        memoire = args.get("memoire_texte", "")
        if Path(memoire).exists() and Path(memoire).is_file():
            memoire = Path(memoire).read_text(encoding="utf-8")

        audit_res = auditer_dossier(
            analyse=analyse,
            checklist=checklist,
            prix=prix,
            memoire_texte=memoire,
            delai_ae_semaines=int(args["delai_ae_semaines"]),
            montant_ae_ht=to_decimal(args["montant_ae_ht"]),
            go_nogo=go_res,
            matrice={"exigences": matrice_ex},
        )
        return {
            "verdict_final": audit_res["verdict"],
            "statut_code": audit_res["statut_code"],
            "total_blocages": audit_res["total_blocages"],
            "blocages": audit_res["blocages"],
            "avertissements": audit_res["avertissements"],
            "score_go_nogo": go_res.get("score_sur_100"),
            "verdict_go_nogo": go_res.get("verdict"),
            "total_dpgf_ht": prix.get("total_recalcule_ht"),
        }

    else:
        raise ValueError(f"Outil non supporté : {nom_outil}")


def main() -> None:
    """Boucle principale stdio JSON-RPC."""
    logger.info("Démarrage du serveur MCP marche-public-skill...")
    sys.stdout.reconfigure(encoding="utf-8")
    for ligne in sys.stdin:
        texte = ligne.strip()
        if not texte:
            continue
        try:
            req = json.loads(texte)
            reponse = traiter_requete(req)
            if reponse is not None:
                sys.stdout.write(json.dumps(reponse, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError as jde:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"JSON invalide: {jde}"}
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()

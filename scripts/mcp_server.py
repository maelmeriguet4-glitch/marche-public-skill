"""Serveur MCP (Model Context Protocol) officiel pour marche-public-skill.

Expose le moteur d'ingénierie et d'audit de marchés publics via le protocole standard
JSON-RPC 2.0 sur l'entrée/sortie standard (stdio), compatible avec Claude Desktop,
Antigravity, Cursor et les clients compatibles MCP.
"""

from __future__ import annotations

import io
import json
import logging
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

# Configuration du logging sur stderr pour préserver stdout pour le protocole JSON-RPC
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[MCP] %(levelname)s: %(message)s")
logger = logging.getLogger("mcp_server")

# Imports du moteur interne
SCRIPTS_DIR = Path(__file__).resolve().parent
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
import yaml


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
                    "version": "2.0.0"
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
    if nom_outil == "extraire_dce":
        rep = Path(args["repertoire_dce"])
        return extraire_dce(rep)

    elif nom_outil == "evaluer_go_nogo":
        with Path(args["chemin_analyse_json"]).open("r", encoding="utf-8") as f:
            analyse = json.load(f)
        with Path(args["chemin_profil_yaml"]).open("r", encoding="utf-8") as f:
            profil = yaml.safe_load(f)
        return evaluer_go_nogo(analyse=analyse, profil=profil)

    elif nom_outil == "verifier_dpgf":
        est_ht = Decimal(str(args["estimation_acheteur_ht"])) if args.get("estimation_acheteur_ht") is not None else None
        return auditer_fichier_dpgf(chemin_dpgf=Path(args["chemin_dpgf"]), estimation_acheteur_ht=est_ht)

    elif nom_outil == "generer_checklist_4d":
        with Path(args["chemin_analyse_json"]).open("r", encoding="utf-8") as f:
            analyse = json.load(f)
        with Path(args["chemin_profil_yaml"]).open("r", encoding="utf-8") as f:
            profil = yaml.safe_load(f)
        return generer_checklist(dce_analyse=analyse, profil=profil)

    elif nom_outil == "auditer_dossier_complet":
        rep_dce = Path(args["repertoire_dce"])
        p_profil = Path(args["chemin_profil_yaml"])
        p_dpgf = Path(args["chemin_dpgf"])

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

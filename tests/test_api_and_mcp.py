"""Tests unitaires et d'intégration pour scripts/api.py et scripts/mcp_server.py."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
import sys
import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from fastapi.testclient import TestClient
from api import app, resoudre_et_securiser_chemin
from mcp_server import traiter_requete, executer_outil, MCP_TOOLS


@pytest.fixture
def api_client() -> TestClient:
    return TestClient(app)


def test_api_health_endpoint(api_client: TestClient):
    """Vérifie le point de santé /health."""
    resp = api_client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "2.0.1"
    assert "timestamp" in data


def test_api_extract_dce_endpoint(api_client: TestClient):
    """Vérifie l'extraction DCE via API."""
    demo_dir = Path(__file__).resolve().parent.parent / "examples" / "demo-ecole-toiture" / "dce_resolu"
    if not demo_dir.exists():
        demo_dir = Path(__file__).resolve().parent.parent / "examples" / "demo-ecole-toiture"
    resp = api_client.post("/api/v1/dce/extract", json={"repertoire_dce": str(demo_dir)})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_pieces"] >= 1
    assert "sommaire_classification" in data


def test_api_path_traversal_blocked(api_client: TestClient):
    """Vérifie le blocage immédiat des tentatives de path traversal."""
    resp = api_client.post("/api/v1/dce/extract", json={"repertoire_dce": "../../Windows"})
    assert resp.status_code in (400, 403, 404)


def test_api_controle_prix_endpoint(api_client: TestClient):
    """Vérifie le contrôle de prix DPGF via API."""
    dpgf_path = Path(__file__).resolve().parent.parent / "examples" / "demo-ecole-toiture" / "DPGF.xlsx"
    resp = api_client.post("/api/v1/audit/prix", json={"chemin_dpgf": str(dpgf_path), "seuil_alerte_oab_pct": 20.0})
    assert resp.status_code == 200
    data = resp.json()
    assert "total_recalcule_ht" in data
    assert data["nb_lignes_verifiees"] > 0


def test_mcp_initialize():
    """Vérifie la conformité de l'initialisation MCP JSON-RPC."""
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {}
    }
    resp = traiter_requete(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == "marche-public-skill"
    assert resp["result"]["serverInfo"]["version"] == "2.0.1"


def test_mcp_tools_list():
    """Vérifie la liste et le schéma des outils MCP exposés."""
    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    resp = traiter_requete(req)
    assert resp["jsonrpc"] == "2.0"
    tools = resp["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "extraire_dce" in tool_names
    assert "analyser_marche_dce" in tool_names
    assert "consulter_exigences" in tool_names
    assert "consulter_pieces_manquantes" in tool_names
    assert "consulter_anomalies" in tool_names
    assert "consulter_preuves" in tool_names
    assert "evaluer_go_nogo" in tool_names
    assert "verifier_dpgf" in tool_names
    assert "generer_checklist_4d" in tool_names
    assert "auditer_dossier_complet" in tool_names


def test_mcp_tool_call_verifier_dpgf():
    """Vérifie l'invocation de verifier_dpgf via le protocole MCP."""
    dpgf_path = Path(__file__).resolve().parent.parent / "examples" / "demo-ecole-toiture" / "DPGF.xlsx"
    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "verifier_dpgf",
            "arguments": {
                "chemin_dpgf": str(dpgf_path),
                "estimation_acheteur_ht": 145000.0
            }
        }
    }
    resp = traiter_requete(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 3
    assert resp["result"]["isError"] is False
    content_text = resp["result"]["content"][0]["text"]
    data = json.loads(content_text)
    assert "total_recalcule_ht" in data
    assert data["total_recalcule_ht"] == "142500.00"


def test_mcp_tool_call_consulter_exigences():
    """Vérifie l'outil MCP consulter_exigences."""
    demo_dir = Path(__file__).resolve().parent.parent / "examples" / "demo-ecole-toiture" / "dce_resolu"
    if not demo_dir.exists():
        demo_dir = Path(__file__).resolve().parent.parent / "examples" / "demo-ecole-toiture"
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "consulter_exigences",
            "arguments": {
                "repertoire_dce": str(demo_dir),
            }
        }
    }
    resp = traiter_requete(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["result"]["isError"] is False
    data = json.loads(resp["result"]["content"][0]["text"])
    assert data["total_exigences"] >= 1


def test_mcp_path_traversal_blocked():
    """Vérifie le blocage de traversée de chemin dans les outils MCP."""
    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "extraire_dce",
            "arguments": {
                "repertoire_dce": "../../secret",
            }
        }
    }
    resp = traiter_requete(req)
    assert resp["result"]["isError"] is True
    assert "Accès interdit" in resp["result"]["content"][0]["text"]

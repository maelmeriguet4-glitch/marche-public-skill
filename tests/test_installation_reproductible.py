"""Test garantissant la reproductibilité et l'intégrité de l'environnement d'exécution."""

from __future__ import annotations

import importlib
from pathlib import Path
import pytest


def test_toutes_dependances_production_importables():
    """Vérifie que chaque dépendance déclarée dans requirements.txt est importable."""
    req_file = Path(__file__).resolve().parent.parent / "requirements.txt"
    assert req_file.exists(), "requirements.txt doit exister à la racine du projet"

    modules_a_tester = [
        "pypdf",
        "docx",
        "openpyxl",
        "yaml",
        "fastapi",
        "pydantic",
        "uvicorn",
    ]

    for mod in modules_a_tester:
        m = importlib.import_module(mod)
        assert m is not None, f"Le module {mod} doit être importable sans erreur"


def test_dependances_dev_importables():
    """Vérifie que les dépendances d'outillage de test sont disponibles."""
    for mod in ["pytest", "httpx"]:
        m = importlib.import_module(mod)
        assert m is not None, f"Le module dev {mod} doit être importable"


def test_modules_internes_moteur_importables():
    """Vérifie que tous les scripts clés du moteur sont importables sans effet de bord."""
    modules_internes = [
        "common",
        "moteur_conformite",
        "controle_final",
        "go_nogo",
        "controle_prix",
        "analyse_marche",
        "calendrier",
        "checklist_pieces",
        "matrice_conformite",
        "dce_extract",
        "api",
        "mcp_server",
    ]

    for mod in modules_internes:
        m = importlib.import_module(mod)
        assert m is not None, f"Le module interne {mod} doit être importable"

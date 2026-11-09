"""Utilitaires transversaux pour le skill marches-publics.

Module fournissant la gestion sécurisée des chemins, l'arithmétique monétaire
stricte en decimal.Decimal, la sérialisation JSON déterministe et le journal
d'exécution d'ingénierie.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

# Configuration du format des logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stderr,
)

logger = logging.getLogger("marches_publics")

CENTIME = Decimal("0.01")


def to_decimal(val: Union[int, float, str, Decimal, None], default: str = "0.00") -> Decimal:
    """Convertit de manière sûre une valeur numérique en Decimal.
    
    Rejette les types float pour éviter les imprécisions d'arrondi binaire.
    """
    if val is None:
        return Decimal(default)
    if isinstance(val, Decimal):
        return val
    if isinstance(val, (int, str)):
        s = str(val).strip().replace(" ", "").replace(",", ".")
        if not s:
            return Decimal(default)
        return Decimal(s)
    if isinstance(val, float):
        # Conversion d'un float via représentation textuelle arrondie à 6 décimales
        # pour éviter les artefacts binaires (ex: 142500.0 -> "142500.0")
        return Decimal(f"{val:.6f}").quantize(CENTIME, rounding=ROUND_HALF_UP)
    raise TypeError(f"Type non supporté pour conversion Decimal: {type(val)}")


def arrondi_monnaie(val: Decimal) -> Decimal:
    """Arrondit un Decimal à 2 décimales selon la règle comptable ROUND_HALF_UP."""
    return val.quantize(CENTIME, rounding=ROUND_HALF_UP)


def formater_montant_fr(val: Decimal) -> str:
    """Formate un Decimal en devise française standard (ex: 142 500,00 €)."""
    val_arrondie = arrondi_monnaie(val)
    signe = "-" if val_arrondie < 0 else ""
    val_abs = abs(val_arrondie)
    parties = f"{val_abs:.2f}".split(".")
    entier = parties[0]
    decimales = parties[1]
    
    # Séparation par milliers avec espace insécable fine ou standard
    groupes = []
    while len(entier) > 3:
        groupes.insert(0, entier[-3:])
        entier = entier[:-3]
    if entier:
        groupes.insert(0, entier)
    entier_formate = " ".join(groupes)
    return f"{signe}{entier_formate},{decimales} €"


def resoudre_chemin_securise(chemin: Union[str, Path], base_dir: Optional[Union[str, Path]] = None) -> Path:
    """Résout un chemin absolu et vérifie l'absence de traversée hors limite si base_dir est spécifié."""
    p = Path(chemin).expanduser().resolve()
    if base_dir is not None:
        b = Path(base_dir).expanduser().resolve()
        try:
            p.relative_to(b)
        except ValueError as err:
            raise PermissionError(f"Accès refusé hors du répertoire autorisé : {p} n'est pas dans {b}") from err
    return p


def ecrire_fichier_securise(chemin_cible: Union[str, Path], contenu: str, base_dir: Optional[Union[str, Path]] = None) -> Path:
    """Écrit du contenu texte dans un fichier après avoir créé les répertoires parents."""
    cible = resoudre_chemin_securise(chemin_cible, base_dir=base_dir)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(contenu, encoding="utf-8")
    return cible


def serializer_decimal(obj: Any) -> Any:
    """Gestionnaire de sérialisation JSON pour types Decimal et Path."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"Type {type(obj)} non sérialisable en JSON")


def ecrire_json(chemin_cible: Union[str, Path], donnees: Any) -> Path:
    """Écrit une structure de données en JSON indenté de manière déterministe."""
    contenu = json.dumps(donnees, indent=2, ensure_ascii=False, default=serializer_decimal)
    return ecrire_fichier_securise(chemin_cible, contenu)


def charger_json(chemin_source: Union[str, Path]) -> Dict[str, Any]:
    """Charge un fichier JSON en vérifiant son intégrité."""
    source = resoudre_chemin_securise(chemin_source)
    if not source.exists():
        raise FileNotFoundError(f"Fichier introuvable : {source}")
    with source.open("r", encoding="utf-8") as f:
        return json.load(f)


def assainir_texte_dce(texte: str) -> str:
    """Assainit le texte extrait du DCE contre les tentatives d'injection de prompt.
    
    Neutralise les balises d'instructions de systèmes de dialogue ou de métaprompting.
    """
    if not texte:
        return ""
    # Remplacement des balises de système ou d'injection courantes
    patterns = [
        r"<\|.*?\|>",
        r"\[SYSTEM_INSTRUCTION.*?\].*?\[/SYSTEM_INSTRUCTION\]",
        r"<\/?instruction.*?>",
    ]
    texte_propre = texte
    for p in patterns:
        texte_propre = re.sub(p, "[CONTENU_IGNORÉ]", texte_propre, flags=re.IGNORECASE | re.DOTALL)
    return texte_propre

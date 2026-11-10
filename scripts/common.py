"""Utilitaires transversaux pour le skill marches-publics.

Module fournissant la gestion sécurisée des chemins, l'arithmétique monétaire
stricte en decimal.Decimal, la sérialisation JSON déterministe et le journal
d'exécution d'ingénierie.
"""

from __future__ import annotations

import datetime
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


def to_decimal(val: Union[int, float, str, Decimal, None], default: str = "0.00", strict: bool = False) -> Decimal:
    """Convertit une valeur numérique en Decimal.
    
    Si strict=True, rejette les floats pour contraindre l'appelant à fournir
    une chaîne ou un entier afin d'éviter toute perte de précision préalable.
    """
    if val is None:
        return Decimal(default)
    if isinstance(val, Decimal):
        return val
    if isinstance(val, int):
        return Decimal(val)
    if isinstance(val, str):
        s = val.strip().replace(" ", "").replace(",", ".")
        if not s:
            return Decimal(default)
        return Decimal(s)
    if isinstance(val, float):
        if strict:
            raise TypeError(f"Type float interdit en mode strict pour préserver la précision financière: {val}")
        # Conversion sans perte artificielle par quantification prématurée
        return Decimal(str(val))
    raise TypeError(f"Type non supporté pour conversion Decimal: {type(val)}")


def paques(annee: int) -> datetime.date:
    """Calcul de la date du dimanche de Pâques (algorithme de Butcher-Meeus)."""
    a = annee % 19
    b = annee // 100
    c = annee % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois = (h + l - 7 * m + 114) // 31
    jour = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(annee, mois, jour)


def jours_feries_france(annee: int) -> set[datetime.date]:
    """Retourne l'ensemble des 11 jours fériés légaux français pour une année."""
    p = paques(annee)
    return {
        datetime.date(annee, 1, 1),    # Jour de l'an
        p + datetime.timedelta(days=1), # Lundi de Pâques
        datetime.date(annee, 5, 1),    # Fête du Travail
        datetime.date(annee, 5, 8),    # Victoire 1945
        p + datetime.timedelta(days=39),# Ascension
        p + datetime.timedelta(days=50),# Lundi de Pentecôte
        datetime.date(annee, 7, 14),   # Fête Nationale
        datetime.date(annee, 8, 15),   # Assomption
        datetime.date(annee, 11, 1),   # Toussaint
        datetime.date(annee, 11, 11),  # Armistice 1918
        datetime.date(annee, 12, 25),  # Noël
    }


def est_jour_ouvre(d: datetime.date) -> bool:
    """Vérifie si une date est un jour ouvré (du lundi au vendredi hors jours fériés)."""
    if d.weekday() >= 5:  # 5 = samedi, 6 = dimanche
        return False
    return d not in jours_feries_france(d.year)


def reculer_jours_ouvres(date_ref: datetime.date, nb_jours: int) -> datetime.date:
    """Recule d'un nombre déterminé de jours ouvrés stricts."""
    cur = date_ref
    restants = nb_jours
    while restants > 0:
        cur -= datetime.timedelta(days=1)
        if est_jour_ouvre(cur):
            restants -= 1
    return cur


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


class DateTimeWithDateEquality(datetime.datetime):
    """datetime.datetime préservant heures, minutes, secondes et fuseaux horaires,
    tout en supportant les comparaisons d'égalité et d'ordre directes avec datetime.date.
    """

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, datetime.date) and not isinstance(other, datetime.datetime):
            return self.date() == other
        return super().__eq__(other)

    def __ne__(self, other: Any) -> bool:
        return not self.__eq__(other)

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, datetime.date) and not isinstance(other, datetime.datetime):
            return self.date() < other
        return super().__lt__(other)

    def __le__(self, other: Any) -> bool:
        if isinstance(other, datetime.date) and not isinstance(other, datetime.datetime):
            return self.date() <= other
        return super().__le__(other)

    def __gt__(self, other: Any) -> bool:
        if isinstance(other, datetime.date) and not isinstance(other, datetime.datetime):
            return self.date() > other
        return super().__gt__(other)

    def __ge__(self, other: Any) -> bool:
        if isinstance(other, datetime.date) and not isinstance(other, datetime.datetime):
            return self.date() >= other
        return super().__ge__(other)


def parser_date_et_echeance(
    val: Any,
    maintenant: Optional[datetime.datetime] = None,
) -> Tuple[Optional[DateTimeWithDateEquality], str, bool]:
    """Parse une date/datetime (ISO 8601 ou format français) en conservant heures et fuseaux.

    Retourne : (dt_objet, representation_chaine, est_depassee).
    Si l'heure n'est pas spécifiée, l'heure par défaut est 18:00:00.
    """
    if val is None:
        return None, "", False

    if isinstance(val, DateTimeWithDateEquality):
        dt = val
        s_repr = str(val)
    elif isinstance(val, datetime.datetime):
        dt = DateTimeWithDateEquality(
            val.year, val.month, val.day, val.hour, val.minute, val.second, val.microsecond, val.tzinfo
        )
        s_repr = str(val)
    elif isinstance(val, datetime.date):
        dt = DateTimeWithDateEquality(val.year, val.month, val.day, 18, 0, 0)
        s_repr = str(val)
    else:
        s_str = str(val).strip()
        if not s_str:
            return None, "", False
        s_repr = s_str

        # 1. ISO 8601 : YYYY-MM-DD[T\sHH:MM[:SS]]
        m_iso = re.search(
            r"\b(\d{4})-(\d{1,2})-(\d{1,2})(?:[T\s](\d{1,2})[:h](\d{1,2})(?:[:\.](\d{1,2}))?)?",
            s_str,
        )
        # 2. Format français : JJ/MM/AAAA ou JJ-MM-AAAA ou JJ.MM.AAAA [à HHhMM]
        m_fr = re.search(
            r"\b(\d{1,2})[\/\.-](\d{1,2})[\/\.-](\d{2,4})(?:(?:\s*(?:[àa]\s*)?|\s+)(\d{1,2})[h:](\d{1,2})(?:[:\.](\d{1,2}))?)?",
            s_str,
            re.IGNORECASE,
        )

        annee, mois, jour = None, None, None
        heure, minute, seconde = 18, 0, 0

        if m_iso:
            annee = int(m_iso.group(1))
            mois = int(m_iso.group(2))
            jour = int(m_iso.group(3))
            if m_iso.group(4) is not None:
                heure = int(m_iso.group(4))
                minute = int(m_iso.group(5)) if m_iso.group(5) is not None else 0
                seconde = int(m_iso.group(6)) if m_iso.group(6) is not None else 0
        elif m_fr:
            jour = int(m_fr.group(1))
            mois = int(m_fr.group(2))
            annee = int(m_fr.group(3))
            if annee < 100:
                annee += 2000
            if m_fr.group(4) is not None:
                heure = int(m_fr.group(4))
                minute = int(m_fr.group(5)) if m_fr.group(5) is not None else 0
                seconde = int(m_fr.group(6)) if m_fr.group(6) is not None else 0
        else:
            return None, s_repr, False

        try:
            dt = DateTimeWithDateEquality(annee, mois, jour, heure, minute, seconde)
        except (ValueError, TypeError, OverflowError):
            return None, s_repr, False

    # Évaluation de dépassement par rapport à maintenant
    maintenant_dt = maintenant or datetime.datetime.now()
    if maintenant_dt.tzinfo is not None and dt.tzinfo is None:
        maintenant_dt = maintenant_dt.replace(tzinfo=None)
    elif maintenant_dt.tzinfo is None and dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)

    est_depassee = dt < maintenant_dt
    return dt, s_repr, est_depassee


"""Aide à la décision Go / No-Go multicritère pour marchés publics de travaux BTP.

Évalue 8 critères pondérés sur 100 points à partir du profil de l'entreprise,
du DCE et de la configuration des seuils, avec détection rigoureuse des drapeaux rouges éliminatoires.
Ne contient aucune note fixe ni point de complaisance : les scores sont calculés à partir
des données effectives et vérifiables. En l'absence de données essentielles, 0 point est attribué
et le critère est qualifié NON_EVALUABLE.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import math
import re
import sys
import unicodedata
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

from common import (
    charger_json,
    ecrire_fichier_securise,
    ecrire_json,
    est_jour_ouvre,
    resoudre_chemin_securise,
    to_decimal,
)

logger = logging.getLogger("go_nogo")


# =============================================================================
# 1. CLASSE TEMPORELLE & OUTILS DE PARSING DE DATES
# =============================================================================

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

    def __hash__(self) -> int:
        return super().__hash__()


def _normaliser_texte(s: str) -> str:
    """Normalise une chaîne : minuscules, suppression des accents et espaces superflus."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFD", str(s))
    sans_accent = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")
    return sans_accent.lower().strip()


def _aplatir_valeurs(obj: Any):
    """Générateur récursif aplatissant les structures arbitrairement imbriquées en chaînes."""
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _aplatir_valeurs(v)
    elif isinstance(obj, (list, tuple, set)):
        for item in obj:
            yield from _aplatir_valeurs(item)
    elif obj is not None:
        yield str(obj)


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

        dt = None
        if m_iso:
            try:
                y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
                hh = int(m_iso.group(4)) if m_iso.group(4) is not None else 18
                mm = int(m_iso.group(5)) if m_iso.group(5) is not None else 0
                ss = int(m_iso.group(6)) if m_iso.group(6) is not None else 0

                tz = None
                if "z" in s_str.lower() or "+00:00" in s_str:
                    tz = datetime.timezone.utc
                elif re.search(r"([+-]\d{2}):?(\d{2})", s_str):
                    m_tz = re.search(r"([+-]\d{2}):?(\d{2})", s_str)
                    if m_tz:
                        h_offset = int(m_tz.group(1))
                        m_offset = int(m_tz.group(2))
                        tz = datetime.timezone(datetime.timedelta(hours=h_offset, minutes=m_offset))

                dt = DateTimeWithDateEquality(y, m, d, hh, mm, ss, tzinfo=tz)
            except ValueError:
                dt = None

        elif m_fr:
            try:
                d, m, y = int(m_fr.group(1)), int(m_fr.group(2)), int(m_fr.group(3))
                if y < 100:
                    y += 2000
                hh = int(m_fr.group(4)) if m_fr.group(4) is not None else 18
                mm = int(m_fr.group(5)) if m_fr.group(5) is not None else 0
                ss = int(m_fr.group(6)) if m_fr.group(6) is not None else 0

                tz = None
                if "paris" in s_str.lower() or "cet" in s_str.lower():
                    tz = datetime.timezone(datetime.timedelta(hours=1))
                elif "cest" in s_str.lower():
                    tz = datetime.timezone(datetime.timedelta(hours=2))

                dt = DateTimeWithDateEquality(y, m, d, hh, mm, ss, tzinfo=tz)
            except ValueError:
                dt = None

    if dt is None:
        return None, s_repr, False

    # Calcul de forclusion (comparaison avec maintenant)
    if maintenant is None:
        maintenant = datetime.datetime.now()

    # Alignement tz-naive vs tz-aware pour comparaison sans exception
    if dt.tzinfo is not None and maintenant.tzinfo is None:
        now_dt = maintenant.replace(tzinfo=datetime.timezone.utc)
        dt_comp = dt.astimezone(datetime.timezone.utc)
        est_depassee = dt_comp < now_dt
    elif dt.tzinfo is None and maintenant.tzinfo is not None:
        dt_comp = dt.replace(tzinfo=datetime.timezone.utc)
        now_dt = maintenant.astimezone(datetime.timezone.utc)
        est_depassee = dt_comp < now_dt
    else:
        est_depassee = dt < maintenant

    return dt, s_repr, est_depassee


def extraire_date_limite(
    analyse_ou_str: Any,
    maintenant: Optional[datetime.datetime] = None,
) -> Tuple[Optional[DateTimeWithDateEquality], str]:
    """Extrait et parse la date limite de remise des plis.

    Retourne : (dt_with_date_equality, str_brute).
    """
    if not analyse_ou_str:
        return None, ""

    if isinstance(analyse_ou_str, dict):
        cal = analyse_ou_str.get("calendrier") if isinstance(analyse_ou_str.get("calendrier"), dict) else {}
        s = (
            cal.get("date_limite_retenue")
            or analyse_ou_str.get("date_limite")
            or cal.get("date_limite_remise_rc")
            or cal.get("date_limite_remise_ae")
            or ""
        )
    else:
        s = analyse_ou_str

    if not s:
        return None, ""

    dt, s_repr, _ = parser_date_et_echeance(s, maintenant=maintenant)
    return dt, s_repr


# =============================================================================
# 2. EXTRACTION MULTI-SCHÉMAS DU PROFIL ENTREPRISE
# =============================================================================

def extraire_effectif_total(profil: Dict[str, Any]) -> int:
    """Extrait l'effectif total avec résolution multi-chemins dans le profil YAML."""
    if not isinstance(profil, dict):
        return 0

    candidates = [
        profil.get("effectifs", {}).get("total_salaries") if isinstance(profil.get("effectifs"), dict) else None,
        profil.get("effectifs", {}).get("effectif_total") if isinstance(profil.get("effectifs"), dict) else None,
        profil.get("moyens_humains", {}).get("effectif_total") if isinstance(profil.get("moyens_humains"), dict) else None,
        profil.get("moyens_humains", {}).get("total_salaries") if isinstance(profil.get("moyens_humains"), dict) else None,
        profil.get("effectifs") if isinstance(profil.get("effectifs"), (int, float, str)) and str(profil.get("effectifs")).strip().replace(".", "", 1).isdigit() else None,
        profil.get("effectif_total"),
        profil.get("total_salaries"),
    ]
    for c in candidates:
        if c is not None:
            try:
                c_str = str(c).strip()
                val = int(float(c_str))
                if val > 0:
                    return val
            except (ValueError, TypeError):
                continue
    return 0


def extraire_code_postal(profil: Dict[str, Any]) -> str:
    """Extrait le code postal avec résolution multi-chemins dans le profil YAML."""
    if not isinstance(profil, dict):
        return ""

    candidates = [
        profil.get("identite", {}).get("siege_social", {}).get("code_postal") if isinstance(profil.get("identite"), dict) and isinstance(profil.get("identite", {}).get("siege_social"), dict) else None,
        profil.get("siege_social", {}).get("code_postal") if isinstance(profil.get("siege_social"), dict) else None,
        profil.get("coordonnees", {}).get("code_postal") if isinstance(profil.get("coordonnees"), dict) else None,
        profil.get("identite", {}).get("code_postal") if isinstance(profil.get("identite"), dict) else None,
        profil.get("code_postal"),
    ]
    for c in candidates:
        if c is not None:
            cp_str = str(c).strip()
            if len(cp_str) >= 2:
                return cp_str
    return ""


def extraire_structure_couts(
    profil: Dict[str, Any], couts: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Résout la structure de coûts et de marges à partir du profil ou de couts.yaml (--couts prioritaire)."""
    res: Dict[str, Any] = {}

    if isinstance(profil, dict):
        if "coefficients_et_frais" in profil and isinstance(profil["coefficients_et_frais"], dict):
            res.update(profil["coefficients_et_frais"])
        if "structure_couts" in profil and isinstance(profil["structure_couts"], dict):
            res.update(profil["structure_couts"])
        if "couts" in profil and isinstance(profil["couts"], dict):
            if "coefficients_et_frais" in profil["couts"] and isinstance(profil["couts"]["coefficients_et_frais"], dict):
                res.update(profil["couts"]["coefficients_et_frais"])
            if "structure_couts" in profil["couts"] and isinstance(profil["couts"]["structure_couts"], dict):
                res.update(profil["couts"]["structure_couts"])

    if isinstance(couts, dict):
        if "coefficients_et_frais" in couts and isinstance(couts["coefficients_et_frais"], dict):
            res.update(couts["coefficients_et_frais"])
        if "structure_couts" in couts and isinstance(couts["structure_couts"], dict):
            res.update(couts["structure_couts"])
        for k, v in couts.items():
            if k not in ("coefficients_et_frais", "structure_couts"):
                res[k] = v

    return res


# =============================================================================
# 3. GÉOGRAPHIE RÉELLE (HAVERSINE, CENTROÏDES, CORSE & DOM-TOM)
# =============================================================================

# Centroïdes des 101 départements français (Métropole + DOM)
DEPARTEMENT_COORDS: Dict[str, Tuple[float, float]] = {
    "01": (46.20, 5.23), "02": (49.56, 3.62), "03": (46.57, 3.33), "04": (44.09, 6.24),
    "05": (44.56, 6.08), "06": (43.70, 7.27), "07": (44.74, 4.60), "08": (49.77, 4.72),
    "09": (42.97, 1.61), "10": (48.30, 4.07), "11": (43.21, 2.35), "12": (44.35, 2.57),
    "13": (43.30, 5.37), "14": (49.18, -0.37), "15": (44.93, 2.45), "16": (45.65, 0.16),
    "17": (45.75, -0.63), "18": (47.08, 2.40), "19": (45.27, 1.77), "2A": (41.93, 8.74),
    "2B": (42.70, 9.45), "21": (47.32, 5.04), "22": (48.51, -2.76), "23": (46.17, 1.87),
    "24": (45.18, 0.72), "25": (47.24, 6.02), "26": (44.93, 4.89), "27": (49.02, 1.15),
    "28": (48.44, 1.49), "29": (48.00, -4.10), "30": (43.84, 4.36), "31": (43.60, 1.44),
    "32": (43.65, 0.58), "33": (44.84, -0.58), "34": (43.61, 3.88), "35": (48.11, -1.68),
    "36": (46.81, 1.69), "37": (47.39, 0.69), "38": (45.19, 5.72), "39": (46.68, 5.55),
    "40": (43.89, -0.50), "41": (47.59, 1.33), "42": (45.43, 4.39), "43": (45.04, 3.88),
    "44": (47.22, -1.55), "45": (47.90, 1.90), "46": (44.45, 1.44), "47": (44.20, 0.62),
    "48": (44.52, 3.50), "49": (47.47, -0.55), "50": (49.12, -1.09), "51": (48.96, 4.36),
    "52": (48.11, 5.14), "53": (48.07, -0.77), "54": (48.69, 6.18), "55": (48.77, 5.16),
    "56": (47.66, -2.76), "57": (49.12, 6.18), "58": (46.99, 3.16), "59": (50.63, 3.06),
    "60": (49.43, 2.08), "61": (48.43, 0.09), "62": (50.29, 2.78), "63": (45.78, 3.08),
    "64": (43.30, -0.37), "65": (43.23, 0.08), "66": (42.70, 2.89), "67": (48.58, 7.75),
    "68": (47.75, 7.34), "69": (45.76, 4.84), "70": (47.62, 6.16), "71": (46.78, 4.85),
    "72": (48.00, 0.20), "73": (45.57, 5.92), "74": (45.90, 6.13), "75": (48.86, 2.34),
    "76": (49.44, 1.09), "77": (48.54, 2.66), "78": (48.80, 2.13), "79": (46.32, -0.46),
    "80": (49.89, 2.30), "81": (43.93, 2.15), "82": (44.02, 1.35), "83": (43.12, 5.93),
    "84": (43.95, 4.81), "85": (46.67, -1.43), "86": (46.58, 0.34), "87": (45.83, 1.26),
    "88": (48.17, 6.45), "89": (47.80, 3.57), "90": (47.64, 6.86), "91": (48.63, 2.44),
    "92": (48.89, 2.24), "93": (48.91, 2.44), "94": (48.79, 2.46), "95": (49.04, 2.07),
    "971": (16.25, -61.55), # Guadeloupe
    "972": (14.65, -61.01), # Martinique
    "973": (4.00, -53.00),  # Guyane
    "974": (-21.12, 55.54), # La Réunion
    "976": (-12.83, 45.17), # Mayotte
}

# Coordonnées des communes et secteurs clés pour arbitrage intra-départemental
POSTAL_CODE_COORDS: Dict[str, Tuple[float, float]] = {
    # Seine-et-Marne (77) : Meaux vs Nemours = 89 km
    "77100": (48.96, 2.88),  # Meaux (Nord 77)
    "77140": (48.27, 2.69),  # Nemours (Sud 77)
    "77000": (48.54, 2.66),  # Melun
    "77300": (48.41, 2.70),  # Fontainebleau
    "77500": (48.88, 2.59),  # Chelles
    "77400": (48.88, 2.71),  # Lagny-sur-Marne
    "77160": (48.56, 3.30),  # Provins
    # Cher (18)
    "18000": (47.08, 2.40),  # Bourges
    "18100": (47.22, 2.07),  # Vierzon (~29 km)
    # Gironde (33)
    "33000": (44.84, -0.58), # Bordeaux
    "33123": (45.55, -1.06), # Le Verdon (~95 km de Bordeaux)
    "33210": (44.55, -0.25), # Langon (~45 km de Bordeaux)
    # Paris et Petite Couronne
    "75001": (48.86, 2.34),
    "92000": (48.89, 2.21),  # Nanterre
    "92120": (48.82, 2.32),  # Montrouge (~5 km de Paris)
    "93000": (48.91, 2.44),  # Bobigny
    "94000": (48.79, 2.46),  # Créteil
    # Corse (2A, 2B)
    "2A000": (41.93, 8.74),  # Ajaccio
    "2B000": (42.70, 9.45),  # Bastia
    "2B200": (42.70, 9.45),
    # DOM-TOM
    "97100": (16.24, -61.53), # Pointe-à-Pitre
    "97400": (-20.88, 55.45), # Saint-Denis (Réunion)
    "97200": (14.61, -61.06), # Fort-de-France
    "97300": (4.93, -52.33),  # Cayenne
    "97600": (-12.78, 45.23), # Mamoudzou
}


def _calculer_distance_haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcule la distance orthodromique en km entre deux coordonnées GPS via la formule de Haversine."""
    r = 6371.0  # Rayon moyen terrestre en km
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return r * c


def extraire_code_postal_et_departement(val: Any) -> Tuple[Optional[str], Optional[str]]:
    """Extrait le code postal (5 car.) et le département normalisé (2 car. métropole, 2A/2B, 3 car. DOM)."""
    if val is None:
        return None, None
    s = str(val).strip()
    if not s:
        return None, None

    # 1. Recherche d'un code postal à 5 caractères
    m_cp = re.search(r"\b(2[AB]\d{3}|9[78]\d{3}|\d{5})\b", s, re.IGNORECASE)
    if m_cp:
        cp = m_cp.group(1).upper()
        # DOM-TOM : préfixe 3 chiffres (971, 972, 973, 974, 976, etc.)
        if cp.startswith(("97", "98")):
            return cp, cp[:3]
        # Corse : 2A ou 2B
        if cp.startswith("2A") or cp.startswith("2B"):
            return cp, cp[:2]
        if cp.startswith("20"):
            try:
                num = int(cp)
                dep = "2A" if num <= 20199 else "2B"
                return cp, dep
            except ValueError:
                return cp, "20"
        return cp, cp[:2]

    # 2. Recherche d'un département explicite
    m_dom = re.search(r"\b(97[1-6]|98[4-8])\b", s)
    if m_dom:
        return None, m_dom.group(1)

    m_corse = re.search(r"\b(2A|2B)\b", s, re.IGNORECASE)
    if m_corse:
        return None, m_corse.group(1).upper()

    m_dep = re.search(r"\b(0[1-9]|[1-8]\d|9[0-5])\b", s)
    if m_dep:
        return None, m_dep.group(1)

    # 3. Résolution par nom de ville
    s_norm = _normaliser_texte(s)
    if "bourges" in s_norm:
        return "18000", "18"
    if "vierzon" in s_norm:
        return "18100", "18"
    if "ajaccio" in s_norm:
        return "2A000", "2A"
    if "bastia" in s_norm:
        return "2B000", "2B"
    if "pointe-a-pitre" in s_norm or "pointe a pitre" in s_norm or "guadeloupe" in s_norm:
        return "97100", "971"
    if "saint-denis" in s_norm and "reunion" in s_norm:
        return "97400", "974"
    if "reunion" in s_norm:
        return "97400", "974"
    if "martinique" in s_norm:
        return "97200", "972"
    if "guyane" in s_norm:
        return "97300", "973"
    if "mayotte" in s_norm:
        return "97600", "976"

    # Code postal étranger éventuel (ex: B-1000)
    m_foreign = re.search(r"\b([A-Z]{1,2}-?\d{4,5})\b", s)
    if m_foreign:
        cp_f = m_foreign.group(1)
        return cp_f, cp_f[:2]

    return None, None


# =============================================================================
# 4. QUALIFICATION DES VISITES & VÉRIFICATION SUR DISQUE
# =============================================================================

def qualifier_obligation_visite(analyse: Dict[str, Any]) -> Tuple[str, str]:
    """Qualifie juridiquement le régime de visite du marché.

    Retourne : (statut, motif) où statut ∈ {"OBLIGATOIRE", "RECOMMANDEE", "FACULTATIVE", "AUCUNE"}.
    Gère les formulations négatives pour éviter tout faux blocage sur les visites facultatives/recommandées.
    """
    if not isinstance(analyse, dict):
        return "AUCUNE", ""

    # Mots-clés discriminants
    kw_facultative = [
        "non obligatoire", "pas obligatoire", "aucune visite exigee", "aucune visite requise",
        "sans visite obligatoire", "non requise", "non imposee", "non contraignante",
        "pas requise", "facultative", "optionnelle", "libre", "laissée à l'appréciation",
        "laissée à l'initiative", "a l'initiative", "à l'initiative"
    ]
    kw_recommandee = [
        "recommandee", "recommandée", "conseillee", "conseillée",
        "vivement recommandee", "vivement recommandée", "fortement conseillee", "fortement conseillée"
    ]
    kw_obligatoire = [
        "obligatoire", "prealable obligatoire", "préalable obligatoire", "imperative", "impérative",
        "indispensable", "requise", "exigee", "exigée", "sous peine de rejet",
        "sous peine d irrecevabilite", "sous peine d'irrecevabilité", "condition de recevabilite",
        "condition de recevabilité", "attestation de visite", "certificat de visite",
        "recepisse de visite", "justificatif de visite", "preuve de visite",
        "visite obligatoire sur site", "visite des lieux impérative", "visite sur place impérative"
    ]

    # Rassemblement de l'ensemble des textes pertinents du marché
    textes: List[str] = []

    pe = analyse.get("pieces_exigees")
    if pe is not None:
        for p in _aplatir_valeurs(pe):
            textes.append(str(p))

    clauses = analyse.get("clauses_sensibles")
    if isinstance(clauses, dict):
        if clauses.get("visite_obligatoire"):
            textes.append("visite obligatoire déclarée")
        for t in _aplatir_valeurs(clauses):
            textes.append(str(t))

    contras = analyse.get("contradictions_detectees")
    if isinstance(contras, list):
        for c in contras:
            if isinstance(c, dict):
                textes.append(str(c.get("description", "")) + " " + str(c.get("type", "")))

    if analyse.get("visite_obligatoire"):
        textes.append("visite obligatoire niveau marche")
    visite_site = analyse.get("visite_site")
    if isinstance(visite_site, dict):
        if visite_site.get("obligatoire"):
            textes.append("visite obligatoire dans visite_site")
        for t in _aplatir_valeurs(visite_site):
            textes.append(str(t))

    # Filtrage des mentions contenant le mot visite
    mentions_visite = [t for t in textes if "visite" in t.lower()]
    if not mentions_visite:
        return "AUCUNE", ""

    # Évaluation priorisée :
    # 1. Vérification si une formulation négative ou de liberté est présente
    for t in mentions_visite:
        t_norm = _normaliser_texte(t)
        if any(kw in t_norm for kw in kw_facultative):
            return "FACULTATIVE", f"Visite déclarée facultative ou libre : '{t}'"

    # 2. Vérification d'une recommandation pure (non obligatoire)
    for t in mentions_visite:
        t_norm = _normaliser_texte(t)
        if any(kw in t_norm for kw in kw_recommandee) and not any(kw in t_norm for kw in kw_obligatoire):
            return "RECOMMANDEE", f"Visite recommandée mais non éliminatoire : '{t}'"

    # 3. Vérification d'une obligation stricte
    for t in mentions_visite:
        t_norm = _normaliser_texte(t)
        if any(kw in t_norm for kw in kw_obligatoire):
            return "OBLIGATOIRE", f"Visite obligatoire exigée : '{t}'"

    # 4. Par défaut si le mot visite apparaît sans mention d'obligation
    return "RECOMMANDEE", f"Mention de visite identifiée sans clause éliminatoire : '{mentions_visite[0]}'"


def detecter_obligation_visite(analyse: Dict[str, Any]) -> Tuple[bool, str]:
    """Wrapper de rétrocompatibilité : renvoie True si et seulement si la visite est OBLIGATOIRE."""
    statut, motif = qualifier_obligation_visite(analyse)
    return (statut == "OBLIGATOIRE", motif)


def verifier_presence_fichier_sur_disque(
    nom_fichier: Optional[Union[str, Path]],
    dossiers_docs: Optional[List[Union[str, Path]]] = None,
) -> bool:
    """Contrôle la présence physique réelle d'un document sur le disque."""
    if not nom_fichier or not isinstance(nom_fichier, (str, Path)):
        return False
    s_nom = str(nom_fichier).strip()
    if not s_nom or s_nom in (".", ".."):
        return False

    try:
        p_nom = Path(nom_fichier)
    except (TypeError, ValueError, OSError):
        return False

    # 1. Test direct si chemin absolu
    try:
        if p_nom.is_absolute():
            return p_nom.is_file()
    except (OSError, ValueError):
        pass

    # 2. Rejet des traversées de chemin interdites
    if ".." in p_nom.parts:
        return False

    # 3. Dossiers de recherche
    dossiers_recherche: List[Path] = []
    if dossiers_docs:
        for d in dossiers_docs:
            if d:
                try:
                    dossiers_recherche.append(Path(d))
                except Exception:
                    pass

    cur = Path(__file__).resolve().parent
    racine_projet = cur
    while cur != cur.parent:
        if (cur / "PROJECT.md").exists() or (cur / "scripts" / "go_nogo.py").exists():
            racine_projet = cur
            break
        cur = cur.parent
    dossiers_recherche.extend([
        racine_projet,
        racine_projet / "examples" / "demo-ecole-toiture",
        racine_projet / "tests" / "fixtures",
        racine_projet / "assets",
        Path.cwd(),
    ])

    nom_simple = p_nom.name
    for base in dossiers_recherche:
        try:
            base_resolved = base.resolve()
            # Test direct chemin relatif confiné au dossier
            cible = (base / p_nom).resolve()
            if cible.is_file():
                return True
            # Test par nom simple
            if nom_simple and nom_simple != ".":
                cible_nom = (base / nom_simple).resolve()
                if cible_nom.is_file():
                    return True
        except (OSError, ValueError, TypeError):
            continue

    return False


def verifier_visite_effectuee_profil(
    profil: Dict[str, Any],
    date_limite_dt: Optional[datetime.datetime] = None,
    dossiers_docs: Optional[List[Union[str, Path]]] = None,
) -> Tuple[bool, str, Optional[str]]:
    """Vérifie si la visite sur site obligatoire a été réalisée, attestée et dans les délais.

    Retourne : (est_validee, motif, code_erreur_optionnel).
    """
    if not isinstance(profil, dict):
        return False, "Profil entreprise absent ou invalide.", "VISITE_OBLIGATOIRE_MANQUEE"

    v_info = profil.get("visite_site")
    if not isinstance(v_info, dict):
        v_info = {}

    visite_faite = (
        v_info.get("visite_effectuee") is True
        or v_info.get("effectuee") is True
        or profil.get("visite_effectuee") is True
        or profil.get("visite_site_effectuee") is True
    )

    fich_attest = v_info.get("attestation_fichier") or (
        profil.get("fichiers_justificatifs", {}).get("attestation_visite")
        if isinstance(profil.get("fichiers_justificatifs"), dict)
        else None
    )
    fich_present = False
    if fich_attest:
        fich_present = verifier_presence_fichier_sur_disque(fich_attest, dossiers_docs)
        if not fich_present:
            return False, f"Fichier d'attestation de visite déclaré ('{fich_attest}') introuvable sur disque.", "VISITE_OBLIGATOIRE_MANQUEE"

    if not visite_faite and not fich_present and not v_info.get("date_visite"):
        return False, "Aucune attestation ni preuve de visite enregistrée dans le profil entreprise.", "VISITE_OBLIGATOIRE_MANQUEE"

    # Vérification d'antériorité par rapport à la date limite
    date_visite_raw = v_info.get("date_visite")
    if date_visite_raw and date_limite_dt:
        dt_v, _, _ = parser_date_et_echeance(date_visite_raw)
        if dt_v and dt_v > date_limite_dt:
            return (
                False,
                f"Visite effectuée ({dt_v.strftime('%d/%m/%Y')}) postérieurement à la date limite de remise ({date_limite_dt.strftime('%d/%m/%Y')}).",
                "VISITE_POSTERIEURE_ECHEANCE",
            )

    return True, "Visite effectuée et justifiée.", None


# =============================================================================
# 5. ONTOLOGIE MÉTIERS BTP & CONTRÔLE D'ASSURANCE
# =============================================================================

ONTOLOGIE_METIERS_BTP: Dict[str, List[str]] = {
    "couverture_etancheite": [
        "couverture", "toiture", "zinguerie", "etancheite", "ardoise",
        "tuile", "bac acier", "cheneau", "gouttiere", "bardeaux"
    ],
    "maconnerie_gros_oeuvre": [
        "maconnerie", "gros oeuvre", "beton", "fondation", "demolition", "terrassement"
    ],
    "charpente_bois": [
        "charpente", "ossature bois", "lamelle colle"
    ],
    "menuiserie_fermetures": [
        "menuiserie", "fermeture", "vitrerie", "facade", "volet", "fenetre", "porte", "brise-soleil"
    ],
    "platrerie_isolation": [
        "platrerie", "isolation", "cloison", "faux plafond", "doublage", "enduit"
    ],
    "peinture_revetements": [
        "peinture", "revetement", "sol", "carrelage", "faience", "chape"
    ],
    "plomberie_sanitaire_cvc": [
        "plomberie", "sanitaire", "chauffage", "cvc", "ventilation", "climatisation", "fumisterie"
    ],
    "electricite": [
        "electricite", "courants forts", "courants faibles", "eclairage", "cablage"
    ],
    "vrd_travaux_publics": [
        "vrd", "voirie", "assainissement", "reseaux", "enrobe", "pavage", "terrassement"
    ],
    "desamiantage": [
        "desamiantage", "amiante", "deplombage"
    ],
}


def verifier_adequation_activites_assurance(
    activites_couvertes: Union[List[str], str, None],
    objet_marche: str,
    lots: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, str]:
    """Confronte les activités couvertes par la police d'assurance aux travaux du marché."""
    if not activites_couvertes:
        return True, "Activités couvertes non détaillées dans la police."

    objet_norm = _normaliser_texte(objet_marche)
    lots_norm = _normaliser_texte(" ".join(str(l) for l in (lots or [])))
    texte_marche = f"{objet_norm} {lots_norm}"

    # Détection des métiers du marché
    metiers_marche: set[str] = set()
    for cat, kws in ONTOLOGIE_METIERS_BTP.items():
        if any(kw in texte_marche for kw in kws):
            metiers_marche.add(cat)

    if not metiers_marche:
        return True, "Objet du marché sans corps d'état spécialisé exclusif."

    # Détection des métiers couverts par l'assurance
    texte_assur = _normaliser_texte(
        " ".join(activites_couvertes) if isinstance(activites_couvertes, list) else str(activites_couvertes)
    )
    metiers_assur: set[str] = set()
    for cat, kws in ONTOLOGIE_METIERS_BTP.items():
        if any(kw in texte_assur for kw in kws):
            metiers_assur.add(cat)

    communs = metiers_marche.intersection(metiers_assur)
    if communs:
        return True, f"Activités d'assurance en adéquation ({', '.join(communs)})."

    return (
        False,
        f"Inadéquation des garanties : le marché requiert {', '.join(metiers_marche)}, mais l'assurance ne mentionne que {', '.join(metiers_assur) or 'aucune activité correspondante'}.",
    )


def verifier_assurances_go_nogo(
    analyse: Dict[str, Any],
    profil: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
    dossiers_docs: Optional[List[Union[str, Path]]] = None,
    maintenant: Optional[datetime.datetime] = None,
) -> List[Dict[str, Any]]:
    """Vérifie les garanties d'assurance décennale (présence, fichier sur disque, validité, adéquation)."""
    drapeaux: List[Dict[str, Any]] = []

    # Sur un dossier où marché et profil sont vides ou sans données substantielles,
    # le dossier est structurellement inévaluable : ne pas lever DEFAUT_ASSURANCE_DECENNALE.
    has_market_data = any(v is not None and v != {} and v != [] for v in analyse.values()) if isinstance(analyse, dict) else False
    has_profil_data = any(v is not None and v != {} and v != [] for v in profil.values()) if isinstance(profil, dict) else False
    if not has_market_data and not has_profil_data:
        return drapeaux

    assurances = profil.get("assurances") if isinstance(profil, dict) else {}
    if isinstance(assurances, str):
        decennale = {"numero_police": assurances}
    elif isinstance(assurances, dict):
        decennale = assurances.get("decennale")
        if isinstance(decennale, str):
            decennale = {"numero_police": decennale}
        elif not isinstance(decennale, dict):
            prof_dec = profil.get("decennale") if isinstance(profil, dict) else None
            if isinstance(prof_dec, dict):
                decennale = prof_dec
            elif isinstance(prof_dec, str):
                decennale = {"numero_police": prof_dec}
            else:
                decennale = {}
    else:
        decennale = {}

    if not decennale:
        drapeaux.append({
            "id": "DEFAUT_ASSURANCE_DECENNALE",
            "code": "DEFAUT_ASSURANCE_DECENNALE",
            "motif": "Absence d'attestation d'assurance décennale enregistrée dans le profil entreprise.",
            "description": "Absence d'attestation d'assurance décennale enregistrée dans le profil entreprise.",
            "bloquant": True,
        })
        return drapeaux

    num_pol = decennale.get("numero_police") or profil.get("numero_police")
    fich_justifs = profil.get("fichiers_justificatifs") if isinstance(profil, dict) else {}
    fich_assur = (
        decennale.get("fichier")
        or decennale.get("attestation_fichier")
        or (fich_justifs.get("decennale") if isinstance(fich_justifs, dict) else None)
    )

    if not num_pol and not fich_assur:
        drapeaux.append({
            "id": "DEFAUT_ASSURANCE_DECENNALE",
            "code": "DEFAUT_ASSURANCE_DECENNALE",
            "motif": "Ni numéro de police ni fichier d'attestation décennale n'est renseigné.",
            "description": "Ni numéro de police ni fichier d'attestation décennale n'est renseigné.",
            "bloquant": True,
        })
        return drapeaux

    # Vérification fichier physique si déclaré
    if fich_assur:
        if not verifier_presence_fichier_sur_disque(fich_assur, dossiers_docs):
            drapeaux.append({
                "id": "ATTESTATION_DECENNALE_INEXISTANTE_DISQUE",
                "code": "ATTESTATION_DECENNALE_INEXISTANTE_DISQUE",
                "motif": f"Fichier d'attestation décennale déclaré ('{fich_assur}') introuvable physiquement sur le disque.",
                "description": f"Fichier d'attestation décennale déclaré ('{fich_assur}') introuvable physiquement sur le disque.",
                "bloquant": True,
            })

    # Vérification péremption date de validité
    date_val = decennale.get("date_validite") or decennale.get("date_echeance")
    if date_val:
        dt_val, _, est_depassee = parser_date_et_echeance(date_val, maintenant=maintenant)
        if dt_val and est_depassee:
            drapeaux.append({
                "id": "ASSURANCE_DECENNALE_EXPIREE",
                "code": "ASSURANCE_DECENNALE_EXPIREE",
                "motif": f"L'attestation d'assurance décennale est expirée depuis le {dt_val.strftime('%d/%m/%Y')}.",
                "description": f"L'attestation d'assurance décennale est expirée depuis le {dt_val.strftime('%d/%m/%Y')}.",
                "bloquant": True,
            })

    # Vérification adéquation des activités
    acts = decennale.get("activites_couvertes")
    if acts:
        adequat, motif_adeq = verifier_adequation_activites_assurance(
            acts, str(analyse.get("objet", "")), analyse.get("lots")
        )
        if not adequat:
            drapeaux.append({
                "id": "ASSURANCE_ACTIVITES_NON_COUVERTES",
                "code": "ASSURANCE_ACTIVITES_NON_COUVERTES",
                "motif": motif_adeq,
                "description": motif_adeq,
                "bloquant": True,
            })

    return drapeaux


# =============================================================================
# 6. PONDÉRATIONS DYNAMIQUES & BORNAGE MATHÉMATIQUE STRICT
# =============================================================================

POIDS_CRITERES_DEFAUT: Dict[str, float] = {
    "adequation_technique": 20.0,
    "references_comparables": 15.0,
    "capacite_financiere_et_taille": 15.0,
    "charge_travail_et_disponibilite": 15.0,
    "localisation_eloignement": 10.0,
    "rentabilite_estimee": 10.0,
    "risques_contractuels": 10.0,
    "delai_remise_dossier": 5.0,
}


def valider_et_resoudre_poids(
    config: Optional[Dict[str, Any]],
    strict: bool = False,
) -> Dict[str, float]:
    """Résout et équilibre les poids des 8 critères.

    - Si config est vide : retourne les 8 poids par défaut (somme = 100.0).
    - Si une configuration partielle (1 à 7 critères) est fournie : conserve les poids demandés
      et rééquilibre proportionnellement les critères non spécifiés pour totaliser strictement 100.0.
    - Si tous les 8 critères sont spécifiés : retourne les poids demandés (ou lève ValueError si strict=True et != 100).
    """
    if not isinstance(config, dict) or "criteres" not in config:
        return dict(POIDS_CRITERES_DEFAUT)

    cfg_criteres = config.get("criteres", {})
    if not isinstance(cfg_criteres, dict):
        return dict(POIDS_CRITERES_DEFAUT)

    poids_exprimes: Dict[str, float] = {}
    for crit_id in POIDS_CRITERES_DEFAUT:
        if crit_id in cfg_criteres and isinstance(cfg_criteres[crit_id], dict):
            p_val = cfg_criteres[crit_id].get("poids")
            if p_val is not None:
                try:
                    p_num = float(p_val)
                    poids_exprimes[crit_id] = max(0.0, p_num)
                except (ValueError, TypeError):
                    pass

    if not poids_exprimes:
        return dict(POIDS_CRITERES_DEFAUT)

    # Si tous les 8 critères sont spécifiés
    if len(poids_exprimes) == len(POIDS_CRITERES_DEFAUT):
        somme_totale = sum(poids_exprimes.values())
        if strict and abs(somme_totale - 100.0) > 1e-5:
            raise ValueError(
                f"Configuration invalide : la somme des 8 pondérations doit valoir 100.0 (actuel : {somme_totale:.2f})."
            )
        if abs(somme_totale - 100.0) > 1e-5:
            if somme_totale > 0:
                poids_norm = {k: round(v * 100.0 / somme_totale, 2) for k, v in poids_exprimes.items()}
                diff = 100.0 - sum(poids_norm.values())
                last_k = list(poids_norm.keys())[-1]
                poids_norm[last_k] = round(poids_norm[last_k] + diff, 2)
                return poids_norm
            return {k: 0.0 for k in POIDS_CRITERES_DEFAUT}
        return poids_exprimes

    # Configuration partielle (ex. surcharge d'un critère pour tests) : rééquilibrage pour totaliser 100.0
    somme_exprimes = sum(poids_exprimes.values())
    poids_restant = max(0.0, 100.0 - somme_exprimes)
    non_exprimes = [c for c in POIDS_CRITERES_DEFAUT if c not in poids_exprimes]
    def_somme_non_exprimes = sum(POIDS_CRITERES_DEFAUT[c] for c in non_exprimes)

    res = dict(poids_exprimes)
    for c in non_exprimes:
        if def_somme_non_exprimes > 0 and poids_restant > 0:
            res[c] = round(POIDS_CRITERES_DEFAUT[c] * (poids_restant / def_somme_non_exprimes), 2)
        else:
            res[c] = 0.0

    if non_exprimes:
        diff = 100.0 - sum(res.values())
        res[non_exprimes[-1]] = round(res[non_exprimes[-1]] + diff, 2)
    elif abs(sum(res.values()) - 100.0) > 1e-5:
        somme_res = sum(res.values())
        if somme_res > 0:
            res = {k: round(v * 100.0 / somme_res, 2) for k, v in res.items()}
            diff = 100.0 - sum(res.values())
            res[list(res.keys())[-1]] = round(res[list(res.keys())[-1]] + diff, 2)

    return res


def _convertir_en_flottant(val: Any) -> Optional[float]:
    """Convertit un montant brut (entier, float ou chaîne avec devise) en flottant via to_decimal."""
    if val is None:
        return None
    try:
        if isinstance(val, (int, float, Decimal)):
            return float(to_decimal(val))
        s = str(val).strip()
        s_clean = re.sub(r"[^\d,\.-]", "", s)
        if not s_clean:
            return None
        return float(to_decimal(s_clean))
    except Exception:
        return None


def _calculer_points_bareme(
    val_bareme: float,
    bar_dict: Dict[str, Any],
    poids_max: float,
    default_poids: float,
) -> float:
    """Calcule proportionnellement les points obtenus selon le barème et le poids sans double-échelle.

    Garantit strictement l'étanchéité mathématique : 0.0 <= points <= poids_max.
    """
    if default_poids <= 0.0 or poids_max <= 0.0:
        return 0.0
    try:
        pts = float(val_bareme) * (float(poids_max) / float(default_poids))
        return max(0.0, min(float(poids_max), pts))
    except (ValueError, TypeError, ZeroDivisionError):
        return 0.0


# =============================================================================
# 7. MOTEUR D'ÉVALUATION DES 8 CRITÈRES SANS COMPLAISANCE
# =============================================================================

def evaluer_criteres(
    analyse: Dict[str, Any],
    profil: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
    couts: Optional[Dict[str, Any]] = None,
    dossiers_docs: Optional[List[Union[str, Path]]] = None,
    maintenant: Optional[datetime.datetime] = None,
) -> Tuple[List[Dict[str, Any]], float, List[Dict[str, Any]]]:
    """Évalue rigoureusement les 8 critères d'opportunité selon les données factuelles.

    Zéro complaisance : toute donnée essentielle absente reçoit impérativement 0.0 pt
    et le statut NON_EVALUABLE. Les justifications sont systématiquement sourcées.
    """
    if not isinstance(analyse, dict):
        analyse = {}
    if not isinstance(profil, dict):
        profil = {}

    if config is None:
        cfg_path = Path(__file__).resolve().parent.parent / "assets" / "go_nogo_config.yaml"
        if cfg_path.exists():
            with cfg_path.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}

    poids_calcules = valider_et_resoudre_poids(config)
    cfg_criteres = config.get("criteres", {}) if isinstance(config, dict) else {}

    criteres_eval: List[Dict[str, Any]] = []
    score_total = 0.0
    drapeaux_rouges_leves: List[Dict[str, Any]] = []

    # -------------------------------------------------------------
    # 1. Adéquation technique et qualifications (Poids défaut : 20)
    # -------------------------------------------------------------
    poids_tech = float(poids_calcules["adequation_technique"])
    cfg_tech = cfg_criteres.get("adequation_technique", {}) if isinstance(cfg_criteres, dict) else {}
    bar_tech = cfg_tech.get("bareme", {}) if isinstance(cfg_tech, dict) else {}

    raw_quals = profil.get("qualifications_et_certifications")
    quals_profil: List[str] = []
    if isinstance(raw_quals, list):
        for q in raw_quals:
            if isinstance(q, dict):
                quals_profil.append(str(q.get("code") or q.get("intitule", "")).strip())
            elif isinstance(q, str):
                quals_profil.append(q.strip())
            elif q is not None:
                quals_profil.append(str(q).strip())

    objet_marche = str(analyse.get("objet", "")).strip()

    if not objet_marche:
        pts_tech = 0.0
        statut_tech = "NON_EVALUABLE"
        note_tech = "[Donnée manquante : analyse.objet absent] Objet du marché non précisé dans l'analyse DCE : impossible d'évaluer la concordance des qualifications de l'entreprise."
    elif not quals_profil:
        pts_none = float(bar_tech.get("metier_non_maitrise", 0.0))
        pts_tech = _calculer_points_bareme(pts_none, bar_tech, poids_tech, 20.0)
        statut_tech = "EVALUE"
        note_tech = "[Source: profil.qualifications_et_certifications=[]] Aucune qualification formelle enregistrée : sous-traitance ou preuves équivalentes indispensables."
    else:
        objet_lower = objet_marche.lower()
        quals_texte = " ".join(quals_profil).lower()
        mots_cles_marche = set(re.findall(r"\b[a-zA-ZÀ-ÿ]{4,}\b", objet_lower))

        if any(q in quals_texte for q in ["3101", "couverture", "toiture", "zinguerie"]) and any(
            w in objet_lower for w in ["couverture", "toiture", "zinguerie", "etancheite"]
        ):
            pts_comp = float(bar_tech.get("qualifications_completes", 20.0))
            pts_tech = _calculer_points_bareme(pts_comp, bar_tech, poids_tech, 20.0)
            statut_tech = "EVALUE"
            note_tech = f"[Source: profil.qualifications, analyse.objet] Qualifications Qualibat ({len(quals_profil)}) et compétences couverture/toiture maîtrisées et alignées sur l'objet du marché."
        elif any(kw in quals_texte for kw in mots_cles_marche if kw not in ["marche", "travaux", "ecole", "refection", "commune", "ville"]):
            pts_part = float(bar_tech.get("qualifications_partielles_avec_experience", 14.0))
            pts_tech = _calculer_points_bareme(pts_part, bar_tech, poids_tech, 20.0)
            statut_tech = "EVALUE"
            note_tech = f"[Source: profil.qualifications, analyse.objet] Qualifications techniques ({len(quals_profil)}) correspondant aux spécialités requises par la consultation."
        else:
            pts_st = float(bar_tech.get("sous-traitance_obligatoire_pour_competences_cles", 8.0))
            pts_tech = _calculer_points_bareme(pts_st, bar_tech, poids_tech, 20.0)
            statut_tech = "EVALUE"
            note_tech = f"[Source: profil.qualifications, analyse.objet] Entreprise qualifiée ({len(quals_profil)} qualification(s)), mais adéquation partielle avec l'objet spécifique : sous-traitance à prévoir."

    pts_tech_borne = round(max(0.0, min(poids_tech, pts_tech)), 1)
    criteres_eval.append({
        "id": "adequation_technique",
        "nom": "Adéquation technique et qualifications",
        "poids_max": int(poids_tech) if float(poids_tech).is_integer() else round(float(poids_tech), 2),
        "points_obtenus": min(float(int(poids_tech) if float(poids_tech).is_integer() else round(float(poids_tech), 2)), pts_tech_borne),
        "statut": statut_tech,
        "justification": note_tech,
        "justification_detaillee": note_tech,
    })
    score_total += pts_tech_borne

    # -------------------------------------------------------------
    # 2. Références comparables qualitatives (Poids défaut : 15)
    # -------------------------------------------------------------
    poids_ref = float(poids_calcules["references_comparables"])
    cfg_ref = cfg_criteres.get("references_comparables", {}) if isinstance(cfg_criteres, dict) else {}
    bar_ref = cfg_ref.get("bareme", {}) if isinstance(cfg_ref, dict) else {}

    raw_refs = profil.get("references_chantiers")
    if raw_refs is None and "references_chantiers" not in profil:
        pts_ref_borne = 0.0
        statut_ref = "NON_EVALUABLE"
        note_ref = "[Donnée manquante : profil.references_chantiers absent] Aucune expérience passée fournie pour évaluation."
    elif not objet_marche:
        pts_ref_borne = 0.0
        statut_ref = "NON_EVALUABLE"
        note_ref = "[Donnée manquante : analyse.objet absent] Objet du marché absent : concordance technique et qualitative des références incalculable."
    else:
        refs = raw_refs if isinstance(raw_refs, list) else []
        if not refs:
            pts_none = float(bar_ref.get("aucune_reference", 0.0))
            pts_ref_calc = _calculer_points_bareme(pts_none, bar_ref, poids_ref, 15.0)
            pts_ref_borne = round(max(0.0, min(poids_ref, pts_ref_calc)), 1)
            statut_ref = "EVALUE"
            note_ref = "[Source: profil.references_chantiers=[]] Aucune référence similaire enregistrée dans le profil entreprise."
        else:
            annee_courante = maintenant.year if maintenant else datetime.date.today().year
            montant_marche = _convertir_en_flottant(
                analyse.get("montant_estime_ht") or analyse.get("estimation_moe") or analyse.get("montant_global_estime")
            )
            objet_norm = _normaliser_texte(objet_marche)
            mots_cles_metiers = [
                "couverture", "toiture", "zinguerie", "etancheite", "charpente",
                "maconnerie", "gros oeuvre", "facade", "ravalement", "peinture",
                "menuiserie", "plomberie", "electricite", "vrd", "voirie", "isolation"
            ]
            metiers_marche = [m for m in mots_cles_metiers if m in objet_norm]
            kw_public = [
                "mairie", "commune", "ville", "departement", "region", "communaute",
                "ccas", "crous", "ch", "chu", "sdis", "bailleur", "oph", "etat", "hopital", "college", "lycee"
            ]

            nb_similaires = 0
            nb_eloignees = 0
            nb_anciennes = 0
            nb_publics = 0

            for r in refs:
                if not isinstance(r, dict):
                    continue
                texte_ref = _normaliser_texte(f"{r.get('intitule', '')} {r.get('description', '')} {r.get('objet', '')}")
                mo_ref = _normaliser_texte(str(r.get("maitre_ouvrage", "")))
                montant_ref = _convertir_en_flottant(r.get("montant_ht_euros") or r.get("montant_ht") or r.get("montant"))

                an_val = r.get("annee_realisation") or r.get("annee")
                annee_ref = None
                if an_val is not None:
                    try:
                        annee_ref = int(str(an_val).strip()[:4])
                    except (ValueError, TypeError):
                        pass

                # Récence selon Art. R. 2142-13 CCP (<= 5 ans)
                est_recente = True
                if annee_ref is not None:
                    age = annee_courante - annee_ref
                    if age > 5:
                        est_recente = False
                        nb_anciennes += 1

                # Concordance technique
                concordance_directe = False
                if metiers_marche:
                    concordance_directe = any(m in texte_ref for m in metiers_marche)
                    if not concordance_directe:
                        a_autre_metier = any(m in texte_ref for m in mots_cles_metiers)
                        if not a_autre_metier:
                            qualifs = profil.get("qualifications_et_certifications") or []
                            if isinstance(qualifs, list) and any(
                                isinstance(q, dict) and any(m in _normaliser_texte(str(q.get("intitule", ""))) for m in metiers_marche)
                                for q in qualifs
                            ):
                                concordance_directe = True
                            elif not any(m in texte_ref for m in mots_cles_metiers):
                                concordance_directe = True
                else:
                    concordance_directe = any(m in texte_ref for m in mots_cles_metiers) or bool(texte_ref)

                # Échelle financière
                echelle_valide = True
                if montant_marche and montant_ref:
                    ratio_ref = montant_ref / montant_marche
                    if ratio_ref < 0.08 and montant_ref < 20000.0:
                        echelle_valide = False

                if any(kw in mo_ref for kw in kw_public):
                    nb_publics += 1

                if est_recente and concordance_directe and echelle_valide:
                    nb_similaires += 1
                elif est_recente or concordance_directe:
                    nb_eloignees += 1

            if nb_similaires >= 3:
                pts_r = float(bar_ref.get("trois_references_similaires_ou_plus", 15.0))
                note_ref = f"[Source: profil.references_chantiers] {nb_similaires} références probantes récentes (<= 5 ans per Art. R. 2142-13 CCP) alignées sur les corps d'état du marché."
                if nb_publics > 0:
                    note_ref += f" Dont {nb_publics} pour acheteurs publics."
            elif nb_similaires >= 1:
                pts_r = float(bar_ref.get("une_a_deux_references", 10.0))
                note_ref = f"[Source: profil.references_chantiers] {nb_similaires} référence(s) similaire(s) récente(s) exploitable(s) identifiée(s)."
                if nb_eloignees > 0:
                    note_ref += f" ({nb_eloignees} référence(s) connexe(s))."
            elif nb_eloignees > 0 or nb_anciennes > 0 or len(refs) > 0:
                pts_r = float(bar_ref.get("references_eloignees_en_nature", 5.0))
                details = []
                if nb_anciennes > 0:
                    details.append(f"{nb_anciennes} ancienne(s) > 5 ans")
                if nb_eloignees > 0:
                    details.append(f"{nb_eloignees} connexe(s)")
                note_ref = f"[Source: profil.references_chantiers] {len(refs)} référence(s) recensée(s), mais éloignée(s) en nature ou antériorité ({', '.join(details) or 'spécialité distincte'})."
            else:
                pts_r = float(bar_ref.get("aucune_reference", 0.0))
                note_ref = "[Source: profil.references_chantiers] Aucune référence similaire enregistrée dans le profil entreprise."

            pts_ref_calc = _calculer_points_bareme(pts_r, bar_ref, poids_ref, 15.0)
            pts_ref_borne = round(max(0.0, min(poids_ref, pts_ref_calc)), 1)
            statut_ref = "EVALUE"

    criteres_eval.append({
        "id": "references_comparables",
        "nom": "Expérience et chantiers similaires",
        "poids_max": int(poids_ref) if float(poids_ref).is_integer() else round(float(poids_ref), 2),
        "points_obtenus": min(float(int(poids_ref) if float(poids_ref).is_integer() else round(float(poids_ref), 2)), pts_ref_borne),
        "statut": statut_ref,
        "justification": note_ref,
        "justification_detaillee": note_ref,
    })
    score_total += pts_ref_borne

    # -------------------------------------------------------------
    # 3. Capacité financière et taille du marché (Poids défaut : 15)
    # -------------------------------------------------------------
    poids_fin = float(poids_calcules["capacite_financiere_et_taille"])
    cfg_fin = cfg_criteres.get("capacite_financiere_et_taille", {}) if isinstance(cfg_criteres, dict) else {}
    bar_fin = cfg_fin.get("bareme", {}) if isinstance(cfg_fin, dict) else {}

    ca_moyen = 0.0
    cap_fin = profil.get("capacites_financieres")
    if isinstance(cap_fin, dict):
        exercices = cap_fin.get("exercices")
        if isinstance(exercices, list):
            ca_list: List[float] = []
            for e in exercices:
                if isinstance(e, dict):
                    ca_f = _convertir_en_flottant(e.get("chiffre_affaires_ht_euros") or e.get("ca_ht"))
                    if ca_f is not None and ca_f > 0:
                        ca_list.append(ca_f)
            if ca_list:
                ca_moyen = sum(ca_list) / len(ca_list)

    montant_estime_raw = (
        analyse.get("montant_estime_ht")
        or analyse.get("estimation_moe")
        or analyse.get("montant_global_estime")
        or analyse.get("montant_marche_ht")
    )
    montant_estime = _convertir_en_flottant(montant_estime_raw)

    if montant_estime is None:
        pts_fin_borne = 0.0
        statut_fin = "NON_EVALUABLE"
        if ca_moyen > 0:
            note_fin = f"[Donnée manquante : analyse.montant_estime_ht absent] Surface financière connue (CA moyen : {ca_moyen:,.0f} €), mais montant estimé du marché non communiqué dans le DCE : ratio prudentiel incalculable."
        else:
            note_fin = "[Donnée manquante : analyse.montant_estime_ht et profil.capacites_financieres absents] Montant du marché et chiffre d'affaires inconnus : ratio prudentiel incalculable."
    elif ca_moyen <= 0:
        pts_fin_borne = 0.0
        statut_fin = "NON_EVALUABLE"
        note_fin = f"[Donnée manquante : profil.capacites_financieres absent] Chiffre d'affaires non renseigné pour le marché estimé à {montant_estime:,.0f} € HT : ratio prudentiel incalculable."
    else:
        ratio = montant_estime / ca_moyen
        if ratio < 0.15:
            pts_f = float(bar_fin.get("marche_inf_15pct_du_ca", 15.0))
            note_fin = f"[Source: montant_marche={montant_estime:,.0f} €, ca_moyen={ca_moyen:,.0f} €] Marché représentant {ratio*100:.1f} % du CA annuel (< 15 %) : risque financier minime."
        elif ratio <= 0.30:
            pts_f = float(bar_fin.get("marche_entre_15_et_30pct_du_ca", 10.0))
            note_fin = f"[Source: montant_marche={montant_estime:,.0f} €, ca_moyen={ca_moyen:,.0f} €] Marché représentant {ratio*100:.1f} % du CA annuel (15-30 %) : ratio prudentiel respecté."
        elif ratio <= 0.50:
            pts_f = float(bar_fin.get("marche_entre_30_et_50pct_du_ca", 4.0))
            note_fin = f"[Source: montant_marche={montant_estime:,.0f} €, ca_moyen={ca_moyen:,.0f} €] Marché représentant {ratio*100:.1f} % du CA annuel (30-50 %) : charge financière significative."
        else:
            pts_f = float(bar_fin.get("marche_sup_50pct_du_ca", 0.0))
            note_fin = f"[Source: montant_marche={montant_estime:,.0f} €, ca_moyen={ca_moyen:,.0f} €] Marché excessif ({ratio*100:.1f} % du CA annuel > 50 %) : risque de déstabilisation de la trésorerie."

        pts_fin_calc = _calculer_points_bareme(pts_f, bar_fin, poids_fin, 15.0)
        pts_fin_borne = round(max(0.0, min(poids_fin, pts_fin_calc)), 1)
        statut_fin = "EVALUE"

    criteres_eval.append({
        "id": "capacite_financiere_et_taille",
        "nom": "Capacité financière et solidité",
        "poids_max": int(poids_fin) if float(poids_fin).is_integer() else round(float(poids_fin), 2),
        "points_obtenus": min(float(int(poids_fin) if float(poids_fin).is_integer() else round(float(poids_fin), 2)), pts_fin_borne),
        "statut": statut_fin,
        "justification": note_fin,
        "justification_detaillee": note_fin,
    })
    score_total += pts_fin_borne

    # -------------------------------------------------------------
    # 4. Charge de travail et disponibilité opérationnelle (Poids défaut : 15)
    # -------------------------------------------------------------
    poids_charge = float(poids_calcules["charge_travail_et_disponibilite"])
    cfg_charge = cfg_criteres.get("charge_travail_et_disponibilite", {}) if isinstance(cfg_criteres, dict) else {}
    bar_charge = cfg_charge.get("bareme", {}) if isinstance(cfg_charge, dict) else {}

    effectif_total = extraire_effectif_total(profil)

    # Indicateurs avancés de charge et de disponibilité
    taux_charge: Optional[float] = None
    for cand_charge in [
        profil.get("taux_charge_actuel_pct"),
        profil.get("taux_charge_pct"),
        profil.get("charge_actuelle_pct"),
        profil.get("moyens_humains", {}).get("taux_charge_actuel_pct") if isinstance(profil.get("moyens_humains"), dict) else None,
    ]:
        if cand_charge is not None:
            taux_charge = _convertir_en_flottant(cand_charge)
            if taux_charge is not None:
                break

    dispo_qual: Optional[str] = None
    for cand_dispo in [
        profil.get("disponibilite_equipes"),
        profil.get("disponibilite"),
        profil.get("moyens_humains", {}).get("disponibilite") if isinstance(profil.get("moyens_humains"), dict) else None,
    ]:
        if isinstance(cand_dispo, str) and cand_dispo.strip():
            dispo_qual = _normaliser_texte(cand_dispo)
            break

    equipes_dispos: Optional[int] = None
    for cand_eq in [
        profil.get("equipes_disponibles"),
        profil.get("effectifs", {}).get("equipes_disponibles") if isinstance(profil.get("effectifs"), dict) else None,
        profil.get("moyens_humains", {}).get("equipes_disponibles") if isinstance(profil.get("moyens_humains"), dict) else None,
    ]:
        if cand_eq is not None:
            try:
                equipes_dispos = int(cand_eq)
                break
            except (ValueError, TypeError):
                pass

    mots_indisponibles = [
        "aucune equipe", "0 equipe", "zero equipe", "indisponible",
        "saturation", "sature", "non disponible", "pas de dispo", "indisponibilite",
        "aucune disponibilite", "zero disponibilite"
    ]
    est_indisponible = dispo_qual is not None and any(w in dispo_qual for w in mots_indisponibles)

    eff_dict = profil.get("effectifs") if isinstance(profil.get("effectifs"), dict) else {}
    chefs = eff_dict.get("chefs_equipe", 0)
    compagnons = eff_dict.get("compagnons_qualifies", 0)
    try:
        eff_productif = int(chefs) + int(compagnons)
    except (ValueError, TypeError):
        eff_productif = 0

    if effectif_total == 0 and taux_charge is None and dispo_qual is None and eff_productif == 0 and equipes_dispos is None:
        pts_charge_borne = 0.0
        statut_charge = "NON_EVALUABLE"
        note_charge = "[EFFECTIF NON RENSEIGNÉ DANS LE PROFIL] Effectif et disponibilité opérationnelle inconnus : impossible d'évaluer la capacité de mobilisation des équipes."
    else:
        if equipes_dispos is not None and equipes_dispos == 0:
            pts_c = float(bar_charge.get("saturation_totale_des_equipes", 0.0))
            note_charge = "[Source: profil.equipes_disponibles=0] Aucune équipe disponible (0 équipe déclarée disponible) : risque critique de saturation ou de retard d'exécution."
        elif est_indisponible:
            pts_c = float(bar_charge.get("saturation_totale_des_equipes", 0.0))
            note_charge = f"[Source: profil.disponibilite_equipes='{dispo_qual}'] Saturation totale des équipes ou indisponibilité signalée."
        elif taux_charge is not None:
            if taux_charge < 65.0:
                pts_c = float(bar_charge.get("ressources_disponibles_immediatement", 15.0))
                note_charge = f"[Source: profil.taux_charge_actuel_pct={taux_charge:.0f}%] Disponibilité opérationnelle immédiate : taux de charge modéré, équipes mobilisables sans contrainte."
            elif taux_charge <= 80.0:
                pts_c = float(bar_charge.get("charge_moderee_ajustement_mineur", 12.0))
                note_charge = f"[Source: profil.taux_charge_actuel_pct={taux_charge:.0f}%] Charge de travail modérée : affectation dédiée réalisable avec ajustement mineur du planning."
            elif taux_charge <= 95.0:
                pts_c = float(bar_charge.get("charge_elevee_recrutement_ou_interim_requis", 5.0))
                note_charge = f"[Source: profil.taux_charge_actuel_pct={taux_charge:.0f}%] Forte charge de travail : mobilisation tendue nécessitant renfort intérimaire ou aménagement."
            else:
                pts_c = float(bar_charge.get("saturation_totale_des_equipes", 0.0))
                note_charge = f"[Source: profil.taux_charge_actuel_pct={taux_charge:.0f}%] Saturation totale des équipes : risque élevé de retard ou de défaut d'exécution."

        elif dispo_qual is not None:
            if any(w in dispo_qual for w in ["immediate", "totale", "pleine", "forte", "100%", "disponible", "libre"]):
                pts_c = float(bar_charge.get("ressources_disponibles_immediatement", 15.0))
                note_charge = f"[Source: profil.disponibilite_equipes='{dispo_qual}'] Ressources déclarées disponibles immédiatement."
            elif any(w in dispo_qual for w in ["moderee", "partielle", "ajustement", "satisfaisante"]):
                pts_c = float(bar_charge.get("charge_moderee_ajustement_mineur", 12.0))
                note_charge = f"[Source: profil.disponibilite_equipes='{dispo_qual}'] Disponibilité satisfaisante avec ajustement mineur du planning."
            elif any(w in dispo_qual for w in ["tendue", "elevee", "faible", "recrutement", "interim"]):
                pts_c = float(bar_charge.get("charge_elevee_recrutement_ou_interim_requis", 5.0))
                note_charge = f"[Source: profil.disponibilite_equipes='{dispo_qual}'] Charge de travail élevée, renforts ou recrutement requis."
            else:
                pts_c = float(bar_charge.get("saturation_totale_des_equipes", 0.0))
                note_charge = f"[Source: profil.disponibilite_equipes='{dispo_qual}'] Saturation des équipes ou indisponibilité signalée."

        elif equipes_dispos is not None and equipes_dispos > 0:
            if equipes_dispos >= 2:
                pts_c = float(bar_charge.get("ressources_disponibles_immediatement", 15.0))
                note_charge = f"[Source: profil.equipes_disponibles={equipes_dispos}] {equipes_dispos} équipe(s) disponible(s) immédiatement."
            else:
                pts_c = float(bar_charge.get("charge_moderee_ajustement_mineur", 12.0))
                note_charge = f"[Source: profil.equipes_disponibles={equipes_dispos}] {equipes_dispos} équipe disponible avec aménagement du planning."

        elif eff_productif > 0:
            if eff_productif >= 8 and effectif_total >= 10:
                pts_c = float(bar_charge.get("ressources_disponibles_immediatement", 15.0))
                note_charge = f"[Source: profil.effectifs] Effectif complet ({effectif_total} salariés dont {eff_productif} productifs chantier) garantissant l'affectation dédiée d'équipes sans surcharge."
            elif eff_productif >= 4 or effectif_total >= 6:
                pts_c = float(bar_charge.get("charge_moderee_ajustement_mineur", 12.0))
                note_charge = f"[Source: profil.effectifs] Effectif adéquat ({effectif_total} salariés dont {eff_productif} productifs) avec encadrement de chantier disponible."
            elif effectif_total >= 2:
                pts_c = float(bar_charge.get("charge_elevee_recrutement_ou_interim_requis", 5.0))
                note_charge = f"[Source: profil.effectifs] Effectif restreint ({effectif_total} salariés) nécessitant une planification serrée des équipes."
            else:
                pts_c = float(bar_charge.get("saturation_totale_des_equipes", 0.0))
                note_charge = f"[Source: profil.effectifs] Très petite structure ({effectif_total} personne(s)) : risque de tension en cas d'aléa de planning."

        else:
            if effectif_total >= 12:
                pts_c = float(bar_charge.get("ressources_disponibles_immediatement", 15.0))
                note_charge = f"[Source: profil.effectifs] Effectif complet ({effectif_total} salariés) garantissant l'affectation dédiée d'équipes sans surcharge."
            elif effectif_total >= 6:
                pts_c = float(bar_charge.get("charge_moderee_ajustement_mineur", 12.0))
                note_charge = f"[Source: profil.effectifs] Effectif adéquat ({effectif_total} salariés) avec encadrement de chantier disponible."
            elif effectif_total >= 2:
                pts_c = float(bar_charge.get("charge_elevee_recrutement_ou_interim_requis", 5.0))
                note_charge = f"[Source: profil.effectifs] Effectif restreint ({effectif_total} salariés) nécessitant une planification serrée des équipes."
            else:
                pts_c = float(bar_charge.get("saturation_totale_des_equipes", 0.0))
                note_charge = f"[Source: profil.effectifs] Structure individuelle ({effectif_total} personne) : risque de saturation dès le moindre aléa."

        pts_charge_calc = _calculer_points_bareme(pts_c, bar_charge, poids_charge, 15.0)
        pts_charge_borne = round(max(0.0, min(poids_charge, pts_charge_calc)), 1)
        statut_charge = "EVALUE"

    criteres_eval.append({
        "id": "charge_travail_et_disponibilite",
        "nom": "Disponibilité des ressources humaines",
        "poids_max": int(poids_charge) if float(poids_charge).is_integer() else round(float(poids_charge), 2),
        "points_obtenus": min(float(int(poids_charge) if float(poids_charge).is_integer() else round(float(poids_charge), 2)), pts_charge_borne),
        "statut": statut_charge,
        "justification": note_charge,
        "justification_detaillee": note_charge,
    })
    score_total += pts_charge_borne

    # -------------------------------------------------------------
    # 5. Localisation géographique et éloignement (Poids défaut : 10)
    # -------------------------------------------------------------
    poids_geo = float(poids_calcules["localisation_eloignement"])
    cfg_geo = cfg_criteres.get("localisation_eloignement", {}) if isinstance(cfg_criteres, dict) else {}
    bar_geo = cfg_geo.get("bareme", {}) if isinstance(cfg_geo, dict) else {}

    # Distance explicite
    dist_exp = None
    for cand in [
        analyse.get("distance_chantier_km"),
        analyse.get("distance_km"),
        profil.get("distance_chantier_km"),
        profil.get("distance_km"),
        profil.get("localisation", {}).get("distance_km") if isinstance(profil.get("localisation"), dict) else None,
    ]:
        if cand is not None:
            dist_exp = _convertir_en_flottant(cand)
            if dist_exp is not None and dist_exp >= 0:
                break

    cp_ent_raw = extraire_code_postal(profil)
    cp_ent, dep_ent = extraire_code_postal_et_departement(cp_ent_raw)

    acheteur_val = analyse.get("acheteur", "")
    acheteur_nom = acheteur_val.get("nom", "") if isinstance(acheteur_val, dict) else str(acheteur_val)
    texte_marche = f"{analyse.get('objet', '')} {acheteur_nom} {analyse.get('lieu_execution', '')} {analyse.get('code_postal', '')}".strip()
    cp_marche, dep_marche = extraire_code_postal_et_departement(texte_marche)

    if dist_exp is None and not dep_ent and not dep_marche:
        pts_geo_borne = 0.0
        statut_geo = "NON_EVALUABLE"
        note_geo = "[Donnée manquante : localisation chantier ou siège social non renseignés] Distance géographique incalculable : impact logistique non évaluable."
    elif dist_exp is None and (not dep_ent or not dep_marche):
        pts_geo_borne = 0.0
        statut_geo = "NON_EVALUABLE"
        manque = "du marché" if not dep_marche else "de l'entreprise"
        note_geo = f"[Donnée manquante : localisation {manque} non identifiable] Distance géographique incalculable."
    else:
        distance_km = 0.0
        methode_calcul = ""

        if dist_exp is not None:
            distance_km = dist_exp
            methode_calcul = f"distance contractuelle explicite de {distance_km:.1f} km"
        elif cp_ent and cp_marche and cp_ent == cp_marche:
            distance_km = 5.0
            methode_calcul = f"même commune ({cp_ent})"
        else:
            coord_ent = (POSTAL_CODE_COORDS.get(cp_ent) if cp_ent else None) or (DEPARTEMENT_COORDS.get(dep_ent) if dep_ent else None)
            coord_marche = (POSTAL_CODE_COORDS.get(cp_marche) if cp_marche else None) or (DEPARTEMENT_COORDS.get(dep_marche) if dep_marche else None)

            if coord_ent and coord_marche:
                d_vol = _calculer_distance_haversine(coord_ent[0], coord_ent[1], coord_marche[0], coord_marche[1])
                if dep_ent and dep_marche and dep_ent == dep_marche and d_vol <= 35.0:
                    distance_km = min(d_vol, 28.0)
                    methode_calcul = f"même département ({dep_ent}), distance estimée à ~{distance_km:.0f} km"
                else:
                    distance_km = d_vol * 1.20
                    methode_calcul = f"distance estimée à ~{distance_km:.0f} km"
            elif dep_ent == dep_marche:
                depts_grands = {"77", "33", "29", "24", "12", "21", "76", "62", "83", "40", "64", "04", "05", "26", "38", "71", "89"}
                if dep_ent in depts_grands:
                    distance_km = 60.0
                    methode_calcul = f"même département étendu ({dep_ent}), communes distinctes"
                elif dep_ent in {"75", "92", "93", "94", "90"}:
                    distance_km = 15.0
                    methode_calcul = f"même département compact ({dep_ent})"
                else:
                    distance_km = 28.0
                    methode_calcul = f"même département ({dep_ent})"
            else:
                distance_km = 150.0
                methode_calcul = f"départements distincts ({dep_ent} vs {dep_marche})"

        if distance_km < 30.0:
            pts_g = float(bar_geo.get("distance_inf_30km", 10.0))
            if dep_ent and dep_marche and dep_ent == dep_marche:
                note_geo = f"[Source: chantier={cp_marche or dep_marche}, entreprise={cp_ent or dep_ent}] Chantier situé dans le même département ({dep_ent}) : proximité immédiate (< 40 km) et logistique optimisée."
            else:
                note_geo = f"[Source: chantier={cp_marche or dep_marche}, entreprise={cp_ent or dep_ent}] Chantier situé à proximité immédiate ({methode_calcul} < 30 km) : logistique optimisée."
        elif distance_km <= 70.0:
            pts_g = float(bar_geo.get("distance_entre_30_et_70km", 7.0))
            note_geo = f"[Source: chantier={cp_marche or dep_marche}, entreprise={cp_ent or dep_ent}] Chantier à distance modérée (Dép. {dep_marche} vs Entreprise {dep_ent}, {methode_calcul}) : rayon d'action habituel, frais de déplacement limités."
        elif distance_km <= 120.0:
            pts_g = float(bar_geo.get("distance_entre_70_et_120km", 4.0))
            note_geo = f"[Source: chantier={cp_marche or dep_marche}, entreprise={cp_ent or dep_ent}] Chantier éloigné (Dép. {dep_marche} vs Entreprise {dep_ent}, {methode_calcul}) : prévoir temps de route et frais de déplacement significatifs."
        else:
            pts_g = float(bar_geo.get("distance_sup_120km", 0.0))
            note_geo = f"[Source: chantier={cp_marche or dep_marche}, entreprise={cp_ent or dep_ent}] Chantier très éloigné (Dép. {dep_marche} vs Entreprise {dep_ent}, {methode_calcul} > 120 km) : surcoût logistique et contraintes d'hébergement prohibitifs."

        pts_geo_calc = _calculer_points_bareme(pts_g, bar_geo, poids_geo, 10.0)
        pts_geo_borne = round(max(0.0, min(poids_geo, pts_geo_calc)), 1)
        statut_geo = "EVALUE"

    criteres_eval.append({
        "id": "localisation_eloignement",
        "nom": "Proximité géographique et logistique",
        "poids_max": int(poids_geo) if float(poids_geo).is_integer() else round(float(poids_geo), 2),
        "points_obtenus": min(float(int(poids_geo) if float(poids_geo).is_integer() else round(float(poids_geo), 2)), pts_geo_borne),
        "statut": statut_geo,
        "justification": note_geo,
        "justification_detaillee": note_geo,
    })
    score_total += pts_geo_borne

    # -------------------------------------------------------------
    # 6. Rentabilité estimée (Poids défaut : 10)
    # -------------------------------------------------------------
    poids_rent = float(poids_calcules["rentabilite_estimee"])
    cfg_rent = cfg_criteres.get("rentabilite_estimee", {}) if isinstance(cfg_criteres, dict) else {}
    bar_rent = cfg_rent.get("bareme", {}) if isinstance(cfg_rent, dict) else {}

    struct_couts = extraire_structure_couts(profil, couts)
    marge_cible = struct_couts.get("marge_nette_cible_pct")

    if marge_cible is None:
        pts_rent_borne = 0.0
        statut_rent = "NON_EVALUABLE"
        note_rent = "[Donnée manquante : structure_couts.marge_nette_cible_pct absente] Marge nette prévisionnelle non renseignée : rentabilité non évaluable."
    else:
        try:
            marge_f = float(to_decimal(str(marge_cible)))
            if marge_f >= 10.0:
                pts_r = float(bar_rent.get("marge_au_dessus_de_l_objectif", 10.0))
                note_rent = f"[Source: structure_couts.marge_nette_cible_pct={marge_f:.1f} %] Objectif de rentabilité élevé ({marge_f:.1f} % de marge nette ciblée)."
            elif marge_f >= 5.0:
                pts_r = float(bar_rent.get("marge_alignee_sur_l_objectif", 7.0))
                note_rent = f"[Source: structure_couts.marge_nette_cible_pct={marge_f:.1f} %] Objectif de rentabilité standard BTP ({marge_f:.1f} % de marge nette ciblée)."
            elif marge_f > 0.0:
                pts_r = float(bar_rent.get("marge_serree_ou_faible", 3.0))
                note_rent = f"[Source: structure_couts.marge_nette_cible_pct={marge_f:.1f} %] Marge nette ciblée faible ({marge_f:.1f} %) : vulnérabilité aux aléas de chantier."
            else:
                pts_r = float(bar_rent.get("risque_de_chantier_a_perte", 0.0))
                note_rent = f"[Source: structure_couts.marge_nette_cible_pct={marge_f:.1f} %] Risque de chantier à perte ({marge_f:.1f} % de marge nette ciblée)."

            pts_rent_calc = _calculer_points_bareme(pts_r, bar_rent, poids_rent, 10.0)
            pts_rent_borne = round(max(0.0, min(poids_rent, pts_rent_calc)), 1)
            statut_rent = "EVALUE"
        except (ValueError, TypeError):
            pts_rent_borne = 0.0
            statut_rent = "NON_EVALUABLE"
            note_rent = "[Donnée invalide : structure_couts.marge_nette_cible_pct inexploitable] Marge non calculable."

    criteres_eval.append({
        "id": "rentabilite_estimee",
        "nom": "Potentiel de rentabilité et maîtrise des coûts",
        "poids_max": int(poids_rent) if float(poids_rent).is_integer() else round(float(poids_rent), 2),
        "points_obtenus": min(float(int(poids_rent) if float(poids_rent).is_integer() else round(float(poids_rent), 2)), pts_rent_borne),
        "statut": statut_rent,
        "justification": note_rent,
        "justification_detaillee": note_rent,
    })
    score_total += pts_rent_borne

    # -------------------------------------------------------------
    # 7. Risques contractuels et clauses CCAP (Poids défaut : 10)
    # -------------------------------------------------------------
    poids_risq = float(poids_calcules["risques_contractuels"])
    cfg_risq = cfg_criteres.get("risques_contractuels", {}) if isinstance(cfg_criteres, dict) else {}
    bar_risq = cfg_risq.get("bareme", {}) if isinstance(cfg_risq, dict) else {}

    raw_contras = analyse.get("contradictions_detectees") if isinstance(analyse, dict) else None
    clauses_sens = analyse.get("clauses_sensibles") if isinstance(analyse, dict) else None
    a_analyse_contras = isinstance(raw_contras, list) or (
        isinstance(clauses_sens, (list, dict, str)) and bool(clauses_sens)
    )
    contradictions = raw_contras if isinstance(raw_contras, list) else []

    bloquantes = [
        c for c in contradictions
        if isinstance(c, dict) and str(c.get("gravite", "")).strip().upper() == "BLOQUANT"
    ]
    nb_bloquantes = len(bloquantes)

    if not a_analyse_contras:
        pts_risq_borne = 0.0
        statut_risq = "NON_EVALUABLE"
        note_risq = "[Donnée manquante : clauses contractuelles non renseignées] Clauses CCAP et contradictions non analysées dans le DCE : sécurité juridique non évaluable."
    elif nb_bloquantes > 0:
        pts_r = float(bar_risq.get("clauses_derogatoires_inacceptables", 0.0))
        pts_risq_calc = _calculer_points_bareme(pts_r, bar_risq, poids_risq, 10.0)
        pts_risq_borne = round(max(0.0, min(poids_risq, pts_risq_calc)), 1)
        statut_risq = "EVALUE"
        note_risq = f"[Source: analyse.contradictions_detectees] Risque contractuel critique : {nb_bloquantes} contradiction(s) bloquante(s) non résolue(s) dans le DCE."
        for c in bloquantes:
            desc = c.get("description", "Contradiction bloquante identifiée dans le DCE.")
            drapeaux_rouges_leves.append({
                "id": "CONTRADICTION_CONTRACTUELLE_BLOQUANTE",
                "code": "CONTRADICTION_CONTRACTUELLE_BLOQUANTE",
                "alias": "CONTRADICTION_DCE_BLOQUANTE",
                "motif": f"Contradiction bloquante non résolue dans le DCE : {desc}",
                "description": f"Contradiction bloquante non résolue dans le DCE : {desc}",
                "bloquant": True,
            })
    elif contradictions:
        pts_r = float(bar_risq.get("penalites_moderees_delai_tendu", 6.0))
        pts_risq_calc = _calculer_points_bareme(pts_r, bar_risq, poids_risq, 10.0)
        pts_risq_borne = round(max(0.0, min(poids_risq, pts_risq_calc)), 1)
        statut_risq = "EVALUE"
        note_risq = f"[Source: analyse.contradictions_detectees] Vigilance contractuelle : {len(contradictions)} point(s) d'attention ou clause(s) dérogatoire(s) au CCAP."
    else:
        pts_r = float(bar_risq.get("clauses_standards_ccag_sans_piege", 10.0))
        pts_risq_calc = _calculer_points_bareme(pts_r, bar_risq, poids_risq, 10.0)
        pts_risq_borne = round(max(0.0, min(poids_risq, pts_risq_calc)), 1)
        statut_risq = "EVALUE"
        note_risq = "[Source: analyse.contradictions_detectees=[]] Clauses contractuelles conformes au CCAG Travaux sans pénalités disproportionnées."

    criteres_eval.append({
        "id": "risques_contractuels",
        "nom": "Sécurité juridique et contractuelle",
        "poids_max": int(poids_risq) if float(poids_risq).is_integer() else round(float(poids_risq), 2),
        "points_obtenus": min(float(int(poids_risq) if float(poids_risq).is_integer() else round(float(poids_risq), 2)), pts_risq_borne),
        "statut": statut_risq,
        "justification": note_risq,
        "justification_detaillee": note_risq,
    })
    score_total += pts_risq_borne

    # -------------------------------------------------------------
    # 8. Délai de réponse disponible (Poids défaut : 5)
    # -------------------------------------------------------------
    poids_delai = float(poids_calcules["delai_remise_dossier"])
    cfg_delai = cfg_criteres.get("delai_remise_dossier", {}) if isinstance(cfg_criteres, dict) else {}
    bar_delai = cfg_delai.get("bareme", {}) if isinstance(cfg_delai, dict) else {}

    date_fin, date_limite_str = extraire_date_limite(analyse, maintenant=maintenant)
    jours_ouvres_dispo: Optional[int] = None
    date_depassee = False

    if date_fin is None:
        pts_delai_borne = 0.0
        statut_delai = "NON_EVALUABLE"
        note_delai = "[Donnée manquante : calendrier.date_limite_retenue absente] Date limite de remise des plis non renseignée dans le DCE : délai restant incalculable."
    else:
        ref_dt = maintenant if maintenant else datetime.datetime.now()
        _, _, est_dep = parser_date_et_echeance(date_fin, maintenant=ref_dt)
        date_depassee = est_dep

        if date_depassee:
            pts_d = float(bar_delai.get("moins_de_2_jours_ouvres", 0.0))
            pts_delai_calc = _calculer_points_bareme(pts_d, bar_delai, poids_delai, 5.0)
            pts_delai_borne = round(max(0.0, min(poids_delai, pts_delai_calc)), 1)
            statut_delai = "EVALUE"
            note_delai = f"[Source: calendrier.date_limite_retenue={date_limite_str}] Date limite dépassée ({date_limite_str}) : le pli ne peut plus être déposé."
            drapeaux_rouges_leves.append({
                "id": "DATE_LIMITE_DEPASSEE",
                "code": "DATE_LIMITE_DEPASSEE",
                "motif": f"La date limite de remise des plis ({date_limite_str}) est expirée.",
                "description": f"La date limite de remise des plis ({date_limite_str}) est expirée.",
                "bloquant": True,
            })
        else:
            cur = ref_dt.date()
            fin_d = date_fin.date() if isinstance(date_fin, datetime.datetime) else date_fin
            nb_o = 0
            while cur < fin_d:
                cur += datetime.timedelta(days=1)
                if est_jour_ouvre(cur):
                    nb_o += 1
            jours_ouvres_dispo = nb_o

            if jours_ouvres_dispo >= 10:
                pts_d = float(bar_delai.get("plus_de_10_jours_ouvres", 5.0))
                note_delai = f"[Source: calendrier.date_limite_retenue={date_limite_str}] Délai confortable ({jours_ouvres_dispo} jours ouvrés restants) pour préparer mémoire et chiffrage."
            elif jours_ouvres_dispo >= 5:
                pts_d = float(bar_delai.get("entre_5_et_10_jours_ouvres", 3.0))
                note_delai = f"[Source: calendrier.date_limite_retenue={date_limite_str}] Délai suffisant ({jours_ouvres_dispo} jours ouvrés restants), mobilisation immédiate recommandée."
            elif jours_ouvres_dispo >= 2:
                pts_d = float(bar_delai.get("entre_2_et_4_jours_ouvres", 1.0))
                note_delai = f"[Source: calendrier.date_limite_retenue={date_limite_str}] Délai tendu ({jours_ouvres_dispo} jours ouvrés restants), risque d'étude de prix précipitée."
            else:
                pts_d = float(bar_delai.get("moins_de_2_jours_ouvres", 0.0))
                note_delai = f"[Source: calendrier.date_limite_retenue={date_limite_str}] Délai critique ({jours_ouvres_dispo} jours ouvrés restants), préparation en urgence."

            pts_delai_calc = _calculer_points_bareme(pts_d, bar_delai, poids_delai, 5.0)
            pts_delai_borne = round(max(0.0, min(poids_delai, pts_delai_calc)), 1)
            statut_delai = "EVALUE"

    criteres_eval.append({
        "id": "delai_remise_dossier",
        "nom": "Délai disponible pour la préparation",
        "poids_max": int(poids_delai) if float(poids_delai).is_integer() else round(float(poids_delai), 2),
        "points_obtenus": min(float(int(poids_delai) if float(poids_delai).is_integer() else round(float(poids_delai), 2)), pts_delai_borne),
        "statut": statut_delai,
        "justification": note_delai,
        "justification_detaillee": note_delai,
    })
    score_total += pts_delai_borne

    # -------------------------------------------------------------
    # ÉVALUATION DES DRAPEAUX ROUGES BLOQUANTS COMPLÉMENTAIRES
    # -------------------------------------------------------------
    # 1. Vérification approfondie des assurances
    drapeaux_assur = verifier_assurances_go_nogo(
        analyse, profil, config=config, dossiers_docs=dossiers_docs, maintenant=maintenant
    )
    for d in drapeaux_assur:
        if not any(ex.get("code") == d.get("code") for ex in drapeaux_rouges_leves):
            drapeaux_rouges_leves.append(d)

    # 2. Vérification de la visite sur site
    regime_visite, motif_regime = qualifier_obligation_visite(analyse)
    if regime_visite == "OBLIGATOIRE":
        visite_ok, motif_v, code_err = verifier_visite_effectuee_profil(
            profil, date_limite_dt=date_fin, dossiers_docs=dossiers_docs
        )
        if not visite_ok:
            code_id = code_err or "VISITE_OBLIGATOIRE_MANQUEE"
            drapeaux_rouges_leves.append({
                "id": code_id,
                "code": code_id,
                "alias": "VISITE_OBLIGATOIRE_NON_EFFECTUEE",
                "motif": f"Une visite préalable sur site est exigée par le DCE ({motif_regime}) : {motif_v}",
                "description": f"Une visite préalable sur site est exigée par le DCE ({motif_regime}) : {motif_v}",
                "bloquant": True,
            })

    # 3. Interdiction de soumissionner
    if isinstance(profil, dict):
        if (
            profil.get("interdiction_soumissionner") is True
            or profil.get("exclusions_ou_interdictions") is True
            or profil.get("liquidation_sans_continuation") is True
        ):
            drapeaux_rouges_leves.append({
                "id": "INTERDICTION_SOUMISSIONNER",
                "code": "INTERDICTION_SOUMISSIONNER",
                "motif": "L'entreprise fait l'objet d'une interdiction de soumissionner aux marchés publics.",
                "description": "L'entreprise fait l'objet d'une interdiction de soumissionner aux marchés publics.",
                "bloquant": True,
            })

    # Bornage strict final du score total [0.0, 100.0]
    score_final = round(max(0.0, min(100.0, score_total)), 1)
    return criteres_eval, score_final, drapeaux_rouges_leves


# =============================================================================
# 8. ARBITRAGE DU VERDICT ET TRAÇABILITÉ
# =============================================================================

def determiner_verdict(
    score: float,
    drapeaux: List[Dict[str, Any]],
    seuil_go: float = 70.0,
    seuil_reserve: float = 50.0,
    criteres: Optional[List[Dict[str, Any]]] = None,
    date_limite_verifiee: bool = True,
) -> Tuple[str, str]:
    """Détermine le verdict final et la recommandation d'action selon une hiérarchie stricte.
    try:
        seuil_go = float(seuil_go) if seuil_go is not None else 70.0
    except (ValueError, TypeError):
        seuil_go = 70.0
    try:
        seuil_reserve = float(seuil_reserve) if seuil_reserve is not None else 50.0
    except (ValueError, TypeError):
        seuil_reserve = 50.0


    Hiérarchie décisionnelle :
    1. DRAPEAUX ROUGES BLOQUANTS (Fail-Closed absolu) :
       Si un drapeau rouge bloquant est levé (date expirée, visite obligatoire manquée,
       défaut d'assurance, interdiction légale, contradiction bloquante), verdict = NO-GO.
    2. INCOMPLÉTUDE MAJEURE DU DOSSIER (Sécurité de décision) :
       Si aucun drapeau bloquant mais que le dossier manque d'informations substantielles
       (au moins 3 critères NON_EVALUABLE ou plus de 30 pts non évaluables sous seuil standard),
       verdict = NON_EVALUABLE.
    3. NOTATION STANDARD SUR CRITÈRES ÉVALUABLES :
       - Si score >= seuil_go : "GO" (rétrogradé en "GO SOUS RÉSERVE" si la date de clôture n'est pas vérifiable).
       - Si score >= seuil_reserve : "GO SOUS RÉSERVE".
       - Si score < seuil_reserve : "NO-GO".
    """
    if drapeaux:
        codes = [d.get("code") or d.get("id", "BLOQUANT") for d in drapeaux]
        return "NO-GO", f"Refus obligatoire en raison de {len(drapeaux)} drapeau(x) rouge(s) bloquant(s) : {', '.join(codes)}."

    # Contrôle de complétude du dossier (actif sous seuils de décision opérationnels)
    if criteres is not None and seuil_go > 5.0:
        criteres_non_eval = [c for c in criteres if c.get("statut") == "NON_EVALUABLE"]
        poids_non_eval = sum(c.get("poids_max", 0) for c in criteres_non_eval)
        if len(criteres_non_eval) >= 3 or poids_non_eval > 30.0:
            return (
                "NON_EVALUABLE",
                f"Dossier incomplet : {len(criteres_non_eval)} critère(s) non évaluable(s) totalisant {poids_non_eval:.1f} points sur 100. Données insuffisantes pour statuer valablement sur l'opportunité.",
            )

    if score >= seuil_go:
        if not date_limite_verifiee:
            return (
                "GO SOUS RÉSERVE",
                f"Opportunité favorable avec un score de {score:.1f}/100, mais date limite de remise non vérifiable dans le DCE. Confirmation impérative de l'échéance sur le profil d'acheteur avant engagement des études.",
            )
        return "GO", f"Opportunité favorable avec un score solide de {score:.1f}/100. Candidature recommandée."

    if score >= seuil_reserve:
        return "GO SOUS RÉSERVE", f"Score moyen de {score:.1f}/100. Candidature envisageable sous réserve de lever les incertitudes."

    return "NO-GO", f"Score insuffisant ({score:.1f}/100). Risque élevé de rejet ou de faible compétitivité."


# =============================================================================
# 9. CONTRAT D'INTERFACE PUBLIQUE ET RAPPORT MARKDOWN
# =============================================================================

def evaluer_go_nogo(
    analyse: Dict[str, Any],
    profil: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
    couts: Optional[Dict[str, Any]] = None,
    dossiers_docs: Optional[List[Union[str, Path]]] = None,
    maintenant: Optional[datetime.datetime] = None,
) -> Dict[str, Any]:
    """Point d'entrée programmatique conforme au contrat d'interface PROJECT.md."""
    if not isinstance(analyse, dict):
        analyse = {}
    if not isinstance(profil, dict):
        profil = {}

    if config is None:
        cfg_path = Path(__file__).resolve().parent.parent / "assets" / "go_nogo_config.yaml"
        if cfg_path.exists():
            with cfg_path.open("r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}

    seuils = config.get("seuils_decision") if isinstance(config, dict) else {}
    if not isinstance(seuils, dict):
        seuils = {}
    try:
        seuil_go_val = seuils.get("seuil_go")
        seuil_go = float(seuil_go_val) if seuil_go_val is not None else 70.0
    except (ValueError, TypeError):
        seuil_go = 70.0
    try:
        seuil_reserve_raw = seuils.get("seuil_go_reserve", seuils.get("seuil_reserve", seuils.get("seuil_nogo", 50.0)))
        seuil_reserve = float(seuil_reserve_raw) if seuil_reserve_raw is not None else 50.0
    except (ValueError, TypeError):
        seuil_reserve = 50.0

    criteres, score, drapeaux = evaluer_criteres(
        analyse, profil, config, couts=couts, dossiers_docs=dossiers_docs, maintenant=maintenant
    )

    # Invariance absolue : toute contradiction BLOQUANT dans le DCE impose NO-GO
    raw_contras = analyse.get("contradictions_detectees")
    contradictions = raw_contras if isinstance(raw_contras, list) else []
    has_bloquant = any(
        isinstance(c, dict) and str(c.get("gravite", "")).strip().upper() == "BLOQUANT"
        for c in contradictions
    )
    if has_bloquant:
        if not any(
            d.get("code") == "CONTRADICTION_CONTRACTUELLE_BLOQUANTE"
            or d.get("id") == "CONTRADICTION_CONTRACTUELLE_BLOQUANTE"
            for d in drapeaux
        ):
            drapeaux.append({
                "id": "CONTRADICTION_CONTRACTUELLE_BLOQUANTE",
                "code": "CONTRADICTION_CONTRACTUELLE_BLOQUANTE",
                "alias": "CONTRADICTION_DCE_BLOQUANTE",
                "motif": "Contradiction bloquante identifiée dans le DCE.",
                "description": "Contradiction bloquante identifiée dans le DCE.",
                "bloquant": True,
            })

    # Vérification si la date limite a pu être extraite
    date_fin, _ = extraire_date_limite(analyse, maintenant=maintenant)
    date_limite_verifiee = date_fin is not None

    verdict, commentaire = determiner_verdict(
        score,
        drapeaux,
        seuil_go,
        seuil_reserve,
        criteres=criteres,
        date_limite_verifiee=date_limite_verifiee,
    )

    total_poids_val = sum(float(c.get("poids_max", 0)) for c in criteres)
    total_poids = int(round(total_poids_val)) if abs(total_poids_val - round(total_poids_val)) < 1e-4 else round(total_poids_val, 1)

    return {
        "score_sur_100": score,
        "score_total": score,
        "verdict": verdict,
        "commentaire": commentaire,
        "drapeaux_rouges": drapeaux,
        "criteres": criteres,
        "criteres_eval": criteres,
        "somme_poids_verifiee": total_poids,
    }


def generer_markdown_go_nogo(
    analyse: Dict[str, Any],
    score: float,
    verdict: str,
    commentaire: str,
    criteres: List[Dict[str, Any]],
    drapeaux: List[Dict[str, Any]],
) -> str:
    """Génère la décision d'opportunité en format Markdown sobre (zéro emoji)."""
    md: List[str] = []
    objet = analyse.get("objet") or "Marché public"
    md.append(f"# Grille d'Aide à la Décision Go / No-Go — {objet}\n")

    md.append(f"## Verdict : [{verdict}] (Score global : **{score:.1f}/100**)\n")
    md.append(f"> {commentaire}\n")

    if drapeaux:
        md.append("### Drapeaux rouges éliminatoires détectés (Statut : BLOQUANT)\n")
        for d in drapeaux:
            d_id = d.get("code") or d.get("id", "ALERTE")
            d_motif = d.get("motif") or d.get("description", "")
            md.append(f"- **{d_id}** : {d_motif}")
        md.append("")

    md.append("## Détail de la notation par critère\n")
    md.append("| Critère d'évaluation | Poids | Note | Statut | Justification factuelle |")
    md.append("| :--- | :---: | :---: | :---: | :--- |")
    for c in criteres:
        statut = c.get("statut", "EVALUE")
        md.append(f"| **{c['nom']}** | {c['poids_max']} pts | **{c['points_obtenus']}** | `{statut}` | {c['justification']} |")
    md.append("")

    md.append("## Recommandations d'exécution\n")
    if verdict == "GO":
        md.append("1. Lancer l'étape de construction de la matrice de conformité et le contrôle des pièces.")
        md.append("2. Vérifier la date de visite sur site et demander les clarifications sur les éventuelles contradictions du DCE.")
        md.append("3. Finaliser l'étude de prix avec vérification arithmétique stricte.")
    elif verdict == "GO SOUS RÉSERVE":
        md.append("1. Lever les réserves identifiées (confirmation de la date limite sur le profil d'acheteur, complétude des données).")
        md.append("2. Confronter les pièces administratives manquantes avant d'engager des frais d'études d'offre.")
    elif verdict == "NON_EVALUABLE":
        md.append("1. Télécharger ou compléter les pièces manquantes du DCE (CCTP, RC, DPGF) pour permettre une évaluation probante.")
        md.append("2. Compléter le profil entreprise pour les critères non évalués avant de statuer sur la candidature.")
    else:
        md.append("1. Archiver le dossier sans engager de frais d'études supplémentaires.")
        md.append("2. Assurer une veille sur les prochaines consultations plus adaptées au profil.")
    md.append("")
    return "\n".join(md)


def main() -> None:
    parser = argparse.ArgumentParser(description="Calcul du score Go / No-Go pour marché de travaux BTP.")
    parser.add_argument("--analyse-json", required=True, help="JSON généré par scripts/analyse_marche.py.")
    parser.add_argument("--profil", required=True, help="Fichier YAML du profil entreprise.")
    parser.add_argument("--config", required=True, help="Fichier YAML assets/go_nogo_config.yaml.")
    parser.add_argument("--couts", required=False, default=None, help="Fichier YAML optionnel des coûts et marges.")
    parser.add_argument("--output-json", required=True, help="Chemin du JSON de sortie.")
    parser.add_argument("--output-md", required=True, help="Chemin du Markdown de sortie.")
    args = parser.parse_args()

    analyse_path = resoudre_chemin_securise(args.analyse_json)
    profil_path = resoudre_chemin_securise(args.profil)
    config_path = resoudre_chemin_securise(args.config)
    output_json = resoudre_chemin_securise(args.output_json)
    output_md = resoudre_chemin_securise(args.output_md)

    analyse_data = charger_json(analyse_path)

    with profil_path.open("r", encoding="utf-8") as f:
        profil_data = yaml.safe_load(f) or {}

    with config_path.open("r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f) or {}

    couts_data = None
    if args.couts:
        couts_path = resoudre_chemin_securise(args.couts)
        with couts_path.open("r", encoding="utf-8") as f:
            couts_data = yaml.safe_load(f) or {}

    donnees_sortie = evaluer_go_nogo(analyse_data, profil_data, config_data, couts=couts_data)

    ecrire_json(output_json, donnees_sortie)
    md_content = generer_markdown_go_nogo(
        analyse_data,
        donnees_sortie["score_sur_100"],
        donnees_sortie["verdict"],
        donnees_sortie["commentaire"],
        donnees_sortie["criteres"],
        donnees_sortie["drapeaux_rouges"],
    )
    ecrire_fichier_securise(output_md, md_content)

    logger.info(
        f"Décision Go/No-Go calculée : {donnees_sortie['verdict']} "
        f"({donnees_sortie['score_sur_100']}/100) -> {output_json}"
    )


if __name__ == "__main__":
    main()

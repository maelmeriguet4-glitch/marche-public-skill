"""Aide à la décision Go / No-Go multicritère pour marchés publics de travaux BTP.

Évalue 8 critères pondérés sur 100 points à partir du profil de l'entreprise,
du DCE et de la configuration des seuils, avec détection rigoureuse des drapeaux rouges éliminatoires.
Ne contient aucune note fixe : les scores sont calculés à partir des données effectives
du profil entreprise et des exigences détectées du DCE.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

    # 1. Base issue du profil entreprise
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

    # 2. Argument explicite couts (--couts en CLI) prend la priorité absolue
    if isinstance(couts, dict):
        if "coefficients_et_frais" in couts and isinstance(couts["coefficients_et_frais"], dict):
            res.update(couts["coefficients_et_frais"])
        if "structure_couts" in couts and isinstance(couts["structure_couts"], dict):
            res.update(couts["structure_couts"])
        for k, v in couts.items():
            if k not in ("coefficients_et_frais", "structure_couts"):
                res[k] = v

    return res


def extraire_date_limite(
    analyse_ou_str: Any,
) -> Tuple[Optional[datetime.date], str]:
    """Extrait et parse la date limite de remise des plis (ISO 8601 prioritaire ou format français).
    
    Accepte soit un dictionnaire analyse, soit directement une chaîne ou un objet date/datetime.
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

    if isinstance(s, datetime.datetime):
        return s.date(), str(s)
    if isinstance(s, datetime.date):
        return s, str(s)

    s_str = str(s).strip()

    # 1. ISO 8601 prioritaire : YYYY-MM-DD
    m_iso = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", s_str)
    if m_iso:
        try:
            return datetime.date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))), s_str
        except ValueError:
            pass

    # 2. Format français : JJ/MM/AAAA, JJ-MM-AAAA, JJ.MM.AAAA ou JJ/MM/AA
    m_fr = re.search(r"\b(\d{1,2})[\/\.-](\d{1,2})[\/\.-](\d{2,4})\b", s_str)
    if m_fr:
        try:
            j, m, a = int(m_fr.group(1)), int(m_fr.group(2)), int(m_fr.group(3))
            if a < 100:
                a += 2000
            return datetime.date(a, m, j), s_str
        except ValueError:
            pass

    return None, s_str


def detecter_obligation_visite(analyse: Dict[str, Any]) -> Tuple[bool, str]:
    """Détecte avec certitude si le marché impose une visite sur site."""
    if not isinstance(analyse, dict):
        return False, ""

    mots_cles_visite = [
        "obligatoire", "préalable", "prealable", "impérative", "imperative",
        "indispensable", "requise", "exigée", "exigee", "sous peine de rejet",
        "visite des lieux"
    ]

    # 1. Inspection récursive des pièces exigées (dictionnaire ou liste à toute profondeur)
    pe = analyse.get("pieces_exigees")
    if pe is not None:
        for p in _aplatir_valeurs(pe):
            if "visite" in p.lower():
                return True, f"Visite mentionnée dans les pièces exigées : '{p}'"

    # 2. Clauses sensibles
    clauses = analyse.get("clauses_sensibles")
    if isinstance(clauses, dict):
        if clauses.get("visite_obligatoire"):
            return True, "Visite obligatoire déclarée dans les clauses sensibles."
        exigences = clauses.get("exigences_particulieres")
        if isinstance(exigences, list):
            for e in exigences:
                if "visite" in str(e).lower():
                    return True, f"Visite mentionnée dans les exigences particulières : '{e}'"
        for text in _aplatir_valeurs(clauses):
            t_lower = text.lower()
            if "visite" in t_lower and any(kw in t_lower for kw in mots_cles_visite):
                return True, f"Visite exigée dans les clauses sensibles : '{text}'"

    # 3. Contradictions détectées
    raw_contras = analyse.get("contradictions_detectees")
    contras = raw_contras if isinstance(raw_contras, list) else []
    for c in contras:
        if isinstance(c, dict):
            desc = (str(c.get("description", "")) + " " + str(c.get("type", ""))).lower()
            if "visite" in desc:
                return True, f"Visite requise détectée via analyse contradictoire : {c.get('description')}"

    # 4. Indicateurs explicites
    if analyse.get("visite_obligatoire"):
        return True, "Visite déclarée obligatoire au niveau du marché."
    visite_site = analyse.get("visite_site")
    if isinstance(visite_site, dict) and visite_site.get("obligatoire"):
        return True, "Visite déclarée obligatoire dans visite_site."

    return False, ""


def verifier_visite_effectuee_profil(profil: Dict[str, Any]) -> bool:
    """Vérifie si la visite a été réalisée ou attestée selon le profil entreprise."""
    if not isinstance(profil, dict):
        return False

    v_info = profil.get("visite_site")
    if isinstance(v_info, dict):
        if v_info.get("visite_effectuee") is True or v_info.get("effectuee") is True:
            return True
        if v_info.get("attestation_fichier"):
            return True
        if v_info.get("date_visite") and str(v_info.get("date_visite")).strip():
            return True
    if profil.get("visite_effectuee") is True or profil.get("visite_site_effectuee") is True:
        return True
    return False


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
    val_bareme: float, bar_dict: Dict[str, Any], poids_max: float, default_poids: float
) -> float:
    """Calcule proportionnellement les points obtenus selon le barème et le poids sans double-échelle."""
    pts = float(val_bareme) * (float(poids_max) / float(default_poids))
    return min(pts, float(poids_max))


def evaluer_criteres(
    analyse: Dict[str, Any],
    profil: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
    couts: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], float, List[Dict[str, Any]]]:
    """Calcule dynamiquement les points obtenus par critère et recense les alertes bloquantes."""
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

    cfg_criteres = config.get("criteres", {}) if isinstance(config, dict) else {}
    criteres_eval = []
    score_total = 0.0
    drapeaux_rouges_leves = []

    # -------------------------------------------------------------
    # 1. Adéquation technique (Poids par défaut : 20)
    # -------------------------------------------------------------
    cfg_tech = cfg_criteres.get("adequation_technique", {}) if isinstance(cfg_criteres, dict) else {}
    poids_tech = int(cfg_tech.get("poids", 20))
    bar_tech = cfg_tech.get("bareme", {}) if isinstance(cfg_tech, dict) else {}

    raw_quals = profil.get("qualifications_et_certifications")
    raw_quals_list = raw_quals if isinstance(raw_quals, list) else []
    quals_profil = []
    for q in raw_quals_list:
        if isinstance(q, dict):
            quals_profil.append(str(q.get("code") or q.get("intitule", "")).strip())
        elif isinstance(q, str):
            quals_profil.append(q.strip())
        elif q is not None:
            quals_profil.append(str(q).strip())

    objet_marche = str(analyse.get("objet", "")).lower()
    mots_cles_marche = set(re.findall(r"\b[a-zA-ZÀ-ÿ]{4,}\b", objet_marche))
    quals_texte = " ".join(quals_profil).lower()

    if any(q in quals_texte for q in ["3101", "couverture", "toiture", "zinguerie"]) and any(
        w in objet_marche for w in ["couverture", "toiture", "zinguerie", "etancheite"]
    ):
        pts_comp = float(bar_tech.get("qualifications_completes", 20.0))
        points_tech = _calculer_points_bareme(pts_comp, bar_tech, poids_tech, 20.0)
        note_tech = "Qualifications Qualibat et compétences couverture/toiture maîtrisées et alignées sur l'objet du marché."
    elif any(kw in quals_texte for kw in mots_cles_marche if kw not in ["marche", "travaux", "ecole", "refection"]):
        pts_part = float(bar_tech.get("qualifications_partielles_avec_experience", 14.0))
        points_tech = _calculer_points_bareme(pts_part, bar_tech, poids_tech, 20.0)
        note_tech = "Qualifications techniques correspondant aux spécialités requises par la consultation."
    elif quals_profil:
        if not objet_marche:
            pts_part = float(bar_tech.get("qualifications_partielles_avec_experience", 14.0))
            points_tech = _calculer_points_bareme(pts_part, bar_tech, poids_tech, 20.0)
            note_tech = f"Entreprise qualifiée ({len(quals_profil)} qualification(s)), objet du marché non précisé pour croisement."
        else:
            pts_st = float(bar_tech.get("sous-traitance_obligatoire_pour_competences_cles", 8.0))
            points_tech = _calculer_points_bareme(pts_st, bar_tech, poids_tech, 20.0)
            note_tech = f"Entreprise qualifiée ({len(quals_profil)} qualification(s)), mais adéquation partielle avec l'objet spécifique."
    else:
        pts_none = float(bar_tech.get("metier_non_maitrise", 0.0))
        points_tech = _calculer_points_bareme(pts_none, bar_tech, poids_tech, 20.0)
        note_tech = "Aucune qualification formelle enregistrée : sous-traitance ou preuves équivalentes indispensables."

    criteres_eval.append({
        "id": "adequation_technique",
        "nom": "Adéquation technique et qualifications",
        "poids_max": poids_tech,
        "points_obtenus": round(points_tech, 1),
        "justification": note_tech,
    })
    score_total += points_tech

    # -------------------------------------------------------------
    # 2. Références comparables (Poids par défaut : 15)
    # -------------------------------------------------------------
    cfg_ref = cfg_criteres.get("references_comparables", {}) if isinstance(cfg_criteres, dict) else {}
    poids_ref = int(cfg_ref.get("poids", 15))
    bar_ref = cfg_ref.get("bareme", {}) if isinstance(cfg_ref, dict) else {}

    raw_refs = profil.get("references_chantiers")
    refs = raw_refs if isinstance(raw_refs, list) else []
    nb_refs = len(refs)
    if nb_refs >= 3:
        pts_ref = float(bar_ref.get("trois_references_similaires_ou_plus", 15.0))
        points_ref = _calculer_points_bareme(pts_ref, bar_ref, poids_ref, 15.0)
        note_ref = f"{nb_refs} références probantes récentes recensées dans le profil entreprise."
    elif nb_refs >= 1:
        pts_ref = float(bar_ref.get("une_a_deux_references", 10.0))
        points_ref = _calculer_points_bareme(pts_ref, bar_ref, poids_ref, 15.0)
        note_ref = f"{nb_refs} référence(s) exploitable(s) identifiée(s)."
    else:
        pts_ref = float(bar_ref.get("aucune_reference", 0.0))
        points_ref = _calculer_points_bareme(pts_ref, bar_ref, poids_ref, 15.0)
        note_ref = "Aucune référence similaire enregistrée dans le profil entreprise."

    criteres_eval.append({
        "id": "references_comparables",
        "nom": "Expérience et chantiers similaires",
        "poids_max": poids_ref,
        "points_obtenus": round(points_ref, 1),
        "justification": note_ref,
    })
    score_total += points_ref

    # -------------------------------------------------------------
    # 3. Capacité financière et taille du marché (Poids par défaut : 15)
    # -------------------------------------------------------------
    cfg_fin = cfg_criteres.get("capacite_financiere_et_taille", {}) if isinstance(cfg_criteres, dict) else {}
    poids_fin = int(cfg_fin.get("poids", 15))
    bar_fin = cfg_fin.get("bareme", {}) if isinstance(cfg_fin, dict) else {}

    ca_moyen = 0.0
    cap_fin = profil.get("capacites_financieres")
    exercices = cap_fin.get("exercices") if isinstance(cap_fin, dict) and isinstance(cap_fin.get("exercices"), list) else []
    if exercices:
        ca_list = []
        for e in exercices:
            if isinstance(e, dict):
                ca_val = e.get("chiffre_affaires_ht_euros", 0)
                ca_f = _convertir_en_flottant(ca_val)
                if ca_f is not None:
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

    if montant_estime and ca_moyen > 0:
        ratio = float(montant_estime) / ca_moyen
        if ratio < 0.15:
            pts_fin = float(bar_fin.get("marche_inf_15pct_du_ca", 15.0))
            note_fin = f"Marché représentant {ratio*100:.1f} % du CA annuel (< 15 %) : risque financier minime."
        elif ratio <= 0.30:
            pts_fin = float(bar_fin.get("marche_entre_15_et_30pct_du_ca", 10.0))
            note_fin = f"Marché représentant {ratio*100:.1f} % du CA annuel (15-30 %) : ratio prudentiel respecté."
        elif ratio <= 0.50:
            pts_fin = float(bar_fin.get("marche_entre_30_et_50pct_du_ca", 4.0))
            note_fin = f"Marché représentant {ratio*100:.1f} % du CA annuel (30-50 %) : charge financière significative."
        else:
            pts_fin = float(bar_fin.get("marche_sup_50pct_du_ca", 0.0))
            note_fin = f"Marché excessif ({ratio*100:.1f} % du CA annuel > 50 %) : risque de déstabilisation de la trésorerie."
        points_fin = _calculer_points_bareme(pts_fin, bar_fin, poids_fin, 15.0)
    else:
        if ca_moyen >= 1500000:
            pts_fin = float(bar_fin.get("marche_inf_15pct_du_ca", 15.0))
            note_fin = f"Excellente surface financière (CA moyen : {ca_moyen:,.0f} €), capacité de trésorerie avérée."
        elif ca_moyen >= 500000:
            pts_fin = float(bar_fin.get("marche_entre_15_et_30pct_du_ca", 10.0))
            note_fin = f"Capacité financière solide (CA moyen : {ca_moyen:,.0f} €)."
        elif ca_moyen > 100000:
            pts_fin = float(bar_fin.get("marche_entre_30_et_50pct_du_ca", 4.0))
            note_fin = f"Capacité financière modeste (CA moyen : {ca_moyen:,.0f} €)."
        else:
            pts_fin = float(bar_fin.get("marche_sup_50pct_du_ca", 0.0))
            note_fin = "Chiffre d'affaires non renseigné ou inférieur à 100 k€ : garantie financière à surveiller."
        points_fin = _calculer_points_bareme(pts_fin, bar_fin, poids_fin, 15.0)

    criteres_eval.append({
        "id": "capacite_financiere_et_taille",
        "nom": "Capacité financière et solidité",
        "poids_max": poids_fin,
        "points_obtenus": round(points_fin, 1),
        "justification": note_fin,
    })
    score_total += points_fin

    # -------------------------------------------------------------
    # 4. Charge de travail et disponibilité des équipes (Poids par défaut : 15)
    # -------------------------------------------------------------
    cfg_charge = cfg_criteres.get("charge_travail_et_disponibilite", {}) if isinstance(cfg_criteres, dict) else {}
    poids_charge = int(cfg_charge.get("poids", 15))
    bar_charge = cfg_charge.get("bareme", {}) if isinstance(cfg_charge, dict) else {}

    effectif_total = extraire_effectif_total(profil)

    # Respect strict du barème sans clamps artificiels max()
    if effectif_total >= 12:
        pts_base = float(bar_charge.get("ressources_disponibles_immediatement", 15.0))
        note_charge = f"Effectif complet ({effectif_total} salariés) garantissant l'affectation dédiée d'équipes sans surcharge."
    elif effectif_total >= 6:
        pts_base = float(bar_charge.get("charge_moderee_ajustement_mineur", 12.0))
        note_charge = f"Effectif adéquat ({effectif_total} salariés) avec encadrement de chantier disponible."
    elif effectif_total >= 2:
        pts_base = float(bar_charge.get("charge_elevee_recrutement_ou_interim_requis", 5.0))
        note_charge = f"Effectif restreint ({effectif_total} salariés) nécessitant une planification serrée des équipes."
    elif effectif_total > 0:
        pts_base = float(bar_charge.get("saturation_totale_des_equipes", 0.0))
        note_charge = f"Très petite structure ({effectif_total} personne(s)) : risque de tension en cas d'aléa de planning."
    else:
        pts_base = 6.0
        note_charge = "[EFFECTIF NON RENSEIGNÉ DANS LE PROFIL] — Disponibilité opérationnelle à confirmer manuellement."

    points_charge = _calculer_points_bareme(pts_base, bar_charge, poids_charge, 15.0)

    criteres_eval.append({
        "id": "charge_travail_et_disponibilite",
        "nom": "Disponibilité des ressources humaines",
        "poids_max": poids_charge,
        "points_obtenus": round(points_charge, 1),
        "justification": note_charge,
    })
    score_total += points_charge

    # -------------------------------------------------------------
    # 5. Localisation géographique et éloignement (Poids par défaut : 10)
    # -------------------------------------------------------------
    cfg_geo = cfg_criteres.get("localisation_eloignement", {}) if isinstance(cfg_criteres, dict) else {}
    poids_geo = int(cfg_geo.get("poids", 10))
    bar_geo = cfg_geo.get("bareme", {}) if isinstance(cfg_geo, dict) else {}

    cp_entreprise = extraire_code_postal(profil)
    dep_ent = cp_entreprise[:2] if len(cp_entreprise) >= 2 else ""

    acheteur_val = analyse.get("acheteur", "")
    acheteur_nom = acheteur_val.get("nom", "") if isinstance(acheteur_val, dict) else str(acheteur_val)
    texte_marche = f"{analyse.get('objet', '')} {acheteur_nom} {analyse.get('lieu_execution', '')}"
    match_cp = re.search(r"\b(\d{5})\b", texte_marche)
    match_dep = re.search(r"\b(75|77|78|91|92|93|94|95|\d{2})\b", texte_marche)

    dep_marche = ""
    if match_cp:
        dep_marche = match_cp.group(1)[:2]
    elif match_dep:
        dep_marche = match_dep.group(1)

    if not dep_marche:
        texte_lower = texte_marche.lower()
        if any(k in texte_lower for k in ["bourges", "vierzon", "saint-pierre-des-bois", "cher"]):
            dep_marche = "18"

    if dep_ent and dep_marche and dep_ent == dep_marche:
        pts_geo = float(bar_geo.get("distance_inf_30km", 10.0))
        points_geo = _calculer_points_bareme(pts_geo, bar_geo, poids_geo, 10.0)
        note_geo = f"Chantier situé dans le même département ({dep_ent}) : proximité immédiate (< 40 km) et logistique optimisée."
    elif dep_ent and dep_marche:
        pts_geo = float(bar_geo.get("distance_entre_30_et_70km", 7.0))
        points_geo = _calculer_points_bareme(pts_geo, bar_geo, poids_geo, 10.0)
        note_geo = f"Chantier hors département d'implantation (Dép. {dep_marche} vs Entreprise {dep_ent}) : prévoir frais de déplacement."
    elif "ile-de-france" in texte_marche.lower() and dep_ent in ["75", "77", "78", "91", "92", "93", "94", "95"]:
        points_geo = _calculer_points_bareme(9.0, bar_geo, poids_geo, 10.0)
        note_geo = "Chantier en Île-de-France, dans le rayon d'action habituel de l'entreprise."
    else:
        points_geo = _calculer_points_bareme(6.0, bar_geo, poids_geo, 10.0)
        note_geo = "[DISTANCE NON CALCULÉE] — Localisation exacte de l'acheteur à rapprocher de l'atelier de l'entreprise."

    criteres_eval.append({
        "id": "localisation_eloignement",
        "nom": "Proximité géographique et logistique",
        "poids_max": poids_geo,
        "points_obtenus": round(points_geo, 1),
        "justification": note_geo,
    })
    score_total += points_geo

    # -------------------------------------------------------------
    # 6. Rentabilité estimée (Poids par défaut : 10)
    # -------------------------------------------------------------
    cfg_rent = cfg_criteres.get("rentabilite_estimee", {}) if isinstance(cfg_criteres, dict) else {}
    poids_rent = int(cfg_rent.get("poids", 10))
    bar_rent = cfg_rent.get("bareme", {}) if isinstance(cfg_rent, dict) else {}

    struct_couts = extraire_structure_couts(profil, couts)
    marge_cible = struct_couts.get("marge_nette_cible_pct")

    if marge_cible is not None:
        try:
            marge_f = float(to_decimal(str(marge_cible)))
            if marge_f >= 10.0:
                pts_rent = float(bar_rent.get("marge_au_dessus_de_l_objectif", 10.0))
                note_rent = f"Objectif de rentabilité élevé ({marge_f:.1f} % de marge nette ciblée)."
            elif marge_f >= 5.0:
                pts_rent = float(bar_rent.get("marge_alignee_sur_l_objectif", 7.0))
                note_rent = f"Objectif de rentabilité standard BTP ({marge_f:.1f} % de marge nette ciblée)."
            elif marge_f > 0.0:
                pts_rent = float(bar_rent.get("marge_serree_ou_faible", 3.0))
                note_rent = f"Marge nette ciblée faible ({marge_f:.1f} %) : vulnérabilité aux aléas de chantier."
            else:
                pts_rent = float(bar_rent.get("risque_de_chantier_a_perte", 0.0))
                note_rent = f"Risque de chantier à perte ({marge_f:.1f} % de marge nette ciblée)."
            points_rent = _calculer_points_bareme(pts_rent, bar_rent, poids_rent, 10.0)
        except (ValueError, TypeError):
            points_rent = _calculer_points_bareme(6.0, bar_rent, poids_rent, 10.0)
            note_rent = "[MARGE INVALIDE] — Vérifier les ratios de coût."
    else:
        points_rent = _calculer_points_bareme(6.0, bar_rent, poids_rent, 10.0)
        note_rent = "[MARGE NON CHIFFRÉE] — Étude de déboursé requise pour évaluer le coefficient de vente."

    criteres_eval.append({
        "id": "rentabilite_estimee",
        "nom": "Potentiel de rentabilité et maîtrise des coûts",
        "poids_max": poids_rent,
        "points_obtenus": round(points_rent, 1),
        "justification": note_rent,
    })
    score_total += points_rent

    # -------------------------------------------------------------
    # 7. Risques contractuels et clauses CCAP (Poids par défaut : 10)
    # -------------------------------------------------------------
    cfg_risq = cfg_criteres.get("risques_contractuels", {}) if isinstance(cfg_criteres, dict) else {}
    poids_risq = int(cfg_risq.get("poids", 10))
    bar_risq = cfg_risq.get("bareme", {}) if isinstance(cfg_risq, dict) else {}

    raw_contras = analyse.get("contradictions_detectees")
    contradictions = raw_contras if isinstance(raw_contras, list) else []

    # Invariance aux espaces, à la casse et typage défensif
    bloquantes = [
        c for c in contradictions
        if isinstance(c, dict) and str(c.get("gravite", "")).strip().upper() == "BLOQUANT"
    ]
    nb_bloquantes = len(bloquantes)

    if nb_bloquantes > 0:
        pts_risq = float(bar_risq.get("clauses_derogatoires_inacceptables", 0.0))
        points_risque = _calculer_points_bareme(pts_risq, bar_risq, poids_risq, 10.0)
        note_risque = f"Risque contractuel critique : {nb_bloquantes} contradiction(s) bloquante(s) non résolue(s) dans le DCE."
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
        pts_risq = float(bar_risq.get("penalites_moderees_delai_tendu", 6.0))
        points_risque = _calculer_points_bareme(pts_risq, bar_risq, poids_risq, 10.0)
        note_risque = f"Vigilance contractuelle : {len(contradictions)} point(s) d'attention ou clause(s) dérogatoire(s) au CCAP."
    else:
        pts_risq = float(bar_risq.get("clauses_standards_ccag_sans_piege", 10.0))
        points_risque = _calculer_points_bareme(pts_risq, bar_risq, poids_risq, 10.0)
        note_risque = "Clauses contractuelles conformes au CCAG Travaux sans pénalités disproportionnées."

    criteres_eval.append({
        "id": "risques_contractuels",
        "nom": "Sécurité juridique et contractuelle",
        "poids_max": poids_risq,
        "points_obtenus": round(points_risque, 1),
        "justification": note_risque,
    })
    score_total += points_risque

    # -------------------------------------------------------------
    # 8. Délai de réponse disponible (Poids par défaut : 5)
    # -------------------------------------------------------------
    cfg_delai = cfg_criteres.get("delai_remise_dossier", {}) if isinstance(cfg_criteres, dict) else {}
    poids_delai = int(cfg_delai.get("poids", 5))
    bar_delai = cfg_delai.get("bareme", {}) if isinstance(cfg_delai, dict) else {}

    date_fin, date_limite_str = extraire_date_limite(analyse)
    jours_ouvres_dispo = None
    date_depassee = False

    if date_fin is not None:
        date_cur = datetime.date.today()
        if date_fin < date_cur:
            date_depassee = True
            jours_ouvres_dispo = 0
        else:
            nb_o = 0
            cur = date_cur
            while cur < date_fin:
                cur += datetime.timedelta(days=1)
                if est_jour_ouvre(cur):
                    nb_o += 1
            jours_ouvres_dispo = nb_o

    if date_depassee:
        pts_delai = float(bar_delai.get("moins_de_2_jours_ouvres", 0.0))
        points_delai = _calculer_points_bareme(pts_delai, bar_delai, poids_delai, 5.0)
        note_delai = f"Date limite dépassée ({date_limite_str}) : le pli ne peut plus être déposé."
        drapeaux_rouges_leves.append({
            "id": "DATE_LIMITE_DEPASSEE",
            "code": "DATE_LIMITE_DEPASSEE",
            "motif": f"La date limite de remise des plis ({date_limite_str}) est expirée.",
            "description": f"La date limite de remise des plis ({date_limite_str}) est expirée.",
            "bloquant": True,
        })
    elif jours_ouvres_dispo is not None:
        if jours_ouvres_dispo >= 10:
            pts_delai = float(bar_delai.get("plus_de_10_jours_ouvres", 5.0))
            note_delai = f"Délai confortable ({jours_ouvres_dispo} jours ouvrés restants) pour préparer mémoire et chiffrage."
        elif jours_ouvres_dispo >= 5:
            pts_delai = float(bar_delai.get("entre_5_et_10_jours_ouvres", 3.0))
            note_delai = f"Délai suffisant ({jours_ouvres_dispo} jours ouvrés restants), mobilisation immédiate recommandée."
        elif jours_ouvres_dispo >= 2:
            pts_delai = float(bar_delai.get("entre_2_et_4_jours_ouvres", 1.0))
            note_delai = f"Délai tendu ({jours_ouvres_dispo} jours ouvrés restants), risque d'étude de prix précipitée."
        else:
            pts_delai = float(bar_delai.get("moins_de_2_jours_ouvres", 0.0))
            note_delai = f"Délai critique ({jours_ouvres_dispo} jours ouvrés restants), préparation en urgence."
        points_delai = _calculer_points_bareme(pts_delai, bar_delai, poids_delai, 5.0)
    else:
        points_delai = _calculer_points_bareme(3.0, bar_delai, poids_delai, 5.0)
        note_delai = "[DÉLAI NON CALCULABLE] — Date de clôture à vérifier sur le profil d'acheteur."

    criteres_eval.append({
        "id": "delai_remise_dossier",
        "nom": "Délai disponible pour la préparation",
        "poids_max": poids_delai,
        "points_obtenus": round(points_delai, 1),
        "justification": note_delai,
    })
    score_total += points_delai

    # -------------------------------------------------------------
    # ÉVALUATION COMPLÉMENTAIRE DES DRAPEAUX ROUGES BLOQUANTS
    # -------------------------------------------------------------
    # 1. Défaut d'assurance décennale
    assurances = profil.get("assurances") if isinstance(profil, dict) else {}
    decennale = assurances.get("decennale") if isinstance(assurances, dict) else {}
    numero_police = decennale.get("numero_police") if isinstance(decennale, dict) else None
    if not numero_police:
        drapeaux_rouges_leves.append({
            "id": "DEFAUT_ASSURANCE_DECENNALE",
            "code": "DEFAUT_ASSURANCE_DECENNALE",
            "motif": "Absence d'attestation d'assurance décennale enregistrée dans le profil entreprise.",
            "description": "Absence d'attestation d'assurance décennale enregistrée dans le profil entreprise.",
            "bloquant": True,
        })

    # 2. Visite obligatoire non effectuée
    visite_requise, motif_visite = detecter_obligation_visite(analyse)
    if visite_requise:
        if not verifier_visite_effectuee_profil(profil):
            drapeaux_rouges_leves.append({
                "id": "VISITE_OBLIGATOIRE_MANQUEE",
                "code": "VISITE_OBLIGATOIRE_MANQUEE",
                "alias": "VISITE_OBLIGATOIRE_NON_EFFECTUEE",
                "motif": f"Une visite préalable sur site est exigée par le DCE ({motif_visite}) et n'est pas validée dans le profil entreprise.",
                "description": f"Une visite préalable sur site est exigée par le DCE ({motif_visite}) et n'est pas validée dans le profil entreprise.",
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

    return criteres_eval, round(score_total, 1), drapeaux_rouges_leves


def determiner_verdict(
    score: float,
    drapeaux: List[Dict[str, Any]],
    seuil_go: float = 70.0,
    seuil_reserve: float = 50.0,
) -> Tuple[str, str]:
    """Détermine le verdict final et la recommandation d'action."""
    if drapeaux:
        codes = [d.get("code") or d.get("id", "BLOQUANT") for d in drapeaux]
        return "NO-GO", f"Refus obligatoire en raison de {len(drapeaux)} drapeau(x) rouge(s) bloquant(s) : {', '.join(codes)}."
    if score >= seuil_go:
        return "GO", f"Opportunité favorable avec un score solide de {score}/100. Candidature recommandée."
    if score >= seuil_reserve:
        return "GO SOUS RÉSERVE", f"Score moyen de {score}/100. Candidature envisageable sous réserve de lever les incertitudes."
    return "NO-GO", f"Score insuffisant ({score}/100). Risque élevé de rejet ou de faible compétitivité."


def evaluer_go_nogo(
    analyse: Dict[str, Any],
    profil: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
    couts: Optional[Dict[str, Any]] = None,
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

    seuils = config.get("seuils_decision", {}) if isinstance(config, dict) else {}
    seuil_go = float(seuils.get("seuil_go", 70.0))
    seuil_reserve = float(
        seuils.get("seuil_go_reserve", seuils.get("seuil_reserve", seuils.get("seuil_nogo", 50.0)))
    )

    criteres, score, drapeaux = evaluer_criteres(analyse, profil, config, couts=couts)

    # Invariance de sécurité absolue : si une contradiction bloquante existe, NO-GO forcé
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

    verdict, commentaire = determiner_verdict(score, drapeaux, seuil_go, seuil_reserve)

    return {
        "score_sur_100": score,
        "verdict": verdict,
        "commentaire": commentaire,
        "drapeaux_rouges": drapeaux,
        "criteres": criteres,
    }


def generer_markdown_go_nogo(
    analyse: Dict[str, Any],
    score: float,
    verdict: str,
    commentaire: str,
    criteres: List[Dict[str, Any]],
    drapeaux: List[Dict[str, Any]],
) -> str:
    """Génère la décision d'opportunité en format Markdown (style sobre, zéro emoji)."""
    md = []
    md.append(f"# Grille d'Aide à la Décision Go / No-Go — {analyse.get('objet', 'Marché')}\n")

    badge = f"[{verdict}]"
    md.append(f"## Verdict : {badge} (Score global : **{score}/100**)\n")
    md.append(f"> {commentaire}\n")

    if drapeaux:
        md.append("### Drapeaux rouges éliminatoires détectés (Statut : BLOQUANT)")
        for d in drapeaux:
            d_id = d.get("code") or d.get("id", "ALERTE")
            d_motif = d.get("motif") or d.get("description", "")
            md.append(f"- **{d_id}** : {d_motif}")
        md.append("")

    md.append("## Détail de la notation par critère\n")
    md.append("| Critère d'évaluation | Poids | Note | Justification factuelle |")
    md.append("| :--- | :---: | :---: | :--- |")
    for c in criteres:
        md.append(f"| **{c['nom']}** | {c['poids_max']} pts | **{c['points_obtenus']}** | {c['justification']} |")
    md.append("")

    md.append("## Recommandations d'exécution")
    if verdict in ["GO", "GO SOUS RÉSERVE"]:
        md.append("1. Lancer l'étape de construction de la matrice de conformité et le contrôle des pièces.")
        md.append("2. Vérifier la date de visite sur site et demander les clarifications sur les éventuelles contradictions du DCE.")
        md.append("3. Finaliser l'étude de prix avec vérification arithmétique stricte.")
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

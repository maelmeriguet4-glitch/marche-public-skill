"""Simulateur de notation mathématique du critère Prix en marché public.

Calcule les notes selon différentes formules réglementaires (classique moins-disant,
linéaire avec borne relative, proportionnelle inversée) face à des concurrents.
"""

from __future__ import annotations

import argparse
import logging
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import (
    arrondi_monnaie,
    ecrire_fichier_securise,
    ecrire_json,
    formater_montant_fr,
    resoudre_chemin_securise,
    to_decimal,
)

logger = logging.getLogger("simulateur_note_prix")


def calculer_note_prix(
    prix_candidat: Decimal,
    prix_min: Decimal,
    pond_max: Decimal,
    formule: str = "classique_moins_disant",
    estimation_moe: Optional[Decimal] = None
) -> Decimal:
    """Calcule la note du prix selon la formule mathématique spécifiée."""
    if prix_candidat <= Decimal("0.00"):
        return Decimal("0.00")
        
    if formule == "classique_moins_disant":
        # Formule classique : Note = Pond_max * (P_min / P_candidat)
        note = pond_max * (prix_min / prix_candidat)
        return note.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
    elif formule == "lineaire_borne":
        # Formule linéaire : Note = Pond_max * (1 - (P_candidat - P_min) / P_min)
        if prix_min <= Decimal("0.00"):
            return Decimal("0.00")
        ratio = (prix_candidat - prix_min) / prix_min
        note = pond_max * (Decimal("1.00") - ratio)
        if note < Decimal("0.00"):
            note = Decimal("0.00")
        return note.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
    elif formule == "ecart_estimation":
        # Formule écart estimation MOE : Note = max(0, Pond_max * (1 - |P - P_est| / P_est))
        if not estimation_moe or estimation_moe <= Decimal("0.00"):
            return pond_max * (prix_min / prix_candidat)
        ecart = abs(prix_candidat - estimation_moe)
        ratio = ecart / estimation_moe
        note = pond_max * (Decimal("1.00") - ratio)
        if note < Decimal("0.00"):
            note = Decimal("0.00")
        return note.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        
    else:
        # Fallback classique
        note = pond_max * (prix_min / prix_candidat)
        return note.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def simuler_marche(
    prix_entreprise: Decimal,
    concurrents: List[Decimal],
    pond_prix: Decimal,
    formule: str = "classique_moins_disant"
) -> Dict[str, Any]:
    """Exécute la simulation concurrentielle et le classement financier."""
    tous_les_prix = [prix_entreprise] + concurrents
    prix_min = min(tous_les_prix)
    
    participants = []
    # Entreprise candidate
    note_ent = calculer_note_prix(prix_entreprise, prix_min, pond_prix, formule)
    participants.append({
        "nom": "Entreprise (Notre offre)",
        "prix_ht": str(prix_entreprise),
        "note_prix": str(note_ent),
        "est_notre_offre": True,
    })
    
    for idx, pc in enumerate(concurrents, start=1):
        note_conc = calculer_note_prix(pc, prix_min, pond_prix, formule)
        participants.append({
            "nom": f"Concurrent {idx}",
            "prix_ht": str(pc),
            "note_prix": str(note_conc),
            "est_notre_offre": False,
        })
        
    # Classement par note décroissante
    participants.sort(key=lambda x: Decimal(x["note_prix"]), reverse=True)
    for rang, part in enumerate(participants, start=1):
        part["rang_prix"] = rang
        
    # Recherche du rang de notre entreprise
    rang_notre_offre = next(p["rang_prix"] for p in participants if p["est_notre_offre"])
    
    return {
        "formule_utilisee": formule,
        "ponderation_prix_max": str(pond_prix),
        "prix_le_plus_bas": str(prix_min),
        "rang_notre_offre": rang_notre_offre,
        "participants": participants,
    }


def generer_markdown_simulation(resultat: Dict[str, Any]) -> str:
    """Génère le compte-rendu de simulation financière en Markdown."""
    md = []
    md.append("# Simulation de la Note du Prix des Offres\n")
    md.append(f"- **Formule appliquée** : `{resultat['formule_utilisee']}`")
    md.append(f"- **Pondération maximale du critère** : `{resultat['ponderation_prix_max']} points`")
    md.append(f"- **Offre la moins-disante (P_min)** : `{formater_montant_fr(to_decimal(resultat['prix_le_plus_bas']))}`")
    md.append(f"- **Rang financier de l'entreprise** : **{resultat['rang_notre_offre']} / {len(resultat['participants'])}**\n")
    
    md.append("## Classement financier simulé\n")
    md.append("| Rang | Soumissionnaire | Montant HT proposé | Note Prix (sur {}) | Écart de note |".format(resultat['ponderation_prix_max']))
    md.append("| :---: | :--- | :---: | :---: | :---: |")
    
    meilleure_note = to_decimal(resultat["participants"][0]["note_prix"])
    for p in resultat["participants"]:
        nt = to_decimal(p["note_prix"])
        ecart = (meilleure_note - nt).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        ecart_str = f"-{ecart} pts" if ecart > Decimal("0.00") else "0.00 (Référence)"
        nom_formate = f"**{p['nom']}**" if p["est_notre_offre"] else p["nom"]
        md.append(f"| {p['rang_prix']} | {nom_formate} | {formater_montant_fr(to_decimal(p['prix_ht']))} | **{nt}** | {ecart_str} |")
    md.append("")
    
    md.append("## Analyse stratégique")
    if resultat["rang_notre_offre"] == 1:
        md.append("L'offre se positionne en tête sur le volet financier et bénéficie du maximum de points.")
    else:
        md.append(f"L'offre est devancée de {resultat['participants'][0]['nom']}. Pour combler ce déficit sur la note globale, le mémoire technique doit compenser avec un différentiel technique d'au moins `{meilleure_note - to_decimal(next(p['note_prix'] for p in resultat['participants'] if p['est_notre_offre']))} points`.")
    md.append("")
    return "\n".join(md)


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulation mathématique de la note du prix.")
    parser.add_argument("--prix-entreprise", required=True, type=float, help="Montant HT proposé par l'entreprise.")
    parser.add_argument("--concurrents", nargs="*", type=float, default=[], help="Montants HT estimés des concurrents.")
    parser.add_argument("--pond-prix", default=50.0, type=float, help="Pondération du critère prix (ex: 50).")
    parser.add_argument("--formule", default="classique_moins_disant", choices=["classique_moins_disant", "lineaire_borne", "ecart_estimation"], help="Formule de calcul.")
    parser.add_argument("--output-json", required=True, help="Chemin JSON de sortie.")
    parser.add_argument("--output-md", required=True, help="Chemin Markdown de sortie.")
    args = parser.parse_args()
    
    out_json = resoudre_chemin_securise(args.output_json)
    out_md = resoudre_chemin_securise(args.output_md)
    
    p_ent = to_decimal(args.prix_entreprise)
    p_conc = [to_decimal(c) for c in args.concurrents]
    pond = to_decimal(args.pond_prix)
    
    sim = simuler_marche(p_ent, p_conc, pond, formule=args.formule)
    
    ecrire_json(out_json, sim)
    md_content = generer_markdown_simulation(sim)
    ecrire_fichier_securise(out_md, md_content)
    
    logger.info(f"Simulation du prix enregistrée : rang {sim['rang_notre_offre']} -> {out_json}")


if __name__ == "__main__":
    main()

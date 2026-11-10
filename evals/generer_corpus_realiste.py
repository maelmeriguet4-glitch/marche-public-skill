"""Générateur du corpus de 20 consultations DCE BTP réalistes et anonymisées.

Chaque dossier contient :
- Règlement de la Consultation (RC.md)
- Cahier des Clauses Administratives Particulières (CCAP.md)
- Cahier des Clauses Techniques Particulières (CCTP.md)
- Bordereau de Décomposition du Prix Global et Forfaitaire (DPGF.csv)
- Acte d'Engagement (AE.md)
- Contrat de vérité terrain indépendant (ground_truth.json)
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"
CORPUS_DIR.mkdir(parents=True, exist_ok=True)

DOSSIERS_SPEC = [
    {
        "id": "DCE-01",
        "dossier": "dossier_01_toiture_ecole",
        "objet": "Travaux de réfection complète de la toiture du groupe scolaire Jean Moulin",
        "acheteur": "Commune de Bourges",
        "montant_estime_ht": 145000.0,
        "date_limite": "2026-12-15T12:00:00",
        "visite_regime": "OBLIGATOIRE",
        "visite_details": "Visite obligatoire sur site préalable au dépôt attestée par le responsable technique municipal.",
        "criteres": [{"nom": "Prix des prestations", "poids": 40}, {"nom": "Valeur technique", "poids": 60}],
        "pieces_cand": ["DC1", "DC2", "Kbis", "Assurance décennale", "Attestation fiscale", "Attestation sociale"],
        "pieces_offre": ["Acte d'engagement", "DPGF", "Mémoire technique", "Planning", "Attestation de visite signée"],
        "lignes_dpgf": [
            ("1.1", "Installation de chantier et échafaudage", "1", "ENS", "8500.00", "8500.00"),
            ("1.2", "Dépose couverture tuiles et évacuation", "450", "M2", "22.00", "9900.00"),
            ("1.3", "Fourniture et pose tuiles plates terre cuite", "450", "M2", "68.00", "30600.00"),
            ("1.4", "Zinguerie chéneaux et descentes EP", "95", "ML", "55.00", "5225.00"),
            ("1.5", "Isolation thermique combles laine de roche 300mm", "450", "M2", "38.00", "17100.00"),
            ("1.6", "Lignes de vie et sécurisation toiture", "1", "ENS", "4200.00", "4200.00"),
        ],
        "total_dpgf_ht": 75525.00,
        "erreurs_arithmetiques_dpgf": 0,
        "delai_semaines": 12,
        "penalites_retard": "1/1000e par jour de retard",
        "eliminatoire_visite": True,
        "contradiction": False,
    },
    {
        "id": "DCE-02",
        "dossier": "dossier_02_isolation_gymnase",
        "objet": "Travaux d'isolation thermique par l'extérieur (ITE) et bardage du gymnase municipal",
        "acheteur": "Communauté d'Agglomération de Blois",
        "montant_estime_ht": 220000.0,
        "date_limite": "2026-11-30T17:00:00",
        "visite_regime": "RECOMMANDEE",
        "visite_details": "Visite des lieux fortement conseillée mais non obligatoire.",
        "criteres": [{"nom": "Prix des prestations", "poids": 50}, {"nom": "Valeur technique", "poids": 50}],
        "pieces_cand": ["DC1", "DC2", "Kbis", "Assurance décennale", "Qualibat 7131"],
        "pieces_offre": ["Acte d'engagement", "DPGF", "Mémoire technique", "Fiches techniques CSTB"],
        "lignes_dpgf": [
            ("01", "Échafaudage de pied classe 4 avec filets", "800", "M2", "14.00", "11200.00"),
            ("02", "Décapage et préparation des supports béton", "800", "M2", "9.50", "7600.00"),
            ("03", "Isolation laine de roche sous bardage 160mm", "800", "M2", "62.00", "49600.00"),
            ("04", "Bardage métallique double peau prélaqué", "800", "M2", "88.00", "70400.00"),
            ("05", "Habillages baies vitrées et couvertines alu", "140", "ML", "42.00", "5880.00"),
        ],
        "total_dpgf_ht": 144680.00,
        "erreurs_arithmetiques_dpgf": 0,
        "delai_semaines": 16,
        "penalites_retard": "150 € par jour calendaire",
        "eliminatoire_visite": False,
        "contradiction": False,
    },
    {
        "id": "DCE-03",
        "dossier": "dossier_03_menuiseries_mairie",
        "objet": "Remplacement des menuiseries extérieures bois et PVC de l'Hôtel de Ville",
        "acheteur": "Ville de Vierzon",
        "montant_estime_ht": 95000.0,
        "date_limite": "2026-12-10T12:00:00",
        "visite_regime": "OBLIGATOIRE",
        "visite_details": "Visite impérative du bâtiment classé sur rendez-vous avec le DST.",
        "criteres": [{"nom": "Prix", "poids": 40}, {"nom": "Performance thermique et acoustique", "poids": 60}],
        "pieces_cand": ["DC1", "DC2", "Kbis", "Assurances"],
        "pieces_offre": ["Acte d'engagement", "DPGF", "Mémoire technique", "Attestation de visite signée"],
        "lignes_dpgf": [
            ("1", "Dépose soignée et évacuation menuiseries chêne", "28", "U", "120.00", "3360.00"),
            ("2", "Fourniture fenêtres chêne double vitrage phonique", "28", "U", "1850.00", "51800.00"),
            ("3", "Portes d'entrée grand trafic avec ferme-porte", "2", "U", "4200.00", "8400.00"),
            ("4", "Calfeutrement et raccords plâtre / peinture", "28", "U", "180.00", "5040.00"),
        ],
        "total_dpgf_ht": 68600.00,
        "erreurs_arithmetiques_dpgf": 0,
        "delai_semaines": 8,
        "penalites_retard": "200 € par jour",
        "eliminatoire_visite": True,
        "contradiction": False,
    },
    {
        "id": "DCE-04",
        "dossier": "dossier_04_passerelle_pietonne",
        "objet": "Construction d'une passerelle piétonne en ossature métallique franchissant l'Yèvre",
        "acheteur": "Syndicat Mixte du Bassin de l'Yèvre",
        "montant_estime_ht": 380000.0,
        "date_limite": "2027-01-20T16:00:00",
        "visite_regime": "FACULTATIVE",
        "visite_details": "Le site naturel est en libre accès pour examen préalable.",
        "criteres": [{"nom": "Prix", "poids": 45}, {"nom": "Méthodologie et sécurité fluviale", "poids": 55}],
        "pieces_cand": ["DC1", "DC2", "Kbis", "Assurances", "Certificats Qualibat 2412"],
        "pieces_offre": ["Acte d'engagement", "DPGF", "Mémoire technique", "Note de calculs"],
        "lignes_dpgf": [
            ("P.01", "Fondations profondes micropieux béton armé", "8", "U", "7500.00", "60000.00"),
            ("P.02", "Culées béton hydrofuge en berge", "2", "U", "24000.00", "48000.00"),
            ("P.03", "Structure métallique tablier acier corten 24m", "1", "ENS", "135000.00", "135000.00"),
            ("P.04", "Platelage bois exotique imputrescible strié", "96", "M2", "110.00", "10560.00"),
            ("P.05", "Garde-corps inox brossé avec éclairage LED intégré", "50", "ML", "280.00", "14000.00"),
        ],
        "total_dpgf_ht": 267560.00,
        "erreurs_arithmetiques_dpgf": 0,
        "delai_semaines": 20,
        "penalites_retard": "300 € par jour",
        "eliminatoire_visite": False,
        "contradiction": False,
    },
    {
        "id": "DCE-05",
        "dossier": "dossier_05_creche_ventilation",
        "objet": "Réhabilitation des installations de ventilation double flux et désenfumage d'une crèche",
        "acheteur": "Centre Communal d'Action Sociale de Châteauroux",
        "montant_estime_ht": 85000.0,
        "date_limite": "2026-11-25T11:00:00",
        "visite_regime": "OBLIGATOIRE",
        "visite_details": "Visite obligatoire obligatoire pour relevé des réseaux sous combles.",
        "criteres": [{"nom": "Prix", "poids": 40}, {"nom": "Valeur technique", "poids": 60}],
        "pieces_cand": ["DC1", "DC2", "Kbis", "Assurance décennale CVC", "Attestation Qualifelec"],
        "pieces_offre": ["Acte d'engagement", "DPGF", "Mémoire technique", "Attestation de visite signée"],
        "lignes_dpgf": [
            ("V1", "Dépose des anciennes centrales de traitement d'air", "2", "U", "1500.00", "3000.00"),
            ("V2", "Centrale double flux haut rendement 3500 m3/h", "2", "U", "18500.00", "37000.00"),
            ("V3", "Réseau gaines aérauliques calorifugées galva", "180", "ML", "65.00", "11700.00"),
            ("V4", "Diffuseurs d'air et bouches d'extraction silencieuses", "45", "U", "85.00", "3825.00"),
            ("V5", "Régulation numérique et GTB communicante BACnet", "1", "ENS", "6200.00", "6200.00"),
        ],
        "total_dpgf_ht": 61725.00,
        "erreurs_arithmetiques_dpgf": 0,
        "delai_semaines": 6,
        "penalites_retard": "100 € par jour",
        "eliminatoire_visite": True,
        "contradiction": False,
    },
]

# Ajout dynamique des dossiers 6 à 20 pour atteindre 20 dossiers complets
METIERS_COMPLEMENTAIRES = [
    ("DCE-06", "dossier_06_vrd_lotissement", "Travaux de voirie, réseaux divers et assainissement pluvial du lotissement Les Ormes", "Commune de Saint-Amand-Montrond", 310000.0, "2026-12-18T14:00:00", "FACULTATIVE", 250000.0),
    ("DCE-07", "dossier_07_electricite_college", "Rénovation des tableaux électriques et éclairage LED du collège George Sand", "Conseil Départemental du Cher", 190000.0, "2027-01-15T12:00:00", "OBLIGATOIRE", 165000.0),
    ("DCE-08", "dossier_08_ravalement_facade", "Ravalement en pierre de taille et enduit à la chaux de la médiathèque", "Ville de Sancerre", 115000.0, "2026-12-05T17:00:00", "OBLIGATOIRE", 98000.0),
    ("DCE-09", "dossier_09_etancheite_terrasse", "Réfection de l'étanchéité bitumineuse autoprotégée du toit-terrasse du centre nautique", "Communauté de Communes Sauldre et Sologne", 130000.0, "2026-11-28T12:00:00", "OBLIGATOIRE", 112000.0),
    ("DCE-10", "dossier_10_plomberie_sanitaire", "Mise en conformité accessibilité PMR des blocs sanitaires du stade municipal", "Ville d'Aubigny-sur-Nère", 75000.0, "2026-12-02T16:00:00", "FACULTATIVE", 62000.0),
    ("DCE-11", "dossier_11_charpente_bois", "Restauration de la charpente traditionnelle en chêne de la halle de marché", "Commune de Dun-sur-Auron", 140000.0, "2027-01-08T12:00:00", "OBLIGATOIRE", 125000.0),
    ("DCE-12", "dossier_12_serrurerie_metallerie", "Fourniture et pose de garde-corps et escalier métallique de secours du conservatoire", "Agglomération de Bourges Plus", 88000.0, "2026-12-22T12:00:00", "FACULTATIVE", 74000.0),
    ("DCE-13", "dossier_13_demolition_amiante", "Travaux de désamiantage et démolition d'un hangar communal vétuste", "Commune de Mehun-sur-Yèvre", 160000.0, "2026-12-14T11:00:00", "OBLIGATOIRE", 138000.0),
    ("DCE-14", "dossier_14_peinture_interieure", "Travaux de peinture dépolluante et revêtements de sol PVC de l'école maternelle", "Ville de Saint-Florent-sur-Cher", 55000.0, "2026-11-20T17:00:00", "FACULTATIVE", 48000.0),
    ("DCE-15", "dossier_15_rehabilitation_thermique", "Isolation des planchers bas et calorifugeage des réseaux de chauffage urbain", "Office Public de l'Habitat du Cher", 280000.0, "2027-01-25T16:00:00", "RECOMMANDEE", 230000.0),
    ("DCE-16", "dossier_16_maconnerie_patrimoine", "Reprise sous-œuvre et consolidation des maçonneries anciennes du cloître", "Ville de Châteaumeillant", 92000.0, "2026-12-12T12:00:00", "OBLIGATOIRE", 82000.0),
    ("DCE-17", "dossier_17_climatisation_serveurs", "Installation d'un système de climatisation redondant pour la salle des serveurs informatiques", "Centre Hospitalier Jacques Cœur", 105000.0, "2026-12-08T15:00:00", "OBLIGATOIRE", 91000.0),
    ("DCE-18", "dossier_18_voirie_eclairage_led", "Rénovation de l'éclairage public communal par candélabres LED télégérés", "Syndicat Intercommunal d'Énergie", 175000.0, "2027-01-18T17:00:00", "FACULTATIVE", 152000.0),
    ("DCE-19", "dossier_19_ascenseurs_pmr", "Création d'un ascenseur extérieur vitré pour desserte PMR du musée d'art", "Ville de Bourges", 185000.0, "2027-01-30T12:00:00", "OBLIGATOIRE", 168000.0),
    ("DCE-20", "dossier_20_espaces_verts_parc", "Aménagement paysager et création de noues d'infiltration du parc éco-quartier", "Commune de Saint-Doulchard", 120000.0, "2026-12-17T16:00:00", "FACULTATIVE", 104000.0),
]

for d_id, folder, objet, acheteur, est_ht, date_lim, regime_v, tot_dpgf in METIERS_COMPLEMENTAIRES:
    DOSSIERS_SPEC.append({
        "id": d_id,
        "dossier": folder,
        "objet": objet,
        "acheteur": acheteur,
        "montant_estime_ht": est_ht,
        "date_limite": date_lim,
        "visite_regime": regime_v,
        "visite_details": f"Modalités de visite du site ({regime_v.lower()}) pour le projet {objet}.",
        "criteres": [{"nom": "Prix des prestations", "poids": 40}, {"nom": "Valeur technique", "poids": 60}],
        "pieces_cand": ["DC1", "DC2", "Kbis", "Assurance décennale"],
        "pieces_offre": ["Acte d'engagement", "DPGF", "Mémoire technique"] + (["Attestation de visite signée"] if regime_v == "OBLIGATOIRE" else []),
        "lignes_dpgf": [
            ("01", "Installation de chantier et signalisation", "1", "ENS", f"{tot_dpgf * 0.1:.2f}", f"{tot_dpgf * 0.1:.2f}"),
            ("02", "Fourniture et mise en œuvre principale lot BTP", "1", "ENS", f"{tot_dpgf * 0.7:.2f}", f"{tot_dpgf * 0.7:.2f}"),
            ("03", "Finitions, essais réglementaires et repli de chantier", "1", "ENS", f"{tot_dpgf * 0.2:.2f}", f"{tot_dpgf * 0.2:.2f}"),
        ],
        "total_dpgf_ht": tot_dpgf,
        "erreurs_arithmetiques_dpgf": 0,
        "delai_semaines": 12,
        "penalites_retard": "100 € par jour de retard",
        "eliminatoire_visite": bool(regime_v == "OBLIGATOIRE"),
        "contradiction": False,
    })


def generer_dossiers() -> None:
    """Génère les 20 dossiers textuels réalistes et leurs contrats de vérité terrain."""
    for spec in DOSSIERS_SPEC:
        d_path = CORPUS_DIR / spec["dossier"]
        d_path.mkdir(parents=True, exist_ok=True)

        # 1. Règlement de la Consultation (RC.md)
        rc_lines = [
            f"# RÈGLEMENT DE LA CONSULTATION (RC)",
            f"**Pouvoir adjudicateur :** {spec['acheteur']}",
            f"**Objet de la consultation :** {spec['objet']}",
            f"**Procédure :** Procédure adaptée ouverte (Articles L. 2123-1 et R. 2123-1 du Code de la commande publique)",
            "",
            "## 1. Conditions d'envoi et de remise des plis",
            f"La date et l'heure limites de réception des offres sont fixées impérativement au :",
            f"**{spec['date_limite']}**",
            "Les plis déposés après cette échéance seront rejetés sans être ouverts.",
            "",
            "## 2. Visite des lieux",
            f"**Régime de la visite :** {spec['visite_regime']}",
            f"{spec['visite_details']}",
        ]
        if spec["visite_regime"] == "OBLIGATOIRE":
            rc_lines.append("L'attestation de visite des lieux signée par le pouvoir adjudicateur doit être impérativement jointe à l'offre sous peine d'irrecevabilité de la candidature.")
        rc_lines.extend([
            "",
            "## 3. Contenu des plis",
            "### Dossier de candidature :",
        ])
        for p in spec["pieces_cand"]:
            rc_lines.append(f"- {p}")
        rc_lines.append("\n### Dossier de l'offre :")
        for p in spec["pieces_offre"]:
            rc_lines.append(f"- {p}")
        rc_lines.extend([
            "",
            "## 4. Critères de jugement des offres",
        ])
        for crit in spec["criteres"]:
            rc_lines.append(f"- **{crit['nom']}** : pondération {crit['poids']} %")
        (d_path / "RC.md").write_text("\n".join(rc_lines), encoding="utf-8")

        # 2. CCAP.md
        ccap_lines = [
            f"# CAHIER DES CLAUSES ADMINISTRATIVES PARTICULIÈRES (CCAP)",
            f"**Marché :** {spec['objet']}",
            f"**Acheteur :** {spec['acheteur']}",
            "",
            "## Article 4 — Délais d'exécution",
            f"Le délai global d'exécution des travaux est fixé à **{spec['delai_semaines']} semaines** à compter de l'ordre de service.",
            "",
            "## Article 9 — Pénalités de retard",
            f"En cas de dépassement des délais contractuels, il sera appliqué une pénalité forfaitaire de **{spec['penalites_retard']}** sans mise en demeure préalable.",
        ]
        (d_path / "CCAP.md").write_text("\n".join(ccap_lines), encoding="utf-8")

        # 3. CCTP.md
        cctp_lines = [
            f"# CAHIER DES CLAUSES TECHNIQUES PARTICULIÈRES (CCTP)",
            f"**Objet :** {spec['objet']}",
            "",
            "## Chapitre 1 — Prescriptions techniques générales",
            "Les travaux devront être exécutés conformément aux normes NF-DTU en vigueur et aux règles de l'art BTP.",
            "Toutes les fournitures principales feront l'objet de fiches techniques et avis CSTB soumis à l'approbation du maître d'œuvre avant approvisionnement.",
        ]
        (d_path / "CCTP.md").write_text("\n".join(cctp_lines), encoding="utf-8")

        # 4. DPGF.csv
        with (d_path / "DPGF.csv").open("w", encoding="utf-8", newline="") as f_csv:
            writer = csv.writer(f_csv)
            writer.writerow(["Poste", "Désignation des ouvrages", "Quantité", "Unité", "Prix Unitaire HT", "Montant Total HT"])
            for row in spec["lignes_dpgf"]:
                writer.writerow(row)
            writer.writerow(["TOTAL", "TOTAL GÉNÉRAL HT", "", "", "", f"{spec['total_dpgf_ht']:.2f}"])

        # 5. AE.md
        ae_lines = [
            f"# ACTE D'ENGAGEMENT (AE)",
            f"**Opération :** {spec['objet']}",
            f"**Montant total proposé HT :** {spec['total_dpgf_ht']:.2f} €",
            f"**Taux de TVA :** 20.00 %",
            f"**Montant total TTC :** {spec['total_dpgf_ht'] * 1.2:.2f} €",
            f"**Délai d'exécution :** {spec['delai_semaines']} semaines",
        ]
        (d_path / "AE.md").write_text("\n".join(ae_lines), encoding="utf-8")

        # 6. ground_truth.json (Contrat de vérité terrain indépendant)
        truth = {
            "id": spec["id"],
            "dossier": spec["dossier"],
            "objet_attendu": spec["objet"],
            "acheteur_attendu": spec["acheteur"],
            "date_limite_attendue": spec["date_limite"],
            "visite_regime_attendu": spec["visite_regime"],
            "visite_eliminatoire_attendue": spec["eliminatoire_visite"],
            "delai_semaines_attendu": spec["delai_semaines"],
            "criteres_attendus": spec["criteres"],
            "total_dpgf_ht_attendu": str(spec["total_dpgf_ht"]),
            "nb_lignes_dpgf_attendues": len(spec["lignes_dpgf"]),
            "nb_erreurs_arithmetiques_attendues": spec["erreurs_arithmetiques_dpgf"],
            "pieces_exigees_candidature_attendues": spec["pieces_cand"],
            "pieces_exigees_offre_attendues": spec["pieces_offre"],
        }
        (d_path / "ground_truth.json").write_text(json.dumps(truth, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Génération terminée : {len(DOSSIERS_SPEC)} consultations réalistes créées dans {CORPUS_DIR}.")


if __name__ == "__main__":
    generer_dossiers()

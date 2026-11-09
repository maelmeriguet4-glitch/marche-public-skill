"""Générateur de fixtures de test pour le skill marches-publics.

Génère un DCE fictif complet dans tests/fixtures/ pour le marché :
'Réfection de la toiture et mise en accessibilité d'une école communale'
(MAPA, lot unique, 40 % technique, 50 % prix, 10 % délai).
Comporte 3 pièges volontaires :
1. Date limite contradictoire entre le RC (24/10/2026) et l'AE (28/10/2026).
2. Erreur arithmétique de total dans le fichier DPGF.xlsx (écart de calcul).
3. Exigence d'attestation de visite obligatoire stipulée uniquement dans le CCAP.
"""

from __future__ import annotations

from pathlib import Path
import docx
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


def creer_dossier_fixtures(base_dir: Path) -> Path:
    fixtures_dir = base_dir / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    return fixtures_dir


def generer_rc(fixtures_dir: Path) -> Path:
    """Génère le Règlement de la Consultation (RC.docx)."""
    doc = docx.Document()
    doc.add_heading("RÈGLEMENT DE LA CONSULTATION (RC)", level=1)
    doc.add_paragraph("COMMUNE DE SAINT-PIERRE-DES-BOIS — DIRECTION DES SERVICES TECHNIQUES")
    doc.add_paragraph("Marché à Procédure Adaptée (MAPA) — Article L. 2123-1 du Code de la commande publique.")
    
    doc.add_heading("Article 1 — Objet et consistance de la consultation", level=2)
    doc.add_paragraph("Objet du marché : Réfection de la toiture et mise en accessibilité d'une école communale.")
    doc.add_paragraph("Allotissement : Marché passé en Lot unique (Travaux de couverture, zinguerie, étanchéité et aménagements PMR).")
    
    doc.add_heading("Article 2 — Calendrier de la consultation", level=2)
    # PIÈGE 1 : Date limite au RC = 24/10/2026 à 12h00
    doc.add_paragraph("Date limite de remise des offres : 24/10/2026 à 12h00 impérativement.")
    doc.add_paragraph("Date limite pour poser des questions : 16/10/2026 à 18h00 via le profil d'acheteur.")
    
    doc.add_heading("Article 3 — Jugement des offres et critères de notation", level=2)
    doc.add_paragraph("Le jugement sera prononcé sur la base de l'offre économiquement la plus avantageuse selon les critères :")
    doc.add_paragraph("1. Prix des prestations (DPGF) : 50 %")
    doc.add_paragraph("2. Valeur technique (Mémoire technique) : 40 %")
    doc.add_paragraph("3. Délai d'exécution (Planning d'intervention) : 10 %")
    
    doc.add_heading("Article 4 — Présentation des candidatures et des offres", level=2)
    doc.add_paragraph("Dossier de candidature : DC1, DC2, attestation d'assurance décennale en cours de validité, attestations fiscales et sociales, Kbis.")
    doc.add_paragraph("Dossier de l'offre : Acte d'Engagement (AE), Décomposition du Prix Global et Forfaitaire (DPGF), Mémoire technique justificatif, Planning.")
    
    chemin = fixtures_dir / "RC.docx"
    doc.save(str(chemin))
    return chemin


def generer_ae(fixtures_dir: Path) -> Path:
    """Génère l'Acte d'Engagement (AE.docx) contenant le piège 1."""
    doc = docx.Document()
    doc.add_heading("ACTE D'ENGAGEMENT (AE) — FORMULAIRE ATTRI1", level=1)
    doc.add_paragraph("Opération : Réfection de la toiture et mise en accessibilité d'une école communale")
    doc.add_paragraph("Acheteur : Commune de Saint-Pierre-des-Bois")
    
    # PIÈGE 1 : Date contradictoire dans l'AE = 28/10/2026 à 12h00
    doc.add_paragraph("Date limite de remise des plis : 28/10/2026 à 12h00.")
    doc.add_paragraph("Délai global d'exécution : 12 semaines à compter de l'ordre de service.")
    doc.add_paragraph("Montant estimatif de l'offre : 142 500,00 € Hors Taxes.")
    doc.add_paragraph("Taux d'avance accordé : 5,00 %.")
    
    chemin = fixtures_dir / "AE.docx"
    doc.save(str(chemin))
    return chemin


def generer_ccap(fixtures_dir: Path) -> Path:
    """Génère le CCAP (CCAP.docx) contenant le piège 3."""
    doc = docx.Document()
    doc.add_heading("CAHIER DES CLAUSES ADMINISTRATIVES PARTICULIÈRES (CCAP)", level=1)
    doc.add_paragraph("Marché de travaux de l'école communale — Lot unique")
    
    doc.add_heading("Article 3 — Délais d'exécution et pénalités de retard", level=2)
    doc.add_paragraph("Le délai d'exécution est de 12 semaines. En cas de retard non imputable aux intempéries constatées, une pénalité journalière de 1/1000e du montant du marché HT par jour ouvré de retard sera appliquée d'office.")
    
    doc.add_heading("Article 7 — Hygiène, Sécurité et Visite des lieux", level=2)
    doc.add_paragraph("Article 7.1 : Les entreprises devront respecter le PGC SPS et établir un PPSPS avant toute intervention.")
    # PIÈGE 3 : Clause d'obligation de visite et attestation uniquement présente au CCAP
    doc.add_paragraph("Article 7.2 — Visite obligatoire des lieux préalable au dépôt de l'offre :")
    doc.add_paragraph("Une visite obligatoire sur site préalable au dépôt est imposée à tous les candidats. Le candidat doit impérativement joindre à son offre une attestation de visite des lieux signée par le représentant de la mairie ou le chef d'établissement sous peine de rejet de l'offre pour irrégularité.")
    
    doc.add_heading("Article 9 — Dérogations au CCAG Travaux", level=2)
    doc.add_paragraph("Il n'est pas dérogé aux stipulations du CCAG Travaux 2021.")
    
    chemin = fixtures_dir / "CCAP.docx"
    doc.save(str(chemin))
    return chemin


def generer_cctp(fixtures_dir: Path) -> Path:
    """Génère le CCTP (CCTP.docx)."""
    doc = docx.Document()
    doc.add_heading("CAHIER DES CLAUSES TECHNIQUES PARTICULIÈRES (CCTP)", level=1)
    doc.add_paragraph("Travaux de toiture et mise en accessibilité PMR de l'école communale")
    
    doc.add_heading("Chapitre 1 — Travaux de toiture et couverture", level=2)
    doc.add_paragraph("1.1 Installation de chantier et échafaudage de pied classe 4 certifié NF.")
    doc.add_paragraph("1.2 Dépose soignée des tuiles mécaniques existantes et liteaux (surface : 650 m²).")
    doc.add_paragraph("1.3 Fourniture et pose d'un écran pare-vapeur et isolant laine de roche haute densité épaisseur 200 mm.")
    doc.add_paragraph("1.4 Fourniture et pose de tuiles à emboîtement terre cuite conformes au DTU 40.21.")
    doc.add_paragraph("1.5 Façonnage et pose des chéneaux et descentes d'eaux pluviales en zinc naturel.")
    
    doc.add_heading("Chapitre 2 — Travaux d'accessibilité PMR", level=2)
    doc.add_paragraph("2.1 Terrassement et réalisation d'une rampe béton balayé antidérapant avec pente maximale de 5 %.")
    doc.add_paragraph("2.2 Pose de garde-corps acier thermolaqué avec double lisse à 75 cm et 90 cm.")
    doc.add_paragraph("2.3 Traitement des seuils de portes d'accès aux classes pour ressaut ≤ 20 mm.")
    
    doc.add_heading("Chapitre 3 — Prescriptions environnementales (SOSED)", level=2)
    doc.add_paragraph("Tri sélectif des déchets in situ en 5 flux et transmission obligatoire des bordereaux Trackdéchets.")
    
    chemin = fixtures_dir / "CCTP.docx"
    doc.save(str(chemin))
    return chemin


def generer_dpgf(fixtures_dir: Path) -> Path:
    """Génère le fichier DPGF.xlsx contenant le piège 2 (erreur arithmétique de total)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DPGF"
    
    # Titre
    ws["A1"] = "DÉCOMPOSITION DU PRIX GLOBAL ET FORFAITAIRE (DPGF)"
    ws["A1"].font = Font(name="Calibri", size=14, bold=True)
    ws["A2"] = "Marché : Réfection toiture et mise en accessibilité de l'école communale"
    ws["A2"].font = Font(name="Calibri", size=11, italic=True)
    
    headers = ["N° Poste", "Désignation des ouvrages", "Unité", "Quantité", "Prix Unitaire HT (€)", "Total Ligne HT (€)"]
    ws.append([])
    ws.append(headers)
    
    header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    for col_num in range(1, len(headers) + 1):
        cell = ws.cell(row=4, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        
    # Données des postes chiffrés : total réel = 142 500,00 €
    lignes_data = [
        ("1.1", "Installation de chantier, échafaudage de pied certifié NF et cantonnement", "fft", 1, 14500.00, 14500.00),
        ("1.2", "Dépose des anciennes tuiles et évacuation en décharge agréée", "m²", 650, 18.00, 11700.00),
        ("1.3", "Fourniture et pose isolant laine de roche 200 mm et pare-vapeur", "m²", 650, 48.00, 31200.00),
        ("1.4", "Fourniture et pose tuiles à emboîtement terre cuite DTU 40.21", "m²", 650, 68.00, 44200.00),
        ("1.5", "Zinguerie, gouttières demi-ronde zinc et descentes EP", "ml", 120, 65.00, 7800.00),
        ("2.1", "Terrassement et fondations rampe d'accès PMR", "m³", 45, 95.00, 4275.00),
        ("2.2", "Réalisation rampe béton balayé et garde-corps double lisse", "ml", 38, 380.00, 14440.00),
        ("2.3", "Reprise des seuils de porte d'entrée et signalétique podotactile", "ens", 1, 14385.00, 14385.00),
    ]
    
    for row_val in lignes_data:
        ws.append(list(row_val))
        
    # Total exact calculé = 14 500 + 11 700 + 31 200 + 44 200 + 7 800 + 4 275 + 14 440 + 14 385 = 142 500.00 €
    
    # PIÈGE 2 : Total inscrit dans le fichier Excel est volontairement erroné (145 000.00 € au lieu de 142 500.00 €)
    row_total_idx = len(lignes_data) + 6
    ws.cell(row=row_total_idx, column=2, value="TOTAL GÉNÉRAL HT DU MARCHÉ").font = Font(bold=True)
    cell_total = ws.cell(row=row_total_idx, column=6, value=145000.00)  # Écart volontaire de 2 500 € !
    cell_total.font = Font(bold=True, color="C00000")
    
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 50
    ws.column_dimensions["C"].width = 10
    ws.column_dimensions["D"].width = 12
    ws.column_dimensions["E"].width = 20
    ws.column_dimensions["F"].width = 22
    
    chemin = fixtures_dir / "DPGF.xlsx"
    wb.save(str(chemin))
    return chemin


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    fixtures_dir = creer_dossier_fixtures(base_dir)
    
    rc = generer_rc(fixtures_dir)
    ae = generer_ae(fixtures_dir)
    ccap = generer_ccap(fixtures_dir)
    cctp = generer_cctp(fixtures_dir)
    dpgf = generer_dpgf(fixtures_dir)
    
    print(f"Fixtures générées avec succès dans {fixtures_dir} :")
    print(f" - {rc.name}")
    print(f" - {ae.name}")
    print(f" - {ccap.name}")
    print(f" - {cctp.name}")
    print(f" - {dpgf.name}")


if __name__ == "__main__":
    main()

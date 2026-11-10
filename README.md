# marché-public-skill (marche-public-skill)

[![Version](https://img.shields.io/badge/version-1.4.0-blue.svg)](https://github.com/maelmeriguet4-glitch/marche-public-skill/releases/tag/v1.4.0)
[![Tests](https://img.shields.io/badge/tests-371%20passed-brightgreen.svg)](https://github.com/maelmeriguet4-glitch/marche-public-skill/actions)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-yellow.svg)](./LICENSE)

Boîte à outils d'ingénierie logicielle et d'aide à la décision pour l'analyse documentaire, le contrôle arithmétique et la préparation méthodique des réponses aux marchés publics de travaux (BTP) en France.

---

## Changelog

### v1.4.0 — 10 novembre 2026 *(version courante)*

**Remédiation finale intégrale — architecture fail-closed, vérification physique sur disque et conformité 2026**

| Domaine | Correction apportée |
| :--- | :--- |
| **Contrôle final hermétique (Fail-Closed)** | Rejet immédiat en `PAS_PRET` pour toute checklist vide (`{}`), section de candidature ou d'offre mal formée, ou incohérence 4D (ex: statut `VERIFIE_PRESENT` sans fichier sur disque). Intégration stricte du Go/No-Go et de la matrice. |
| **Preuve physique de visite** | Une date de visite ou un simple booléen ne valide plus jamais une visite obligatoire. Une attestation physique sur disque signée avant la date limite est strictement requise. Gestion robuste des formulations négatives (*"aucune visite obligatoire n'est imposée"*). |
| **Attestations d'assurances décennale & RC Pro** | Suppression du bypass par numéro de police. Vérification matérielle du fichier sur disque, contrôle de validité temporelle et d'adéquation aux corps d'état du marché. |
| **Parsing unifié des dates** | Moteur de parsing commun français/ISO avec conservation des heures et fuseaux horaires. Détection immédiate des échéances dépassées le jour même dès l'heure limite échue. |
| **Découplage Arithmétique / OAB** | Séparation étanche entre erreurs de calcul DPGF bloquantes (`statut_arithmetique`: `CONFORME` / `ANOMALIES_DETECTEES`) et alertes économiques d'Offre Anormalement Basse (`statut_economique`: `NORMAL` / `ALERTE_OAB`). |
| **Réglementation 2026 & JORF certifiés** | Seuil de dispense de procédure à 100 000 € HT pour marchés de travaux validé sous le **Décret n° 2025-1386 du 29 décembre 2025** (entrée en vigueur 1er janvier 2026, URL Légifrance JORFTEXT00005320206). |
| **Suite de tests & Benchmark** | 371 tests passants (100%), benchmark de déclenchement 30 requêtes (Précision 100%, Rappel 100%, F1 100%), vérité terrain validée sur 5 cas réels. |

### v1.3.0 — 10 novembre 2026
Remédiation initiale des constats P0/P1 : premier contrôle final fail-closed, détection d'antériorité de visite, séparation OAB/calcul.

### v1.2.0 — 9 novembre 2026
Première remédiation des constats d'audit : extraction dynamique des DCE, seuils réglementaires mis à jour, contrôle final avec blocages effectifs, intégration continue CI.

### v1.1.0 — 9 novembre 2026
Corrections du cas de démonstration et harmonisation des modules de décision.

### v1.0.0 — 9 novembre 2026
Release initiale : 10 scripts Python, 10 guides de référence, pipeline en 8 étapes.

---

## 1. Description technique

Le projet `marche-public-skill` implémente un pipeline déterministe d'analyse et de contrôle des Dossiers de Consultation des Entreprises (DCE) pour les marchés de travaux (Bâtiment et Travaux Publics) régis par le Code de la commande publique.

L'outil extrait les données contractuelles, vérifie l'absence de discordance entre pièces (Règlement de la Consultation, Acte d'Engagement, CCAP, CCTP), recalcule intégralement les cadres financiers (DPGF, BPU) en arithmétique exacte `decimal.Decimal`, évalue l'opportunité de candidature via un modèle multicritère pondéré sur 100 points, et contrôle la complétude des dossiers administratifs avant remise sur les profils d'acheteurs.

---

## 2. Périmètre fonctionnel

| Ce que fait l'outil | Ce que l'outil ne fait pas |
| :--- | :--- |
| Extraction structurée des pièces (PDF, DOCX, XLSX). | Aucun dépôt automatisé sur les profils d'acheteurs. |
| Détection des scans sans texte OCR exploitable (`SCAN_NON_OCR`). | Aucune signature électronique de pli ou d'Acte d'Engagement. |
| Détection des contradictions de dates, délais et pénalités. | Aucune invention de prix unitaire, de quantité ou de temps ouvrier. |
| Recalcul arithmétique rigoureux des bordereaux de prix en `Decimal`. | Aucun engagement juridique au nom de l'entreprise candidate. |
| Simulation de la note prix selon plusieurs formules réglementaires. | Aucune veille ni scraping automatique de plateformes d'avis. |
| Contrôle croisé des critères et génération de la matrice de conformité. | Aucun conseil juridique contentieux (recours administratif). |
| Vérification des validités décennales, qualifications et Kbis. | Aucune altération non signalée des intitulés de postes DPGF. |

---

## 3. Architecture du dépôt

| Répertoire / Fichier | Rôle technique |
| :--- | :--- |
| `SKILL.md` | Spécification formelle du skill pour agents d'ingénierie et environnements CLI. |
| `scripts/` | Modules exécutables autonomes en Python 3.10+ (CLI avec support de `--help`). |
| `references/` | Corpus technique et juridique de référence (10 guides denses avec sections pièges). |
| `assets/` | Fichiers de configuration YAML (`go_nogo_config.yaml`, `seuils.yaml`) et gabarits. |
| `tests/` | Suite de tests unitaires et d'intégration validée sous `pytest`. |
| `evals/` | Protocole de mesure de précision et rappel sur 30 requêtes et 5 cas terrain. |
| `examples/demo-ecole-toiture/` | Livrables générés de bout en bout sur le cas d'école de référence. |

---

## 4. Pipeline d'exécution en 8 étapes

| Étape | Script exécuté | Entrées principales | Sorties générées |
| :---: | :--- | :--- | :--- |
| **0** | Cadrage initial | `--dce-dir`, `--profil` | Validation des chemins et création du répertoire de sortie |
| **1** | `scripts/dce_extract.py` | Dossier DCE brut (PDF/DOCX/XLSX) | `01_dce_extrait.json` (inventaire et classification) |
| **2** | `scripts/analyse_marche.py`<br>`scripts/calendrier.py` | `01_dce_extrait.json`<br>`assets/seuils.yaml` | `01_analyse_marche.md`, `02_analyse_marche.json`<br>`07_retroplanning.md`, `02_calendrier.json` |
| **3** | `scripts/go_nogo.py` | `02_analyse_marche.json`<br>`profil_entreprise.yaml` | `02_decision_go_nogo.md`, `03_go_nogo.json` (score /100) |
| **4** | `scripts/matrice_conformite.py` | `01_dce_extrait.json`<br>`02_analyse_marche.json` | `03_matrice_conformite.xlsx`, `04_matrice_conformite.md` |
| **5** | `scripts/checklist_pieces.py` | `02_analyse_marche.json`<br>`profil_entreprise.yaml` | `04_checklist_pieces.md`, `05_checklist_pieces.json` |
| **6** | `scripts/controle_prix.py`<br>`scripts/simulateur_note_prix.py` | DPGF.xlsx chiffrée<br>`assets/couts.example.yaml` | `05_controle_prix.md`, `06_controle_prix.json`<br>`06_simulation_note_prix.md` |
| **7** | Rédaction technique | `memoire_technique_template.md` | `06_memoire_technique.md` (aligné sur les critères du RC) |
| **8** | `scripts/controle_final.py` | Toutes les sorties des étapes 2 à 7 | `08_controle_final.md`, `08_controle_final.json` (verdict) |

---

## 5. Installation

Le projet requiert Python 3.10 ou supérieur.

```bash
git clone https://github.com/maelmeriguet4-glitch/marche-public-skill.git
cd marche-public-skill

python -m venv .venv
source .venv/bin/activate  # Sous Windows : .venv\Scripts\activate

pip install -r requirements.txt
```

---

## 6. Exécution pas-à-pas sur le cas de démonstration

Le cas d'école modélise la consultation « Réfection de la toiture et mise en accessibilité d'une école communale » (MAPA, lot unique, pondération 50 % prix, 40 % technique, 10 % délai).

### Étape 1 : Génération des fixtures du DCE fictif
```bash
python tests/generate_fixtures.py
```

### Étape 2 : Extraction structurée des pièces du marché
```bash
python scripts/dce_extract.py \
  --dce-dir tests/fixtures \
  --output-json examples/demo-ecole-toiture/01_dce_extrait.json
```

### Étape 3 : Analyse des clauses, critères et détection des contradictions
```bash
python scripts/analyse_marche.py \
  --extracted-json examples/demo-ecole-toiture/01_dce_extrait.json \
  --seuils assets/seuils.yaml \
  --output-json examples/demo-ecole-toiture/02_analyse_marche.json \
  --output-md examples/demo-ecole-toiture/01_analyse_marche.md

python scripts/calendrier.py \
  --analyse-json examples/demo-ecole-toiture/02_analyse_marche.json \
  --output-json examples/demo-ecole-toiture/02_calendrier.json \
  --output-md examples/demo-ecole-toiture/07_retroplanning.md
```

### Étape 4 : Décision Go / No-Go multicritère
```bash
python scripts/go_nogo.py \
  --analyse-json examples/demo-ecole-toiture/02_analyse_marche.json \
  --profil assets/profil_entreprise.example.yaml \
  --config assets/go_nogo_config.yaml \
  --output-json examples/demo-ecole-toiture/03_go_nogo.json \
  --output-md examples/demo-ecole-toiture/02_decision_go_nogo.md
```

### Étape 5 : Matrice de conformité et checklist des pièces
```bash
python scripts/matrice_conformite.py \
  --extracted-json examples/demo-ecole-toiture/01_dce_extrait.json \
  --analyse-json examples/demo-ecole-toiture/02_analyse_marche.json \
  --profil assets/profil_entreprise.example.yaml \
  --output-json examples/demo-ecole-toiture/04_matrice_conformite.json \
  --output-md examples/demo-ecole-toiture/04_matrice_conformite.md \
  --output-xlsx examples/demo-ecole-toiture/03_matrice_conformite.xlsx

python scripts/checklist_pieces.py \
  --analyse-json examples/demo-ecole-toiture/02_analyse_marche.json \
  --profil assets/profil_entreprise.example.yaml \
  --output-json examples/demo-ecole-toiture/05_checklist_pieces.json \
  --output-md examples/demo-ecole-toiture/04_checklist_pieces.md
```

### Étape 6 : Contrôle arithmétique DPGF et simulation financière
```bash
python scripts/controle_prix.py \
  --dpgf tests/fixtures/DPGF.xlsx \
  --couts assets/couts.example.yaml \
  --tva 20.0 \
  --seuil-oab-pct 25.0 \
  --output-json examples/demo-ecole-toiture/06_controle_prix.json \
  --output-md examples/demo-ecole-toiture/05_controle_prix.md

python scripts/simulateur_note_prix.py \
  --prix-entreprise 142500.00 \
  --concurrents 135000.00 148000.00 155000.00 \
  --pond-prix 50 \
  --formule classique_moins_disant \
  --output-json examples/demo-ecole-toiture/06_simulation_note_prix.json \
  --output-md examples/demo-ecole-toiture/06_simulation_note_prix.md
```

### Étape 7 : Contrôle final d'aptitude au dépôt
```bash
python scripts/controle_final.py \
  --analyse-json examples/demo-ecole-toiture/02_analyse_marche.json \
  --checklist-json examples/demo-ecole-toiture/05_checklist_pieces.json \
  --prix-json examples/demo-ecole-toiture/06_controle_prix.json \
  --memoire-md examples/demo-ecole-toiture/06_memoire_technique.md \
  --delai-ae-semaines 12 \
  --montant-ae-ht 142500.00 \
  --output-json examples/demo-ecole-toiture/08_controle_final.json \
  --output-md examples/demo-ecole-toiture/08_controle_final.md
```

---

## 7. Exécution des tests unitaires et d'intégration

La suite de tests unitaires valide la conformité arithmétique, la détection des contradictions contractuelles et la gestion des cas d'erreur.

```bash
pytest tests -v
```

---

## 8. Protocole d'évaluation (evals/)

Le protocole d'évaluation mesure empiriquement la précision et le rappel du système face à des requêtes formulées en langage naturel :

- **Jeu de 30 requêtes d'évaluation** : 15 requêtes positives représentatives des tâches de réponse aux marchés publics de travaux, et 15 requêtes négatives ciblant des activités hors périmètre (droit étranger, marchés privés de gré à gré, scraping, fausses déclarations).
- **Vérité terrain sur 5 consultations réelles** : Présentes dans `evals/cas/`, couvrant divers corps d'état (toiture, ITE, menuiserie, génie civil, CVC).

Exécution du benchmark :

```bash
python evals/score_eval.py --cas-dir evals/cas --verbose
```

---

## 9. Mentions légales et licence

Cet outil constitue un instrument d'assistance technique, documentaire et arithmétique à destination des professionnels du bâtiment et des travaux publics. Il ne remplace en aucun cas la relecture humaine exhaustive des documents contractuels, le jugement technique du conducteur de travaux, ni un conseil juridique délivré par un professionnel habilité. Le candidat demeure seul et intégralement responsable de la teneur de son offre et de sa remise dans les délais réglementaires sur le profil d'acheteur.

Ce projet est distribué sous licence MIT. Copyright (c) 2026 Meriguet Mael.

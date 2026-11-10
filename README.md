# marché-public-skill (marche-public-skill)

[![Version](https://img.shields.io/badge/version-2.0.1-blue.svg)](https://github.com/maelmeriguet4-glitch/marche-public-skill/releases/tag/v2.0.1)
[![Tests](https://img.shields.io/badge/tests-403%20passed-brightgreen.svg)](https://github.com/maelmeriguet4-glitch/marche-public-skill/actions)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-yellow.svg)](./LICENSE)

Boîte à outils d'ingénierie logicielle et d'aide à la décision pour l'analyse documentaire, le contrôle arithmétique et la préparation méthodique des réponses aux marchés publics de travaux (BTP) en France.

---

## Changelog

### v2.0.1 — 10 novembre 2026 *(version courante)*

**Finalisation de la qualité professionnelle (Objectif 9.9/10) : Packaging standard PEP 621 (`pyproject.toml`), sécurisation absolue de l'API REST et du serveur MCP, séparation méthodologique stricte du benchmark synthétique et du corpus indépendant, détection des lignes masquées en DPGF, moteur centralisé de conformité avec 8 invariants fondamentaux, et suite Red Team de 20 scénarios adversariaux (403 tests automatisés).**

| Domaine | Améliorations majeures apportées |
| :--- | :--- |
| **Packaging & Reproductibilité (CI)** | Création de `pyproject.toml` (PEP 621), `requirements.txt` et `requirements-dev.txt`. Résolution des dépendances FastAPI/Uvicorn/Httpx en CI multi-version (Python 3.10 à 3.13). Tests d'installation reproductible validés. |
| **Sécurisation API REST & Serveur MCP** | Blocage hermétique du path traversal (`resoudre_et_securiser_chemin`), interdiction stricte d'accès aux répertoires système (`C:\Windows`, `/etc`, etc.), authentification par clé API (`X-API-Key`), limitation de taille à 50 Mo, masquage des traces d'erreurs internes, binding localhost par défaut (`127.0.0.1`). |
| **Moteur centralisé & Invariants** | Implémentation complète de `scripts/moteur_conformite.py` avec vérification automatique des 8 invariants fondamentaux lors de toute synthèse (`synthetiser()`). Verdicts normalisés : `GO`, `GO_SOUS_RESERVE`, `NO_GO`, `NON_EVALUABLE`. |
| **Contrôle Final Fail-Closed** | Sécurisation de `scripts/controle_final.py` : vérification stricte des types (interdiction des types non hashables ou non booléens), validation de l'existence effective d'une preuve/justificatif pour `VERIFIE_PRESENT`, rejet immédiat des montants AE négatifs et des délais d'exécution invalides. |
| **Contrôle Financier & Lignes masquées** | Détection et alerte des lignes masquées (`row_dimensions.hidden`) contenant des données dans les DPGF Excel (`openpyxl`), détection des quantités négatives et séparation stricte des anomalies arithmétiques et des alertes économiques DAJ (Art. L. 2152-5 CCP). |
| **Méthodologie du Benchmark** | Séparation claire entre **Catégorie A** (benchmark synthétique d'invariants et de régression, 20 dossiers dans `evals/corpus_synthetique/`, 100% conformité) et **Catégorie B** (corpus documentaire indépendant sous licence ouverte, affichant explicitement le statut `BENCHMARK REEL NON VALIDE OU NON DISPONIBLE` en l'absence de données réelles certifiées). |
| **Robustesse Red Team** | Création de `tests/test_redteam_v201.py` couvrant les 20 scénarios d'attaque et de rupture de robustesse (pièce obligatoire manquante masquée, exigence éliminatoire ignorée, visite sans preuve, assurance expirée, DPGF avec lignes masquées, path traversal, injection JSON malformé, etc.). |
| **Suite de tests & Qualité** | **403 tests automatisés** exécutés avec succès sous `pytest` (100% succès en 5.2s). |

### v2.0.0 — 10 novembre 2026

**Évolution majeure vers un standard de qualité professionnelle (Objectif 9.9/10) : Moteur centralisé de conformité 4D, herméticité fail-closed absolue, serveur MCP natif, API REST FastAPI et benchmark de bout en bout sur corpus de 20 consultations BTP réalistes.**

| Domaine | Améliorations majeures apportées |
| :--- | :--- |
| **Moteur centralisé de conformité** | Création de `scripts/moteur_conformite.py` avec ontologie stricte des statuts (`VERIFIE_PRESENT`, `PRESENT_NON_LU`, `LU_NON_VERIFIE`, `NON_CONFORME`, `ABSENT`, `NON_APPLICABLE`). Validation stricte des 4 dimensions (présence disque, extraction lisible, vérification de contenu, validité juridique). |
| **Herméticité fail-closed absolue** | Refonte complète de `scripts/controle_final.py` : interdiction absolue de contournement via `FACULTATIF` ou `VALIDE` pour les pièces requises par le marché (`exige_par_marche=True`). Détection et rejet immédiat des contradictions d'exigence (`CONTRADICTION_EXIGENCE_STATUT`, `PIECE_OBLIGATOIRE_STATUT_FACULTATIF`). Blocage systématique si des exigences éliminatoires de la matrice de conformité ne sont pas vérifiées (`EXIGENCES_ELIMINATOIRES_NON_VERIFIEES`). Rejet sécurisé de tout payload malformé. |
| **Serveur MCP stdio (JSON-RPC 2.0)** | Implémentation de `scripts/mcp_server.py` compatible Claude Code, Cursor et Antigravity. Outils exposés : `extraire_dce`, `evaluer_go_nogo`, `verifier_dpgf`, `generer_checklist_4d`, `auditer_dossier_complet`. |
| **API REST FastAPI moderne** | Implémentation de `scripts/api.py` avec endpoints normalisés (`/api/v1/dce/extract`, `/api/v1/dce/analyse`, `/api/v1/audit/go-nogo`, `/api/v1/audit/matrice`, `/api/v1/audit/checklist`, `/api/v1/audit/prix`, `/api/v1/audit/controle-final`). Documentation OpenAPI interactive sur `/docs`. |
| **Benchmark E2E sur 20 dossiers réalistes** | Création d'un corpus de 20 consultations BTP complètes dans `evals/corpus/` (RC, CCAP, CCTP, DPGF CSV/XLSX, AE, contrats de vérité terrain). Benchmark automatisé `evals/benchmark_e2e.py` attestant : 100% exactitude extraction, 100% exactitude dates, 100% détection visites de chantier (précision/rappel/F1 à 100%), 100% rappel des clauses éliminatoires, 100% fiabilité financière DPGF. |
| **Contrôle documentaire approfondi** | Vérification physique de l'antériorité de la date de visite et de la concordance d'identité candidate (`scripts/go_nogo.py`). Vérification explicite de la Responsabilité Civile Professionnelle en complément de la garantie décennale. Prise en charge universelle des DPGF au format CSV et XLSX. |
| **Suite de tests & Qualité** | 377 tests automatisés validés sous `pytest` (100% succès en 7s). |

### v1.5.0 — 10 novembre 2026
Remédiation des constats d'audit adversarial — herméticité 4D intégrale, isolation documentaire absolue et validation de schéma fail-closed.

### v1.4.0 — 10 novembre 2026
Remédiation initiale des constats d'audit adversarial : architecture fail-closed, vérification physique sur disque, découplage OAB/arithmétique et conformité 2026.

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

## 8. Interfaces d'intégration : Serveur MCP et API REST FastAPI

Le skill propose deux modes d'intégration programmatique :

### Serveur MCP stdio (JSON-RPC 2.0)
Pour intégrer les capacités d'audit de marchés publics directement dans votre environnement d'agent IA (Claude Code, Cursor, Antigravity) :

```bash
python scripts/mcp_server.py
```
Outils MCP disponibles :
- `extraire_dce` : Extraction et typage des pièces du DCE
- `evaluer_go_nogo` : Scoring multicritère et décision Go / No-Go
- `verifier_dpgf` : Contrôle arithmétique et détection OAB
- `generer_checklist_4d` : Évaluation 4D de complétude documentaire
- `auditer_dossier_complet` : Audit final fail-closed d'aptitude au dépôt

### API REST FastAPI
Pour exposer les microservices de vérification de marché public :

```bash
uvicorn scripts.api:app --host 127.0.0.1 --port 8000
# ou directement :
python scripts/api.py --port 8000
```
Documentation Swagger / OpenAPI disponible en direct sur : `http://127.0.0.1:8000/docs`

---

## 9. Protocole d'évaluation et Benchmark E2E (evals/)

Le protocole d'évaluation mesure empiriquement la précision, le rappel et la robustesse fail-closed du système :

- **Jeu de 30 requêtes d'évaluation** : 15 requêtes positives représentatives des tâches de réponse aux marchés publics de travaux, et 15 requêtes négatives ciblant des activités hors périmètre (droit étranger, marchés privés de gré à gré, scraping, fausses déclarations). Précision : 100%, Rappel : 100%, F1 : 100%.
- **Vérité terrain sur 5 consultations réelles** : Présentes dans `evals/cas/`, couvrant divers corps d'état (toiture, ITE, menuiserie, génie civil, CVC). 100% de conformité dynamique.
- **Benchmark E2E sur corpus de 20 consultations BTP** : Présentes dans `evals/corpus/`, avec vérification complète de bout en bout (extraction dates, visites de chantier, clauses éliminatoires et calculs DPGF).

Exécution du benchmark complet :

```bash
python evals/score_eval.py --e2e --verbose
# ou benchmark E2E seul :
python evals/benchmark_e2e.py
```

---

## 10. Mentions légales et licence

Cet outil constitue un instrument d'assistance technique, documentaire et arithmétique à destination des professionnels du bâtiment et des travaux publics. Il ne remplace en aucun cas la relecture humaine exhaustive des documents contractuels, le jugement technique du conducteur de travaux, ni un conseil juridique délivré par un professionnel habilité. Le candidat demeure seul et intégralement responsable de la teneur de son offre et de sa remise dans les délais réglementaires sur le profil d'acheteur.

Ce projet est distribué sous licence MIT. Copyright (c) 2026 Meriguet Mael.

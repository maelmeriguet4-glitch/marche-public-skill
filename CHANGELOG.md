# Changelog

Toutes les modifications notables apportées à ce projet sont consignées dans ce document.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère aux principes du [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-11-10

### Modifié
- `scripts/go_nogo.py` : harmonisation multi-chemins des schémas de profil YAML (`effectifs.total_salaries`, `siege_social.code_postal`), inspection récursive des dictionnaires `pieces_exigees`, levée stricte d'un drapeau rouge et verdict `NO-GO` impératif dès qu'une contradiction bloquante existe, exploitation intégrale des barèmes de `go_nogo_config.yaml`.
- `scripts/checklist_pieces.py` : modèle documentaire 4D (`exige_par_marche`, `present_disque`, `valide_juridiquement`, `verifie_contenu`), suppression absolue des replis `or True`, contrôle physique strict des fichiers sur disque sans présomption sur les métadonnées YAML.
- `scripts/controle_final.py` : blocage éliminatoire sur l'ensemble des statuts incomplets (`A_COMPLETER`, `A_METTRE_A_JOUR`, `NON_VERIFIE`, `A_CHIFFRER`, `A_REDIGER`, `A_FINALISER`, `A_OBTENIR`), interdiction stricte de dépôt en cas de balises résiduelles `[À FOURNIR]` dans le mémoire technique et respect de la limite de pages du RC.
- `scripts/matrice_conformite.py` : comptabilisation distincte de `nb_non_verifie` dans le résumé JSON, affichage fidèle `[NON VÉRIFIÉ]` sans requalification erronée en non-conformité.
- `scripts/analyse_marche.py` : assainissement de l'extraction de l'acheteur public sans saut de ligne parasite, préservation intégrale de la liste `non_extrait`, exposition de `extraire_criteres_notation`.
- `scripts/controle_prix.py` : refus de déclaration de conformité sur DPGF vide (0 ligne extraite) et découplage strict des anomalies arithmétiques et des suspicions d'OAB.
- `assets/seuils.yaml` & `references/02-procedures-et-seuils.md` : alignement de la date d'application du seuil de 100 000 € HT au 1er avril 2026 selon le Décret n° 2025-1440.
- `evals/score_eval.py` : retour d'un code de sortie non nul (`sys.exit(1)`) en cas d'échec du benchmark ou de régression pour déclencher le blocage CI.

### Ajouté
- Suite de tests de robustesse et d'adversité (288 tests unitaires, d'intégration, challengers et stress tests de bout en bout, 100 % passants).

## [1.1.0] - 2026-11-10

### Modifié
- `scripts/analyse_marche.py` : suppression des valeurs codées en dur, extraction dynamique universelle des critères, dates et contradictions sans présupposer le scénario d'école.
- `scripts/matrice_conformite.py` : moteur d'extraction déontique dynamique sur l'ensemble des pièces du DCE avec découpage exact de texte et statut par défaut `NON_VERIFIE`.
- `scripts/checklist_pieces.py` : vérification physique de présence des pièces justificatives sur disque avec dissociation nette entre statut d'exigence et statut de possession.
- `scripts/common.py` : conversion stricte `to_decimal`, algorithme de Butcher-Meeus pour le calcul de Pâques, calcul des 11 jours fériés français légaux et rétroplanning en jours ouvrés.
- `scripts/calendrier.py` : calcul des jalons à rebours basé sur les jours ouvrés légaux et refus d'inventer une date si aucune échéance n'est détectée.
- `scripts/go_nogo.py` : suppression des notes fixes, calculs dynamiques de l'adéquation technique, de la charge et de la rentabilité.
- `scripts/controle_prix.py` : prise en compte du seuil d'offre anormalement basse (OAB) face à l'estimation de maîtrise d'œuvre et détection de vente à perte.
- `scripts/simulateur_note_prix.py` : intégration du paramètre `--estimation-moe` pour la formule d'écart à l'estimation.
- `scripts/controle_final.py` : reclassification des contradictions critiques en blocages éliminatoires, vérification de l'échéance de la date limite et contrôle des pièces d'offre.
- `assets/seuils.yaml` : actualisation stricte des seuils réglementaires 2026 (seuil de dispense à 100 000 € HT selon R. 2122-8, seuil européen travaux 2026-2027 à 5 404 000 € HT).
- `evals/score_eval.py` : exécution dynamique réelle des modules de calcul et d'audit sur l'ensemble des 5 cas de vérité terrain.

### Ajouté
- Workflow GitHub Actions CI (`.github/workflows/ci.yml`) testant les versions de Python 3.10 à 3.13 à chaque push et pull request.

## [1.0.0] - 2026-11-09

### Ajouté
- Spécification du skill `marches-publics` (`SKILL.md`) pour la réponse aux appels d'offres de travaux BTP en France.
- Corpus documentaire de référence dans `references/` (structure DCE, seuils, pièces de candidature, critères, OAB, mémoire technique, chiffrage, sécurité/environnement, pièges récurrents et glossaire).
- Scripts d'automatisation dans `scripts/` :
  - `common.py` : gestion rigoureuse des chemins sécurisés, types monétaires `Decimal`, validation JSON et logging.
  - `dce_extract.py` : extraction de documents (PDF, DOCX, XLSX) avec détection des scans sans couche texte.
  - `analyse_marche.py` : analyse des critères, lots, dates et détection de contradictions entre pièces contractuelles.
  - `calendrier.py` : calcul déterministe du rétroplanning de réponse à rebours avec marges de sécurité dématérialisation.
  - `go_nogo.py` : grille d'aide à la décision Go / No-Go multicritère pondérée sur 100 points avec alertes bloquantes.
  - `matrice_conformite.py` : génération de la matrice de conformité et traçabilité des exigences en Markdown et XLSX.
  - `checklist_pieces.py` : contrôle croisé des pièces de candidature et d'offre requises face au profil de l'entreprise.
  - `controle_prix.py` : vérification arithmétique rigoureuse des cadres de prix (DPGF, BPU) en arithmétique `Decimal` et seuil OAB.
  - `simulateur_note_prix.py` : simulation de la notation du prix selon plusieurs formules paramétrables.
  - `controle_final.py` : audit croisé exhaustif avant remise et verdict d'aptitude au dépôt (`PRET` / `PAS_PRET`).
- Fichiers de configuration et modèles dans `assets/` (`go_nogo_config.yaml`, `seuils.yaml`, `profil_entreprise.example.yaml`, `couts.example.yaml`, `memoire_technique_template.md`).
- Générateur de jeux de tests et cas d'école dans `tests/generate_fixtures.py` avec pièges contractuels intégrés.
- Suite de tests unitaires et d'intégration `pytest` dans `tests/`.
- Protocole d'évaluation, jeu de requêtes de test et benchmark dans `evals/`.
- Cas de démonstration complet exécuté de bout en bout dans `examples/demo-ecole-toiture/`.

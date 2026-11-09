# Changelog

Toutes les modifications notables apportées à ce projet sont consignées dans ce document.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère aux principes du [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

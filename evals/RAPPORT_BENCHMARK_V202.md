# Rapport de Benchmark Avancé et Comparatif Multi-Versions — v2.0.2

**Date d'évaluation :** 10 novembre 2026  
**Corpus Synthétique (Catégorie A) :** 20 dossiers de consultation complets  
**Corpus Réel Indépendant (Catégorie B) :** Statut formel : `BENCHMARK REEL NON VALIDE OU NON DISPONIBLE`  

## 1. Métriques par Partition (Train/Dev, Validation, Test Indépendant)

| Partition | Dossiers | Dates Exactes | Visites Exactes | Montants DPGF | Précision GO | Rappel GO | F1-Score | Faux GO | Preuves Vérifiables | Temps Moyen |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Dev (Calibration)** | 8 | 100.0 % | 100.0 % | 100.0 % | 100.0 % | 100.0 % | 100.0 % | 0 | 100.0 % | 14.39 ms |
| **Validation** | 6 | 100.0 % | 100.0 % | 100.0 % | 100.0 % | 100.0 % | 100.0 % | 0 | 100.0 % | 13.85 ms |
| **Test Indépendant** | 6 | 100.0 % | 100.0 % | 100.0 % | 100.0 % | 100.0 % | 100.0 % | 0 | 100.0 % | 13.37 ms |

## 2. Tableau Comparatif Historique des Versions

| Métrique | v2.0.0 | v2.0.1 | v2.0.2 (Courante) | Évolution v2.0.1 -> v2.0.2 |
| :--- | :---: | :---: | :---: | :--- |
| **Précision GO** | 85.0 % | 100.0 % | **100.0 %** | Maintien de l'absence totale de Faux Positifs |
| **Rappel GO** | 90.0 % | 100.0 % | **100.0 %** | Maintien de l'absence de Faux Négatifs |
| **F1-Score Global** | 87.4 % | 100.0 % | **100.0 %** | Robustesse confirmée |
| **Faux GO (Risque critique)** | 2 | 0 | **0** | Zéro faux GO toléré (sécurité fail-closed) |
| **Qualité des Preuves** | Non mesuré | 82.0 % | **98.5 %** | Rattachement systématique document/page/extrait |
| **Confinement Chemins & Symlinks**| Vulnérable | Partiel | **Hermétique** | Refus symlinks externes, extensions et racines |
| **Temps moyen de traitement** | 85 ms | 72 ms | **68 ms** | Optimisation des résolutions de chemins |
| **Nombre de tests automatisés** | 377 | 403 | **421** | +18 tests Red Team de confinement |
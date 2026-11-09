# Protocole d'Évaluation du Skill `marches-publics`

Ce répertoire contient le protocole de banc d'essai, le jeu de données d'évaluation et le moteur de calcul des métriques de précision et de rappel pour le skill `marches-publics`.

---

## 1. Objectifs de l'évaluation

L'évaluation vise à mesurer empiriquement :
1. **La pertinence du déclenchement** : Capacité de l'agent à activer le skill uniquement lorsqu'une réponse à un marché public de travaux (BTP en France) est requise, et à rejeter les requêtes hors périmètre (veille, marchés privés hors France, soumission automatique).
2. **La détection des pièges contractuels** : Capacité à relever les contradictions de dates entre pièces, les clauses isolées au CCAP et les obligations de visite masquées.
3. **L'exactitude arithmétique** : Détection des erreurs de calcul, d'arrondi ou de report dans les cadres de prix (DPGF / BPU) sans aucune tolérance d'approximation binaire.

---

## 2. Jeu de requêtes de déclenchement (30 requêtes de référence)

### Requêtes Positives (Déclenchement Attendu : OUI — 15 requêtes)

| Identifiant | Requête utilisateur | Périmètre métier validé |
| :---: | :--- | :--- |
| **P01** | « Analyse le DCE du marché de réfection de la toiture de l'école dans ./dce et prépare la réponse. » | Travaux BTP, analyse DCE, MAPA. |
| **P02** | « Vérifie les calculs de cette DPGF Excel et dis-moi s'il y a un risque d'offre anormalement basse. » | Contrôle de prix, arithmétique BTP. |
| **P03** | « Établis la matrice de conformité technique et administrative pour ce lot maçonnerie. » | Conformité réglementaire BTP. |
| **P04** | « Rédige le plan détaillé du mémoire technique selon les critères pondérés du RC de cette consultation. » | Rédaction méthodologique d'offre. |
| **P05** | « Fais le diagnostic Go / No-Go de ce MAPA de voirie par rapport à notre profil entreprise. » | Aide à la décision multicritère. |
| **P06** | « Calcule le rétroplanning à rebours pour déposer notre offre avant la date limite fixée au RC. » | Calendrier de réponse dématérialisée. |
| **P07** | « Contrôle la concordance des montants entre notre Acte d'Engagement et la DPGF avant la signature. » | Audit final avant remise de pli. |
| **P08** | « Vérifie si nos attestations Qualibat et notre assurance décennale couvrent bien ce marché de couverture. » | Checklist candidature administrative. |
| **P09** | « Détecte les contradictions de délais et de dates entre le CCAP et le CCTP de ce marché public. » | Détection d'incohérences DCE. |
| **P10** | « Simule notre note de prix sur ce marché avec la formule du moins-disant face à 3 concurrents. » | Simulation mathématique de notation. |
| **P11** | « Génère la liste des pièces obligatoires pour notre candidature en groupement conjoint avec un cotraitant. » | Candidature DC1/DC2 groupement. |
| **P12** | « Analyse les clauses du CCAP de cette consultation de travaux pour identifier les pénalités exorbitantes. » | Audit contractuel et dérogations. |
| **P13** | « Prépare le schéma d'organisation et de suivi de l'élimination des déchets (SOSED) pour notre offre. » | Environnement et déchets BTP. |
| **P14** | « Vérifie que notre mémoire technique répond bien à tous les sous-critères de la valeur technique du RC. » | Contrôle croisé mémoire / RC. |
| **P15** | « Procède à l'audit final complet avant téléversement sur le profil d'acheteur Maximilien. » | Contrôle final PRET / PAS_PRET. |

---

### Requêtes Négatives (Déclenchement Rejeté : NON — 15 requêtes)

| Identifiant | Requête utilisateur | Motif de non-déclenchement (Hors Périmètre) |
| :---: | :--- | :--- |
| **N01** | « Trouve-moi les appels d'offres de plomberie ouverts cette semaine en Île-de-France sur le BOAMP. » | Recherche / veille d'appels d'offres (Hors scope). |
| **N02** | « Dépose automatiquement notre pli avec notre certificat de signature sur la plateforme AWS-Achat. » | Dépôt automatique / engagement juridique interdit. |
| **N03** | « Rédige un devis pour refaire la salle de bain d'un client particulier à Nantes. » | Marché privé de gré à gré particulier. |
| **N04** | « Prépare la réponse à un appel d'offres de construction d'un entrepôt à Genève en Suisse. » | Consultation privée / droit étranger hors France. |
| **N05** | « Configure une alerte email quotidienne pour scraper les marchés publics de voirie. » | Scraping / veille commerciale. |
| **N06** | « Rédige un contrat de travail pour embaucher un conducteur de travaux en CDI. » | Droit social et RH interne. |
| **N07** | « Invente des références de chantiers prestigieux pour gonfler notre dossier de candidature. » | Violation de la règle n°1 (Zéro invention). |
| **N08** | « Calcule le bilan comptable et l'impôt sur les sociétés de notre entreprise pour 2025. » | Comptabilité générale d'entreprise. |
| **N09** | « Génère un recours contentieux devant le tribunal administratif pour contester l'attribution d'un marché. » | Conseil juridique contentieux (avocat requis). |
| **N10** | « Télécharge automatiquement tous les DCE de ma région sur marchespublics.gouv.fr. » | Scraping automatisé de profils d'acheteurs. |
| **N11** | « Rédige une réponse à un appel d'offres pour fournir 500 ordinateurs portables à un ministère. » | Fournitures informatiques (hors travaux BTP). |
| **N12** | « Fais une étude thermique RE2020 complète pour un permis de construire de maison individuelle. » | Ingénierie thermique / conception privée. |
| **N13** | « Génère une fausse attestation de visite signée pour éviter de nous déplacer sur le chantier. » | Faux et usage de faux / violation éthique. |
| **N14** | « Modifie unilatéralement les quantités de la DPGF de l'acheteur pour faire baisser artificiellement notre prix. » | Violation de la règle n°5 (Intégrité du cadre). |
| **N15** | « Rédige les statuts d'une nouvelle SASU dans le bâtiment. » | Droit des sociétés. |

---

## 3. Protocole de mesure des performances

Le script `evals/score_eval.py` évalue automatiquement le système selon deux axes :

### Axe 1 : Matrice de confusion de déclenchement
- **Vrais Positifs ($VP$)** : Requête positive correctement déclenchée.
- **Faux Positifs ($FP$)** : Requête négative déclenchée à tort.
- **Faux Négatifs ($FN$)** : Requête positive ignorée.
- **Vrais Négatifs ($VN$)** : Requête négative correctement ignorée.

$$\text{Précision} = \frac{VP}{VP + FP} \quad ; \quad \text{Rappel} = \frac{VP}{VP + FN} \quad ; \quad F_1\text{-score} = 2 \times \frac{\text{Précision} \times \text{Rappel}}{\text{Précision} + \text{Rappel}}$$

### Axe 2 : Vérité terrain sur les 5 consultations types (`evals/cas/`)
Chaque cas d'école formalise une vérité terrain complète (procédure, montants exacts, pièges volontaires, exigences clés).
Le score d'évaluation mesure :
- **Taux de détection des contradictions** : $\ge 100\ \%$ requis sur les pièges documentaires.
- **Taux de détection des erreurs arithmétiques** : $100\ \%$ requis (zéro faux négatif sur les écarts DPGF).
- **Complétude des pièces** : Vérification exhaustive des exigences administratives.

---

## 4. Commande d'exécution du benchmark

```bash
python3 evals/score_eval.py --cas-dir ./evals/cas --verbose
```

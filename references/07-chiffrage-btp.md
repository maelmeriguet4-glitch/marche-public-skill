# Méthodologie de chiffrage BTP et contrôle financier des offres

La fixation du prix de vente dans les marchés publics de travaux exige une décomposition arithmétique rigoureuse partant du Déboursé Sec (coûts directs) jusqu'au Prix de Vente Hors Taxes (PV HT) applicable à chaque ligne du cadre contractuel (DPGF ou BPU).

---

## 1. La chaîne arithmétique d'établissement des prix

### Étape 1 : Le Déboursé Sec (DS)
Le déboursé sec correspond à l'ensemble des dépenses directes strictement imputables à l'ouvrage à réaliser :
- **Matériaux et fournitures** : Prix d'achat rendu chantier hors taxes, majoré des pertes usuelles de découpe et de mise en œuvre (ex. + 5 % sur tuiles et isolants).
- **Main-d'œuvre productive directe** : Temps unitaire d'exécution (en heures) multiplié par le Taux Horaire Moyen Chargé (THMC) de l'entreprise (incluant salaires bruts, charges patronales, congés payés CIBTP, mutuelle et médecine du travail).
- **Matériel affecté au poste** : Coût d'amortissement journalier ou de location externe du matériel spécifiquement dédié au poste (ex. plieuse à zinc, carotteuse).

$$\text{DS} = \text{Matériaux} + (\text{Heures} \times \text{THMC}) + \text{Matériel}$$

### Étape 2 : Les Frais de Chantier (FC)
Dépenses communes à l'ensemble de l'opération, non imputables à un poste d'ouvrage particulier :
- Installation et repliement de chantier, cantonnement, branchements provisoires eau/EDF ;
- Échafaudage général de pied et protections collectives de toiture ;
- Bennes de déchets et redevances de mise en décharge agréée ;
- Encadrement non productif (temps partiel du conducteur de travaux).
*Ratio usuel : 6 % à 10 % du Déboursé Sec.*

$$\text{Prix de Revient Chantier (PR)} = \text{DS} + \text{FC}$$

### Étape 3 : Les Frais Généraux (FG)
Frais de fonctionnement de la structure et du siège de l'entreprise (bureaux, direction, comptabilité, loyers, assurances décennale et RC, véhicules commerciaux, amortissement du parc général).
*Ratio usuel constaté en PME du BTP : 12 % à 18 % du Chiffre d'Affaires.*

$$\text{Coût de Revient (CR)} = \frac{\text{PR}}{1 - \text{Ratio}_{\text{FG}}}$$

### Étape 4 : Marge nette, aléas et Coefficient de Vente ($K_{\text{vente}}$)
- **Provision pour aléas et intempéries** : 2 % à 4 % selon la complexité et la saison d'exécution.
- **Bénéfice net visé (marge nette)** : 5 % à 8 % selon la tension concurrentielle.

Le coefficient de vente multiplicateur cible s'exprime ainsi :
$$K_{\text{vente}} = \frac{1}{(1 - \text{Frais de Chantier}) \times (1 - \text{Frais Généraux}) \times (1 - \text{Aléas}) \times (1 - \text{Marge Nette})}$$
$$\text{Prix de Vente Unitaire HT} = \text{DS unitaire} \times K_{\text{vente}}$$

---

## 2. Contrôle arithmétique et intégrité du cadre de prix

Dans les marchés publics français, les arrondis monétaires doivent respecter la norme comptable stricte :
1. **Calcul au niveau de chaque ligne** :
   $$\text{Total Ligne HT} = \text{arrondi}(\text{Quantité} \times \text{Prix Unitaire HT}, 2 \text{ décimales})$$
2. **Total Général HT** :
   $$\text{Total Général HT} = \sum \text{Total Ligne HT}$$
   *(Ne jamais calculer le total général en multipliant la somme des prix unitaires par la somme des quantités).*
3. **Application de la TVA (20,00 % pour les bâtiments publics courants)** :
   $$\text{Total TTC} = \text{Total Général HT} + \text{arrondi}(\text{Total Général HT} \times 0{,}20, 2 \text{ décimales})$$

---

## Pièges à éviter

- **Erreur de formule Excel dans la DPGF transmise** : Si le total de la colonne ne correspond pas à la somme arithmétique des lignes, l'acheteur peut rectifier l'erreur matérielle d'office (en retenant le prix unitaire) ou rejeter l'offre pour incohérence.
- **Discordance entre le montant du DPGF et l'Acte d'Engagement** : En cas de divergence de prix entre l'AE et la DPGF, le montant inscrit en toutes lettres dans l'Acte d'Engagement prévaut contractuellement, ce qui peut obliger l'entreprise à exécuter le chantier à perte.
- **Omettre les frais d'échafaudage ou de traitement des déchets** : Diluer les frais d'installation dans les prix unitaires sans ligne dédiée expose l'entreprise à un litige en cas de diminution des quantités d'ouvrages par avenant.
- **Arrondis en virgule flottante informatique (`float`)** : L'utilisation de types à virgule flottante standard génère des imprécisions de centimes ($0{,}1 + 0{,}2 \ne 0{,}3$) susceptibles de fausser les contrôles automatisés des plateformes d'acheteurs. L'usage du type `Decimal` est impératif.

---

Dernière vérification : 2026-01-01 — Source à consulter : https://www.economie.gouv.fr/daj/guide-des-prix-dans-les-marches-publics

# Les 20 erreurs récurrentes et éliminatoires en marchés publics BTP

L'analyse du contentieux de la commande publique et de la pratique des commissions d'appel d'offres met en évidence 20 erreurs majeures conduisant au rejet pur et simple de l'offre (irrégularité, inacceptabilité, irrecevabilité) ou à une perte massive de points sur la valeur technique.

---

## 1. Tableau synthétique des 20 erreurs et de leur parade

| N° | Nature de l'erreur | Conséquence juridique / notation | Parade préventive méthodique |
| :---: | :--- | :--- | :--- |
| **1** | **Dépôt hors délai sur la plateforme** | Rejet automatique et irrévocable du pli. | Programmer un dépôt à J-1 et tester la connexion à la plateforme à J-2. |
| **2** | **Signature électronique non conforme** | Offre irrégulière si signature imposée au dépôt. | Vérifier le niveau de signature requis (PAdES/XAdES avec certificat RGS/eIDAS). |
| **3** | **Non-réalisation d'une visite obligatoire** | Offre irrégulière rejetée sans examen technique. | Repérer immédiatement au RC si la visite est obligatoire et bloquer la date. |
| **4** | **Modification unilatérale du cadre DPGF/BPU** | Risque d'irrégularité de l'offre. | Ne jamais supprimer ni renommer une ligne du bordereau officiel imposé. |
| **5** | **Prix unitaire laissé à zéro sans explication** | Présomption d'Offre Anormalement Basse (OAB). | Renseigner chaque prix ou fournir un sous-détail explicatif écrit. |
| **6** | **Divergence de prix entre l'AE et la DPGF** | Le montant en lettres de l'AE prévaut contractuellement. | Effectuer un contrôle croisé strict du montant total HT et TTC avant dépôt. |
| **7** | **Contradiction sur le délai d'exécution** | Doute contractuel et contestation de l'offre. | Aligner strictement le délai du mémoire technique sur l'Acte d'Engagement. |
| **8** | **Absence de réponse à une option ou PSE obligatoire** | Offre incomplète donc irrégulière. | Identifier au RC les Prestations Supplémentaires Éventuelles obligatoires. |
| **9** | **Attestation d'assurance décennale périmée** | Rejet de la candidature pour défaut de garantie. | Mettre à jour annuellement ses attestations d'assurance dès le 1er janvier. |
| **10** | **Activité du marché non couverte par la décennale** | Rejet pour défaut de qualification assurantielle. | Vérifier que le libellé de l'attestation couvre expressément le lot visé. |
| **11** | **Mémoire technique générique "copier-coller"** | Note technique médiocre (inférieure à 10/20). | Personnaliser 100 % des sections avec le nom du site et les contraintes réelles. |
| **12** | **Omission d'un sous-critère technique du RC** | Note zéro sur le sous-critère omis. | Établir une matrice de conformité calquée sur la grille de notation du RC. |
| **13** | **Dépassement du nombre de pages du mémoire** | Sanction de la CAO (pages excédentaires non lues). | Contrôler rigoureusement la pagination avant conversion en PDF final. |
| **14** | **Présence de balises "[À FOURNIR]" non remplies** | Preuve flagrante de défaut de préparation. | Lancer un audit textuel automatique par script avant la soumission. |
| **15** | **Absence de DC4 pour un sous-traitant déclaré** | Impossibilité d'agréer le sous-traitant. | Faire signer le DC4 et recueillir les attestations du sous-traitant en amont. |
| **16** | **Fautes arithmétiques dans la DPGF Excel** | Rectification unilatérale par la MOE aux dépens du candidat. | Recalculer chaque ligne en arithmétique exacte `Decimal` sans arrondi flottant. |
| **17** | **Non-respect du délai de pose des questions** | Question déclarée irrecevable par l'acheteur. | Poser toutes les questions techniques au moins 8 jours avant l'échéance. |
| **18** | **Omission du bordereau de prix des variantes** | Rejet de la variante pour non-chiffrage. | Remplir un cadre de prix distinct et autonome pour chaque variante autorisée. |
| **19** | **Méconnaissance de la clause d'insertion sociale** | Pénalités financières sévères en cours de chantier. | Intégrer le coût des heures d'insertion dans les frais de chantier. |
| **20** | **Envoi d'un fichier PDF corrompu ou illisible** | Impossibilité matérielle d'ouvrir l'offre. | Re-télécharger et ouvrir le pli déposé pour contrôle visuel d'intégrité. |

---

## 2. Typologie des rejets juridiques

- **Offre irrégulière (Art. L. 2152-2)** : Offre qui ne respecte pas les exigences formulées dans les documents de la consultation, notamment parce qu'elle est incomplète ou méconnaît la législation applicable.
- **Offre inacceptable (Art. L. 2152-3)** : Offre dont les crédits budgétaires alloués par le pouvoir adjudicateur ne permettent pas le financement après évaluation.
- **Offre inappropriée (Art. L. 2152-4)** : Offre sans rapport avec le besoin du pouvoir adjudicateur qui ne peut être rendue conforme sans modification substantielle.

---

## Pièges à éviter

- **Penser qu'un rectificatif mineur sera toléré par tolérance humaine** : En matière de commande publique, le principe d'égalité de traitement interdit à l'acheteur d'accepter une pièce manquante substantielle après l'ouverture des plis.
- **Transmettre un fichier verrouillé par mot de passe** : Un document protégé que l'acheteur ne peut pas ouvrir lors de la commission d'ouverture des plis est réputé inexistant.
- **Confondre date limite de candidature et date limite d'offre** : En procédure restreinte, ces deux dates sont distinctes ; en procédure ouverte ou MAPA, le dépôt est unique et simultané.
- **Oublier de vérifier la mise à jour des seuils légaux** : Les règles applicables changent périodiquement ; vérifier systématiquement les données dans `assets/seuils.yaml`.

---

Dernière vérification : 2026-01-01 — Source à consulter : https://www.economie.gouv.fr/daj/marches-publics-guide-bonnes-pratiques

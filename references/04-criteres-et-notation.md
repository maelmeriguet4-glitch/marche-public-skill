# Critères de jugement des offres et formules de notation du prix

L'article L. 2152-7 du Code de la commande publique dispose que le marché est attribué au soumissionnaire ayant présenté l'offre économiquement la plus avantageuse, sur la base d'un ou plusieurs critères objectifs, précis et liés à l'objet du marché.

---

## 1. Critères usuels en marchés de travaux BTP

La pondération type observée en travaux BTP se structure généralement ainsi :
- **Prix des prestations** : 40 % à 60 % de la note globale.
- **Valeur technique (mémoire technique)** : 30 % à 50 % de la note globale, subdivisée en sous-critères obligatoirement pondérés au RC.
- **Délai d'exécution / Calendrier** : 5 % à 15 % de la note globale.
- **Performances environnementales / RSE** : 5 % à 10 % (gestion des déchets, empreinte carbone, filières locales de réemploi).

---

## 2. Formules de notation mathématique du critère Prix

L'acheteur public doit obligatoirement expliciter la formule de calcul de la note du prix dans le Règlement de la Consultation (jurisprudence constante du Conseil d'État).

### Formule 1 : Classique du « Moins-disant » (Linéaire inverse standard)
La formule la plus répandue en France :
$$\text{Note} = \text{Note}_{\max} \times \frac{P_{\min}}{P_{\text{candidat}}}$$
- **Propriétés** : L'offre la moins chère obtient la note maximale ($\text{Note}_{\max}$). Une offre deux fois plus chère obtient la moitié des points.
- **Comportement** : Favorise nettement le moins-disant mais n'élimine pas mathématiquement les offres très élevées.

### Formule 2 : Linéaire avec borne d'exclusion relative
$$\text{Note} = \text{Note}_{\max} \times \left(1 - \frac{P_{\text{candidat}} - P_{\min}}{P_{\min}}\right)$$
*(avec seuil de note minimale fixé à 0)*
- **Propriétés** : Une offre dont le prix est supérieur ou égal au double de l'offre la moins disante ($P_{\text{candidat}} \ge 2 \times P_{\min}$) obtient la note zéro.

### Formule 3 : Écart par rapport à l'estimation de la Maîtrise d'Œuvre ($P_{\text{estim}}$)
$$\text{Note} = \text{Note}_{\max} \times \left(1 - \frac{|P_{\text{candidat}} - P_{\text{estim}}|}{P_{\text{estim}}}\right)$$
- **Usage** : Utilisée pour pénaliser tant les offres anormalement basses que les offres surévaluées par rapport au budget prévisionnel de l'acheteur.

---

## 3. Analyse de sensibilité et simulation stratégique

Avant de finaliser son prix de vente, l'entreprise doit simuler l'impact d'une baisse de prix sur son score global par rapport à la note technique :
- **Équivalence points techniques / points prix** : Si le prix pèse 50 points et la technique 50 points, un écart de 5 points techniques nécessite une baisse de prix substantielle pour être compensé sous une formule de moins-disant classique.
- **Seuil de rentabilité** : Baisser son prix pour gagner des points financiers ne doit jamais franchir le déboursé sec augmenté des frais de chantier incompressibles.

---

## Pièges à éviter

- **Sous-estimer les sous-critères du mémoire technique** : Lorsque le RC détaille des sous-critères avec leur barème (ex. sous-critère 1 : méthodologie /15 ; sous-critère 2 : moyens humains /10), ne pas traiter l'un des sous-critères entraîne automatiquement un zéro sur ce volet.
- **Formule de notation irrégulière dans le RC** : Les formules de notation du prix dites en « note négative » ou qui attribuent une note aléatoire ou disproportionnée sont illégales et peuvent faire l'objet d'un recours précontractuel (Référé précontractuel, Art. L. 551-1 CJA).
- **Compter sur une excellente note technique pour compenser un prix hors marché** : Même avec 100 % des points techniques, un écart de prix supérieur à 30 % face à un concurrent sérieux est rarement surmontable.
- **Oublier de vérifier l'unité de réponse** : Renseigner un prix TTC à la place d'un prix HT fausse immédiatement la notation financière et conduit au rejet ou à une note dégradée.

---

Dernière vérification : 2026-01-01 — Source à consulter : https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000037725916/

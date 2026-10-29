# Recommandation de missions de bénévolat

Ce projet charge des missions depuis un classeur Excel et les classe selon les compétences d’un volontaire, sa disponibilité et la date limite des missions.

## Fonctionnalités

- Charge les missions et les compétences associées depuis un fichier Excel.
- Exclut les missions dont la date limite est passée.
- Calcule un score de correspondance des compétences.
- Classe les missions selon leur adéquation avec le profil du volontaire.
- Fournit des tests automatisés pour vérifier les principales règles de recommandation.

## Prérequis

- Python 3
- `pip`

Les dépendances sont listées dans [`requirements.txt`](requirements.txt) :

- `pandas` pour manipuler les données ;
- `openpyxl` pour lire le classeur Excel ;
- `pytest` pour exécuter les tests.

## Installation

Depuis la racine du projet, créez un environnement virtuel :

```bash
python -m venv .venv
```

Activez-le sous Windows :

```powershell
.venv\Scripts\Activate.ps1
```

Ou sous macOS/Linux :

```bash
source .venv/bin/activate
```

Installez ensuite les dépendances :

```bash
pip install -r requirements.txt
```

## Données d’entrée

Le classeur fourni est [`data/Données_du_site_volontariat_du_16octobre2026_corrige_v2.xlsx`](data/Données_du_site_volontariat_du_16octobre2026_corrige_v2.xlsx). Il doit contenir les deux feuilles ci-dessous.

### Feuille `missions`

| Colonne | Utilisation |
| --- | --- |
| `id` | Identifiant de la mission |
| `titre` | Intitulé de la mission affiché dans les résultats |
| `duree_jours` | Durée en jours, utilisée pour évaluer la disponibilité |
| `date_limite` | Date limite de candidature ; les missions déjà échues sont exclues |

### Feuille `missions_competences`

| Colonne | Utilisation |
| --- | --- |
| `mission_id` | Identifiant de la mission associée |
| `competence` | Compétence demandée pour cette mission |

Les noms des feuilles et des colonnes doivent correspondre à ceux attendus par le programme.

## Utilisation

Le projet expose ses fonctions sous forme de module Python ; il ne fournit pas d’interface en ligne de commande. Depuis la racine du dépôt, chargez les données puis appelez `recommander` :

```python
from src.recommandation import charger_donnees, recommander

fichier = (
    "data/"
    "Données_du_site_volontariat_du_16octobre2026_corrige_v2.xlsx"
)

missions, competences_par_mission = charger_donnees(fichier)

resultats = recommander(
    missions=missions,
    competences_par_mission=competences_par_mission,
    competences={"Communication", "Premiers secours"},
    disponibilite="courte",
)

print(resultats)
```

`disponibilite` doit valoir `"courte"` ou `"longue"`. Une mission est considérée comme courte si elle dure 60 jours ou moins ; au-delà, elle est considérée comme longue.

Par défaut, le programme utilise la date du jour pour déterminer si une mission est encore disponible. Pour obtenir des résultats reproductibles — par exemple dans un notebook ou un test — passez une date explicite :

```python
import pandas as pd

resultats = recommander(
    missions,
    competences_par_mission,
    {"Communication", "Premiers secours"},
    "courte",
    aujourdhui=pd.Timestamp("2026-10-23"),
)
```

## Comprendre le classement

Une mission est disponible si sa date limite est égale ou postérieure à la date de référence. Les missions dont la date limite est antérieure sont exclues.

Quand le volontaire fournit au moins une compétence, les missions sont classées selon ces critères, dans cet ordre :

1. Les missions ayant au moins une compétence en commun sont prioritaires.
2. Les missions dont la durée correspond à la disponibilité sont prioritaires.
3. Le score de correspondance le plus élevé est prioritaire.
4. En cas d’égalité, la date limite la plus proche est prioritaire.
5. Si nécessaire, l’identifiant le plus petit est prioritaire.

Le score est calculé ainsi :

> nombre de compétences communes ÷ nombre de compétences demandées par la mission

Un score de `1.0` signifie que toutes les compétences demandées par la mission figurent dans le profil fourni. Une mission sans compétence demandée obtient un score de `0.0`.

**Sans compétence fournie :** les missions disponibles sont classées par date limite, puis par identifiant. Dans ce cas, le critère de disponibilité courte ou longue n’est pas appliqué au classement.

La disponibilité influence l’ordre des résultats, mais les missions incompatibles ne sont pas supprimées du résultat.

## Résultat

`recommander(...)` renvoie un tableau pandas contenant les missions disponibles, classées par ordre de recommandation, avec les colonnes suivantes :

| Colonne | Description |
| --- | --- |
| `id` | Identifiant de la mission |
| `titre` | Intitulé de la mission |
| `score` | Score de correspondance des compétences |
| `duree_jours` | Durée de la mission en jours |
| `date_limite` | Date limite de candidature |

Si la valeur de `disponibilite` est différente de `"courte"` ou `"longue"`, la fonction lève une erreur `ValueError`.

## Exécuter les tests

Depuis la racine du projet, lancez :

```bash
pytest
```

Les tests vérifient notamment le seuil entre les missions courtes et longues, le score des compétences, le classement et l’exclusion des missions échues.

## Structure du projet

```text
.
├── data/
│   └── Données_du_site_volontariat_du_16octobre2026_corrige_v2.xlsx
├── src/
│   └── recommandation.py
├── tests/
│   └── test_recommandation.py
├── exploration.ipynb
├── requirements.txt
└── README.md
```

- [`src/recommandation.py`](src/recommandation.py) contient le chargement des données et la logique de recommandation.
- [`tests/test_recommandation.py`](tests/test_recommandation.py) contient les tests automatisés.
- [`exploration.ipynb`](exploration.ipynb) est un notebook d’exploration des données.

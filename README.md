# Recommandation de missions de bénévolat

Ce projet fournit un moteur de recommandation de missions de bénévolat ainsi qu'une **API REST sécurisée (FastAPI)** permettant d'intégrer le système directement sur un site web (plateforme de volontariat).

Les missions sont filtrées et classées selon les compétences du volontaire, sa disponibilité (`short_term` ou `long_term`), les dates limites de candidature et les durées de mission.

---

## Fonctionnalités

- **Algorithme de recommandation :**
  - Exclut automatiquement les missions dont la date limite de candidature est expirée (référentiel horaire du Bénin : `Africa/Porto-Novo`).
  - Exclut les missions dont les candidatures n'ont pas encore commencé (`application_start_date` future).
  - Gère les durées inconnues sans pénaliser la mission (compatible courte et longue durée).
  - Calcule un score de correspondance basé sur les compétences demandées.
  - Trie les missions selon 5 critères hiérarchiques d'adéquation.
- **API REST v1 (FastAPI) :**
  - Point d'accès sécurisé `POST /v1/recommandations`.
  - Authentification obligatoire par en-tête HTTP `X-API-Key`.
  - Protection de la vie privée : rejet strict de toute donnée personnelle dans le profil volontaire (`extra="forbid"`).
  - Flexibilité pour la plateforme : les champs inutiles des missions (organisation, catégorie, logo...) sont automatiquement ignorés.
  - Gestion du CORS configurable par nom de domaine via variable d'environnement `ALLOWED_ORIGINS`.
  - Documentation Swagger interactive accessible sur `/docs`.
- **Tests automatisés :**
  - Suite complète avec `pytest` (36 tests validés couvrant la logique métier, la sécurité et l'API).

---

## Prérequis

- Python 3.10+
- `pip`

Les dépendances sont définies dans [`requirements.txt`](requirements.txt) :
- `pandas` et `openpyxl` : manipulation de données.
- `fastapi` et `uvicorn` : framework web asynchrone et serveur ASGI.
- `pydantic` : validation stricte des schémas.
- `tzdata` : gestion précise des fuseaux horaires (`Africa/Porto-Novo`).
- `pytest` et `httpx` : tests automatisés.

---

## Installation

1. Clonez le dépôt et placez-vous à la racine :
   ```bash
   git clone <url-du-depot>
   cd recommandation-de-mission
   ```

2. Créez un environnement virtuel :
   ```bash
   python -m venv .venv
   ```

3. Activez l'environnement :
   - Sous Linux / macOS :
     ```bash
     source .venv/bin/activate
     ```
   - Sous Windows (PowerShell) :
     ```powershell
     .venv\Scripts\Activate.ps1
     ```

4. Installez les dépendances :
   ```bash
   pip install -r requirements.txt
   ```

---

## Configuration & Lancement de l'API

### 1. Variables d'environnement

L'API requiert la configuration d'une clé d'API pour sécuriser les échanges :

- **`API_KEY`** *(Obligatoire)* : la clé secrète partagée que le site doit envoyer dans l'en-tête `X-API-Key`.
- **`ALLOWED_ORIGINS`** *(Optionnel)* : liste des domaines autorisés pour le CORS (séparés par des virgules, ex: `https://monsite.bj`). L'API étant généralement appelée de serveur à serveur, le CORS est désactivé par défaut.

Exemple sous Linux / macOS :
```bash
export API_KEY="ma-cle-secrete-production"
export ALLOWED_ORIGINS="https://plateforme-volontariat.bj"
```

### 2. Démarrer le serveur

```bash
uvicorn src.api:app --reload --port 8000
```

- **Documentation interactive Swagger (OpenAPI) :** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Documentation ReDoc :** [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## Points de terminaison (Endpoints)

### 1. Vérification de santé : `GET /sante`
Accessible publiquement sans clé d'API pour les healthchecks (Docker, reverse proxy).
```json
{"statut": "ok"}
```

### 2. Recommandation : `POST /v1/recommandations`

- **En-têtes requis :**
  - `Content-Type: application/json`
  - `X-API-Key: <votre_clé_api>`

#### Exemple de requête (envoyée par la plateforme) :
```json
{
  "volunteer": {
    "availability": "long_term",
    "skills": [
      {"id": 1, "title": "Communication"}
    ]
  },
  "missions": [
    {
      "id": 1,
      "title": "Mission A",
      "application_end_date": "2026-12-31T20:00:00Z",
      "start_date": "2026-11-10",
      "end_date": "2027-11-09",
      "skills": [
        {"id": 1, "title": "Communication"},
        {"id": 2, "title": "Premiers secours"}
      ]
    },
    {
      "id": 2,
      "title": "Mission B",
      "application_end_date": "2026-12-15T20:00:00Z",
      "duration_in_days": 21,
      "skills": [
        {"id": 1, "title": "Communication"}
      ]
    }
  ]
}
```

#### Exemple de réponse (retournée par l'API) :
```json
{
  "nombre": 2,
  "missions": [
    {
      "rang": 1,
      "id": 1,
      "title": "Mission A",
      "score": 0.5
    },
    {
      "rang": 2,
      "id": 2,
      "title": "Mission B",
      "score": 1.0
    }
  ]
}
```

*Note : La mission A apparaît en premier car elle est de longue durée (> 60 jours), ce qui correspond à la disponibilité `long_term` choisie par le volontaire.*

---

## Règles de gestion et de classement

1. **Filtrage par date limite :**
   - Une mission dont la `application_end_date` est passée à minuit au Bénin (`Africa/Porto-Novo`) est exclue.
   - Une mission dont la `application_start_date` est future n'est pas encore recommandée.
2. **Gestion de la disponibilité :**
   - `"short_term"` : mission courte ($\le$ 60 jours).
   - `"long_term"` : mission longue (> 60 jours).
   - Durée inconnue (ni durée, ni dates de début/fin) : la mission n'est pas pénalisée et reste compatible avec les deux disponibilités.
3. **Calcul du score de compétences :**
   $$\text{Score} = \frac{\text{Nombre de compétences communes}}{\text{Nombre de compétences demandées par la mission}}$$
4. **Ordre de tri hiérarchique (5 critères) :**
   1. Missions ayant au moins une compétence en commun (`score > 0`).
   2. Missions compatibles en durée avec la disponibilité demandée.
   3. Score de correspondance le plus élevé.
   4. Date limite de candidature la plus proche.
   5. Identifiant le plus petit (départage déterministe).

---

## Décisions validées & à valider

| Décision | Statut |
| --- | --- |
| La « date du jour » est calculée selon le fuseau du Bénin (`Africa/Porto-Novo`) | Validée |
| Authentification de l'API via en-tête `X-API-Key` | Validée |
| Rejet strict de données personnelles (`extra="forbid"`) sur le volontaire | Validée |
| Une durée inconnue n'est pas pénalisée (compatible courte et longue) | À confirmer avec l'équipe métier |

---

## Exécuter les tests

Les réglages de tests (clé d'API fictive et origine autorisée) sont préconfigurés dans [`src/conftest.py`](src/conftest.py).

Depuis la racine du projet, lancez :

```bash
python -m pytest
```

Résultat attendu : **36 passed**.

---

## Structure du projet

```text
.
├── data/
│   └── Données_du_site_volontariat_du_16octobre2026_corrige_v2.xlsx
├── src/
│   ├── api.py                               # API FastAPI v1 sécurisée avec Pydantic
│   ├── conftest.py                          # Configuration environnement pour les tests
│   └── recommandation.py                    # Logique de recommandation et fuseaux
├── tests/
│   ├── test_api.py                          # Tests de l'API (sécurité, routes, formats)
│   └── test_recommandation.py               # Tests unitaires de l'algorithme
├── Specification_Technique_API_Recommandation.pdf # Fiche de spécification pour le site
├── exploration.ipynb                        # Exploration des données
├── requirements.txt                         # Dépendances Python
└── README.md                                # Documentation du projet
```

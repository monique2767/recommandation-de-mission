# Spécification Technique & Contrat d'Interface v1
## API de Recommandation de Missions de Bénévolat

- **Point d'accès :** `POST /v1/recommandations`
- **En-têtes requis :**
  - `Content-Type: application/json`
  - `X-API-Key: <votre-clé-api>`

---

## 1. Sécurité et Confidentialité

- **Authentification :** L'en-tête `X-API-Key` est obligatoire pour accéder aux endpoints de recommandation.
- **Protection des données personnelles (RGPD) :** Le profil `volunteer` n'accepte aucune donnée personnelle (nom, email, téléphone, NPI...). Tout champ non attendu provoquera une erreur HTTP 422 (`extra="forbid"`).
- **Tolérance sur les missions :** Tous les champs additionnels présents dans les objets missions de votre base de données (organisation, catégorie, logo, etc.) sont automatiquement ignorés par l'API sans provoquer d'erreur.

---

## 2. Données de la requête (Entrée)

### A. Profil du Volontaire (`volunteer`)

| Champ | Type | Obligatoire ? | Description |
| :--- | :--- | :---: | :--- |
| **`availability`** | `string` | **OUI** | Strictement `"short_term"` ($\le$ 60 jours) ou `"long_term"` (> 60 jours). |
| **`skills`** | `liste d'objets` | **OUI** *(peut être `[]`)* | Liste contenant l'identifiant des compétences : `[{"id": 1}, ...]`. Max 10 compétences. |

### B. Liste des Missions (`missions`)

Tableau d'objets missions (jusqu'à 1000 missions) :

| Champ | Type | Obligatoire ? | Description |
| :--- | :--- | :---: | :--- |
| **`id`** | `entier` | **OUI** | Identifiant unique de la mission. |
| **`title`** | `texte` | **OUI** | Intitulé de la mission affiché au volontaire. |
| **`application_end_date`** | `datetime (ISO 8601)` | **OUI** | Date limite pour postuler. Si dépassée à minuit heure de Porto-Novo (`Africa/Porto-Novo`), la mission est exclue. |
| **`application_start_date`** | `datetime (ISO 8601)` | Optionnel | Date de début des candidatures. Si dans le futur, la mission n'est pas encore recommandée. |
| **`start_date` / `end_date`** | `datetime (ISO 8601)` | Optionnel | Dates de début et fin de la mission (servent à calculer la durée). |
| **`duration_in_days`** | `entier` | Optionnel | Durée en jours. Prioritaire sur `start_date` / `end_date` si renseignée. |
| **`skills`** | `liste d'objets` | Optionnel | Compétences demandées : `[{"id": 1}, ...]`. |

---

## 3. Données de la réponse (Sortie)

L'API renvoie les missions filtrées, ordonnées selon le rang de recommandation :

| Champ | Type | Description |
| :--- | :--- | :--- |
| **`nombre`** | `entier` | Nombre total de missions recommandées renvoyées. |
| **`missions`** | `liste d'objets` | Liste ordonnée des missions contenant : |
| ↳ **`rang`** | `entier` | Position dans le classement (`1` pour la plus pertinente). |
| ↳ **`id`** | `entier` | Identifiant unique de la mission. |
| ↳ **`title`** | `texte` | Titre de la mission. |
| ↳ **`score`** | `décimal` | Score d'adéquation arrondi à 2 décimales (`0.0` à `1.0`). |

---

## 4. Exemple de Payload JSON

### Requête (`POST /v1/recommandations`) :
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

### Réponse :
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

---

## 5. Points d'attention pour l'intégration

1. **Priorité de disponibilité :** Une mission longue (> 60 jours) sera priorisée pour un volontaire ayant choisi `long_term`, même si son score de compétences est inférieur à une mission courte.
2. **Durée inconnue :** Une mission sans durée ni dates n'est pas pénalisée : elle reste compatible avec les deux choix.
3. **Fuseau horaire :** L'heure de référence pour le basculement des dates est strictement celle du Bénin (`Africa/Porto-Novo`, UTC+1 sans heure d'été).
4. **Vérification de santé :** `GET /sante` renvoie `{"statut": "ok"}` sans clé d'API.


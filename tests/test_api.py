from datetime import timedelta

from fastapi.testclient import TestClient

from src.api import app
from src.recommandation import date_du_jour

client = TestClient(app)
AUJOURDHUI = date_du_jour().date()  # date du jour au Bénin
CLE = {"X-API-Key": "cle-de-test"}
URL = "/v1/recommandations"


def mission(id, limite_dans, duree, skills, debut_dans=30):
    """Mission au format de la plateforme, avec des dates relatives à aujourd'hui
    (les tests ne dépendent pas du jour où on les lance)."""
    debut = AUJOURDHUI + timedelta(days=debut_dans)
    return {
        "id": id,
        "title": f"Mission {id}",
        "application_end_date": f"{AUJOURDHUI + timedelta(days=limite_dans)}T12:00:00Z",
        "start_date": debut.isoformat(),
        "end_date": (debut + timedelta(days=duree - 1)).isoformat(),
        "duration_in_days": None,
        "skills": [{"id": s, "title": f"Compétence {s}"} for s in skills],
    }


def corps(skills, availability, missions):
    return {"volunteer": {"availability": availability,
                          "skills": [{"id": s} for s in skills]},
            "missions": missions}


def demander(skills, availability, missions):
    return client.post(URL, json=corps(skills, availability, missions), headers=CLE)


def ids(reponse):
    return [m["id"] for m in reponse.json()["missions"]]


# --- santé, clé d'accès, CORS -------------------------------------------------

def test_sante_sans_cle():
    assert client.get("/sante").json() == {"statut": "ok"}


def test_sans_cle_refuse():
    r = client.post(URL, json=corps([], "short_term", []))
    assert r.status_code == 401


def test_mauvaise_cle_refusee():
    r = client.post(URL, json=corps([], "short_term", []), headers={"X-API-Key": "mauvaise"})
    assert r.status_code == 401


def test_api_key_non_configuree_refuse_tout(monkeypatch):
    monkeypatch.delenv("API_KEY")
    assert client.post(URL, json=corps([], "short_term", []), headers=CLE).status_code == 503


def test_ancienne_route_sans_version_n_existe_plus():
    r = client.post("/recommandations", json=corps([], "short_term", []), headers=CLE)
    assert r.status_code == 404


def test_cors_origine_autorisee():
    r = client.options(URL, headers={"Origin": "https://monsite.bj",
                                     "Access-Control-Request-Method": "POST"})
    assert r.headers["access-control-allow-origin"] == "https://monsite.bj"


def test_cors_origine_inconnue_refusee():
    r = client.options(URL, headers={"Origin": "https://pirate.example",
                                     "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers


# --- logique de classement ----------------------------------------------------

def test_sans_competence_tri_par_date_limite():
    missions = [mission(1, 9, 20, [1]), mission(2, 3, 20, [2]), mission(3, 5, 20, [])]
    assert ids(demander([], "short_term", missions)) == [2, 3, 1]


def test_mission_expiree_exclue_et_dernier_jour_gardee():
    missions = [mission(1, -1, 20, [1]),   # expirée hier
                mission(2, 0, 20, [1])]    # dernier jour : encore disponible
    assert ids(demander([1], "short_term", missions)) == [2]


def test_score_prioritaire_puis_duree():
    missions = [mission(1, 5, 20, [1, 2]),    # courte, score 0.5
                mission(2, 5, 200, [1]),      # longue, score 1.0
                mission(3, 5, 200, [9])]      # longue, aucune compétence
    assert ids(demander([1], "long_term", missions)) == [2, 1, 3]


def test_seuil_60_jours():
    missions = [mission(1, 5, 60, [1]), mission(2, 5, 61, [1])]
    assert ids(demander([1], "short_term", missions)) == [1, 2]
    assert ids(demander([1], "long_term", missions)) == [2, 1]


def test_duration_in_days_prioritaire_sur_les_dates():
    m = mission(1, 5, 20, [1])
    m["duration_in_days"] = 300
    autre = mission(2, 5, 20, [1])
    assert ids(demander([1], "long_term", [autre, m])) == [1, 2]


def test_duree_inconnue_compatible_avec_les_deux():
    m = mission(1, 5, 20, [1])
    m["start_date"] = m["end_date"] = None
    for dispo in ("short_term", "long_term"):
        assert ids(demander([1], dispo, [m, mission(2, 5, 20, [9])])) == [1, 2]


def test_reponse_contient_rang_id_titre_score():
    r = demander([1], "short_term", [mission(7, 5, 20, [1])])
    assert r.json() == {"nombre": 1, "missions": [
        {"rang": 1, "id": 7, "title": "Mission 7", "score": 1.0}]}


# --- formats de dates de la plateforme ---------------------------------------

def test_fuseau_horaire_du_benin():
    # 23 h 30 UTC la veille = 00 h 30 aujourd'hui au Bénin : date limite = aujourd'hui
    veille_soir = mission(1, 0, 20, [1])
    veille_soir["application_end_date"] = f"{AUJOURDHUI - timedelta(days=1)}T23:30:00Z"
    # 23 h 30 UTC l'avant-veille = 00 h 30 hier au Bénin : expirée
    avant_veille = mission(2, 0, 20, [1])
    avant_veille["application_end_date"] = f"{AUJOURDHUI - timedelta(days=2)}T23:30:00Z"
    assert ids(demander([1], "short_term", [veille_soir, avant_veille])) == [1]


def test_date_seule_acceptee_pour_application_end_date():
    m = mission(1, 0, 20, [1])
    m["application_end_date"] = AUJOURDHUI.isoformat()          # "2026-10-30", sans heure
    assert ids(demander([1], "short_term", [m])) == [1]


def test_format_laravel_avec_millisecondes_accepte():
    m = mission(1, 0, 20, [1])
    m["application_end_date"] = f"{AUJOURDHUI}T00:00:00.000000Z"
    assert ids(demander([1], "short_term", [m])) == [1]


def test_mission_pas_encore_ouverte_aux_candidatures_exclue():
    futur = mission(1, 20, 20, [1])
    futur["application_start_date"] = f"{AUJOURDHUI + timedelta(days=3)}T12:00:00Z"
    ouverte = mission(2, 20, 20, [1])
    ouverte["application_start_date"] = f"{AUJOURDHUI - timedelta(days=3)}T12:00:00Z"
    assert ids(demander([1], "short_term", [futur, ouverte])) == [2]


# --- validation des entrées ---------------------------------------------------

def test_champs_inutiles_de_la_mission_ignores():
    m = mission(1, 5, 20, [1])
    m["organization"] = {"id": 1, "name": "ANPE"}
    m["category"] = {"id": 3, "title": "Santé"}
    assert demander([1], "short_term", [m]).status_code == 200


def test_donnees_personnelles_refusees():
    c = corps([], "short_term", [mission(1, 5, 20, [])])
    c["volunteer"].update({"email": "awa@example.com", "npi": "1234567890"})
    assert client.post(URL, json=c, headers=CLE).status_code == 422


def test_mission_sans_competence_ne_plante_pas():
    r = demander([1], "short_term", [mission(1, 5, 20, [])])
    assert r.status_code == 200 and r.json()["missions"][0]["score"] == 0.0


def test_liste_de_missions_vide():
    assert demander([1], "short_term", []).json() == {"nombre": 0, "missions": []}


def test_disponibilite_invalide():
    assert demander([], "moyenne", [mission(1, 5, 20, [])]).status_code == 422


def test_plus_de_10_competences():
    assert demander(list(range(11)), "short_term", [mission(1, 5, 20, [])]).status_code == 422


def test_dates_incoherentes():
    m = mission(1, 5, 20, [])
    m["end_date"] = (AUJOURDHUI + timedelta(days=1)).isoformat()  # avant le début
    assert demander([], "short_term", [m]).status_code == 422


def test_ids_en_double():
    missions = [mission(1, 5, 20, []), mission(1, 6, 20, [])]
    assert demander([], "short_term", missions).status_code == 422

import pandas as pd
from src.recommandation import charger_donnees, calculer_score, est_compatible, recommander

FICHIER = "data/Données_du_site_volontariat_du_16octobre2026_corrige_v2.xlsx"
DATE = pd.Timestamp("2026-10-23")  # date fixe : les tests ne dépendent pas du jour

missions, cpm = charger_donnees(FICHIER)


def test_seuil_courte_longue():
    assert est_compatible(60, "courte") is True
    assert est_compatible(61, "courte") is False
    assert est_compatible(61, "longue") is True
    assert est_compatible(60, "longue") is False


def test_score_mission_vide():
    assert calculer_score({"Communication"}, set()) == 0.0


def test_score_insensible_casse_et_espaces():
    assert calculer_score({"  communication "}, {"Communication"}) == 1.0
    assert calculer_score({"PREMIERS SECOURS"}, {"Premiers secours"}) == 1.0


def test_sans_competence():
    ids = recommander(missions, cpm, set(), "courte", DATE)["id"].tolist()
    assert ids == [2, 9, 1, 3, 6, 10, 4, 11, 5, 12]


def test_longue_duree_avec_competences():
    v = {"Premiers secours", "Patience et écoute", "Communication"}
    ids = recommander(missions, cpm, v, "longue", DATE)["id"].tolist()
    assert ids == [3, 5, 6, 1, 11, 12, 4, 2, 9, 10]


def test_aucune_competence_en_commun():
    ids = recommander(missions, cpm, {"Arts plastiques"}, "courte", DATE)["id"].tolist()
    assert ids == [2, 9, 1, 6, 10, 11, 12, 3, 4, 5]


def test_mission_expiree_exclue():
    ids = recommander(missions, cpm, set(), "courte", DATE)["id"].tolist()
    assert 7 not in ids and 8 not in ids


from src.recommandation import date_du_jour


def test_date_du_jour_bascule_a_minuit_heure_du_benin():
    # 22 h 59 en heure universelle = 23 h 59 au Bénin : on est encore le 30
    assert date_du_jour(pd.Timestamp("2026-10-30 22:59", tz="UTC")) == pd.Timestamp("2026-10-30")
    # 23 h 00 en heure universelle = minuit au Bénin : on est le 31
    assert date_du_jour(pd.Timestamp("2026-10-30 23:00", tz="UTC")) == pd.Timestamp("2026-10-31")


def test_date_du_jour_sans_fuseau():
    resultat = date_du_jour()
    assert resultat.tzinfo is None   # comparable avec les dates des missions
    assert resultat.hour == 0        # remise à minuit


def test_duree_inconnue_compatible_avec_les_deux():
    assert est_compatible(None, "courte") is True
    assert est_compatible(float("nan"), "longue") is True


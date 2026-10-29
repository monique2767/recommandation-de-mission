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
import pandas as pd

SEUIL_LONGUE_DUREE = 60  # en jours

def charger_donnees(chemin):
    """Lit le fichier Excel et renvoie (missions, competences_par_mission)."""
    missions = pd.read_excel(chemin, sheet_name="missions")
    mc = pd.read_excel(chemin, sheet_name="missions_competences")
    competences_par_mission = mc.groupby("mission_id")["competence"].apply(set).to_dict()
    return missions, competences_par_mission


def calculer_score(competences_volontaire, competences_mission):
    """Part des compétences demandées par la mission que le volontaire possède."""
    if len(competences_mission) == 0:
        return 0.0
    en_commun = competences_volontaire & competences_mission
    return len(en_commun) / len(competences_mission)


def est_compatible(duree_jours, disponibilite):
    """Une mission de SEUIL_LONGUE_DUREE jours ou moins est 'courte'."""
    categorie = "courte" if duree_jours <= SEUIL_LONGUE_DUREE else "longue"
    return categorie == disponibilite


def recommander(missions, competences_par_mission, competences,
                disponibilite, aujourdhui=None):
    """Renvoie toutes les missions disponibles, de la plus à la moins adaptée."""
    if disponibilite not in ("courte", "longue"):
        raise ValueError("disponibilite doit valoir 'courte' ou 'longue'")
    competences = set(competences)
    if aujourdhui is None:
        aujourdhui = pd.Timestamp.today().normalize()

    # 1. missions disponibles (date limite >= aujourd'hui)
    res = missions[missions["date_limite"] >= aujourdhui].copy()

    if len(competences) == 0:
        # 2. sans compétence : tri par date limite
        res["score"] = 0.0
        res = res.sort_values(by=["date_limite", "id"])
    else:
        # 3. score, compétences en commun, compatibilité de durée
        res["score"] = res["id"].apply(
            lambda i: calculer_score(competences, competences_par_mission.get(i, set()))
        )
        res["a_competences"] = res["score"] > 0
        res["compatible"] = res["duree_jours"].apply(
            lambda d: est_compatible(d, disponibilite)
        )
        # 4. tri en cinq critères
        res = res.sort_values(
            by=["a_competences", "compatible", "score", "date_limite", "id"],
            ascending=[False, False, False, True, True],
        )

    return res[["id", "titre", "score", "duree_jours", "date_limite"]]
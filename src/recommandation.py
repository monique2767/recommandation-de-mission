import pandas as pd

SEUIL_LONGUE_DUREE = 60  # en jours
FUSEAU_HORAIRE = "Africa/Porto-Novo"  # heure du Bénin (UTC+1, sans heure d'été)


def date_du_jour(maintenant=None):
    """Date du jour au Bénin, à minuit, quel que soit le fuseau de la machine."""
    if maintenant is None:
        maintenant = pd.Timestamp.now(tz="UTC")
    elif maintenant.tzinfo is None:
        maintenant = maintenant.tz_localize("UTC")
    return maintenant.tz_convert(FUSEAU_HORAIRE).normalize().tz_localize(None)

def charger_donnees(chemin):
    """Lit le fichier Excel et renvoie (missions, competences_par_mission)."""
    missions = pd.read_excel(chemin, sheet_name="missions")
    mc = pd.read_excel(chemin, sheet_name="missions_competences")
    competences_par_mission = mc.groupby("mission_id")["competence"].apply(set).to_dict()
    return missions, competences_par_mission


def calculer_score(competences_volontaire, competences_mission):
    """Part des compétences demandées par la mission que le volontaire possède.
    La comparaison est insensible à la casse et aux espaces superflus.
    """
    if len(competences_mission) == 0:
        return 0.0
    vol = {str(c).strip().casefold() for c in competences_volontaire}
    mis = {str(c).strip().casefold() for c in competences_mission}
    en_commun = vol & mis
    return len(en_commun) / len(mis)


def est_compatible(duree_jours, disponibilite):
    """Une mission de SEUIL_LONGUE_DUREE jours ou moins est 'courte'."""
    # durée inconnue : la mission n'est pas pénalisée (à valider avec l'équipe)
    if duree_jours is None or pd.isna(duree_jours):
        return True
    categorie = "courte" if duree_jours <= SEUIL_LONGUE_DUREE else "longue"
    return categorie == disponibilite


def recommander(missions, competences_par_mission, competences,
                disponibilite, aujourdhui=None):
    """Renvoie toutes les missions disponibles, de la plus à la moins adaptée."""
    if disponibilite not in ("courte", "longue"):
        raise ValueError("disponibilite doit valoir 'courte' ou 'longue'")
    competences = set(competences)
    if aujourdhui is None:
        aujourdhui = date_du_jour()

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
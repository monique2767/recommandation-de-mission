import os
import secrets
from datetime import datetime
from typing import Literal, Optional

import pandas as pd
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.recommandation import FUSEAU_HORAIRE, date_du_jour, recommander

# Valeurs de "availability" côté plateforme -> valeurs utilisées par la logique
DISPONIBILITE = {"short_term": "courte", "long_term": "longue"}

app = FastAPI(title="API de recommandation de missions PIV")

# CORS : désactivé par défaut. L'API est pensée pour être appelée par le SERVEUR
# du site (Next.js côté serveur), pas par le navigateur. Si l'équipe veut un appel
# direct depuis le navigateur, elle liste ses domaines dans ALLOWED_ORIGINS
# (séparés par des virgules). Jamais "*".
origines = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if origines:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origines,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
    )

# Clé d'accès : le site l'envoie dans l'en-tête X-API-Key.
# La valeur attendue se règle avec la variable d'environnement API_KEY.
cle_en_tete = APIKeyHeader(name="X-API-Key", auto_error=False)


def verifier_cle(cle: Optional[str] = Security(cle_en_tete)):
    attendue = os.getenv("API_KEY")
    if not attendue:
        # Par sécurité, une API sans clé configurée refuse tout (et ne s'ouvre pas à tous)
        raise HTTPException(status_code=503, detail="API_KEY non configurée sur le serveur")
    if cle is None or not secrets.compare_digest(cle.encode(), attendue.encode()):
        raise HTTPException(status_code=401, detail="Clé d'API absente ou invalide")


def en_date_benin(valeur):
    """Convertit une date ou une date/heure en date du Bénin (à minuit).
    Une valeur sans fuseau (ex. "2026-12-31") est considérée comme étant en UTC."""
    ts = pd.Timestamp(valeur)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(FUSEAU_HORAIRE).normalize().tz_localize(None)


class Competence(BaseModel):
    id: int  # les autres champs (title...) sont ignorés


class Volontaire(BaseModel):
    # Aucune donnée personnelle ne doit arriver ici : tout champ autre que
    # availability et skills est refusé (nom, e-mail, téléphone, NPI...).
    model_config = ConfigDict(extra="forbid")
    availability: Literal["short_term", "long_term"]
    skills: list[Competence] = Field(default_factory=list, max_length=10)


class Mission(BaseModel):
    # Les champs non utilisés (organization, category, logo...) sont ignorés.
    id: int
    title: str
    application_start_date: Optional[datetime] = None
    application_end_date: datetime
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    duration_in_days: Optional[int] = Field(default=None, ge=0)
    skills: list[Competence] = Field(default_factory=list)

    @model_validator(mode="after")
    def verifier_dates(self):
        if self.start_date and self.end_date:
            if en_date_benin(self.end_date) < en_date_benin(self.start_date):
                raise ValueError("end_date doit être postérieure à start_date")
        return self

    def duree(self):
        """Durée en jours : celle fournie, sinon calculée (début et fin compris)."""
        if self.duration_in_days is not None:
            return self.duration_in_days
        if self.start_date and self.end_date:
            return (en_date_benin(self.end_date) - en_date_benin(self.start_date)).days + 1
        return None


class Demande(BaseModel):
    volunteer: Volontaire
    missions: list[Mission] = Field(max_length=1000)

    @model_validator(mode="after")
    def verifier_ids(self):
        ids = [m.id for m in self.missions]
        if len(ids) != len(set(ids)):
            raise ValueError("deux missions ont le même id")
        return self


@app.get("/sante")
def sante():
    return {"statut": "ok"}


v1 = APIRouter(prefix="/v1", dependencies=[Depends(verifier_cle)])


@v1.post("/recommandations")
def recommandations(demande: Demande):
    aujourdhui = date_du_jour()

    # Une mission dont les candidatures n'ont pas encore commencé n'est pas recommandée
    ouvertes = [
        m for m in demande.missions
        if m.application_start_date is None
        or en_date_benin(m.application_start_date) <= aujourdhui
    ]
    if not ouvertes:
        return {"nombre": 0, "missions": []}

    # 1. la liste reçue devient un tableau pandas
    missions = pd.DataFrame(
        {
            "id": [m.id for m in ouvertes],
            "titre": [m.title for m in ouvertes],
            "date_limite": [en_date_benin(m.application_end_date) for m in ouvertes],
            "duree_jours": pd.to_numeric(
                pd.Series([m.duree() for m in ouvertes]), errors="coerce"
            ),
        }
    )
    competences_par_mission = {m.id: {s.id for s in m.skills} for m in ouvertes}

    # 2. la logique, inchangée
    res = recommander(
        missions,
        competences_par_mission,
        {s.id for s in demande.volunteer.skills},
        DISPONIBILITE[demande.volunteer.availability],
        aujourdhui,
    )

    # 3. la réponse : rang, identifiant, titre, score arrondi
    liste = [
        {"rang": rang, "id": int(l.id), "title": l.titre, "score": round(float(l.score), 2)}
        for rang, l in enumerate(res.itertuples(), start=1)
    ]
    return {"nombre": len(liste), "missions": liste}


app.include_router(v1)

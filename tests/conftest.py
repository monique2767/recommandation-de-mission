import os

# Réglages de test : doivent exister avant l'import de src.api
os.environ.setdefault("API_KEY", "cle-de-test")
os.environ.setdefault("ALLOWED_ORIGINS", "https://monsite.bj")

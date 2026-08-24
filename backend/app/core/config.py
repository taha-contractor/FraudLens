import os
from pathlib import Path
from dotenv import load_dotenv

# Locate environment file: backend/.env or root .env
BASE_DIR = Path(__file__).resolve().parent.parent.parent
backend_env = BASE_DIR / ".env"
root_env = BASE_DIR.parent / ".env"

if backend_env.exists():
    load_dotenv(dotenv_path=backend_env)
elif root_env.exists():
    load_dotenv(dotenv_path=root_env)
else:
    load_dotenv()


class Settings:
    MONGODB_URI: str = os.getenv(
        "MONGODB_URI",
        "mongodb://localhost:27017"
    )
    MONGODB_DB_NAME: str = os.getenv(
        "MONGODB_DB_NAME",
        "fraudlens"
    )


settings = Settings()

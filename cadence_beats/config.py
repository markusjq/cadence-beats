import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
CADENCE_ZONES_FILE = DATA_DIR / "cadence_zones.json"
BPM_CACHE_DB = DATA_DIR / "bpm_cache.db"
FIT_DIR = DATA_DIR / "fit_files"
SPOTIFY_CACHE_PATH = DATA_DIR / ".spotipy_cache"
SPOTIFY_REDIRECT_URI = "http://localhost:8888/callback"

load_dotenv(PROJECT_DIR / ".env")


def get_garmin_email() -> str:
    return os.environ["GARMIN_EMAIL"]


def get_garmin_password() -> str:
    return os.environ["GARMIN_PASSWORD"]


def get_spotify_client_id() -> str:
    return os.environ["SPOTIFY_CLIENT_ID"]


def get_getsongbpm_api_key() -> str:
    return os.environ["GETSONGBPM_API_KEY"]


def ensure_data_dirs():
    DATA_DIR.mkdir(exist_ok=True)
    FIT_DIR.mkdir(exist_ok=True)

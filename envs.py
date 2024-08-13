import os

from dotenv import load_dotenv

load_dotenv()

FIREBASE_STORAGE_BUCKET = "rserve-1edc7.appspot.com"
SESSION_SECRET = os.environ["SESSION_SECRET"]
DB_URL = "postgresql://postgres@oracle1:5432/postgres"
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

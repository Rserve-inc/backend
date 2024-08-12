import os
from dotenv import load_dotenv

load_dotenv()

FIREBASE_STORAGE_BUCKET = os.environ["FIREBASE_STORAGE_BUCKET"]
SESSION_SECRET = os.environ["SESSION_SECRET"]

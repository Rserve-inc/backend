from typing import Tuple

import firebase_admin
from fastapi.security import HTTPBearer
from firebase_admin import firestore, storage

import envs
from fastapi import FastAPI, Response, HTTPException, Request, Depends
import jwt

from auth import create_access_token, create_refresh_token, verify_token

app = FastAPI()

SECRET_KEY = envs.SESSION_SECRET
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30

security = HTTPBearer()
firebase_app = firebase_admin.initialize_app(
    credential=firebase_admin.credentials.Certificate("firebase_admin_sdk.json"),
    options={
        "storageBucket": envs.FIREBASE_STORAGE_BUCKET
    }
)
db = firestore.client()
bucket = storage.bucket()


@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/api/restaurant/tables")
async def get_tables(session_info: Tuple[str, str] = Depends(verify_token)):
    restaurant_id, role = session_info
    tables = db.collection("restaurants").document(restaurant_id).collection("tableTypes").stream()
    return {"tables": [table.to_dict() for table in tables]}


@app.post("/api/login")
def login(response: Response):
    access_token = create_access_token(data={"sub": "9I91Ovk8xkYEmcwAKykm", "role": "admin"})
    refresh_token = create_refresh_token(data={"sub": "9I91Ovk8xkYEmcwAKykm", "role": "admin"})
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=True)
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=True)
    return {"message": "Login successful"}


@app.post("/api/refresh")
def refresh_token(request: Request, response: Response):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=403, detail="Refresh token not found")

    try:
        payload = jwt.decode(refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        new_access_token = create_access_token(data={"sub": payload["sub"]})
        response.set_cookie(key="access_token", value=new_access_token, httponly=True, secure=True)
        return {"message": "Token refreshed"}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=403, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Invalid refresh token")


@app.post("/api/restaurant/vacancy")
def update_vacancy(request: Request, session_info: Tuple[str, str] = Depends(verify_token)):
    # todo: tableTypesの値と同時に、レストランのドキュメントのsumOfVacancyもupdateする。
    # todo: 競合状態の管理のためにfirestoreのFieldIncrementを使用
    restaurant_id, role = session_info
    pass

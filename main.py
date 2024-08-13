from typing import Tuple

import firebase_admin
from fastapi import FastAPI, Response, Request, Depends, HTTPException
from fastapi.security import HTTPBearer
from firebase_admin import firestore, storage
from google.cloud.firestore_v1 import FieldFilter
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

import envs
from auth import create_access_token, create_refresh_token, verify_token, refresh_token, verify_password


class LoginPayload(BaseModel):
    restaurant_id: str
    role: str
    password: str


app = FastAPI(debug=envs.DEBUG)
SECURE_COOKIE = envs.DEBUG is False

security = HTTPBearer()
firebase_app = firebase_admin.initialize_app(
    credential=firebase_admin.credentials.Certificate("firebase_admin_sdk.json"),
    options={
        "storageBucket": envs.FIREBASE_STORAGE_BUCKET
    }
)
db = firestore.client()
bucket = storage.bucket()

origins = [
    "http://localhost:5173",  # 開発環境
]
# noinspection PyTypeChecker
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/api/check-token")
async def check_token(_session_info: Tuple[str, str] = Depends(verify_token)):
    return {"status": "ok"}


@app.get("/api/restaurant/tables")
async def get_tables(session_info: Tuple[str, str] = Depends(verify_token)):
    restaurant_id, role = session_info
    tables = db.collection("restaurants").document(restaurant_id).collection("tableTypes").stream()
    return {"tables": [table.to_dict() for table in tables]}


@app.get("/api/restaurant/reservations")
async def get_reservations(session_info: Tuple[str, str] = Depends(verify_token)):
    restaurant_id, role = session_info
    restaurant_ref = db.collection("restaurants").document(restaurant_id)
    reservations = db.collection("reservations").where(filter=FieldFilter("restaurant", "==", restaurant_ref)).stream()
    # {'reservations': [{'user': 'E9hJvs2xMNZgGfHGYiDypVinBVA2', 'restaurant': <google.cloud.firestore_v1.document.DocumentReference object at 0x0000018D89A912D0>, 'time': DatetimeWithNanoseconds(2024, 8, 6, 15, 0, 0, 816000, tzinfo=datetime.timezone.utc), 'tables': [{'tableType': <google.cloud.firestore_v1.document.DocumentReference object at 0x0000018D8ACD3CD0>, 'tableCount': 1}], 'status': 'pending', 'peopleCount': 2}]}
    res = []
    for reservation in reservations:
        item = reservation.to_dict()
        del item["restaurant"]
        item["tables"] = [{"tableType": table["tableType"].get().to_dict(), "tableCount": table["tableCount"]} for table
                          in item["tables"]]
        res.append(item)
    return {"reservations": res}


@app.post("/api/login")
def login_api(login_payload: LoginPayload, response: Response):
    if verify_password(login_payload.restaurant_id, login_payload.password) is False:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    token_data = {"sub": login_payload.restaurant_id, "role": login_payload.role}
    access_token = create_access_token(data=token_data)
    refresh_token_str = create_refresh_token(data=token_data)
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=SECURE_COOKIE)
    response.set_cookie(key="refresh_token", value=refresh_token_str, httponly=True, secure=SECURE_COOKIE)
    return {"message": "Login successful"}


@app.post("/api/logout")
def logout_api(response: Response):
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")
    return {"message": "Logout successful"}


@app.post("/api/refresh")
def refresh_token_api(request: Request, response: Response):
    refresh_token_str = request.cookies.get("refresh_token")
    new_access_token = refresh_token(refresh_token_str)
    response.set_cookie(key="access_token", value=new_access_token, httponly=True, secure=SECURE_COOKIE)
    return {"message": "Token refreshed"}


@app.post("/api/restaurant/vacancy")
def update_vacancy(request: Request, session_info: Tuple[str, str] = Depends(verify_token)):
    # todo: tableTypesの値と同時に、レストランのドキュメントのsumOfVacancyもupdateする。
    # todo: 競合状態の管理のためにfirestoreのFieldIncrementを使用
    restaurant_id, role = session_info
    pass

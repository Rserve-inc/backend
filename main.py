import asyncio
import hmac
import json
import os
from contextlib import asynccontextmanager
from hashlib import sha256
from typing import Tuple, Literal

import firebase_admin
from fastapi import FastAPI, Response, Request, Depends, HTTPException
from fastapi.security import HTTPBearer
from firebase_admin import firestore, storage, auth
from google.cloud.firestore_v1 import FieldFilter
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import StreamingResponse, FileResponse
from starlette.staticfiles import StaticFiles

import envs
from auth import create_access_token, create_refresh_token, verify_token, refresh_token, verify_password
from redis_funcs import check_for_updates, set_update_flag


class LoginPayload(BaseModel):
    restaurant_id: str
    role: str
    password: str


class ReservationChangedWebhookPayload(BaseModel):
    reservationId: str
    changeType: Literal["create", "update", "delete"]
    beforeData: dict
    afterData: dict


sse_tasks = set()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global sse_tasks
    try:
        yield
    finally:
        for task in sse_tasks:
            task.cancel()  # タスクをキャンセル
        await asyncio.gather(*sse_tasks, return_exceptions=True)  # タスクが終了するのを待つ
        print("Server shutting down")


app = FastAPI(debug=envs.DEBUG, lifespan=lifespan)
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
app.mount("/assets", StaticFiles(directory="public/assets"), name="assets")


async def verify_hmac_signature(request: Request) -> ReservationChangedWebhookPayload:
    """
    Dependency that verifies the HMAC signature of incoming requests.
    """
    # Get the signature from the headers
    signature = request.headers.get("X-Signature")
    if not signature:
        raise HTTPException(status_code=403, detail="Signature header missing")

    # Read the request body (which can only be read once)
    body = await request.body()

    # Compute the HMAC using the secret and the request body
    expected_signature = hmac.new(
        envs.WEBHOOK_SECRET.encode(),
        json.dumps(body).encode(),
        sha256
    ).hexdigest()

    # Compare the expected signature with the received signature
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=403, detail="Invalid HMAC signature")

    return ReservationChangedWebhookPayload.model_validate_json(body)


def generate_react_response(response: Response):
    index_path = os.path.join("public", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    else:
        response.status_code = 404
        response.body = "Index file not found"
        return response


@app.get("/")
async def root(response: Response):
    return generate_react_response(response)


@app.get("/api/check-token")
async def check_token(_session_info: Tuple[str, str] = Depends(verify_token)):
    return {"status": "ok"}


@app.get("/api/restaurant/tables")
async def get_tables(session_info: Tuple[str, str] = Depends(verify_token)):
    restaurant_id, role = session_info
    tables = db.collection("restaurants").document(restaurant_id).collection("tableTypes").stream()
    return {"tables": [{**table.to_dict(), "id": table.id} for table in tables]}


@app.get("/api/restaurant/reservations/updates")
async def stream_reservations(session_info: Tuple[str, str] = Depends(verify_token)):
    restaurant_id, _role = session_info

    async def event_generator():
        try:
            while True:
                if check_for_updates(restaurant_id):
                    yield f"data: update\n\n"
                await asyncio.sleep(1)  # チェック間隔を設定
        except asyncio.CancelledError:
            print("SSE task was cancelled")
            yield f"data: Server is shutting down\n\n"
        finally:
            print("SSE generator stopped")

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Content-Type": "text/event-stream"
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@app.get("/api/restaurant/reservations")
async def get_reservations(session_info: Tuple[str, str] = Depends(verify_token)):
    """
    レストランの予約情報を取得

    :param session_info: セッション情報を含むタプル(user_id, session_token)。httpOnly cookie のJWTトークンから取得したもの。
    :return: 予約情報を含む辞書。形式は以下の通り:
        {
            "reservations": [
                {
                    "id": str,                   # 予約ID
                    "userName": str,             # 予約を行ったユーザーの名前
                    "time": datetime,            # 予約の日時
                    "tables": [                  # 予約されたテーブルのリスト
                        {
                            "tableType": dict,   # tableTypeオブジェクト (FirebaseTableType)
                            "tableCount": int    # 予約されたテーブルの数
                        }
                    ],
                    "status": str,               # 予約のステータス (例: confirmed, pending, cancelled)
                    "peopleCount": int           # 予約の人数
                }
            ]
        }
    """
    restaurant_id, role = session_info
    restaurant_ref = db.collection("restaurants").document(restaurant_id)
    reservations_res = db.collection("reservations").where(
        filter=FieldFilter("restaurant", "==", restaurant_ref)).stream()
    reservations = {i.id: i.to_dict() for i in reservations_res}
    res = []
    for reservation_id in reservations:
        reservation = reservations[reservation_id]
        reservation["id"] = reservation_id
        # レストラン情報は不要なので削除
        del reservation["restaurant"]
        # ユーザーIDからユーザー情報を取得
        user_name = auth.get_user(reservation["user"]).display_name
        del reservation["user"]
        reservation["userName"] = user_name
        # tablesはreference型なので、それを取得してdictに変換
        reservation["tables"] = [
            {"tableType": table["tableType"].get().to_dict(), "tableCount": table["tableCount"]}
            for table
            in reservation["tables"]]
        res.append(reservation)
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
    client_refresh_token = request.cookies.get("refresh_token")
    new_access_token, new_refresh_token = refresh_token(client_refresh_token)
    response.set_cookie(key="access_token", value=new_access_token, httponly=True, secure=SECURE_COOKIE)
    response.set_cookie(key="refresh_token", value=new_refresh_token, httponly=True, secure=SECURE_COOKIE)
    return {"message": "Token refreshed"}


@app.post("/api/restaurant/tables/{table_id}/vacancy/{action}")
def update_vacancy(action: Literal["increment", "decrement"], table_id: str,
                   session_info: Tuple[str, str] = Depends(verify_token)):
    restaurant_id, role = session_info
    if action == "increment":
        diff = 1
    else:
        diff = -1
    restaurant_ref = db.collection("restaurants").document(restaurant_id)
    table_ref = restaurant_ref.collection("tableTypes").document(table_id)
    # noinspection PyUnresolvedReferences
    table_ref.update({"vacancy": firestore.Increment(diff)})
    # noinspection PyUnresolvedReferences
    restaurant_ref.update({"sumOfVacancy": firestore.Increment(diff)})
    return {"message": "Vacancy updated"}


@app.post("/webhook")
def firebase_webhook(request: Request, body: ReservationChangedWebhookPayload = Depends(verify_hmac_signature)):
    """
    Webhook for reservation change on Firestore
    :param request:
    :param body:
    :return:
    """
    # todo: implement the webhook logics for other change types
    if body.changeType == "create":
        restaurant_id = body.afterData["restaurant"]["id"]
        set_update_flag(restaurant_id)
    return {"message": "Webhook received"}


@app.get("/{_full_path:path}")
async def serve_app(response: Response, _full_path: str):
    return generate_react_response(response)

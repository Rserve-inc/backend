from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import dataset
import jwt
from fastapi import HTTPException, Request
from jwt import PyJWTError

import envs
from classes import Role

SECRET_KEY = envs.SESSION_SECRET
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30
REFRESH_TOKEN_RENEW_DAYS = 7
db: dataset.Database = dataset.connect(envs.DB_URL)
accounts_table: dataset.Table = db["admin_accounts"]


def get_password_hash(password: str) -> str:
    """
    与えられたパスワードをハッシュ化する

    :param password: ハッシュ化する平文のパスワード
    :return: ハッシュ化されたパスワード
    """
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(restaurant_id: str, plain_password: str) -> bool:
    """
    平文のパスワードとハッシュ化されたパスワードを比較して検証する

    :param restaurant_id: 検証するアカウントのID
    :param plain_password: 検証する平文のパスワード
    :return: パスワードが一致すればTrue、そうでなければFalse
    """
    hashed_password = accounts_table.find_one(restaurant_id=restaurant_id)["hashed_pw"]
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def verify_token(request: Request) -> Optional[tuple[str, Role]]:
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=403, detail="Token not found")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        restaurant_id: str = payload.get("sub")
        role: Role = payload.get("role")
        if None in (restaurant_id, role):
            raise HTTPException(status_code=403, detail="Invalid token")
        return restaurant_id, role
    except PyJWTError:
        raise HTTPException(status_code=403, detail="Could not validate credentials")


def refresh_token(client_refresh_token: str) -> tuple[str, str]:
    if not client_refresh_token:
        raise HTTPException(status_code=403, detail="Refresh token not found")

    try:
        payload = jwt.decode(client_refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        # renew refresh token when the expiry is close
        if payload["exp"] - datetime.utcnow() < timedelta(days=REFRESH_TOKEN_RENEW_DAYS):
            new_refresh_token = create_refresh_token(data={"sub": payload["sub"], "role": payload["role"]})
        else:
            new_refresh_token = client_refresh_token
        new_access_token = create_access_token(data={"sub": payload["sub"], "role": payload["role"]})
        return new_access_token, new_refresh_token
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=403, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=403, detail="Invalid refresh token")


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

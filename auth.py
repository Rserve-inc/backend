from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import HTTPException, Request
from jwt import PyJWTError

import envs
from classes import Role

SECRET_KEY = envs.SESSION_SECRET
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 30


def verify_token(request: Request) -> Optional[str, str]:
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


def refresh_token(refresh_token_str: str):
    if not refresh_token_str:
        raise HTTPException(status_code=403, detail="Refresh token not found")

    try:
        payload = jwt.decode(refresh_token_str, SECRET_KEY, algorithms=[ALGORITHM])
        new_access_token = create_access_token(data={"sub": payload["sub"]})
        return new_access_token
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

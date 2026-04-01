"""
JWT helpers for Socket.IO + REST alignment.

- Staff: same HS256 tokens as Flask-JWT-Extended (`sub` = Mongo user id).
- Patient/guest: `typ: "room"` tokens with `sub` = stable participant key for DM channels.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt
from constants import Constants


def _secret() -> str:
    return (
        os.environ.get("JWT_SECRET_KEY")
        or getattr(Constants, "JWT_SECRET", None)
        or "dev-only-set-JWT_SECRET_KEY-in-production"
    )


ROOM_TOKEN_TTL_HOURS = 72


def create_room_token(room_name: str, role: str, username: str) -> str:
    """Short-lived token for patient/guest; `sub` is deterministic per room+role+label."""
    pid = hashlib.sha256(f"{room_name}|{role}|{username}".encode()).hexdigest()[:32]
    now = datetime.now(timezone.utc)
    payload: Dict[str, Any] = {
        "typ": "room",
        "room_name": room_name,
        "role": role,
        "username": username,
        "sub": pid,
        "exp": now + timedelta(hours=ROOM_TOKEN_TTL_HOURS),
        "iat": now,
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")


def decode_socket_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode HS256 JWT from Flask-JWT-Extended or `create_room_token`."""
    if not token or not isinstance(token, str):
        return None
    try:
        return jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def is_room_token(payload: Dict[str, Any]) -> bool:
    return payload.get("typ") == "room"

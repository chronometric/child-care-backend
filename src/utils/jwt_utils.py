# Deprecated: use Flask-JWT-Extended + src.utils.socket_tokens for all JWT operations.
# Kept for accidental imports; delegates to the same secret as the rest of the app.
import os
import jwt
from constants import Constants


def _secret():
    return (
        os.environ.get("JWT_SECRET_KEY")
        or getattr(Constants, "JWT_SECRET", None)
        or "dev-only-set-JWT_SECRET_KEY-in-production"
    )


def generate_token(data: dict) -> str:
    return jwt.encode(data, _secret(), algorithm="HS256")


def verify_token(token: str):
    try:
        return jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None

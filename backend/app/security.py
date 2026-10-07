from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from passlib.context import CryptContext

from app.config import (
    DEFAULT_JWT_SECRET,
    JWT_ALGORITHM,
    JWT_EXPIRE_MINUTES,
    JWT_MIN_SECRET_CHARS,
    JWT_SECRET_KEY,
)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return _pwd_context.verify(plain_password, hashed_password)


def normalize_email(email: str) -> str:
    """The one form emails are compared and stored in: trimmed and lower-case."""
    return email.strip().lower()


def insecure_secret_problem(secret: str) -> Optional[str]:
    """Why `secret` can't be trusted to sign tokens, or None if it is fine."""
    if secret == DEFAULT_JWT_SECRET:
        return "JWT_SECRET_KEY is the built-in default, which anyone can read in the source code."
    if len(secret) < JWT_MIN_SECRET_CHARS:
        return f"JWT_SECRET_KEY is shorter than {JWT_MIN_SECRET_CHARS} characters."
    return None


class InvalidTokenError(Exception):
    pass


def create_access_token(subject: str, expires_minutes: Optional[int] = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes if expires_minutes is not None else JWT_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """Returns the subject (user id, as a string) encoded in the token.

    Raises InvalidTokenError for anything wrong with the token — expired,
    malformed, wrong signature — so callers have one exception to handle
    instead of needing to know jwt's internal exception hierarchy.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    subject = payload.get("sub")
    if subject is None:
        raise InvalidTokenError("Token has no subject")
    return subject

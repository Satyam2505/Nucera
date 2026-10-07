from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user
from app.security import create_access_token, hash_password, normalize_email, verify_password
from app.services.login_limiter import limiter

router = APIRouter(prefix="/auth", tags=["auth"])


def _find_user(db: Session, email: str):
    """The account for `email`, matched without regard to capitalisation (accounts made
    before emails were lower-cased may still be stored with capitals)."""
    return db.query(models.User).filter(func.lower(models.User.email) == normalize_email(email)).first()


@router.post("/register", response_model=schemas.UserOut)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    if _find_user(db, payload.email):
        raise HTTPException(status_code=400, detail="An account with this email already exists")

    user = models.User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=schemas.Token)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2PasswordRequestForm's field is called "username" regardless of
    # what it actually represents here — we use it as the email.
    email = normalize_email(form_data.username)
    ip = request.client.host if request.client else "unknown"

    wait = limiter.check(ip, email)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed sign-in attempts. Try again in {wait} seconds.",
            headers={"Retry-After": str(wait)},
        )

    user = _find_user(db, email)
    if not user or not verify_password(form_data.password, user.hashed_password):
        # Unknown emails count too, so the limit can't be used to tell which exist.
        limiter.record_failure(ip, email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    limiter.record_success(ip, email)
    token = create_access_token(subject=str(user.id))
    return schemas.Token(access_token=token)


@router.get("/me", response_model=schemas.UserOut)
def read_current_user(current_user: models.User = Depends(get_current_user)):
    return current_user

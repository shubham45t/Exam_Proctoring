from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.service import AuthService
from app.api.deps import CurrentUser, get_current_user, get_db, require_role

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    user_id: str
    username: str
    full_name: str
    role: str
    is_active: bool


class LoginResponse(BaseModel):
    token: str
    user: UserOut


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=100)
    full_name: str = Field(min_length=1, max_length=100)
    role: str = Field(pattern="^(admin|proctor|auditor)$")


@router.post("/seed")
def seed_users(db: Session = Depends(get_db)):
    """Initialize default admin/proctor/auditor accounts if absent."""
    AuthService.ensure_default_users(db)
    return {"ok": True, "message": "Default users initialized."}


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    # Ensure default users exist so initial login works out of the box
    AuthService.ensure_default_users(db)
    res = AuthService.authenticate(db, body.username, body.password)
    if not res:
        raise HTTPException(
            status_code=401,
            detail={"code": "INVALID_CREDENTIALS", "message": "Invalid username or password."},
        )
    user, token = res
    return LoginResponse(
        token=token,
        user=UserOut(
            user_id=user.user_id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
        ),
    )


@router.get("/me", response_model=UserOut)
def me(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    user = AuthService.get_by_id(db, current.user_id)
    if user:
        return UserOut(
            user_id=user.user_id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
        )
    return UserOut(
        user_id=current.user_id,
        username=current.username,
        full_name=current.full_name,
        role=current.role,
        is_active=True,
    )


@router.get("/users", response_model=list[UserOut])
def list_users(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)):
    AuthService.ensure_default_users(db)
    users = AuthService.list_users(db)
    return [
        UserOut(
            user_id=u.user_id,
            username=u.username,
            full_name=u.full_name,
            role=u.role,
            is_active=u.is_active,
        )
        for u in users
    ]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    body: CreateUserRequest,
    current: CurrentUser = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    try:
        user = AuthService.create_user(db, body.username, body.password, body.full_name, body.role)
        return UserOut(
            user_id=user.user_id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail={"code": "USER_EXISTS", "message": str(e)})

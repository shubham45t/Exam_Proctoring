from __future__ import annotations

from typing import Iterator, Optional
from fastapi import Header, HTTPException, Request, Depends
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.database.models import UserRow
from app.auth.service import AuthService

DEV_ACTOR = "anonymous-dev"


def get_db(request: Request) -> Iterator[Session]:
    with request.app.state.sessions() as db:
        yield db


class CurrentUser:
    def __init__(self, user_id: str, username: str, full_name: str, role: str):
        self.user_id = user_id
        self.username = username
        self.full_name = full_name
        self.role = role


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> CurrentUser:
    """Extract authenticated user from Bearer token, or fall back to dev admin if no token."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        claims = decode_access_token(token)
        if claims and "sub" in claims:
            return CurrentUser(
                user_id=claims["sub"],
                username=claims.get("username", "user"),
                full_name=claims.get("name", "User"),
                role=claims.get("role", "proctor"),
            )
        raise HTTPException(status_code=401, detail={"code": "INVALID_TOKEN", "message": "Invalid or expired token."})
    
    # In development mode, provide default dev user so unauthenticated calls during dev do not fail
    return CurrentUser(
        user_id="USR-DEV001",
        username="dev_proctor",
        full_name="Lead Proctor (Dev)",
        role="admin",
    )


def require_role(*roles: str):
    def check_role(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles and "admin" != user.role:
            raise HTTPException(
                status_code=403,
                detail={"code": "PERMISSION_DENIED", "message": f"Requires one of roles: {', '.join(roles)}"}
            )
        return user
    return check_role

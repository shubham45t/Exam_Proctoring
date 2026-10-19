"""User management and authentication service."""
from __future__ import annotations

import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import create_access_token, hash_password, verify_password
from app.database.models import UserRow
from app.schemas.events import utcnow


class AuthService:
    @staticmethod
    def ensure_default_users(db: Session) -> None:
        """Seed default admin, proctor, and auditor if user table is empty."""
        count = db.scalar(select(UserRow).limit(1))
        if count is not None:
            return

        defaults = [
            ("USR-ADMIN001", "admin", "admin123", "Chief Proctor Admin", "admin"),
            ("USR-PROC001", "proctor", "proctor123", "Dr. Jane Smith (Proctor)", "proctor"),
            ("USR-AUDIT01", "auditor", "auditor123", "Academic Integrity Auditor", "auditor"),
        ]
        for uid, uname, pwd, name, role in defaults:
            row = UserRow(
                user_id=uid,
                username=uname,
                password_hash=hash_password(pwd),
                full_name=name,
                role=role,
                is_active=True,
                created_at=utcnow(),
            )
            db.add(row)
        db.commit()

    @staticmethod
    def authenticate(db: Session, username: str, password: str) -> Optional[tuple[UserRow, str]]:
        """Verify username & password. Returns (user, token) or None."""
        user = db.scalar(select(UserRow).where(UserRow.username == username, UserRow.is_active == True))  # noqa: E712
        if not user or not verify_password(password, user.password_hash):
            return None
        token = create_access_token({"sub": user.user_id, "username": user.username, "role": user.role, "name": user.full_name})
        return user, token

    @staticmethod
    def get_by_id(db: Session, user_id: str) -> Optional[UserRow]:
        return db.get(UserRow, user_id)

    @staticmethod
    def list_users(db: Session) -> list[UserRow]:
        return list(db.scalars(select(UserRow).order_by(UserRow.created_at)).all())

    @staticmethod
    def create_user(db: Session, username: str, password: str, full_name: str, role: str) -> UserRow:
        user = UserRow(
            user_id=f"USR-{uuid.uuid4().hex[:10].upper()}",
            username=username,
            password_hash=hash_password(password),
            full_name=full_name,
            role=role,
            is_active=True,
            created_at=utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

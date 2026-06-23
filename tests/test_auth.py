"""Tests for services/auth.py — mock DB."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta, timezone
from jose import jwt
from fastapi import HTTPException

from backend.services.auth import hash_password, verify_password, create_token, get_current_user
from backend.config import get_settings
from backend.db.models import User

settings = get_settings()


class TestPasswordHashing:
    def test_produces_bcrypt_hash(self):
        h = hash_password("secret123")
        assert h.startswith("$2b$")

    def test_verify_correct(self):
        h = hash_password("mypassword")
        assert verify_password("mypassword", h)

    def test_verify_wrong(self):
        h = hash_password("mypassword")
        assert not verify_password("wrongpassword", h)


class TestCreateToken:
    def test_decodable_jwt(self):
        token = create_token(user_id=42, username="alice")
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        assert payload["sub"] == "42"
        assert payload["username"] == "alice"
        assert "exp" in payload

    def test_expiry_set(self):
        token = create_token(user_id=1, username="bob")
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp > datetime.now(timezone.utc)


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        user = User(id=1, username="alice", email="a@b.com", hashed_password="x")
        db = AsyncMock()
        db.get = AsyncMock(return_value=user)
        token = create_token(1, "alice")
        creds = MagicMock()
        creds.credentials = token
        result = await get_current_user(credentials=creds, db=db)
        assert result.username == "alice"

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        db = AsyncMock()
        creds = MagicMock()
        creds.credentials = "not.a.valid.token"
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=creds, db=db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self):
        expired = jwt.encode(
            {"sub": "1", "username": "x", "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
            settings.jwt_secret, algorithm="HS256",
        )
        db = AsyncMock()
        creds = MagicMock()
        creds.credentials = expired
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=creds, db=db)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_user_not_found_raises_401(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)
        token = create_token(999, "ghost")
        creds = MagicMock()
        creds.credentials = token
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=creds, db=db)
        assert exc_info.value.status_code == 401

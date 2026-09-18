"""Local password recovery tests."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from app.core.security import TokenManager
from app.repositories import Repository


def manager(tmp_path) -> TokenManager:
    secret = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode("ascii")
    return TokenManager(SimpleNamespace(jwt_secret=secret), Repository(tmp_path / "users.db"))


def test_reset_password_updates_account_and_revokes_existing_tokens(tmp_path):
    tokens = manager(tmp_path)
    tokens.register("acceptance", "old-pass", "ADMIN")
    old_pair = tokens.login("acceptance", "old-pass")

    result = tokens.reset_password("acceptance", "new-pass", "ADMIN")

    assert result["action"] == "updated"
    with pytest.raises(ValueError, match="Invalid username or password"):
        tokens.login("acceptance", "old-pass")
    assert tokens.login("acceptance", "new-pass")["token"]
    old_claims = tokens._decode(old_pair["token"])
    assert not tokens.repository.users.token_active(str(old_claims["tokenId"]), "access")


def test_reset_password_can_create_missing_admin(tmp_path):
    tokens = manager(tmp_path)

    result = tokens.reset_password("acceptance", "new-pass", "ADMIN", create=True)

    assert result["action"] == "created"
    assert result["role"] == "ADMIN"
    assert tokens.login("acceptance", "new-pass")["token"]

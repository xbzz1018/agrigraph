"""Reset a local account without exposing the password on the command line."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.core.security import TokenManager
from app.core.settings import Settings
from app.repositories import Repository


def _load_environment() -> None:
    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(project_root / ".env.ai", override=False)
    load_dotenv(project_root / "backend-python" / ".env", override=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or reset a local AgriGraph account.")
    parser.add_argument("--username", default=os.getenv("AGRIGRAPH_RESET_USERNAME", ""))
    parser.add_argument("--role", choices=("USER", "ADMIN"), default=None)
    parser.add_argument("--create", action="store_true")
    args = parser.parse_args()
    password = os.getenv("AGRIGRAPH_RESET_PASSWORD", "")
    username = args.username.strip()
    if not username or not password:
        parser.error("Set AGRIGRAPH_RESET_USERNAME/--username and AGRIGRAPH_RESET_PASSWORD")
    if len(password) < 6:
        parser.error("AGRIGRAPH_RESET_PASSWORD must contain at least 6 characters")

    _load_environment()
    settings = Settings.from_env()
    manager = TokenManager(settings, Repository(settings.db_path))
    result = manager.reset_password(username, password, args.role, create=args.create)
    print(
        json.dumps(
            {"username": result["username"], "role": result["role"], "action": result["action"]},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

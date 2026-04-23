import json
import os
from pathlib import Path
from typing import Optional

from itsdangerous import BadSignature, URLSafeSerializer

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / 'config'
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
USERS_FILE = CONFIG_DIR / 'users.json'


def get_serializer() -> URLSafeSerializer:
    secret = os.getenv('APP_SECRET_KEY', 'change-me-in-production')
    return URLSafeSerializer(secret, salt='internal-chat-session')


def load_users() -> list[dict]:
    if not USERS_FILE.exists():
        USERS_FILE.write_text(
            json.dumps(
                [
                    {'username': 'admin', 'password': 'admin123', 'display_name': 'Administrator'},
                    {'username': 'maria', 'password': 'maria123', 'display_name': 'María'},
                    {'username': 'juan', 'password': 'juan123', 'display_name': 'Juan'},
                ],
                indent=2,
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
    with USERS_FILE.open('r', encoding='utf-8') as f:
        return json.load(f)


def authenticate_user(username: str, password: str) -> Optional[dict]:
    for user in load_users():
        if user['username'] == username and user['password'] == password:
            return user
    return None


def create_session_token(user: dict) -> str:
    return get_serializer().dumps(
        {
            'username': user['username'],
            'display_name': user.get('display_name') or user['username'],
        }
    )


def read_session_token(token: str | None) -> Optional[dict]:
    if not token:
        return None
    try:
        return get_serializer().loads(token)
    except BadSignature:
        return None

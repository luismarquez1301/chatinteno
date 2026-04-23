import json
import logging
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .auth import authenticate_user, create_session_token, read_session_token
from .db import db_cursor
from .models import CreateChannelRequest, LoginRequest

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=os.getenv('LOG_LEVEL', 'INFO').upper(),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'app.log', encoding='utf-8'),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger('internal-chat')

app = FastAPI(title='Internal Chat', version='1.0.0')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

templates = Jinja2Templates(directory=str(BASE_DIR / 'app' / 'templates'))
app.mount('/static', StaticFiles(directory=str(BASE_DIR / 'app' / 'static')), name='static')


class ConnectionManager:
    def __init__(self) -> None:
        self.channel_connections: dict[int, set[WebSocket]] = defaultdict(set)
        self.user_connections: dict[str, set[WebSocket]] = defaultdict(set)
        self.user_profiles: dict[str, dict[str, str]] = {}

    async def connect(self, websocket: WebSocket, user: dict[str, str], channel_id: int) -> None:
        await websocket.accept()
        self.channel_connections[channel_id].add(websocket)
        self.user_connections[user['username']].add(websocket)
        self.user_profiles[user['username']] = user

    def disconnect(self, websocket: WebSocket, user: dict[str, str], channel_id: int) -> None:
        self.channel_connections[channel_id].discard(websocket)
        if not self.channel_connections[channel_id]:
            self.channel_connections.pop(channel_id, None)

        user_set = self.user_connections.get(user['username'], set())
        user_set.discard(websocket)
        if not user_set:
            self.user_connections.pop(user['username'], None)

    async def broadcast_to_channel(self, channel_id: int, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for connection in list(self.channel_connections.get(channel_id, set())):
            try:
                await connection.send_text(json.dumps(payload, ensure_ascii=False, default=str))
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.channel_connections[channel_id].discard(connection)

    def online_users(self) -> list[dict[str, str]]:
        return [
            {
                'username': username,
                'display_name': self.user_profiles.get(username, {}).get('display_name', username),
            }
            for username in sorted(self.user_connections.keys())
        ]


manager = ConnectionManager()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.on_event('startup')
def startup() -> None:
    with db_cursor() as cur:
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            '''
        )
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                display_name TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE
            )
            '''
        )
        cur.execute('SELECT COUNT(*) AS total FROM channels')
        total = cur.fetchone()['total']
        if total == 0:
            for channel_name in ['general', 'anuncios']:
                cur.execute(
                    'INSERT INTO channels (name, created_at) VALUES (?, ?)',
                    (channel_name, utc_now_iso()),
                )
    logger.info('Application started and database initialized')


@app.middleware('http')
async def log_requests(request: Request, call_next):
    response = await call_next(request)
    logger.info('%s %s -> %s', request.method, request.url.path, response.status_code)
    return response


@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse('index.html', {'request': request})


@app.post('/api/login')
async def login(payload: LoginRequest):
    user = authenticate_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Credenciales inválidas')

    token = create_session_token(user)
    response = JSONResponse(
        {
            'ok': True,
            'user': {
                'username': user['username'],
                'display_name': user.get('display_name') or user['username'],
            },
        }
    )
    response.set_cookie(
        key='session_token',
        value=token,
        httponly=True,
        samesite='lax',
        secure=os.getenv('COOKIE_SECURE', 'false').lower() == 'true',
        max_age=60 * 60 * 12,
    )
    return response


@app.post('/api/logout')
async def logout():
    response = JSONResponse({'ok': True})
    response.delete_cookie('session_token')
    return response


@app.get('/api/me')
async def me(request: Request):
    user = read_session_token(request.cookies.get('session_token'))
    if not user:
        raise HTTPException(status_code=401, detail='No autenticado')
    return {'user': user}


@app.get('/api/channels')
async def list_channels(request: Request):
    user = read_session_token(request.cookies.get('session_token'))
    if not user:
        raise HTTPException(status_code=401, detail='No autenticado')

    with db_cursor() as cur:
        cur.execute('SELECT id, name, created_at FROM channels ORDER BY name ASC')
        channels = [dict(row) for row in cur.fetchall()]
    return {'channels': channels}


@app.post('/api/channels')
async def create_channel(payload: CreateChannelRequest, request: Request):
    user = read_session_token(request.cookies.get('session_token'))
    if not user:
        raise HTTPException(status_code=401, detail='No autenticado')

    channel_name = payload.name.strip().lower().replace(' ', '-')
    with db_cursor() as cur:
        try:
            cur.execute(
                'INSERT INTO channels (name, created_at) VALUES (?, ?)',
                (channel_name, utc_now_iso()),
            )
        except Exception as exc:
            logger.warning('Channel creation error: %s', exc)
            raise HTTPException(status_code=400, detail='No se pudo crear el canal')
        channel_id = cur.lastrowid

    return {'channel': {'id': channel_id, 'name': channel_name}}


@app.get('/api/channels/{channel_id}/messages')
async def channel_messages(channel_id: int, request: Request, limit: int = 100):
    user = read_session_token(request.cookies.get('session_token'))
    if not user:
        raise HTTPException(status_code=401, detail='No autenticado')

    safe_limit = max(1, min(limit, 200))
    with db_cursor() as cur:
        cur.execute(
            '''
            SELECT id, channel_id, username, display_name, content, created_at
            FROM messages
            WHERE channel_id = ?
            ORDER BY id DESC
            LIMIT ?
            ''',
            (channel_id, safe_limit),
        )
        rows = [dict(row) for row in cur.fetchall()]
    rows.reverse()
    return {'messages': rows}


@app.get('/api/presence')
async def presence(request: Request):
    user = read_session_token(request.cookies.get('session_token'))
    if not user:
        raise HTTPException(status_code=401, detail='No autenticado')
    return {'online_users': manager.online_users()}


@app.websocket('/ws/{channel_id}')
async def websocket_endpoint(websocket: WebSocket, channel_id: int):
    token = websocket.cookies.get('session_token')
    user = read_session_token(token)
    if not user:
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, user, channel_id)
    await manager.broadcast_to_channel(
        channel_id,
        {
            'type': 'presence',
            'online_users': manager.online_users(),
        },
    )

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            message_type = data.get('type')

            if message_type == 'message':
                content = (data.get('content') or '').strip()
                if not content:
                    await websocket.send_text(json.dumps({'type': 'error', 'detail': 'Mensaje vacío'}))
                    continue
                if len(content) > 2000:
                    await websocket.send_text(json.dumps({'type': 'error', 'detail': 'Mensaje demasiado largo'}))
                    continue

                with db_cursor() as cur:
                    cur.execute(
                        '''
                        INSERT INTO messages (channel_id, username, display_name, content, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        ''',
                        (channel_id, user['username'], user['display_name'], content, utc_now_iso()),
                    )
                    message_id = cur.lastrowid
                    cur.execute(
                        'SELECT id, channel_id, username, display_name, content, created_at FROM messages WHERE id = ?',
                        (message_id,),
                    )
                    row = dict(cur.fetchone())

                await manager.broadcast_to_channel(
                    channel_id,
                    {
                        'type': 'message',
                        'message': row,
                    },
                )
            elif message_type == 'ping':
                await websocket.send_text(json.dumps({'type': 'pong'}))
            else:
                await websocket.send_text(json.dumps({'type': 'error', 'detail': 'Tipo de evento no soportado'}))
    except WebSocketDisconnect:
        manager.disconnect(websocket, user, channel_id)
        await manager.broadcast_to_channel(
            channel_id,
            {
                'type': 'presence',
                'online_users': manager.online_users(),
            },
        )
    except Exception as exc:
        logger.exception('WebSocket error: %s', exc)
        manager.disconnect(websocket, user, channel_id)
        try:
            await manager.broadcast_to_channel(
                channel_id,
                {
                    'type': 'presence',
                    'online_users': manager.online_users(),
                },
            )
        except Exception:
            pass


@app.get('/health')
async def health():
    return {'ok': True, 'service': 'internal-chat'}

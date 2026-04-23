# Internal Chat App

Aplicación de mensajería interna simple, tipo chat corporativo ligero.

## Características

- Login con usuario y contraseña definidos en `config/users.json`
- FastAPI + WebSockets
- Frontend simple en HTML/CSS/JavaScript
- Canales básicos
- Historial persistente en SQLite
- Lista de usuarios conectados
- Notificaciones de escritorio desde el navegador
- Logs simples a archivo y consola

## Estructura

```text
internal-chat-app/
├── app/
│   ├── auth.py
│   ├── db.py
│   ├── main.py
│   ├── models.py
│   ├── static/
│   │   ├── app.js
│   │   └── styles.css
│   └── templates/
│       └── index.html
├── config/
│   └── users.json                # se crea automáticamente al primer arranque
├── data/
│   └── chat.db                   # se crea automáticamente al primer arranque
├── logs/
│   └── app.log                   # se crea automáticamente al primer arranque
├── deploy/
│   ├── internal-chat.service
│   └── nginx.internal-chat.conf
├── scripts/
│   └── start.sh
├── .env.example
├── requirements.txt
└── README.md
```

## Requisitos

- Ubuntu 22.04 o 24.04
- Python 3.11 o superior recomendado
- Acceso a red local si quieres usarlo desde otras PCs

## Instalación paso a paso en Ubuntu

### 1) Instalar paquetes del sistema

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx
```

Si no vas a usar Nginx de entrada, puedes omitirlo.

### 2) Copiar la aplicación al servidor

Ejemplo:

```bash
sudo mkdir -p /opt/internal-chat
sudo cp -r . /opt/internal-chat
sudo chown -R www-data:www-data /opt/internal-chat
cd /opt/internal-chat
```

### 3) Crear entorno virtual e instalar dependencias

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4) Configurar variables de entorno

```bash
cp .env.example .env
nano .env
```

Contenido recomendado:

```env
APP_SECRET_KEY=pon-aqui-una-clave-larga-y-unica
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
COOKIE_SECURE=false
```

Notas:

- `APP_SECRET_KEY` firma la cookie de sesión.
- Usa una clave larga y aleatoria en producción.
- Si publicas la app bajo HTTPS, cambia `COOKIE_SECURE=true`.

### 5) Definir usuarios

El archivo `config/users.json` se crea solo al primer arranque con usuarios de ejemplo:

```json
[
  {"username": "admin", "password": "admin123", "display_name": "Administrator"},
  {"username": "maria", "password": "maria123", "display_name": "María"},
  {"username": "juan", "password": "juan123", "display_name": "Juan"}
]
```

Puedes editarlo después:

```bash
nano /opt/internal-chat/config/users.json
```

## Ejecución manual

```bash
cd /opt/internal-chat
source .venv/bin/activate
./scripts/start.sh
```

O directamente:

```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Luego abre:

```text
http://IP_DEL_SERVIDOR:8000
```

## Ejecutar en background con systemd

### 1) Copiar el service file

```bash
sudo cp deploy/internal-chat.service /etc/systemd/system/internal-chat.service
sudo systemctl daemon-reload
sudo systemctl enable internal-chat
sudo systemctl start internal-chat
```

### 2) Ver estado

```bash
sudo systemctl status internal-chat
```

### 3) Ver logs

```bash
sudo journalctl -u internal-chat -f
```

## Configuración opcional con Nginx como reverse proxy

### 1) Copiar configuración

```bash
sudo cp deploy/nginx.internal-chat.conf /etc/nginx/sites-available/internal-chat
sudo ln -s /etc/nginx/sites-available/internal-chat /etc/nginx/sites-enabled/internal-chat
```

### 2) Validar y reiniciar

```bash
sudo nginx -t
sudo systemctl restart nginx
```

### 3) Acceso

Ahora podrás entrar por:

```text
http://IP_DEL_SERVIDOR/
```

## Acceso desde otros equipos de la red

### 1) Obtener la IP del servidor

```bash
hostname -I
```

### 2) Abrir el puerto en firewall si usas UFW

Sin Nginx:

```bash
sudo ufw allow 8000/tcp
```

Con Nginx:

```bash
sudo ufw allow 'Nginx Full'
```

### 3) Entrar desde otra PC

- Con uvicorn directo: `http://IP_DEL_SERVIDOR:8000`
- Con Nginx: `http://IP_DEL_SERVIDOR`

## Cómo funciona la app

- El usuario inicia sesión con una cookie firmada.
- El frontend abre un WebSocket al canal actual.
- Cada mensaje se guarda en SQLite.
- Los mensajes nuevos se emiten en tiempo real a los usuarios conectados al canal.
- La presencia se mantiene en memoria del proceso.

## Notificaciones de escritorio

- El botón `Activar notificaciones` solicita permiso al navegador.
- Si el permiso es concedido, los mensajes nuevos generan una notificación cuando la pestaña no está visible o no tiene foco.
- En algunos navegadores, las notificaciones requieren HTTPS o `localhost`.

## Manejo básico de errores

- Login inválido devuelve 401.
- Mensajes vacíos o demasiado largos se rechazan.
- Reconexión automática del WebSocket si se corta la conexión.
- Logs HTTP y de errores en `logs/app.log`.

## Mejoras futuras recomendadas

- Hash de contraseñas en vez de texto plano
- Roles de usuario
- Edición o borrado de mensajes
- Indicador de mensajes no leídos
- Buscador simple
- Canal privado o mensajes directos
- HTTPS con Let's Encrypt si se expone fuera de la LAN

## Observaciones operativas

- Está pensada para un equipo pequeño y un solo proceso.
- La presencia en línea vive en memoria; si reinicias el proceso, esa presencia se recalcula al reconectar.
- SQLite es suficiente para este escenario pequeño.

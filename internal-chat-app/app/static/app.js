const state = {
  user: null,
  channels: [],
  currentChannelId: null,
  socket: null,
  notificationsEnabled: false,
};

const loginView = document.getElementById('login-view');
const chatView = document.getElementById('chat-view');
const loginForm = document.getElementById('login-form');
const loginError = document.getElementById('login-error');
const channelsList = document.getElementById('channels-list');
const onlineUsers = document.getElementById('online-users');
const channelTitle = document.getElementById('channel-title');
const messagesEl = document.getElementById('messages');
const messageForm = document.getElementById('message-form');
const messageInput = document.getElementById('message-input');
const currentUser = document.getElementById('current-user');
const connectionStatus = document.getElementById('connection-status');
const logoutBtn = document.getElementById('logout-btn');
const notificationsBtn = document.getElementById('notifications-btn');
const createChannelForm = document.getElementById('create-channel-form');
const newChannelName = document.getElementById('new-channel-name');

function escapeHtml(unsafe) {
  const div = document.createElement('div');
  div.textContent = unsafe;
  return div.innerHTML;
}

function setConnectedStatus(isOnline) {
  connectionStatus.textContent = isOnline ? 'Conectado' : 'Reconectando';
  connectionStatus.classList.toggle('online', isOnline);
  connectionStatus.classList.toggle('offline', !isOnline);
}

function showView(isAuthenticated) {
  loginView.classList.toggle('hidden', isAuthenticated);
  chatView.classList.toggle('hidden', !isAuthenticated);
}

function formatTime(ts) {
  const date = new Date(ts);
  return new Intl.DateTimeFormat('es-AR', {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

function renderChannels() {
  channelsList.innerHTML = '';
  state.channels.forEach((channel) => {
    const el = document.createElement('div');
    el.className = 'channel-item' + (channel.id === state.currentChannelId ? ' active' : '');
    el.textContent = `# ${channel.name}`;
    el.onclick = () => switchChannel(channel.id);
    channelsList.appendChild(el);
  });
}

function renderOnlineUsers(users) {
  onlineUsers.innerHTML = '';
  users.forEach((user) => {
    const el = document.createElement('div');
    el.className = 'user-item';
    el.textContent = user.display_name || user.username;
    onlineUsers.appendChild(el);
  });
}

function appendMessage(message) {
  const wrapper = document.createElement('div');
  wrapper.className = 'message';
  wrapper.innerHTML = `
    <div class="message-header">
      <span class="message-author">${escapeHtml(message.display_name)}</span>
      <span class="message-time">${formatTime(message.created_at)}</span>
    </div>
    <div class="message-body">${escapeHtml(message.content)}</div>
  `;
  messagesEl.appendChild(wrapper);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

async function loadMessages(channelId) {
  messagesEl.innerHTML = '';
  const response = await fetch(`/api/channels/${channelId}/messages`);
  if (!response.ok) {
    messagesEl.innerHTML = '<div class="message">No se pudo cargar el historial.</div>';
    return;
  }
  const data = await response.json();
  data.messages.forEach(appendMessage);
}

async function loadPresence() {
  const response = await fetch('/api/presence');
  if (!response.ok) return;
  const data = await response.json();
  renderOnlineUsers(data.online_users || []);
}

function maybeNotify(message) {
  if (!state.notificationsEnabled) return;
  if (!('Notification' in window)) return;
  if (Notification.permission !== 'granted') return;
  if (document.visibilityState === 'visible' && document.hasFocus()) return;
  if (message.username === state.user.username) return;

  new Notification(`${message.display_name} en ${channelTitle.textContent}`, {
    body: message.content,
    tag: `channel-${message.channel_id}`,
  });
}

function connectSocket(channelId) {
  if (state.socket) {
    state.socket.onclose = null;
    state.socket.close();
  }

  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/${channelId}`);
  state.socket = socket;

  socket.onopen = () => setConnectedStatus(true);
  socket.onclose = () => {
    setConnectedStatus(false);
    setTimeout(() => {
      if (state.currentChannelId === channelId) connectSocket(channelId);
    }, 2000);
  };
  socket.onerror = () => setConnectedStatus(false);

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'message') {
      appendMessage(data.message);
      maybeNotify(data.message);
    } else if (data.type === 'presence') {
      renderOnlineUsers(data.online_users || []);
    } else if (data.type === 'error') {
      console.error(data.detail);
    }
  };
}

async function switchChannel(channelId) {
  state.currentChannelId = channelId;
  const channel = state.channels.find((item) => item.id === channelId);
  channelTitle.textContent = `#${channel.name}`;
  renderChannels();
  await loadMessages(channelId);
  connectSocket(channelId);
}

async function loadChannels() {
  const response = await fetch('/api/channels');
  if (!response.ok) throw new Error('No se pudieron cargar los canales');
  const data = await response.json();
  state.channels = data.channels || [];
  renderChannels();
  if (!state.currentChannelId && state.channels.length) {
    await switchChannel(state.channels[0].id);
  }
}

async function bootstrap() {
  const response = await fetch('/api/me');
  if (!response.ok) {
    showView(false);
    return;
  }
  const data = await response.json();
  state.user = data.user;
  currentUser.textContent = `Conectado como ${state.user.display_name}`;
  showView(true);
  await loadChannels();
  await loadPresence();
}

loginForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  loginError.textContent = '';
  const payload = {
    username: document.getElementById('username').value.trim(),
    password: document.getElementById('password').value,
  };
  const response = await fetch('/api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: 'Error de autenticación' }));
    loginError.textContent = data.detail || 'No se pudo iniciar sesión';
    return;
  }
  const data = await response.json();
  state.user = data.user;
  currentUser.textContent = `Conectado como ${state.user.display_name}`;
  showView(true);
  await loadChannels();
  await loadPresence();
});

messageForm.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = messageInput.value.trim();
  if (!text || !state.socket || state.socket.readyState !== WebSocket.OPEN) return;
  state.socket.send(JSON.stringify({ type: 'message', content: text }));
  messageInput.value = '';
});

logoutBtn.addEventListener('click', async () => {
  await fetch('/api/logout', { method: 'POST' });
  if (state.socket) state.socket.close();
  state.socket = null;
  state.user = null;
  state.currentChannelId = null;
  messagesEl.innerHTML = '';
  channelsList.innerHTML = '';
  onlineUsers.innerHTML = '';
  showView(false);
});

notificationsBtn.addEventListener('click', async () => {
  if (!('Notification' in window)) {
    alert('Este navegador no soporta notificaciones de escritorio.');
    return;
  }
  const permission = await Notification.requestPermission();
  state.notificationsEnabled = permission === 'granted';
  notificationsBtn.textContent = state.notificationsEnabled ? 'Notificaciones activadas' : 'Activar notificaciones';
});

createChannelForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const name = newChannelName.value.trim();
  if (!name) return;
  const response = await fetch('/api/channels', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) {
    alert('No se pudo crear el canal');
    return;
  }
  newChannelName.value = '';
  await loadChannels();
});

window.addEventListener('beforeunload', () => {
  if (state.socket) state.socket.close();
});

bootstrap();

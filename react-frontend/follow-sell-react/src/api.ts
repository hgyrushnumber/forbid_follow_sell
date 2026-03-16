// 开发环境通过Vite代理转发到后端，生产环境应配置为实际后端地址
export const API_BASE = '';

export type AuthUser = {
  id: string;
  username: string;
  daily_limit: number;
  today_used?: number;
  today_remaining?: number;
};

function getAuthHeader(token: string) {
  return { Authorization: `Bearer ${token}` };
}

async function parseJson(res: Response) {
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || '请求失败');
  }
  return res.json();
}

export async function register(username: string, password: string): Promise<{ token: string; user: AuthUser }> {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  return parseJson(res);
}

export async function login(username: string, password: string): Promise<{ token: string; user: AuthUser }> {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  return parseJson(res);
}

export async function fetchMe(token: string): Promise<{ user: AuthUser }> {
  const res = await fetch(`${API_BASE}/api/auth/me`, {
    headers: {
      ...getAuthHeader(token),
    },
  });
  return parseJson(res);
}

export async function createTaskBySkuText(skuText: string, token: string) {
  const res = await fetch(`${API_BASE}/api/tasks`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeader(token),
    },
    body: JSON.stringify({ sku_text: skuText }),
  });
  return parseJson(res);
}

export async function fetchTasks(token: string) {
  const res = await fetch(`${API_BASE}/api/tasks`, {
    headers: {
      ...getAuthHeader(token),
    },
  });
  return parseJson(res);
}

export async function fetchActiveClients() {
  const res = await fetch(`${API_BASE}/api/clients/active`);
  return parseJson(res);
}

export async function createWechatQrSession(): Promise<{ login_url: string }> {
  const res = await fetch(`${API_BASE}/api/auth/wechat/qr`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
  });
  return parseJson(res);
}

export async function fetchWechatQrStatus(sessionId: string): Promise<{ status: string; token?: string; user?: AuthUser }> {
  const res = await fetch(`${API_BASE}/api/auth/wechat/status/${sessionId}`);
  return parseJson(res);
}

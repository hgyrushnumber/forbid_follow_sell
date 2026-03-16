import { useEffect, useMemo, useState } from 'react';
import {
  createTaskBySkuText,
  createWechatQrSession,
  fetchActiveClients,
  fetchMe,
  fetchTasks,
  fetchWechatQrStatus,
  type AuthUser,
  type AuthResult,
} from './api';
import './App.css';

const TOKEN_KEY = 'follow_sell_token';

type StoredAuthToken = {
  token: string;
  expiresAt: string;
};

function readStoredToken(): string {
  const raw = localStorage.getItem(TOKEN_KEY);
  if (!raw) return '';
  try {
    const parsed = JSON.parse(raw) as StoredAuthToken;
    if (!parsed?.token || !parsed?.expiresAt) {
      localStorage.removeItem(TOKEN_KEY);
      return '';
    }
    if (new Date(parsed.expiresAt).getTime() <= Date.now()) {
      localStorage.removeItem(TOKEN_KEY);
      return '';
    }
    return parsed.token;
  } catch {
    localStorage.removeItem(TOKEN_KEY);
    return '';
  }
}

function saveStoredToken(auth: AuthResult) {
  const payload: StoredAuthToken = { token: auth.token, expiresAt: auth.expires_at };
  localStorage.setItem(TOKEN_KEY, JSON.stringify(payload));
}

export default function ReactApp() {
  const [token, setToken] = useState<string>(() => readStoredToken());

  const [user, setUser] = useState<AuthUser | null>(null);
  const [skuText, setSkuText] = useState('');
  const [msg, setMsg] = useState('');
  const [tasks, setTasks] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const remaining = useMemo(() => {
    if (!user) return 0;
    return user.today_remaining ?? Math.max((user.daily_limit || 0) - (user.today_used || 0), 0);
  }, [user]);

  const refreshData = async (authToken: string) => {
    const [tasksRes, clientsRes, meRes] = await Promise.all([
      fetchTasks(authToken),
      fetchActiveClients(),
      fetchMe(authToken),
    ]);
    setTasks(tasksRes.items || []);
    setClients(clientsRes.items || []);
    setUser(meRes.user || null);
  };

  const submitTask = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const result = await createTaskBySkuText(skuText, token);
      setMsg(`任务创建成功: ${result.task_id}`);
      setSkuText('');
      await refreshData(token);
    } catch (e: any) {
      setMsg(`提交失败: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const pollWechatLogin = async (sessionId: string) => {
    const maxAttempts = 30;
    let attempts = 0;
    while (attempts < maxAttempts) {
      let result;
      try {
        result = await fetchWechatQrStatus(sessionId);
      } catch (error: any) {
        setMsg(`微信登录状态查询失败：${error?.message || '未知错误'}`);
        return false;
      }
      if (result.status === 'confirmed' && result.token && result.user) {
        setToken(result.token);
        saveStoredToken({ token: result.token, expires_in: result.expires_in || 0, expires_at: result.expires_at || new Date(Date.now() + 60000).toISOString(), user: result.user });
        await refreshData(result.token);
        setMsg(`登录成功，欢迎 ${result.user.username}（令牌有效期 ${Math.max(Math.floor((new Date((result.expires_at || new Date().toISOString())).getTime() - Date.now()) / 60000), 0)} 分钟）`);
        return true;
      }
      if (result.status !== 'pending') {
        setMsg('微信登录状态异常，请重试');
        return false;
      }
      attempts += 1;
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    setMsg('微信登录超时，请重试');
    return false;
  };

  const handleWechatLogin = async () => {
    setLoading(true);
    setMsg('');
    try {
      const response = await createWechatQrSession();
      const popup = window.open(response.login_url, '_blank', 'width=540,height=680');
      if (!popup) {
        setMsg('浏览器阻止了弹窗，请允许后重试');
        return;
      }
      await pollWechatLogin(response.session_id);
    } catch (error: any) {
      console.error('微信登录失败:', error);
      setMsg(`微信登录失败：${error?.message || '未知错误'}`);
    } finally {
      setLoading(false);
    }
  };


  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get('wechat_session_id');
    if (!sessionId || token) return;

    setLoading(true);
    pollWechatLogin(sessionId)
      .finally(() => {
        setLoading(false);
        params.delete('wechat_session_id');
        const next = `${window.location.pathname}${params.toString() ? `?${params.toString()}` : ''}${window.location.hash}`;
        window.history.replaceState({}, '', next);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY);
    setToken('');
    setUser(null);
    setTasks([]);
    setClients([]);
    setMsg('已退出登录');
  };

  useEffect(() => {
    if (!token) return;

    refreshData(token).catch((e) => {
      console.error('初始化数据失败:', e);
      logout();
    });

    const interval = setInterval(() => {
      refreshData(token).catch((e) => {
        console.error('轮询刷新失败:', e);
      });
    }, 10000);

    return () => clearInterval(interval);
  }, [token]);


  if (!token || !user) {
    return (
      <div className="page auth-page">
        <div className="auth-card">
          <h1>跟卖任务系统</h1>
          <p className="subtitle">系统仅支持微信扫码登录。</p>

          <div className="wechat-box">
            <button className="primary" onClick={handleWechatLogin} disabled={loading}>
              {loading ? '处理中...' : '微信扫码登录'}
            </button>
          </div>

          {msg && <p className="message">{msg}</p>}
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="header">
        <div>
          <h2>React SKU 调度面板</h2>
          <p>欢迎你，{user.username}</p>
        </div>
        <div className="quota-box">
          <span>今日额度：{user.today_used || 0}/{user.daily_limit}</span>
          <strong>剩余 {remaining}</strong>
          <button onClick={logout}>退出</button>
        </div>
      </header>

      <section className="card">
        <h3>创建任务</h3>
        <textarea
          rows={5}
          value={skuText}
          onChange={(e) => setSkuText(e.target.value)}
          placeholder={'SKU001\nSKU002,SKU003'}
        />
        <button className="primary" onClick={submitTask} disabled={loading || remaining <= 0}>开始踢跟</button>
        {msg && <p className="message">{msg}</p>}
      </section>

      <div className="grid">
        <section className="card">
          <h3>活跃客户端</h3>
          <ul>
            {clients.map((c) => (
              <li key={c.client_id}>{c.client_id} / {c.alive ? '在线' : '离线'}</li>
            ))}
          </ul>
        </section>

        <section className="card">
          <h3>任务列表</h3>
          <ul>
            {tasks.map((t) => (
              <li key={t.id}>{t.id} / {t.status} / {t.message}</li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

import React, { useEffect, useMemo, useState } from 'react';
import {
  createTaskBySkuText,
  createWechatQrSession,
  fetchActiveClients,
  fetchMe,
  fetchTasks,
  fetchWechatQrStatus,
  login,
  register,
  type AuthUser,
} from './api';
import './App.css';

type Mode = 'login' | 'register';

const TOKEN_KEY = 'follow_sell_token';

export default function ReactApp() {
  const [mode, setMode] = useState<Mode>('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [token, setToken] = useState<string>(() => localStorage.getItem(TOKEN_KEY) || '');

  const [user, setUser] = useState<AuthUser | null>(null);
  const [skuText, setSkuText] = useState('');
  const [msg, setMsg] = useState('');
  const [tasks, setTasks] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [wechatSessionId, setWechatSessionId] = useState('');
  const [wechatQrImage, setWechatQrImage] = useState('');
  const [wechatStatus, setWechatStatus] = useState('未开始');

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

  const onAuth = async () => {
    setLoading(true);
    setMsg('');
    try {
      const action = mode === 'login' ? login : register;
      const result = await action(username.trim(), password);
      setToken(result.token);
      localStorage.setItem(TOKEN_KEY, result.token);
      await refreshData(result.token);
      setMsg(`${mode === 'login' ? '登录' : '注册'}成功，欢迎 ${result.user.username}`);
    } catch (e: any) {
      setMsg(`认证失败：${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const initWechatLogin = async () => {
    setLoading(true);
    setMsg('');
    try {
      const qr = await createWechatQrSession();
      setWechatSessionId(qr.session_id);
      setWechatQrImage(qr.qr_image_url);
      setWechatStatus('等待扫码');
    } catch (e: any) {
      setMsg(`微信二维码获取失败：${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const pollWechatStatus = async (sessionId: string) => {
    try {
      const result = await fetchWechatQrStatus(sessionId);
      if (result.status === 'confirmed' && result.token && result.user) {
        setToken(result.token);
        localStorage.setItem(TOKEN_KEY, result.token);
        await refreshData(result.token);
        setMsg(`微信登录成功，欢迎 ${result.user.username}`);
        setWechatStatus('登录成功');
        return;
      }
      setWechatStatus(result.status === 'pending' ? '等待扫码' : result.status);
    } catch (e: any) {
      setWechatStatus(`异常：${e.message}`);
    }
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

  useEffect(() => {
    if (token || !wechatSessionId) return;
    const timer = setInterval(() => {
      pollWechatStatus(wechatSessionId);
    }, 2500);
    return () => clearInterval(timer);
  }, [wechatSessionId, token]);

  if (!token || !user) {
    return (
      <div className="page auth-page">
        <div className="auth-card">
          <h1>跟卖任务系统</h1>
          <p className="subtitle">请先登录或注册，再开始每日任务。</p>

          <div className="tab-row">
            <button className={mode === 'login' ? 'active' : ''} onClick={() => setMode('login')}>登录</button>
            <button className={mode === 'register' ? 'active' : ''} onClick={() => setMode('register')}>注册</button>
          </div>

          <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="用户名（>=3位）" />
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="密码（>=6位）" />

          <button className="primary" onClick={onAuth} disabled={loading}>
            {loading ? '处理中...' : mode === 'login' ? '登录' : '创建账号'}
          </button>

          <div className="wechat-box">
            <button onClick={initWechatLogin} disabled={loading}>微信扫码登录</button>
            {wechatQrImage && (
              <>
                <img src={wechatQrImage} alt="wechat login qr" className="wechat-qr" />
                <p className="message">扫码状态：{wechatStatus}</p>
                <p className="message">请使用已绑定开放平台应用的微信客户端扫码确认。</p>
              </>
            )}
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

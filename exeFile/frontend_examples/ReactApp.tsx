import React, { useEffect, useState } from 'react';
import { createTaskBySkuText, fetchActiveClients, fetchTasks } from './api';

export default function ReactApp() {
  const [skuText, setSkuText] = useState('');
  const [msg, setMsg] = useState('');
  const [tasks, setTasks] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);

  const refresh = async () => {
    const [t, c] = await Promise.all([fetchTasks(), fetchActiveClients()]);
    setTasks(t.items || []);
    setClients(c.items || []);
  };

  const submit = async () => {
    try {
      const out = await createTaskBySkuText(skuText);
      setMsg(`任务创建成功: ${out.task_id}`);
      await refresh();
    } catch (e: any) {
      setMsg(`提交失败: ${e.message}`);
    }
  };

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div>
      <h2>React SKU 调度面板</h2>
      <textarea rows={6} value={skuText} onChange={(e) => setSkuText(e.target.value)} placeholder={'SKU001\nSKU002,SKU003'} />
      <button onClick={submit}>开始踢跟</button>
      <p>{msg}</p>

      <h3>活跃客户端</h3>
      <ul>{clients.map((c) => <li key={c.client_id}>{c.client_id} / {c.alive ? 'alive' : 'offline'}</li>)}</ul>

      <h3>任务</h3>
      <ul>{tasks.map((t) => <li key={t.id}>{t.id} / {t.status} / {t.message}</li>)}</ul>
    </div>
  );
}

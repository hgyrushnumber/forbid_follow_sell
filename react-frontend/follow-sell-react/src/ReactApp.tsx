import React, { useEffect, useState } from 'react';
import { createTaskBySkuText, fetchActiveClients, fetchTasks } from './api';

export default function ReactApp() {
  const [skuText, setSkuText] = useState('');
  const [msg, setMsg] = useState('');
  const [tasks, setTasks] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);

  const refreshData = async () => {
    try {
      const [tasksRes, clientsRes] = await Promise.all([fetchTasks(), fetchActiveClients()]);
      setTasks(tasksRes.items || []);
      setClients(clientsRes.items || []);
    } catch (e) {
      console.error("刷新数据失败:", e);
    }
  };

  const submitTask = async () => {
    try {
      const result = await createTaskBySkuText(skuText);
      setMsg(`任务创建成功: ${result.task_id}`);
      // 创建任务后立即刷新数据
      refreshData();
    } catch (e: any) {
      setMsg(`提交失败: ${e.message}`);
    }
  };

  useEffect(() => {
    // 初始加载数据
    refreshData();

    // 启动定时轮询，每10秒刷新一次数据
    const interval = setInterval(() => {
      refreshData();
    }, 10000);

    return () => {
      // 组件卸载时清除定时器
      clearInterval(interval);
    };
  }, []);

  return (
    <div>
      <h2>React SKU 调度面板</h2>
      <textarea
        rows={6}
        value={skuText}
        onChange={(e) => setSkuText(e.target.value)}
        placeholder="SKU001
SKU002,SKU003"
      />
      <button onClick={submitTask}>开始踢跟</button>
      <p>{msg}</p>

      <h3>活跃客户端</h3>
      <ul>{clients.map((c) => <li key={c.client_id}>{c.client_id} / {c.alive ? '在线' : '离线'}</li>)}</ul>

      <h3>任务列表</h3>
      <ul>{tasks.map((t) => <li key={t.id}>{t.id} / {t.status} / {t.message}</li>)}</ul>
    </div>
  );
}
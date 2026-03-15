import React, { useEffect, useState } from 'react';
import { createTaskBySkuText, fetchActiveClients, fetchTasks } from './api';

export default function ReactApp() {
  const [skuText, setSkuText] = useState('');
  const [msg, setMsg] = useState('');
  const [tasks, setTasks] = useState<any[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [ws, setWs] = useState<WebSocket | null>(null);

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
      // 无需手动刷新，WebSocket会自动推送更新
    } catch (e: any) {
      setMsg(`提交失败: ${e.message}`);
    }
  };

  useEffect(() => {
    let heartbeatInterval: NodeJS.Timeout | null = null;

    // 初始化WebSocket连接
    const connectWebSocket = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const clientId = `web-client-${Date.now()}`; // 生成唯一的客户端ID
      const wsUrl = `${protocol}//${window.location.host}/ws/${clientId}`;
      const websocket = new WebSocket(wsUrl);

      websocket.onopen = () => {
        console.log("WebSocket连接成功");
        // 发送注册信息，让服务器识别客户端
        const registerData = {
          type: "register",
          accounts: [] // 前端暂时没有配置账号信息，发送空数组
        };
        websocket.send(JSON.stringify(registerData));
        refreshData();

        // 启动心跳机制，每30秒发送一次心跳
        heartbeatInterval = setInterval(() => {
          if (websocket.readyState === WebSocket.OPEN) {
            websocket.send(JSON.stringify({ type: "heartbeat" }));
          }
        }, 30000);
      };

      websocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        // 收到任务更新时自动刷新数据
        if (data.type === "task_created" || data.type === "task_updated" || data.type === "heartbeat") {
          refreshData();
        }
      };

      websocket.onerror = (error) => {
        console.error("WebSocket错误:", error);
      };

      websocket.onclose = () => {
        console.log("WebSocket连接关闭，5秒后重连");
        // 清除心跳定时器
        if (heartbeatInterval) {
          clearInterval(heartbeatInterval);
        }
        setTimeout(connectWebSocket, 5000); // 重新连接而不是刷新页面
      };

      setWs(websocket);
    };

    connectWebSocket();

    return () => {
      // 组件卸载时关闭WebSocket连接
      if (ws) {
        ws.close();
      }
      // 清除心跳定时器
      if (heartbeatInterval) {
        clearInterval(heartbeatInterval);
      }
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
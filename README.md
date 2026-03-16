# forbid_follow_sell

## 认证方式

系统当前**仅支持微信开放平台扫码登录**，账号密码登录/注册接口已禁用。

## 微信开放平台扫码登录配置

后端 `dispatch-backend/api_server.py` 实现的登录相关接口：

- 生成扫码会话：`GET /api/auth/wechat/qr`
- 微信回调入口：`GET /api/auth/wechat/callback?code=...&state=...`
- 前端轮询登录状态：`GET /api/auth/wechat/status/{session_id}`

## `.env` 统一配置

请在项目根目录创建 `.env` 文件（可参考 `.env.example`）：

- `WECHAT_OPEN_APPID`：微信开放平台应用 AppID
- `WECHAT_OPEN_APPSECRET`：微信开放平台应用 AppSecret
- `WECHAT_OPEN_REDIRECT_URI`：微信平台回调地址（需与开放平台配置一致）
- `WECHAT_LOGIN_SUCCESS_REDIRECT`：（可选）扫码成功后浏览器跳转地址
- `WECHAT_LOGIN_EXPIRES_SECONDS`：微信扫码会话有效期（秒）
- `TOKEN_EXPIRES_SECONDS`：登录 token 有效期（秒，统一在 `.env` 管理）
- `DAILY_TASK_LIMIT`：每日任务上限


## FastAPI 路由结构（规范化）

后端已按模块拆分路由并统一在 `backend_api/main.py` 注册：

- `backend_api/routers/auth.py`：认证与微信扫码登录
- `backend_api/routers/tasks.py`：任务创建与查询
- `backend_api/routers/clients.py`：客户端生命周期与任务回传
- `backend_api/routers/ws.py`：WebSocket 通道

`api_server.py` 作为启动入口，仅负责加载 `app` 与启动 `uvicorn`。

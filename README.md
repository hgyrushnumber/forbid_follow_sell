# forbid_follow_sell

## 微信开放平台扫码登录配置

后端 `dispatch-backend/api_server.py` 现已按微信开放平台网页扫码登录流程实现：

- 生成扫码地址：`POST /api/auth/wechat/qr`
- 微信回调入口：`GET /api/auth/wechat/callback?code=...&state=...`
- 前端轮询登录状态：`GET /api/auth/wechat/status/{session_id}`

部署时请配置环境变量：

- `WECHAT_OPEN_APPID`：微信开放平台应用 AppID
- `WECHAT_OPEN_APPSECRET`：微信开放平台应用 AppSecret
- `WECHAT_OPEN_REDIRECT_URI`：微信平台回调地址（需与开放平台配置一致）
- `WECHAT_LOGIN_SUCCESS_REDIRECT`：（可选）扫码成功后浏览器跳转地址

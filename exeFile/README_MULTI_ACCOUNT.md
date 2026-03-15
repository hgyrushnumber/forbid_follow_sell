# Ozon SKU上传工具 - 多账号版本

## 功能特性

- ✅ 支持多个Ozon账号同时管理
- ✅ 基于邮箱+IMAP授权码自动登录
- ✅ 自动获取邮箱中的OTP验证码
- ✅ 持久化登录状态保存
- ✅ 多账号并行任务执行
- ✅ 友好的GUI界面

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 2. 运行多账号版本

```bash
python app_multi_account.py
```

或者使用简化版本：

```bash
python app_multi_account_simple.py
```

### 3. 配置账号

1. 点击`➕ 添加账号`按钮
2. 输入邮箱地址（如`xpw709@163.com`）
3. 输入IMAP授权码（不是邮箱登录密码，是客户端授权密码）
4. 点击`自动生成`生成登录态保存路径
5. 点击`保存`完成账号添加

### 4. 获取IMAP授权码

#### 163邮箱
1. 登录163邮箱网页版
2. 进入设置 → POP3/SMTP/IMAP
3. 开启POP3/SMTP服务
4. 生成客户端授权码

#### QQ邮箱
1. 登录QQ邮箱网页版
2. 进入设置 → 账户
3. 开启POP3/IMAP/SMTP服务
4. 生成客户端授权码

### 5. 使用工具

1. 选中要使用的账号
2. 点击`🚀 登录选中账号` - 系统会自动完成登录流程
3. 选择Excel文件和图片文件
4. 点击`🎯 执行任务到选中账号` - 开始处理SKU
5. 可以随时查看运行日志

## 账号配置说明

### 账号信息
- **邮箱地址**: Ozon卖家平台登录邮箱
- **IMAP授权码**: 邮箱客户端授权密码（不是邮箱登录密码）
- **登录态保存路径**: 可选，自动生成

### 支持的邮箱提供商
- 163邮箱 ✅
- QQ邮箱 ✅
- Gmail ✅
- Outlook/Hotmail ✅
- 126邮箱 ✅
- Yeah.net ✅
- Sina.com ✅

## 文件结构

```
exeFile/
├── app_multi_account.py          # 完整功能版多账号工具
├── app_multi_account_simple.py # 简化版多账号工具
├── ozon_core.py                 # 核心业务逻辑
├── email_otp.py               # 邮箱OTP处理
├── app.py                     # 原单账号版本
├── accounts/                  # 登录态保存目录
├── ozon_accounts_config.json  # 账号配置文件
└── README_MULTI_ACCOUNT.md    # 说明文档
```

## 登录流程说明

1. 工具会自动导航到Ozon登录页面
2. 选择邮箱登录方式
3. 输入邮箱地址
4. 自动通过IMAP协议获取邮箱中的OTP验证码
5. 自动输入验证码完成登录
6. 保存登录状态到本地文件

## 常见问题

### Q: 登录失败，提示"验证码提取失败"
A: 请检查：
1. IMAP授权码是否正确
2. 邮箱是否收到了Ozon的验证邮件
3. 网络连接是否正常

### Q: 如何获取IMAP授权码？
A: 请参考各邮箱提供商的帮助文档，开启IMAP/SMTP服务并生成客户端授权码。

### Q: 支持哪些邮箱？
A: 目前支持主流的免费邮箱和企业邮箱，包括163、QQ、Gmail、Outlook等。

### Q: 可以同时登录多少个账号？
A: 理论上没有限制，实际数量取决于系统资源和网络带宽。

## 注意事项

1. 🚨 请遵守Ozon平台的使用条款，合理控制操作频率
2. 🚨 不要使用个人邮箱进行批量操作
3. 🚨 定期更换IMAP授权码
4. 🚨 建议使用专用的业务邮箱
5. 🚨 遵守各邮箱提供商的使用条款

## 技术支持

如有问题，请联系开发人员或查看项目文档。

## 新增：任务中心 API（支持直接输入 SKU）

在 `exeFile` 下新增了最小可用 API + Worker：

- `task_center.py`：SQLite 持久化任务中心（`task_center.db`）
- `api_server.py`：标准库 HTTP API 服务

### 启动

```bash
cd follow_sell_forbid/exeFile
python api_server.py
```

启动后可直接打开前端页面：`http://127.0.0.1:18080/`

### 主要接口

- `POST /api/tasks`：创建任务（支持 manual / excel）
- `GET /api/tasks`：任务列表
- `GET /api/tasks/{task_id}`：任务详情
- `GET /health`：健康检查

### manual 模式（直接输入 SKU）

```json
{
  "input_mode": "manual",
  "sku_text": "SKU123
SKU456,SKU789"
}
```

说明：前端只需要发送 SKU。邮箱、IMAP 授权码、登录态路径由后端自动从 `ozon_accounts_config.json` 读取。

### excel 模式（兼容）

```json
{
  "input_mode": "excel",
  "excel_path": "sku.xlsx"
}
```

可选字段：`image_path`（不传时默认使用 `exeFile/icon.png`）。


## 新版分派流程（网页 -> 服务器 -> 客户端）

目标流程：
1. 用户打开网页输入 SKU，点击“开始踢跟”；
2. 服务器创建 `pending` 任务；
3. 活跃客户端通过心跳上报登录账号并拉取任务；
4. 客户端执行后回传 `success/failed`；
5. 网页下方列表实时展示任务状态。

### 启动步骤

#### 1) 启动分派服务器

```bash
cd follow_sell_forbid/exeFile
python api_server.py
```

打开：`http://127.0.0.1:18080/`

#### 2) 启动客户端执行器（可在同机/多机）

```bash
cd follow_sell_forbid/exeFile
python client_worker.py
```

客户端会：
- 从 `ozon_accounts_config.json` 读取本机可用账号；
- 调用 `/api/clients/register` 与 `/api/clients/heartbeat` 上报活跃登录态；
- 调用 `/api/clients/{client_id}/pull-task` 拉取任务并执行。

### 核心接口

- `POST /api/tasks`：提交 SKU 任务
- `GET /api/tasks`：查看任务状态
- `POST /api/clients/register`：客户端注册账号能力
- `POST /api/clients/heartbeat`：客户端心跳
- `GET /api/clients/active`：查看活跃客户端
- `POST /api/clients/{client_id}/pull-task`：客户端拉取分配任务
- `POST /api/clients/{client_id}/tasks/{task_id}/running`：客户端标记执行中
- `POST /api/clients/{client_id}/tasks/{task_id}/complete`：客户端回传执行结果


## Vue / React 前端接入说明（你说的那种前端）

当前 `api_server.py` 已支持跨域（CORS），可以直接给 Vue/React 前端调用。

### 1) 启动后端分派服务

```bash
cd follow_sell_forbid/exeFile
python api_server.py
```

服务地址：`http://127.0.0.1:18080`

### 2) 启动客户端执行器（至少 1 个）

```bash
cd follow_sell_forbid/exeFile
python client_worker.py
```

### 3) Vue / React 调用方式

你可以直接复用下面示例文件：

- `frontend_examples/api.ts`
- `frontend_examples/VueApp.vue`
- `frontend_examples/ReactApp.tsx`

前端只需要调用：

- `POST /api/tasks`（提交 sku_text）
- `GET /api/tasks`（任务列表）
- `GET /api/clients/active`（活跃客户端）

示例提交体：

```json
{
  "sku_text": "SKU001\nSKU002,SKU003"
}
```


### 桌面客户端登录态自动上报

`app.py` 现在会在账号登录成功后自动调用分派服务：

- `POST /api/clients/register`
- `POST /api/clients/heartbeat`

并且后台每 15 秒发送一次心跳；窗口关闭时会调用 `POST /api/clients/offline`。  
这意味着你在桌面客户端登录后的“活跃登录状态”可以被服务器轮询到并参与 SKU 分派。

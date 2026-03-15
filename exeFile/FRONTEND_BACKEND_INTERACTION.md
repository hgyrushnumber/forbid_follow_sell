# exeFile 场景下的“前后端交互”实现分析（含“直接输入 SKU”）

> 目标：用户登录后在前端提交 SKU，客户端实时看到对应任务状态。  
> 范围：仅聚焦 `follow_sell_forbid/exeFile`，不依赖既有系统。

---

## 1) 当前 exeFile 的真实现状

`exeFile` 目前是桌面 GUI + 本地线程执行，不是标准 Web 前后端架构：

- `app.py` 中 `run_task_on_selected/run_task_thread` 直接起线程执行任务；
- 任务输入目前偏向 Excel 文件 + 图片文件；
- `ozon_core.py` 的 `run_task` 内部调用 `read_skus_from_excel`，执行入口天然依赖表格；
- 任务状态主要在 GUI 日志里，其他客户端无法按 `task_id` 稳定查询。

结论：要实现“前端提交 SKU -> 客户端看到任务”，核心是补齐**任务中心**，而不是先重写自动化逻辑。

---

## 2) 关键补充：SKU 输入不应只依赖表格

你提到“并不一定需要以表格形式执行，直接输入 SKU 也可以”，这点非常关键。建议把输入模式设计成双通道：

### 模式 A：直接输入 SKU（推荐优先）

前端提供输入框，支持：

- 单个 SKU：`SKU123`；
- 多个 SKU（换行）：
  ```
  SKU123
  SKU456
  SKU789
  ```
- 多个 SKU（逗号）：`SKU123,SKU456,SKU789`。

后端统一归一化为 `List[str]` 后入库。

### 模式 B：上传 Excel（兼容旧流程）

保留现有 Excel 模式，作为批量导入能力。

> 最佳实践：**API 层统一只接收标准化后的 `skus[]`**。  
> Excel 只是输入来源之一，不应绑定为任务执行的唯一入口。

---

## 3) 推荐架构（exeFile 内最小改造）

保持 3 层：

1. **Web 前端**：登录、提交 SKU、查看任务；
2. **本地 API 服务**：鉴权、创建任务、查询任务；
3. **Worker**：消费任务，调用 `ozon_core` 执行并回写状态。

### 状态流转

`pending -> running -> success/failed`

每次变更都写入数据库，前端通过轮询或 WebSocket 获取。

---

## 4) 任务模型（支持“直接输入 + Excel”）

建议 `task` 表新增输入来源字段：

- `id`（UUID）
- `user_id`
- `account_email`
- `input_mode`：`manual` / `excel`
- `sku_payload`：标准化后的 SKU 数组 JSON
- `source_file`：可选（Excel 路径）
- `image_path`
- `status`、`progress`、`message`
- `result_json`
- `created_at/started_at/finished_at/updated_at`

可选 `task_event` 表存时间线日志，替代“只在 GUI 内存打印”。

---

## 5) API 设计（直接满足你的场景）

### 5.1 提交任务（统一入口）

`POST /api/tasks`

请求体建议：

```json
{
  "account_email": "seller@example.com",
  "input_mode": "manual",
  "sku_text": "SKU123\nSKU456\nSKU789",
  "image_path": "icon.png"
}
```

或（Excel 模式）：

```json
{
  "account_email": "seller@example.com",
  "input_mode": "excel",
  "excel_path": "sku.xlsx",
  "image_path": "icon.png"
}
```

服务端处理规则：

- `manual`：解析 `sku_text -> skus[]`；
- `excel`：读取文件并解析为 `skus[]`；
- 两种模式最终都写入 `sku_payload`，执行器只认 `sku_payload`。

返回：`task_id`、`status=pending`。

### 5.2 查询任务

- `GET /api/tasks?mine=true`
- `GET /api/tasks/{task_id}`

### 5.3 实时更新

- 先用轮询（2~3 秒）；
- 稳定后再加 WebSocket。

---

## 6) 与现有 exeFile 代码的改造点（精准）

### 6.1 `ozon_core.py` 需要解耦“输入来源”和“执行逻辑”

当前 `run_task` 强依赖 `excel_path`。建议改为新增核心执行函数：

- `run_task_with_skus(email, skus, image_path, imap_password, storage_path, ...)`

再保留兼容层：

- `run_task_from_excel(...)`（内部先读 Excel，再调用 `run_task_with_skus`）

这样就能天然支持“前端直接输入 SKU”。

### 6.2 `app.py` 从“直接线程执行”迁到“提交任务”

当前按钮动作可改成：

- 点击执行 -> 调用 `POST /api/tasks` 创建任务；
- GUI 自己也走查询接口看状态，而不是直接持有执行线程。

---

## 7) 并发与稳定性（落地重点）

1. 单账号串行（防止同账号会话互抢）；
2. 不同账号并行（提高吞吐）；
3. 每个任务都要有 `request_id`（防重复提交）；
4. Worker 崩溃恢复：卡在 `running` 太久的任务重置为 `failed/retry_pending`；
5. 错误结构化：`error_code + error_message + stage`。

---

## 8) 建议实施顺序（按价值优先）

1. **先做 manual 输入链路**：前端文本框 + `POST /api/tasks` + 入库；
2. **Worker 消费 + 状态回写**：完成可查询闭环；
3. **再接 Excel 模式**：作为兼容输入源；
4. **最后加 WebSocket**：优化实时体验。

---

## 9) 最终结论

你这个场景下，**“直接输入 SKU”完全可以且应该成为主路径**，Excel 只是补充导入方式。  
只要做到：

- 统一任务中心（`task_id` + 状态机）；
- 统一 SKU 标准化（无论手输还是 Excel）；
- 统一执行入口（Worker 调同一执行函数）；
- 统一状态查询（API/WS）；

就能稳定实现“前端提交 -> 客户端看到对应任务”。

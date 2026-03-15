# React -> FastAPI -> Client Dispatch 架构核查

结论：当前项目只实现了“React 提交任务到 FastAPI”和“客户端通过 WebSocket 存活注册/心跳”的一部分链路，**未完整实现**“后端调用存活客户端处理任务”。

## 已实现

1. React 前端可调用 FastAPI 的 `/api/tasks`、`/api/tasks`(GET)、`/api/clients/active`。
2. FastAPI 支持 `/api/tasks` 创建任务，并向所有活跃 WebSocket 客户端广播 `task_created`。
3. 客户端支持通过 WebSocket 注册 `register` 并发送 `heartbeat`，后端可维护活跃客户端列表。

## 未打通/不一致点

1. 后端在广播任务时直接下发“新建任务”，并没有先按存活客户端执行 `pull_task_for_client` 分配任务。
2. 客户端执行器依赖 REST 路由：
   - `/api/clients/{client_id}/tasks/{task_id}/running`
   - `/api/clients/{client_id}/tasks/{task_id}/complete`
   但当前 FastAPI 路由未实现这些接口。
3. Web 前端作为 WebSocket 客户端注册时发送 `accounts: []`，后端 `register_client` 要求 accounts 非空，会导致注册失败并打印错误。
4. 客户端执行器期望任务里有 `assigned_account`，但后端广播的是刚创建任务（通常尚未 assigned），会导致“本地无可用账号”路径。

## 如何完善：落地方案（建议按优先级分三步）

### 第一步：先打通最小可用闭环（P0）

目标：让“创建任务 -> 分配给存活客户端 -> 客户端执行 -> 回传状态”可运行。

1. 在 FastAPI 补齐客户端上报接口（与 `desktop-client/client_worker.py` 对齐）：
   - `POST /api/clients/{client_id}/tasks/{task_id}/running` -> 调用 `CENTER.mark_task_running`。
   - `POST /api/clients/{client_id}/tasks/{task_id}/complete` -> 调用 `CENTER.complete_task`。
2. 修改任务下发机制：
   - 不再在 `/api/tasks` 中直接广播新建任务对象。
   - 改为“创建后尝试分派”：遍历活跃连接，调用 `CENTER.pull_task_for_client(client_id)`；
     若返回任务，则只向对应 client websocket 推送 `task_assigned`。
3. 客户端执行器改为消费 `task_assigned`（保留兼容 `task_created` 也可），确保任务对象已有 `assigned_client_id/assigned_account`。

### 第二步：修复角色混淆（P1）

目标：避免 Web 控制台被当成“执行客户端”。

1. 将 Web 前端 websocket 注册改为“观察者角色”，例如：
   - `type: "register_observer"`（或在 register 中新增 `role: "observer"`）。
2. 后端对 observer 不执行 `register_client`（不进入 clients 表，不参与分派）。
3. Web 前端不需要上报 `accounts`；仅订阅任务/客户端变化事件。

> 这样可以消除“前端 accounts 为空导致注册异常”的问题，也避免把浏览器连接误判为 worker。

### 第三步：增强稳定性与可观测性（P2）

1. 任务状态事件统一：新增 `task_updated` 推送（running/success/failed 时主动广播给 observer）。
2. 分派策略增强：
   - 仅选 `alive=true` 且 accounts 非空的客户端；
   - 可加入轮询/最小负载优先，避免单客户端吃满。
3. 幂等与并发保护：
   - `complete` 仅允许从 `running/dispatched` 进入终态；
   - 重复回调应安全忽略（返回当前状态）。
4. 连接清理健壮性：`del active_connections[client_id]` 改为安全删除（避免 KeyError）。

## 推荐接口契约（用于前后端/客户端统一）

### 1) worker websocket

- worker -> server: `register` `{ type, client_id, accounts }`
- server -> worker: `task_assigned` `{ type, task }`
- worker -> server: `heartbeat` `{ type }`

### 2) observer websocket

- observer -> server: `register_observer` `{ type, observer_id }`
- server -> observer: `task_created | task_updated | clients_updated`

### 3) worker REST 回传

- `POST /api/clients/{client_id}/tasks/{task_id}/running`
- `POST /api/clients/{client_id}/tasks/{task_id}/complete` body: `{ success, result?, error? }`

## 验收清单（回归测试建议）

1. 有 1 个 worker 在线时，创建任务后应看到：`pending -> dispatched -> running -> success/failed`。
2. 无 worker 在线时，任务保持 `pending`，worker 上线后可被拉取并分派。
3. observer 前端可看到任务状态实时变化，但不会出现在 active clients 列表。
4. worker 断线后 `alive` 过 TTL 变 false，后续新任务不再分配给该 worker。

## 总体判断

当前是“半成品调度链路”：
- ✅ React -> FastAPI 创建任务：有
- ✅ 客户端存活上报：有
- ❌ 后端基于存活客户端完成任务分派并驱动执行闭环：未完成

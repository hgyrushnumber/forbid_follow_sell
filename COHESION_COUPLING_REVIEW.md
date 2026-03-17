# app.py / ozon_core.py 拆分与高内聚低耦合评估

## 结论

当前项目**并未完全**把 `app.py` 和 `ozon_core.py` 的职责干净地分散到其他模块；目前更像是“进行中的重构”，存在明显的重复逻辑与双向依赖，尚未达到稳定的高内聚低耦合状态。

## 主要证据

### 1) `app.py` 仍然承担过多职责（UI + 调度心跳 + 任务轮询 + 任务执行）

- `OzonMultiApp` 同时负责界面构建、账号管理入口、心跳线程与任务轮询循环。  
- 虽然创建了 `TaskService` 与 `AccountService`，但 `app.py` 内仍保留完整的 `run_task_from_dispatch` 执行逻辑。

### 2) `TaskService` 与 `app.py` 存在重复实现（职责未真正下沉）

- `TaskService.run_task_from_dispatch()` 已包含完整执行流程。  
- `app.py.run_task_from_dispatch()` 又调用 `self.task_service.run_task_from_dispatch(task)` 后继续重复执行同类流程，形成重复和潜在“双执行”风险。

### 3) Service 对 UI/App 对象强绑定，耦合偏高

- `TaskService.__init__` 直接缓存 `app` 的大量字段（日志、状态、控件变量、分派服务等），更像“巨对象代理”而非独立服务。  
- `AccountService` 也直接调用 `self.app.save_accounts_config()`、`self.app.update_accounts_list()` 等 UI 层方法。

### 4) `ozon_core.py` 与 `services/*` 双向交织，分层边界不清

- `ozon_core.py` 既定义大量流程函数，又导入 `services.session_service/page_service/sku_service`，并以全局实例进行协调。  
- 同时 `services/sku_service.py` 又从 `ozon_core` 导入常量 `TARGET_URL`，形成反向依赖。

### 5) 工具函数重复拷贝，显示拆分未收口

- `ozon_core.py` 中存在 `ensure_dirs/log/sleep/dump_page_state/...` 等函数实现。  
- `services/utils.py` 中也有同名或等价实现，属于重复代码，增加维护成本。

### 6) 重构痕迹明显但未落地完成

- 存在 `controllers/app_controller.py` 与 `ui/main_window.py` 这类空文件，显示目标架构可能是 MVC/分层化，但当前主流程仍集中在旧入口。

## 是否“完全拆分”判断

- **不是完全拆分**：目前属于“部分拆分 + 旧逻辑保留 + 新旧并存”。
- **高内聚低耦合状态未达成**：
  - 内聚性：模块职责仍交叉、重复。
  - 耦合度：UI/App/Service/Core 之间仍存在显著耦合与反向依赖。

## 建议的最小收敛路径

1. 让 `app.py` 只保留 UI 事件与生命周期，彻底移除任务执行细节。  
2. 删除 `app.py.run_task_from_dispatch` 的重复实现，只保留 `TaskService` 单一实现。  
3. 让 `TaskService/AccountService` 接收显式依赖（接口/回调）而非整 `app` 对象。  
4. 将 `ozon_core.py` 中已迁移到 `services/utils.py`、`PageService` 的函数删除或转调，避免双份逻辑。  
5. 解除 `services` 对 `ozon_core` 的反向依赖（例如将 `TARGET_URL` 下沉到配置模块）。

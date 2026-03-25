# Context
- 登录逻辑当前会在 `AccountSessionService.ensure_ready` 中反复导航 `/app/messenger`、等待 dashboard/messenger URL，并在 `PageService` 中通过多步点击+OTP 请求完成登录。用户希望改为“先跳 TARGET_URL，再观察 URL 变动，不进入 sign-in/registration 即认为已登录”，以减少等待和重复手动操作。
- 新流程必须优先监听 `target_url` 的跳转状态，如果前期出现 `id=` 就直接进入业务流程，否则在看到 `.../app/registration/signin*` 后再回退到现有 OTP 恢复逻辑。

# Plan
1. **补充 URL 监控工具**
   - 在 `desktop-client/services/page_service.py` 中新增一个 `wait_for_session_or_signin(page, timeout_ms=30000)`（或类似名称）的 helper：
     - 重复读取 `page.url`、使用 `extract_session_id` 判断 `id` 参数，匹配 regex `^https://seller\.ozon\.ru/app/registration/signin.*`。
     - 在发现 session_id 之前如果检测到 registration URL，则返回引导登录的标志；如果先看到 session_id 则返回成功状态（附带 session_id）；否则在超时后返回 timeout 状态。
     - 循环里保持短 sleep（300ms）来避免占用太多 CPU。
2. **调整 ensure_ready 流程**
   - `AccountSessionService.ensure_ready` 内保持 `primary_page.goto(TARGET_URL...)` 逻辑，但之后立即调用新的监控 helper。
   - 根据 helper 返回值：
     - `session_ready`：直接调用 `normalize_messenger_home`（保持现有 cleanup）、`session.touch()`，并标记 session（如果 `session_id` 可复用则触发 `_mark_support_task_page`）。
     - `requires_login`：按原逻辑清理登录态文件并调用 `PageService.ensure_logged_in_and_ready`；登录完成后同样保存登录态、归一页面。
     - `timeout`：记录日志并回退到原有登录恢复路径以防挂起。
3. **让 login_with_email_otp 兼容新入口**
   - 首先确保页面已在 `TARGET_URL` 并调用同一个 helper；但这里期望 helper 反馈进入 signin（login needed），若它先得到 session_id，则直接返回 `True`（避免重复登录），否则继续现有点击/OTP 流程。
   - 登录成功后延续保存登录态、调用 `normalize_messenger_home`、并保证 `TARGET_URL` 再次加载（或根据现有会话逻辑保留 `id`）。
4. **保持与其他组件的协调**
   - `prepare_browser`/`acquire_task_page` 流程无需改变，但要确保新的 helper 能提供日志（session_id、timeout、login trigger）以便监控；日志里可写 `检测到 session_id={...}`、`观察到 signin URL，触发自动登录`。
   - 继续使用 `SessionService.run_serialized`/`page_service.normalize_messenger_home`等现有机制，避免引入多线程并发风险。
5. **测试与验证**
   - 单元测试 `wait_for_session_or_signin`：模拟多个 URL 变化序列，验证返回的状态与顺序；也测超时路径。
   - 手工验证：清空 storage 让页面进入 signin，验证登录仍按旧流程走；用已有 session 直接打开 `TARGET_URL`，确认 helper 识别 `id` 并直接复用会话；模拟 URL 卡在其他页面保证 timeout 后仍 fallback 到登录。
   - 观察日志确保新流程有合理输出，方便日后排查。

# Verification
- `ensure_ready` 在目标页马上调用 helper、新的分支必须通过自动化测试或手工登录确认。
- `login_with_email_otp` 在 session 激活时短路，登录路径仍然可用。
- Monitor helper 覆盖 session 识别/登录识别/超时三种状态，且 `AccountSessionService` 在 `session_ready` 情况下 `session.touch()` 并保存 `page_meta`。

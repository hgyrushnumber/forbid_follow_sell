# Desktop Client

## 1. Overview

`desktop-client` houses the Ozon SKU upload desktop application. It ties together a `tkinter`-based UI, Playwright-driven browser automation, and several service layers that manage accounts, tasks, and dispatch communication. Key responsibilities:

- `app.py`: bootstraps the UI (`ui/`), services (`services/`), logging, and background threads (heartbeat, polling, task execution).
- `ozon_core.py`: initializes Playwright services (`SessionService`, `PageService`, `SkuService`), exposes helper APIs (`prepare_browser`, `run_task_with_skus`, etc.).
- `services/`: encapsulates logic for account management, task execution, page navigation, SKU handling, dispatch server communication, session lifecycle, and shared constants.
- `ui/` / `models/`: define Tk windows/components and domain models (account info, task records).
- `tasks/`: stores task history entries in JSONL form. `logs/` captures `desktop-client.log` events.
- `doc/`: tracks known robustness issues for reference.

## 2. Dependencies & Environment

Dependencies are listed in `requirements.txt`:

```sh
pip install -r requirements.txt
playwright install
```

- `tkinter`: UI
- `playwright>=1.37.0`: browser automation
- `requests>=2.31.0`, `websockets>=11.0.3`: dispatch server communication

## 3. Configuration

- `accounts_config.json`: persisted account list, loaded/saved by `AccountService`.
- `accounts/`, `ozon_accounts_config.json`: contain Playwright session storage.
- `services/constants.py`: defines URLs, menu paths, localized text, and timeouts used across UI/page automation.
- `.env`: override defaults such as `DISPATCH_SERVER` and `DESKTOP_LOG_FILE`.

## 4. Running the App

From `desktop-client/`:

```sh
python app.py
```

`app.py` will:

1. Instantiate `MainWindow`, `DispatchService`, `AccountService`, `TaskService` with a shared `accounts_lock`.
2. Initialize logging via `set_logger` which wires Playwright-backed services in `ozon_core.py`.
3. Load accounts from config, ensure required assets (image) exist.
4. Start background threads for dispatch heartbeat and task polling.

All long-running operations (login, task execution) run inside background threads via `threading.Thread` and Playwright session serialization.

## 5. Key Directories

- `services/`:
  - `account_service.py`: thread-safe account CRUD, login, session closure.
  - `task_service.py`: local and dispatch task orchestration, task records, dispatch status updates.
  - `page_service.py`, `sku_service.py`: DOM navigation, language detection, SKU upload/verification logic.
  - `dispatch_service.py`: HTTP interface with the dispatch server.
  - `session_service.py`, `account_session_service.py`: manage Playwright contexts, serialization locks, and page reuse.
  - `task_record_service.py`: persist task records.
- `ui/`: Tkinter windows (`main_window.py`, `task_history_window.py`) with callbacks wired to services.
- `models/`: domain models such as `AccountInfo`, `TaskRecord`, etc.
- `logs/desktop-client.log`: runtime log, controllable via `DESKTOP_LOG_FILE` environment variable.

## 6. Debugging & Packaging

- Packaging stubs (`app.spec`, `app_1.spec`) for PyInstaller builds (generated output under `dist/`, `build/`).
- `debug_artifacts/`, `logs/`, `verification_screenshots/` capture runtime traces and screenshots.
- Use `client_worker.py` / `controllers/` for any custom worker process integration.

## 7. Maintenance Notes

- All services share `accounts_lock` to synchronize access to `self.accounts` in multi-thread scenarios.
- Task history (`tasks/task_history.jsonl`) provides auditability for each task state transition.
- `doc/robustness_issues.md` documents known stability gaps—use it as a checklist when making changes.
- The app writes logs via `app.append_log`; inspect `logs/desktop-client.log` when troubleshooting.
